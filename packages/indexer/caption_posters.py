"""VLM(비전언어모델) 포스터 캡션 -> posters.caption + Qdrant poster_caption.

비전 모델이 포스터 이미지를 보고 한국어 '검색용 장면 설명 + 태그'를 생성한다. 결과는 두 곳에 쓰인다:
- SQLite posters.caption -> embed_text 의 [장면] 블록으로 videos 임베딩에 합류(채팅 검색).
- Qdrant poster_caption -> bge-m3 임베딩(이미지 화면 텍스트->포스터 CLIP+캡션 하이브리드 검색).

- 모델: config.models.vision (예: huihui_ai/gemma-4-abliterated:e4b). Ollama /api/chat.
  gemma 계열은 think=False 로 추론을 꺼서 빠르게 답을 받는다(장당 ~3초).
- caption 이 비어있는 포스터만 처리(resumable). 전체 재생성은 force=True.
- 프롬프트는 '검색용 비노골 속성'(장소/의상 종류/분위기/인원/화면 텍스트)에 집중.
"""

from __future__ import annotations

import base64
import logging
import sqlite3
import time
from collections.abc import Iterable

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _embedder, _qdrant, opus_to_id
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "poster_caption"
VECTOR_DIM = 1024  # bge-m3

# 검색 메타데이터 목적의 비노골 속성 추출 프롬프트
PROMPT = (
    "이 포스터 이미지를 한국어로 분석해 '검색용 메타데이터'를 만드세요. "
    "성적·노골적 묘사는 하지 말고, 검색에 쓸 장면·속성 키워드만 뽑으세요.\n"
    "다음 항목 위주:\n"
    "- 장소/배경 (실내/실외, 구체적으로: 해변/교실/사무실/침실/야외 등)\n"
    "- 의상/복장 '종류' (교복/드레스/수영복/정장/유니폼 등 — 노출 정도가 아니라 종류)\n"
    "- 분위기/톤 (밝음/어두움/청량/차분/화려함 등)\n"
    "- 등장 인원 수\n"
    "- 화면에 보이는 텍스트/로고 (있으면 그대로)\n"
    "출력 형식(한국어만):\n"
    "설명: <1~2문장>\n"
    "태그: <쉼표로 구분된 키워드 5개 이내>"
)


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
        where += " AND (caption IS NULL OR caption = '')"
    sql = f"SELECT opus, path, kind, video_path FROM posters {where} ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql)]


def _fetch_payload_extra(conn: sqlite3.Connection, opus: str) -> dict:
    v = conn.execute(
        "SELECT release_year, release_month, studio FROM videos WHERE opus = ?", (opus,)
    ).fetchone()
    actrs = [
        r["canonical_name"]
        for r in conn.execute("SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))
    ]
    return {
        "year": v["release_year"] if v else None,
        "month": v["release_month"] if v else None,
        "studio": v["studio"] if v else None,
        "actresses": actrs,
    }


def _caption_one(client: httpx.Client, url: str, model: str, path: str) -> str:
    """포스터 한 장 -> 한국어 캡션 텍스트. 실패/거부 시 빈 문자열."""
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        log.warning("read fail %s: %s", path, e)
        return ""
    try:
        r = client.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
                "stream": False,
                "think": False,  # gemma 계열은 thinking 을 꺼야 빠르고 바로 답함
                "options": {"temperature": 0.2, "num_predict": 512},
            },
            timeout=180.0,
        )
        r.raise_for_status()
        msg = r.json().get("message") or {}
        return (msg.get("content") or "").strip()
    except Exception as e:
        log.warning("caption fail %s: %s", path, e)
        return ""


# --- 실행 --------------------------------------------------------


def _batched(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def run(limit: int | None = None, force: bool = False, embed_batch: int = 16) -> dict:
    cfg = load_config()
    model = cfg["models"].get("vision")
    if not model:
        raise RuntimeError("config.models.vision 미설정 — 비전 모델명을 지정하세요.")
    url = cfg["server"]["ollama"].rstrip("/") + "/api/chat"

    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    ensure_collection(qc)
    emb = _embedder()

    targets = _fetch_targets(conn, force=force, limit=limit)
    total = len(targets)
    log.info("caption_posters: %d targets (model=%s force=%s)", total, model, force)

    done = 0
    failed = 0
    embedded = 0
    t_start = time.time()
    pending: list[tuple[str, str, dict]] = []  # (opus, caption, payload_extra)

    def _flush(batch: list[tuple[str, str, dict]]) -> None:
        nonlocal embedded
        if not batch:
            return
        docs = [c for _, c, _ in batch]
        vecs = emb.encode(
            docs, batch_size=embed_batch, normalize_embeddings=True, show_progress_bar=False
        )
        points = []
        for (opus, cap, extra), vec in zip(batch, vecs):
            payload = {
                "opus": opus,
                "kind": extra.get("kind"),
                "year": extra.get("year"),
                "month": extra.get("month"),
                "studio": extra.get("studio"),
                "canonical_actresses": extra.get("actresses", []),
                "playable": bool(extra.get("video_path")),
                "caption": cap,
            }
            points.append(qm.PointStruct(id=opus_to_id(opus), vector=vec.tolist(), payload=payload))
        qc.upsert(collection_name=COLLECTION, points=points, wait=False)
        embedded += len(points)

    with httpx.Client() as hc:
        for row in targets:
            opus, path = row["opus"], row["path"]
            cap = _caption_one(hc, url, model, path)
            # 빈 결과도 저장해 재시도를 막는다(force 로만 재실행).
            conn.execute("UPDATE posters SET caption = ? WHERE opus = ?", (cap, opus))
            if not cap:
                failed += 1
            else:
                extra = _fetch_payload_extra(conn, opus)
                extra["kind"] = row.get("kind")
                extra["video_path"] = row.get("video_path")
                pending.append((opus, cap, extra))
            done += 1

            if done % 10 == 0:
                conn.commit()
            if len(pending) >= embed_batch:
                _flush(pending)
                pending.clear()
            if done % 20 == 0 or done == total:
                elapsed = time.time() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                log.info(
                    "caption_posters %d/%d  failed=%d  embedded=%d  %.2f it/s  ETA %.0fs",
                    done,
                    total,
                    failed,
                    embedded,
                    rate,
                    eta,
                )
                update_stage(
                    "caption_posters", completed=done, total=total, failed=failed, embedded=embedded
                )

    _flush(pending)
    conn.commit()
    update_stage(
        "caption_posters",
        done=(limit is None and not force),
        completed=done,
        total=total,
        failed=failed,
        embedded=embedded,
    )
    conn.close()
    return {
        "total": total,
        "processed": done,
        "embedded": embedded,
        "failed": failed,
        "elapsed_sec": round(time.time() - t_start, 2),
    }
