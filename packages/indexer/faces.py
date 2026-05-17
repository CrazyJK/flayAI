"""InsightFace (buffalo_l) -> poster_faces (SQLite) + Qdrant `faces` 컬렉션.

AI_PLAN.md §10 M4 / §6.1 [8].
- 모델: insightface FaceAnalysis (buffalo_l), CUDAExecutionProvider 우선
- 입력: posters.path 전체
- SQLite poster_faces: (poster_opus, face_idx, cluster_id=NULL, bbox=JSON)
- Qdrant `faces` (size=512, Cosine), payload:
    {opus, face_idx, kind, year, studio, canonical_actresses, bbox, det_score}
- 멱등: 같은 opus 재처리 시 poster_faces / qdrant 의 해당 opus point 모두 제거 후 재삽입
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _qdrant
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "faces"
VECTOR_DIM = 512

_FA = None


# --- 모델 로더 ----------------------------------------------------


def _load_face_app():
    global _FA
    if _FA is not None:
        return _FA
    import insightface

    cfg = load_config()
    name = cfg["models"]["face_model"]
    log.info("loading InsightFace %s", name)
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    fa = insightface.app.FaceAnalysis(name=name, providers=providers)
    fa.prepare(ctx_id=0, det_size=(640, 640))
    _FA = fa
    return fa


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
        ("face_idx", qm.PayloadSchemaType.INTEGER),
        ("cluster_id", qm.PayloadSchemaType.INTEGER),
        ("kind", qm.PayloadSchemaType.KEYWORD),
        ("year", qm.PayloadSchemaType.INTEGER),
        ("studio", qm.PayloadSchemaType.KEYWORD),
        ("canonical_actresses", qm.PayloadSchemaType.KEYWORD),
    ]:
        try:
            client.create_payload_index(COLLECTION, field, field_schema=ftype)
        except Exception as e:
            log.debug("index create skipped %s: %s", field, e)


def _face_id(opus: str, idx: int) -> int:
    h = hashlib.sha1(f"{opus}#{idx}".encode()).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


# --- 데이터 -------------------------------------------------------


def _fetch_meta(conn: sqlite3.Connection, opus: str) -> dict:
    v = conn.execute(
        """
        SELECT release_year, release_month, studio, kind FROM videos WHERE opus = ?
    """,
        (opus,),
    ).fetchone()
    actrs = [
        r["canonical_name"]
        for r in conn.execute("SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))
    ]
    p = conn.execute("SELECT kind, video_path FROM posters WHERE opus = ?", (opus,)).fetchone()
    return {
        "year": v["release_year"] if v else None,
        "month": v["release_month"] if v else None,
        "studio": v["studio"] if v else None,
        "kind": (v["kind"] if v and v["kind"] else (p["kind"] if p else None)),
        "actresses": actrs,
        "playable": bool(p and p["video_path"]),
    }


def _opus_iter(
    conn: sqlite3.Connection, limit: int | None, only_missing: bool
) -> list[tuple[str, str]]:
    if only_missing:
        sql = """
            SELECT p.opus, p.path FROM posters p
            WHERE p.path IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM poster_faces f WHERE f.poster_opus = p.opus)
            ORDER BY p.opus
        """
    else:
        sql = "SELECT opus, path FROM posters WHERE path IS NOT NULL ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [(r["opus"], r["path"]) for r in conn.execute(sql)]


def _delete_existing(conn: sqlite3.Connection, qc: QdrantClient, opus: str) -> None:
    conn.execute("DELETE FROM poster_faces WHERE poster_opus = ?", (opus,))
    try:
        qc.delete(
            collection_name=COLLECTION,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(key="opus", match=qm.MatchValue(value=opus)),
                    ]
                )
            ),
        )
    except Exception as e:
        log.debug("qdrant delete skipped for %s: %s", opus, e)


# --- 실행 ---------------------------------------------------------


def run(
    limit: int | None = None, only_missing: bool = True, det_score_threshold: float = 0.5
) -> dict:
    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    ensure_collection(qc)
    fa = _load_face_app()

    targets = _opus_iter(conn, limit, only_missing)
    total = len(targets)
    processed = 0
    faces_added = 0
    failed = 0

    for opus, path in targets:
        try:
            im = Image.open(Path(path)).convert("RGB")
            arr = np.array(im)[:, :, ::-1]  # RGB -> BGR (insightface convention)
        except Exception as e:
            log.warning("image load failed %s: %s", opus, e)
            failed += 1
            processed += 1
            continue

        try:
            faces = fa.get(arr)
        except Exception as e:
            log.warning("face detect failed %s: %s", opus, e)
            failed += 1
            processed += 1
            continue

        # 멱등: 기존 행 제거
        _delete_existing(conn, qc, opus)

        meta = _fetch_meta(conn, opus)
        rows = []
        points = []
        for idx, f in enumerate(faces):
            score = float(getattr(f, "det_score", 1.0))
            if score < det_score_threshold:
                continue
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                emb = f.embedding / (np.linalg.norm(f.embedding) + 1e-9)
            bbox = [float(x) for x in f.bbox.tolist()]
            rows.append((opus, idx, None, json.dumps(bbox)))
            payload = {
                "opus": opus,
                "face_idx": idx,
                "cluster_id": None,
                "kind": meta["kind"],
                "year": meta["year"],
                "month": meta["month"],
                "studio": meta["studio"],
                "canonical_actresses": meta["actresses"],
                "bbox": bbox,
                "det_score": score,
                "playable": meta["playable"],
            }
            points.append(
                qm.PointStruct(
                    id=_face_id(opus, idx),
                    vector=emb.tolist(),
                    payload=payload,
                )
            )

        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO poster_faces (poster_opus, face_idx, cluster_id, bbox) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
        if points:
            qc.upsert(collection_name=COLLECTION, points=points, wait=False)
        faces_added += len(points)
        processed += 1

        if processed % 100 == 0:
            conn.commit()
            update_stage("extract_faces", completed=processed, faces=faces_added)
            log.info(
                "extract_faces %d / %d (faces=%d failed=%d)", processed, total, faces_added, failed
            )

    conn.commit()
    update_stage(
        "extract_faces",
        done=True,
        completed=processed,
        total=total,
        faces=faces_added,
        failed=failed,
    )
    conn.close()
    return {"total": total, "processed": processed, "faces_added": faces_added, "failed": failed}
