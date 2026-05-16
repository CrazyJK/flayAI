"""RapidOCR(ONNX) -> posters.ocr_text + Qdrant `poster_ocr` 컬렉션.

AI_PLAN.md §6.1 [6], §5.2.
- 모델: rapidocr-onnxruntime (PP-OCR ONNX, paddle 불필요)
- 텍스트가 비어있는 포스터만 처리 (resumable)
- bge-m3 임베딩 -> 컬렉션 `poster_ocr` (size=1024, cosine)
- payload: opus, kind, year, month, studio, canonical_actresses[], playable, ocr_text
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _embedder, _qdrant, opus_to_id
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "poster_ocr"
VECTOR_DIM = 1024

_OCR = None


def _load_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        log.info("loading RapidOCR (onnxruntime)")
        _OCR = RapidOCR()
    return _OCR


# --- Qdrant ------------------------------------------------------

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
        ("playable", qm.PayloadSchemaType.BOOL),
    ]:
        try:
            client.create_payload_index(COLLECTION, field, field_schema=ftype)
        except Exception as e:
            log.debug("payload index skipped %s: %s", field, e)


# --- 데이터 ------------------------------------------------------

def _fetch_targets(conn: sqlite3.Connection, force: bool, limit: int | None) -> list[dict]:
    where = "WHERE path IS NOT NULL"
    if not force:
        where += " AND (ocr_text IS NULL OR ocr_text = '')"
    sql = f"SELECT opus, path, kind, video_path FROM posters {where} ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql)]


def _fetch_payload_extra(conn: sqlite3.Connection, opus: str) -> dict:
    v = conn.execute("""
        SELECT release_year, release_month, studio
        FROM videos WHERE opus = ?
    """, (opus,)).fetchone()
    actrs = [r["canonical_name"] for r in conn.execute(
        "SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))]
    return {
        "year": v["release_year"] if v else None,
        "month": v["release_month"] if v else None,
        "studio": v["studio"] if v else None,
        "actresses": actrs,
    }


def _ocr_one(path: str) -> tuple[str, float]:
    """RapidOCR 한 장. (concat text, mean score) 반환."""
    ocr = _load_ocr()
    try:
        result, _elapse = ocr(path)
    except Exception as e:
        log.warning("ocr failed %s: %s", path, e)
        return "", 0.0
    if not result:
        return "", 0.0
    texts: list[str] = []
    scores: list[float] = []
    for item in result:
        try:
            _bbox, text, score = item
        except ValueError:
            continue
        text = (text or "").strip()
        if not text:
            continue
        texts.append(text)
        scores.append(float(score or 0.0))
    joined = " ".join(texts)
    mean = sum(scores) / len(scores) if scores else 0.0
    return joined, mean


# --- 실행 --------------------------------------------------------

def _batched(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def run(limit: int | None = None, force: bool = False,
        embed_batch: int = 16) -> dict:
    cfg = load_config()
    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    ensure_collection(qc)
    emb = _embedder()

    targets = _fetch_targets(conn, force=force, limit=limit)
    total = len(targets)
    log.info("ocr_posters: %d targets (force=%s)", total, force)

    done = 0
    embedded = 0
    failed = 0
    t_start = time.time()

    # OCR + DB 저장은 1건씩, 임베딩은 batch
    pending: list[tuple[str, str, dict]] = []  # (opus, text, payload_extra)

    def _flush(batch: list[tuple[str, str, dict]]):
        nonlocal embedded
        if not batch:
            return
        docs = [t for _, t, _ in batch]
        vecs = emb.encode(docs, batch_size=embed_batch,
                          normalize_embeddings=True, show_progress_bar=False)
        points = []
        for (opus, text, extra), vec in zip(batch, vecs):
            payload = {
                "opus": opus,
                "kind": extra.get("kind"),
                "year": extra.get("year"),
                "month": extra.get("month"),
                "studio": extra.get("studio"),
                "canonical_actresses": extra.get("actresses", []),
                "playable": bool(extra.get("video_path")),
                "ocr_text": text,
            }
            points.append(qm.PointStruct(
                id=opus_to_id(opus), vector=vec.tolist(), payload=payload,
            ))
        qc.upsert(collection_name=COLLECTION, points=points, wait=False)
        embedded += len(points)

    for row in targets:
        opus = row["opus"]
        path = row["path"]
        text, mean_score = _ocr_one(path)
        if not text:
            # 빈 결과도 저장해서 재시도 방지 (force 로만 재실행)
            conn.execute("UPDATE posters SET ocr_text = ? WHERE opus = ?", ("", opus))
            failed += 1
        else:
            conn.execute("UPDATE posters SET ocr_text = ? WHERE opus = ?", (text, opus))
            extra = _fetch_payload_extra(conn, opus)
            extra["kind"] = row.get("kind")
            extra["video_path"] = row.get("video_path")
            pending.append((opus, text, extra))
        done += 1

        if done % 20 == 0:
            conn.commit()
        if len(pending) >= embed_batch:
            _flush(pending)
            pending.clear()
        if done % 50 == 0 or done == total:
            elapsed = time.time() - t_start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            log.info("ocr_posters %d/%d  failed=%d  embedded=%d  %.2f it/s  ETA %.0fs",
                     done, total, failed, embedded, rate, eta)
            update_stage("ocr_posters", completed=done, total=total,
                         failed=failed, embedded=embedded)

    _flush(pending)
    conn.commit()
    update_stage("ocr_posters", done=(limit is None and not force),
                 completed=done, total=total, failed=failed, embedded=embedded)
    conn.close()
    return {
        "total": total, "processed": done, "embedded": embedded,
        "failed": failed, "elapsed_sec": round(time.time() - t_start, 2),
    }
