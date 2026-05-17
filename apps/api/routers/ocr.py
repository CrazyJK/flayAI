"""포스터 OCR 검색 라우터 (AI_PLAN.md §10 M5).

엔드포인트:
- POST /api/search/poster-ocr  {query, limit, kind}
  bge-m3 텍스트 임베딩 -> Qdrant `poster_ocr` -> video hit + matched ocr_text 발췌
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from qdrant_client.http import models as qm

from packages.indexer.db import connect
from packages.indexer.embed_text import _embedder, _qdrant
from packages.indexer.ocr import COLLECTION as POSTER_OCR
from packages.rag.tools import _video_to_hit

log = logging.getLogger(__name__)
router = APIRouter()


class PosterOcrSearchRequest(BaseModel):
    query: str
    limit: int = 10
    kind: str | None = None  # 'instance' | 'archive' | None


def _kind_filter(kind: str | None) -> qm.Filter | None:
    if kind not in ("instance", "archive"):
        return None
    return qm.Filter(must=[qm.FieldCondition(key="kind", match=qm.MatchValue(value=kind))])


@router.post("/api/search/poster-ocr")
def poster_ocr_search(req: PosterOcrSearchRequest) -> dict[str, Any]:
    emb = _embedder()
    vec = emb.encode([req.query], normalize_embeddings=True, show_progress_bar=False)[0].tolist()
    qc = _qdrant()
    res = qc.query_points(
        collection_name=POSTER_OCR,
        query=vec,
        limit=req.limit,
        query_filter=_kind_filter(req.kind),
        with_payload=True,
    ).points

    conn = connect()
    items: list[dict[str, Any]] = []
    try:
        for p in res:
            payload = p.payload or {}
            opus = payload.get("opus")
            if not opus:
                continue
            hit = _video_to_hit(conn, opus)
            if not hit:
                continue
            hit["score"] = round(float(p.score), 4)
            hit["ocr_text"] = payload.get("ocr_text", "")
            items.append(hit)
    finally:
        conn.close()
    return {"items": items, "query": req.query}
