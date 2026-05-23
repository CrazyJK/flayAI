"""LLM tool 정의.

AI_PLAN.md §7.3.
모든 함수는 read-only. write 는 별도 admin 라우트.

각 함수는:
- JSON-serializable 인자/반환
- LLM tool calling JSON Schema 와 일관된 시그니처
- 외부 effect 없음 (DB read + Qdrant search 만)
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from packages.indexer.actress_merge import normalize_actress
from packages.indexer.db import connect
from packages.rag.ranker import rank as rerank
from packages.rag.retriever import Filters, hybrid_search

log = logging.getLogger(__name__)


def _resolve_actress_alias(conn, name: str | None) -> str | None:
    if not name:
        return None
    norm = normalize_actress(name)
    row = conn.execute(
        "SELECT canonical_name FROM actress_aliases WHERE alias_norm = ?",
        (norm,),
    ).fetchone()
    return row["canonical_name"] if row else None


def _resolve_tag_id(conn, tag_name: str | None) -> int | None:
    if not tag_name:
        return None
    row = conn.execute("SELECT id FROM tags WHERE name = ? LIMIT 1", (tag_name,)).fetchone()
    return int(row["id"]) if row else None


def _video_to_hit(conn, opus: str, scored=None) -> dict | None:
    v = conn.execute(
        """
        SELECT opus, title_jp, title_ko, desc_ko, studio, release_date,
               release_year, release_month, kind, rank, play, like_count, last_play
        FROM videos WHERE opus = ?
    """,
        (opus,),
    ).fetchone()
    if not v:
        return None
    actrs = [
        r["canonical_name"]
        for r in conn.execute("SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))
    ]
    poster = conn.execute(
        "SELECT path, video_path, kind FROM posters WHERE opus = ?", (opus,)
    ).fetchone()
    out: dict[str, Any] = {
        "opus": v["opus"],
        "title": v["title_ko"] or v["title_jp"],
        "title_jp": v["title_jp"],
        "title_ko": v["title_ko"],
        "studio": v["studio"],
        "release_date": v["release_date"],
        "year": v["release_year"],
        "month": v["release_month"],
        "kind": v["kind"],
        "rank": v["rank"],
        "play": v["play"],
        "like_count": v["like_count"],
        "actresses": actrs,
        "poster_path": poster["path"] if poster else None,
        "video_path": poster["video_path"] if poster else None,
        "playable": bool(poster and poster["video_path"]),
    }
    if scored is not None:
        out["score"] = round(scored.final_score, 4)
        out["score_breakdown"] = {
            "semantic": round(scored.semantic, 4),
            "fts": round(scored.fts, 4),
            "usage": round(scored.usage, 4),
            "recency": round(scored.recency, 4),
        }
    return out


# =================================================================
# Tools
# =================================================================


def search_videos(
    query: str = "",
    year: int | None = None,
    month: int | None = None,
    actress: str | None = None,
    tag: str | None = None,
    studio: str | None = None,
    kind: Literal["instance", "archive", "any"] = "any",
    playable: bool | None = None,
    min_rank: int | None = None,
    rank: int | None = None,
    min_likes: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """자연어 검색 + 메타 필터. query 비어있고 필터만 있어도 동작 (메타 only).

    min_rank: 평점 N 이상(rank >= N). rank: 정확히 평점 N(rank == N).
    min_likes: 좋아요 N 이상(like_count >= N).
    """
    conn = connect()
    try:
        actress_canon = _resolve_actress_alias(conn, actress)
        # LLM 이 일반명사·테마(예: '며느리')를 actress 로 잘못 넣었거나 미인덱스 배우인 경우,
        # 필터를 조용히 버리지 말고 query 로 흡수해 의미/FTS 검색에 활용(빈손 결과 방지).
        if actress and actress_canon is None:
            query = f"{query} {actress}".strip()
            log.info("search_videos: unresolved actress %r -> query 로 흡수", actress)
        tag_id = _resolve_tag_id(conn, tag)
        filt = Filters(
            year=year,
            month=month,
            studio=studio,
            actress_canonical=actress_canon,
            tag_id=tag_id,
            kind=None if kind in (None, "any") else kind,
            playable=playable,
            min_rank=min_rank,
            rank=rank,
            min_likes=min_likes,
        )
        if query.strip():
            top_k = max(limit * 3, 30)
            cands = hybrid_search(query, top_k=top_k, filters=filt, conn=conn)
            scored = rerank(cands)[:limit]
            hits: list[dict] = []
            for s in scored:
                h = _video_to_hit(conn, s.opus, scored=s)
                if h:
                    hits.append(h)
            return hits
        # 메타-only fallback: SQL 직접 정렬
        return _meta_only_search(conn, filt, limit)
    finally:
        conn.close()


def _meta_only_search(conn, f: Filters, limit: int) -> list[dict]:
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
    if f.rank is not None:
        where.append("v.rank = ?")
        params.append(int(f.rank))
    if f.min_likes is not None:
        where.append("v.like_count >= ?")
        params.append(int(f.min_likes))
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
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT v.opus FROM videos v {where_sql}
        ORDER BY v.rank DESC, v.last_play DESC NULLS LAST
        LIMIT ?
    """
    rows = conn.execute(sql, [*params, int(limit)]).fetchall()
    return [h for r in rows if (h := _video_to_hit(conn, r["opus"]))]


def similar_to(opus: str, exclude_watched: bool = True, limit: int = 10) -> list[dict]:
    """opus 의 임베딩과 유사한 영상."""
    from packages.indexer.embed_text import COLLECTION, _qdrant, opus_to_id

    qc = _qdrant()
    try:
        rec = qc.retrieve(
            collection_name=COLLECTION,
            ids=[opus_to_id(opus)],
            with_vectors=True,
            with_payload=False,
        )
    except Exception as e:
        log.warning("retrieve seed vector failed: %s", e)
        return []
    if not rec:
        return []
    seed_vec = rec[0].vector
    try:
        resp = qc.query_points(
            collection_name=COLLECTION, query=seed_vec, limit=limit + 5, with_payload=True
        )
    except Exception as e:
        log.warning("similar search failed: %s", e)
        return []
    conn = connect()
    try:
        out: list[dict] = []
        for hit in resp.points:
            cand_opus = (hit.payload or {}).get("opus")
            if not cand_opus or cand_opus == opus:
                continue
            if exclude_watched and (hit.payload or {}).get("play", 0) > 0:
                continue
            h = _video_to_hit(conn, cand_opus)
            if h:
                h["score"] = round(float(hit.score), 4)
                out.append(h)
            if len(out) >= limit:
                break
        return out
    finally:
        conn.close()


def get_video(opus: str) -> dict | None:
    conn = connect()
    try:
        return _video_to_hit(conn, opus)
    finally:
        conn.close()


def get_actress(name: str) -> dict | None:
    """alias -> canonical -> 상세."""
    conn = connect()
    try:
        canon = _resolve_actress_alias(conn, name)
        if not canon:
            return None
        a = conn.execute("SELECT * FROM actresses WHERE canonical_name = ?", (canon,)).fetchone()
        if not a:
            return None
        aliases = [
            r["alias_raw"]
            for r in conn.execute(
                "SELECT alias_raw FROM actress_aliases WHERE canonical_name = ?", (canon,)
            )
        ]
        n_videos = conn.execute(
            "SELECT COUNT(*) AS c FROM video_actresses WHERE canonical_name = ?", (canon,)
        ).fetchone()["c"]
        return {**dict(a), "aliases": aliases, "video_count": int(n_videos)}
    finally:
        conn.close()


def stats(actress: str | None = None, tag: str | None = None, year: int | None = None) -> dict:
    """간단 집계."""
    conn = connect()
    try:
        where: list[str] = []
        params: list[Any] = []
        joins = ""
        if actress:
            canon = _resolve_actress_alias(conn, actress)
            if not canon:
                return {"count": 0}
            joins += " JOIN video_actresses va ON va.opus = v.opus AND va.canonical_name = ?"
            params.append(canon)
        if tag:
            tid = _resolve_tag_id(conn, tag)
            if tid is None:
                return {"count": 0}
            joins += " JOIN video_tags vt ON vt.opus = v.opus AND vt.tag_id = ?"
            params.append(tid)
        if year is not None:
            where.append("v.release_year = ?")
            params.append(int(year))
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
            SELECT COUNT(*) AS c, AVG(v.rank) AS avg_rank, SUM(v.play) AS total_play,
                   COUNT(CASE WHEN v.kind='instance' THEN 1 END) AS instance_count,
                   COUNT(CASE WHEN v.kind='archive'  THEN 1 END) AS archive_count
            FROM videos v {joins} {where_sql}
        """
        r = conn.execute(sql, params).fetchone()
        return {
            "count": r["c"],
            "avg_rank": r["avg_rank"],
            "total_play": r["total_play"],
            "instance_count": r["instance_count"],
            "archive_count": r["archive_count"],
        }
    finally:
        conn.close()


# =================================================================
# tool schema (Ollama / OpenAI 함수 호출 호환)
# =================================================================

TOOL_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_videos",
            "description": "비디오 검색. 자연어 query + 메타 필터(연도/월/배우/태그/제작사/kind/playable/평점). "
            "kind='instance' 는 지금 볼 수 있는 것, 'archive' 는 보관소.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "자연어 검색어. 빈 문자열이면 메타 필터만 사용.",
                    },
                    "year": {"type": "integer"},
                    "month": {"type": "integer"},
                    "actress": {"type": "string", "description": "배우 이름 (별칭 자동 정규화)"},
                    "tag": {"type": "string"},
                    "studio": {"type": "string"},
                    "kind": {"type": "string", "enum": ["instance", "archive", "any"]},
                    "playable": {
                        "type": "boolean",
                        "description": "true 면 video_path 보유한 것만",
                    },
                    "min_rank": {"type": "integer", "description": "평점 N 이상(rank >= N)"},
                    "rank": {"type": "integer", "description": "정확히 평점 N(rank == N). '평점 5'처럼 '이상' 없이 특정 평점만."},
                    "min_likes": {"type": "integer", "description": "좋아요 N 이상(like_count >= N)"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "similar_to",
            "description": "opus 와 의미적으로 유사한 영상.",
            "parameters": {
                "type": "object",
                "properties": {
                    "opus": {"type": "string"},
                    "exclude_watched": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["opus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_video",
            "description": "opus 의 상세 메타.",
            "parameters": {
                "type": "object",
                "properties": {"opus": {"type": "string"}},
                "required": ["opus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_actress",
            "description": "배우 상세 (alias 자동 정규화 + 출연 영상 수).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stats",
            "description": "배우/태그/연도별 집계 (count, avg_rank, total_play, instance/archive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "actress": {"type": "string"},
                    "tag": {"type": "string"},
                    "year": {"type": "integer"},
                },
            },
        },
    },
]


TOOL_DISPATCH = {
    "search_videos": search_videos,
    "similar_to": similar_to,
    "get_video": get_video,
    "get_actress": get_actress,
    "stats": stats,
}
