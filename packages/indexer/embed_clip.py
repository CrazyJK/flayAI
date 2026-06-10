"""OpenCLIP ViT-L/14 -> Qdrant `posters_clip` 컬렉션.

AI_PLAN.md §10 M4 / §6.1 [7].
- 모델: open_clip_torch (ViT-L-14, laion2b_s32b_b82k), vector=768, Cosine
- 입력: posters 테이블의 path (instance + archive 모두)
- 타일링: 포스터당 전체 + 좌/우 절반 + 4분면 = 7벡터 (잘린 이미지 질의 대응)
- payload: opus, kind, tile, year, month, studio, canonical_actresses[],
           rank, play, like_count, playable
- 멱등: full 타일은 opus -> SHA1 id (레거시 단일점 덮어쓰기), 나머지는 opus#tile 파생 id
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import torch
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema, load_embed_sigs, save_embed_sigs
from packages.indexer.embed_text import _existing_ids, _qdrant, opus_to_id
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "posters_clip"
VECTOR_DIM = 768

# 타일 구성: 절반·1/4 조각 질의가 대응 타일과 직접 매칭되게 한다.
# 시그니처에 포함되므로 구성을 바꾸면 다음 실행 때 자동으로 전량 재임베딩된다.
TILE_SCHEME = "tiles7"
TILE_NAMES = ("full", "left", "right", "tl", "tr", "bl", "br")

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
        "SELECT opus, path, kind, video_path, mtime FROM posters WHERE opus = ?", (opus,)
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
        "mtime": p["mtime"],
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


def _poster_sig(b: dict) -> str:
    """포스터 벡터 입력의 시그니처 = 경로 + 수정시각 + 타일 구성."""
    return hashlib.sha1(f"{b['path']}|{b.get('mtime')}|{TILE_SCHEME}".encode()).hexdigest()


def tile_point_id(opus: str, tile: str) -> int:
    """full 은 기존 단일점 id 유지(덮어쓰기), 나머지 타일은 opus#tile 파생 id."""
    return opus_to_id(opus) if tile == "full" else opus_to_id(f"{opus}#{tile}")


def _tile_crops(im: Image.Image) -> dict[str, Image.Image]:
    """전체 + 좌/우 절반 + 4분면. TILE_NAMES 와 키가 일치해야 한다."""
    w, h = im.size
    return {
        "full": im,
        "left": im.crop((0, 0, w // 2, h)),
        "right": im.crop((w // 2, 0, w, h)),
        "tl": im.crop((0, 0, w // 2, h // 2)),
        "tr": im.crop((w // 2, 0, w, h // 2)),
        "bl": im.crop((0, h // 2, w // 2, h)),
        "br": im.crop((w // 2, h // 2, w, h)),
    }


def _encode_tensors(tensors: list[torch.Tensor], bs: int) -> torch.Tensor:
    """전처리된 텐서를 bs 단위 미니배치로 인코딩(타일 7배수여도 VRAM 상한 유지) 후 정규화."""
    model, _, device = _load_model()
    outs = []
    with torch.no_grad():
        for i in range(0, len(tensors), bs):
            batch = torch.stack(tensors[i : i + bs]).to(device)
            feats = model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            outs.append(feats.detach().cpu())
    return torch.cat(outs)


def run(limit: int | None = None, batch_size: int | None = None, force: bool = False) -> dict:
    """증분: 포스터 path|mtime|타일구성 시그니처가 직전과 같으면 인코딩 스킵.

    포스터 이미지는 opus 당 불변(교체 시 mtime 변경)이고 payload 는 sync-payload 가
    갱신하므로 벡터 재계산은 신규·교체분만 하면 충분. 신규 포스터도 동일하게
    7타일 전부 임베딩된다. TILE_SCHEME 변경 시 시그니처가 달라져 자동 전량 재임베딩.
    force=True 면 시그니처 무시하고 전량 재임베딩.
    """
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
    unchanged = 0

    sigs = {} if force else load_embed_sigs(conn, COLLECTION)
    existing = set() if force else _existing_ids(qc, COLLECTION)
    new_sigs: list[tuple[str, str]] = []

    for chunk in _batched(all_opus, bs):
        to_embed: list[tuple[dict, str]] = []  # (bundle, sig)
        for opus in chunk:
            b = _fetch_poster_bundle(conn, opus)
            if b is None:
                skipped += 1
                continue
            sig = _poster_sig(b)
            if not force:
                prev = sigs.get(opus)
                if prev == sig:
                    unchanged += 1
                    continue
                if prev is None and all(tile_point_id(opus, t) in existing for t in TILE_NAMES):
                    # 첫 실행 시드: 7타일 점이 모두 있으면 유효로 보고 sig 만 기록(재임베딩 X)
                    new_sigs.append((opus, sig))
                    unchanged += 1
                    continue
            to_embed.append((b, sig))
        if to_embed:
            _, preprocess, _ = _load_model()
            tensors: list[torch.Tensor] = []
            owners: list[tuple[int, str]] = []  # (to_embed 인덱스, tile 이름)
            ok_idx: list[int] = []
            for i, (b, _s) in enumerate(to_embed):
                try:
                    im = Image.open(Path(b["path"])).convert("RGB")
                except Exception as e:
                    log.warning("image load failed %s: %s", b["path"], e)
                    failed += 1
                    continue
                for tile, crop in _tile_crops(im).items():
                    tensors.append(preprocess(crop))
                    owners.append((i, tile))
                ok_idx.append(i)
            if tensors:
                feats = _encode_tensors(tensors, bs)
                points = []
                for j, (i, tile) in enumerate(owners):
                    b, _s = to_embed[i]
                    payload = _build_payload(b)
                    payload["tile"] = tile
                    points.append(
                        qm.PointStruct(
                            id=tile_point_id(b["opus"], tile),
                            vector=feats[j].tolist(),
                            payload=payload,
                        )
                    )
                qc.upsert(collection_name=COLLECTION, points=points, wait=False)
                for i in ok_idx:
                    b, s = to_embed[i]
                    new_sigs.append((b["opus"], s))
                upserted += len(ok_idx)  # 포스터(opus) 단위 카운트, 점 수는 x7
                if upserted % (bs * 8) == 0 and upserted > 0:
                    update_stage("embed_clip", completed=upserted)
                    log.info("embed_clip %d / %d (unchanged %d)", upserted, total, unchanged)
        if len(new_sigs) >= 1000:
            save_embed_sigs(conn, COLLECTION, new_sigs)
            new_sigs = []

    save_embed_sigs(conn, COLLECTION, new_sigs)
    update_stage(
        "embed_clip",
        done=True,
        completed=upserted,
        total=total,
        skipped=skipped + unchanged,
        failed=failed,
    )
    conn.close()
    return {
        "total": total,
        "upserted": upserted,
        "skipped": skipped,
        "unchanged": unchanged,
        "failed": failed,
    }
