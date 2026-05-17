"""검색 retriever: Qdrant semantic + SQLite FTS5 + RRF.

AI_PLAN.md §7.1, §7.2.
- semantic_search(query, top_k, filters) -> [(opus, sim, payload)]
- fts_search(query, top_k, filters)      -> [(opus, bm25_score)]
- hybrid_search(...)                      -> RRF 결합 후보 리스트
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from qdrant_client.http import models as qm

from packages.indexer.db import connect
from packages.indexer.embed_text import COLLECTION, _embedder, _qdrant

log = logging.getLogger(__name__)


@dataclass
class Filters:
    year: int | None = None
    month: int | None = None
    studio: str | None = None
    actress_canonical: str | None = None
    tag_id: int | None = None
    kind: str | None = None  # "instance" | "archive" | None
    playable: bool | None = None
    min_rank: int | None = None


@dataclass
class Candidate:
    opus: str
    semantic_score: float = 0.0
    fts_score: float = 0.0
    rrf_score: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)


# --- Qdrant filter builder ---------------------------------------


def _build_qdrant_filter(f: Filters) -> qm.Filter | None:
    must: list[qm.FieldCondition] = []
    if f.year is not None:
        must.append(qm.FieldCondition(key="year", match=qm.MatchValue(value=int(f.year))))
    if f.month is not None:
        must.append(qm.FieldCondition(key="month", match=qm.MatchValue(value=int(f.month))))
    if f.studio:
        must.append(qm.FieldCondition(key="studio", match=qm.MatchValue(value=f.studio)))
    if f.actress_canonical:
        must.append(
            qm.FieldCondition(
                key="canonical_actresses",
                match=qm.MatchValue(value=f.actress_canonical),
            )
        )
    if f.tag_id is not None:
        must.append(qm.FieldCondition(key="tag_ids", match=qm.MatchValue(value=int(f.tag_id))))
    if f.kind:
        must.append(qm.FieldCondition(key="kind", match=qm.MatchValue(value=f.kind)))
    if f.playable is not None:
        must.append(qm.FieldCondition(key="playable", match=qm.MatchValue(value=bool(f.playable))))
    if f.min_rank is not None:
        must.append(qm.FieldCondition(key="rank", range=qm.Range(gte=int(f.min_rank))))
    return qm.Filter(must=must) if must else None


# --- semantic ----------------------------------------------------


def semantic_search(query: str, top_k: int = 30, filters: Filters | None = None) -> list[Candidate]:
    if not query.strip():
        return []
    qc = _qdrant()
    emb = _embedder()
    vec = emb.encode([query], normalize_embeddings=True)[0].tolist()
    flt = _build_qdrant_filter(filters or Filters())
    try:
        resp = qc.query_points(
            collection_name=COLLECTION,
            query=vec,
            limit=top_k,
            query_filter=flt,
            with_payload=True,
        )
    except Exception as e:
        log.warning("qdrant search failed: %s", e)
        return []
    out: list[Candidate] = []
    for hit in resp.points:
        opus = (hit.payload or {}).get("opus")
        if not opus:
            continue
        out.append(
            Candidate(opus=opus, semantic_score=float(hit.score), payload=dict(hit.payload or {}))
        )
    return out


# --- FTS ---------------------------------------------------------

_BM25_NORM = 10.0


def _fts_query(query: str) -> str:
    """FTS5 안전한 쿼리: 토큰별로 인용해서 phrase OR 결합.
    trigram tokenizer 라 CJK도 정상 매칭됨.
    """
    s = query.strip()
    if not s:
        return ""
    # 공백/구두점으로 분할 후 각 토큰을 phrase 로
    import re as _re

    toks = [t for t in _re.split(r"[\s,.:;!?\u3000、。・]+", s) if t]
    if not toks:
        return ""
    quoted = [f"\"{t.replace(chr(34), '')}\"" for t in toks]
    return " OR ".join(quoted)


def fts_search(
    conn: sqlite3.Connection, query: str, top_k: int = 30, filters: Filters | None = None
) -> list[Candidate]:
    q = _fts_query(query)
    if not q:
        return []
    f = filters or Filters()

    # videos_fts MATCH -> bm25() 스코어 (낮을수록 좋음 -> 음수 사용)
    where: list[str] = []
    params: list[Any] = []
    if f.year is not None:
        where.append("v.release_year = ?")
        params.append(int(f.year))
    if f.month is not None:
        where.append("v.release_month = ?")
        params.append(int(f.month))
    if f.studio:
        where.append("v.studio = ?")
        params.append(f.studio)
    if f.kind:
        where.append("v.kind = ?")
        params.append(f.kind)
    if f.min_rank is not None:
        where.append("v.rank >= ?")
        params.append(int(f.min_rank))
    if f.actress_canonical:
        where.append(
            "EXISTS (SELECT 1 FROM video_actresses va "
            "WHERE va.opus = v.opus AND va.canonical_name = ?)"
        )
        params.append(f.actress_canonical)
    if f.tag_id is not None:
        where.append(
            "EXISTS (SELECT 1 FROM video_tags vt WHERE vt.opus = v.opus AND vt.tag_id = ?)"
        )
        params.append(int(f.tag_id))
    if f.playable is True:
        where.append(
            "EXISTS (SELECT 1 FROM posters p WHERE p.opus = v.opus AND p.video_path IS NOT NULL)"
        )
    where_sql = (" AND " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT v.opus AS opus, bm25(videos_fts) AS bscore
        FROM videos_fts
        JOIN videos v ON v.opus = videos_fts.opus
        WHERE videos_fts MATCH ? {where_sql}
        ORDER BY bscore ASC
        LIMIT ?
    """
    rows = conn.execute(sql, [q, *params, top_k]).fetchall()
    out: list[Candidate] = []
    for r in rows:
        # bm25() : 작을수록 좋음. 정규화: 1 / (1 + bscore/N)
        bscore = float(r["bscore"]) if r["bscore"] is not None else 0.0
        norm = 1.0 / (1.0 + max(bscore, 0.0) / _BM25_NORM)
        out.append(Candidate(opus=r["opus"], fts_score=norm))
    return out


# --- RRF 결합 -----------------------------------------------------

RRF_K = 60


def rrf_merge(*lists: list[Candidate]) -> list[Candidate]:
    by_opus: dict[str, Candidate] = {}
    for lst in lists:
        for rank, c in enumerate(lst):
            existing = by_opus.setdefault(c.opus, Candidate(opus=c.opus))
            existing.rrf_score += 1.0 / (RRF_K + rank + 1)
            existing.semantic_score = max(existing.semantic_score, c.semantic_score)
            existing.fts_score = max(existing.fts_score, c.fts_score)
            if c.payload and not existing.payload:
                existing.payload = c.payload
    merged = list(by_opus.values())
    merged.sort(key=lambda x: x.rrf_score, reverse=True)
    return merged


def hybrid_search(
    query: str,
    top_k: int = 30,
    filters: Filters | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[Candidate]:
    own = conn is None
    if own:
        conn = connect()
    try:
        sem = semantic_search(query, top_k=top_k, filters=filters)
        fts = fts_search(conn, query, top_k=top_k, filters=filters)
        return rrf_merge(sem, fts)
    finally:
        if own:
            conn.close()
