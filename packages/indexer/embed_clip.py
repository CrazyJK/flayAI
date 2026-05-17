"""OpenCLIP ViT-L/14 -> Qdrant `posters_clip` 컬렉션.

AI_PLAN.md §10 M4 / §6.1 [7].
- 모델: open_clip_torch (ViT-L-14, laion2b_s32b_b82k), vector=768, Cosine
- 입력: posters 테이블의 path (instance + archive 모두)
- payload: opus, kind, year, month, studio, canonical_actresses[],
           rank, play, like_count, playable
- 멱등: opus -> SHA1 id (embed_text 와 동일 함수 재사용)
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import torch
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _qdrant, opus_to_id
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "posters_clip"
VECTOR_DIM = 768

_MODEL = None
_PREPROCESS = None
_DEVICE = None


# --- 모델 로더 ----------------------------------------------------


def _load_model():
    global _MODEL, _PREPROCESS, _DEVICE
    if _MODEL is not None:
        return _MODEL, _PREPROCESS, _DEVICE
    import open_clip

    cfg = load_config()
    name = cfg["models"]["clip_model"]
    pretrained = cfg["models"]["clip_pretrained"]
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("loading OpenCLIP %s (%s) on %s", name, pretrained, _DEVICE)
    model, _, preprocess = open_clip.create_model_and_transforms(name, pretrained=pretrained)
    model.eval().to(_DEVICE)
    _MODEL, _PREPROCESS = model, preprocess
    return model, preprocess, _DEVICE


# --- Qdrant -------------------------------------------------------


def ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION in existing:
        return
    log.info("creating qdrant collection %s (size=%d, cosine)", COLLECTION, VECTOR_DIM)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(size=VECTOR_DIM, distance=qm.Distance.COSINE),
    )
    for field, ftype in [
        ("opus", qm.PayloadSchemaType.KEYWORD),
        ("kind", qm.PayloadSchemaType.KEYWORD),
        ("year", qm.PayloadSchemaType.INTEGER),
        ("month", qm.PayloadSchemaType.INTEGER),
        ("studio", qm.PayloadSchemaType.KEYWORD),
        ("canonical_actresses", qm.PayloadSchemaType.KEYWORD),
        ("rank", qm.PayloadSchemaType.INTEGER),
        ("playable", qm.PayloadSchemaType.BOOL),
    ]:
        try:
            client.create_payload_index(COLLECTION, field, field_schema=ftype)
        except Exception as e:
            log.debug("index create skipped %s: %s", field, e)


# --- 데이터 -------------------------------------------------------


def _fetch_poster_bundle(conn: sqlite3.Connection, opus: str) -> dict | None:
    p = conn.execute(
        "SELECT opus, path, kind, video_path FROM posters WHERE opus = ?", (opus,)
    ).fetchone()
    if not p or not p["path"]:
        return None
    v = conn.execute(
        """
        SELECT release_year, release_month, studio, rank, play, like_count, last_play
        FROM videos WHERE opus = ?
    """,
        (opus,),
    ).fetchone()
    actrs = [
        r["canonical_name"]
        for r in conn.execute("SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))
    ]
    return {
        "opus": p["opus"],
        "path": p["path"],
        "kind": p["kind"],
        "video_path": p["video_path"],
        "year": v["release_year"] if v else None,
        "month": v["release_month"] if v else None,
        "studio": v["studio"] if v else None,
        "rank": (v["rank"] or 0) if v else 0,
        "play": (v["play"] or 0) if v else 0,
        "like_count": (v["like_count"] or 0) if v else 0,
        "last_play": v["last_play"] if v else None,
        "actresses": actrs,
    }


def _build_payload(b: dict) -> dict:
    return {
        "opus": b["opus"],
        "kind": b["kind"],
        "year": b["year"],
        "month": b["month"],
        "studio": b["studio"],
        "canonical_actresses": b["actresses"],
        "rank": b["rank"],
        "play": b["play"],
        "like_count": b["like_count"],
        "last_play": b["last_play"],
        "playable": bool(b["video_path"]),
        "poster_path": b["path"],
    }


# --- 실행 ---------------------------------------------------------


def _opus_iter(conn: sqlite3.Connection, limit: int | None) -> list[str]:
    sql = "SELECT opus FROM posters WHERE path IS NOT NULL ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r["opus"] for r in conn.execute(sql)]


def _batched(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _embed_images(paths: list[Path]) -> tuple[torch.Tensor | None, list[int]]:
    model, preprocess, device = _load_model()
    imgs = []
    keep_idx = []
    for i, p in enumerate(paths):
        try:
            im = Image.open(p).convert("RGB")
            imgs.append(preprocess(im))
            keep_idx.append(i)
        except Exception as e:
            log.warning("image load failed %s: %s", p, e)
    if not imgs:
        return None, []
    batch = torch.stack(imgs).to(device)
    with torch.no_grad():
        feats = model.encode_image(batch)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.detach().cpu(), keep_idx


def run(limit: int | None = None, batch_size: int | None = None) -> dict:
    cfg = load_config()
    bs = int(batch_size or cfg["indexing"]["clip_batch_size"])
    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    ensure_collection(qc)

    all_opus = _opus_iter(conn, limit)
    total = len(all_opus)
    upserted = 0
    skipped = 0
    failed = 0

    for chunk in _batched(all_opus, bs):
        bundles = []
        for opus in chunk:
            b = _fetch_poster_bundle(conn, opus)
            if b is None:
                skipped += 1
                continue
            bundles.append(b)
        if not bundles:
            continue
        paths = [Path(b["path"]) for b in bundles]
        feats, keep_idx = _embed_images(paths)
        if feats is None:
            failed += len(bundles)
            continue
        points = []
        for j, idx in enumerate(keep_idx):
            b = bundles[idx]
            points.append(
                qm.PointStruct(
                    id=opus_to_id(b["opus"]),
                    vector=feats[j].tolist(),
                    payload=_build_payload(b),
                )
            )
        failed += len(bundles) - len(keep_idx)
        if points:
            qc.upsert(collection_name=COLLECTION, points=points, wait=False)
            upserted += len(points)
        if upserted % (bs * 8) == 0 and upserted > 0:
            update_stage("embed_clip", completed=upserted)
            log.info("embed_clip %d / %d", upserted, total)

    update_stage(
        "embed_clip", done=True, completed=upserted, total=total, skipped=skipped, failed=failed
    )
    conn.close()
    return {"total": total, "upserted": upserted, "skipped": skipped, "failed": failed}
