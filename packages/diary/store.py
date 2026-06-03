"""일기 세션·메시지 저장소 + 회상(hybrid 검색).

- 세션: '한 자리 대화'. idle_hours 넘게 끊기면 새 세션, 아니면 최근 세션 이어감.
- 메시지 저장 시 user 발화는 FTS 인덱싱 + bge-m3 임베딩 + Qdrant upsert(동기, 즉시 회상 가능).
- 회상: Qdrant 의미검색 + SQLite FTS5(BM25) → RRF 결합(영상 retriever 와 동일 패턴, RRF_K=60).
  Qdrant 가 없거나 실패하면 FTS 단독으로 graceful degrade(테스트·오프라인 대비).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from qdrant_client.http import models as qm

from packages.diary.schema import DIARY_COLLECTION
from packages.settings import load_config

log = logging.getLogger(__name__)

RRF_K = 60
_BM25_NORM = 10.0


# --- 시각 헬퍼 ----------------------------------------------------


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _iso_to_epoch(iso: str) -> int:
    try:
        return int(datetime.fromisoformat(iso).timestamp())
    except (ValueError, TypeError):
        return 0


# --- 세션 --------------------------------------------------------


def get_or_create_session(conn: sqlite3.Connection, idle_hours: float | None = None) -> int:
    """가장 최근 세션을 이어가거나(마지막 메시지가 idle_hours 이내), 새 세션 생성.

    레거시 임포트 세션(source_key 존재)은 이어쓰지 않는다(라이브 챗 세션만 대상).
    """
    if idle_hours is None:
        idle_hours = float(load_config().get("diary", {}).get("idle_hours", 6))
    row = conn.execute(
        "SELECT id, ended_at FROM diary_sessions "
        "WHERE source_key IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row and row["ended_at"]:
        try:
            last = datetime.fromisoformat(row["ended_at"])
            if datetime.now() - last <= timedelta(hours=idle_hours):
                return int(row["id"])
        except ValueError:
            pass
    return create_session(conn)


def create_session(
    conn: sqlite3.Connection,
    started_at: str | None = None,
    ended_at: str | None = None,
    title: str | None = None,
    weather: str | None = None,
    summary: str | None = None,
    source_key: str | None = None,
) -> int:
    started = started_at or _now_iso()
    cur = conn.execute(
        "INSERT INTO diary_sessions(started_at, ended_at, title, weather, summary, source_key) "
        "VALUES(?,?,?,?,?,?)",
        (started, ended_at or started, title, weather, summary, source_key),
    )
    conn.commit()
    return int(cur.lastrowid)


def session_by_source_key(conn: sqlite3.Connection, source_key: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM diary_sessions WHERE source_key = ?", (source_key,)
    ).fetchone()
    return int(row["id"]) if row else None


# --- 메시지 ------------------------------------------------------


def add_message(
    conn: sqlite3.Connection,
    session_id: int,
    role: str,
    content: str,
    raw_html: str | None = None,
    created_at: str | None = None,
    source: str = "chat",
    embed: bool = True,
) -> int:
    """메시지 저장. user 발화면 FTS 인덱싱 + (embed=True 시) 임베딩·Qdrant upsert.

    embed=False 는 테스트/오프라인용(Qdrant 없이 FTS 경로만 검증).
    """
    ts = created_at or _now_iso()
    cur = conn.execute(
        "INSERT INTO diary_messages(session_id, role, content, raw_html, created_at, source) "
        "VALUES(?,?,?,?,?,?)",
        (session_id, role, content, raw_html, ts, source),
    )
    msg_id = int(cur.lastrowid)
    conn.execute(
        "UPDATE diary_sessions SET ended_at = ? WHERE id = ?",
        (ts, session_id),
    )
    if role == "user" and content.strip():
        conn.execute(
            "INSERT INTO diary_messages_fts(content, message_id, session_id) VALUES(?,?,?)",
            (content, msg_id, session_id),
        )
    conn.commit()
    if role == "user" and embed and content.strip():
        _embed_message(msg_id, session_id, role, content, _iso_to_epoch(ts))
    return msg_id


def _embed_message(msg_id: int, session_id: int, role: str, content: str, epoch: int) -> None:
    """단일 user 메시지를 bge-m3 임베딩 → Qdrant diary 컬렉션 upsert. 실패는 경고만."""
    try:
        from packages.indexer.embed_text import _embedder, _qdrant

        vec = _embedder().encode(
            [content], normalize_embeddings=True, show_progress_bar=False
        )[0].tolist()
        _qdrant().upsert(
            collection_name=DIARY_COLLECTION,
            points=[
                qm.PointStruct(
                    id=msg_id,
                    vector=vec,
                    payload={
                        "message_id": msg_id,
                        "session_id": session_id,
                        "role": role,
                        "created_at_epoch": epoch,
                        "content": content,
                    },
                )
            ],
            wait=False,
        )
    except Exception as e:
        log.warning("diary 임베딩/업서트 실패(msg %s): %s", msg_id, e)


def get_session_transcript(conn: sqlite3.Connection, session_id: int) -> dict[str, Any] | None:
    """세션 메타 + 전체 메시지(시간순)."""
    s = conn.execute(
        "SELECT id, started_at, ended_at, title, weather, summary, source_key "
        "FROM diary_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not s:
        return None
    msgs = conn.execute(
        "SELECT id, role, content, raw_html, created_at, source "
        "FROM diary_messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    return {
        "session": dict(s),
        "messages": [dict(m) for m in msgs],
    }


def list_sessions(conn: sqlite3.Connection, limit: int = 50, offset: int = 0) -> list[dict]:
    """세션 목록(최신순) + 첫 user 메시지 발췌."""
    rows = conn.execute(
        """
        SELECT s.id, s.started_at, s.ended_at, s.title, s.weather, s.source_key,
               (SELECT COUNT(*) FROM diary_messages m WHERE m.session_id = s.id) AS msg_count,
               (SELECT m.content FROM diary_messages m
                  WHERE m.session_id = s.id AND m.role = 'user'
                  ORDER BY m.id ASC LIMIT 1) AS first_text
        FROM diary_sessions s
        ORDER BY s.ended_at DESC, s.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


# --- 회상 (hybrid 검색) ------------------------------------------


@dataclass
class _Cand:
    message_id: int
    session_id: int = 0
    rrf: float = 0.0
    semantic: float = 0.0
    fts: float = 0.0
    content: str = ""
    payload: dict = field(default_factory=dict)


def _fts_query(query: str) -> str:
    toks = [t for t in re.split(r"[\s,.:;!?　、。・]+", query.strip()) if t]
    if not toks:
        return ""
    return " OR ".join(f'"{t.replace(chr(34), "")}"' for t in toks)


def _semantic(query: str, top_k: int) -> list[_Cand]:
    try:
        from packages.indexer.embed_text import _embedder, _qdrant

        vec = _embedder().encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0].tolist()
        resp = _qdrant().query_points(
            collection_name=DIARY_COLLECTION, query=vec, limit=top_k, with_payload=True
        )
    except Exception as e:
        log.warning("diary 의미검색 실패(FTS 로 폴백): %s", e)
        return []
    out: list[_Cand] = []
    for hit in resp.points:
        p = hit.payload or {}
        mid = p.get("message_id")
        if mid is None:
            continue
        out.append(
            _Cand(
                message_id=int(mid),
                session_id=int(p.get("session_id") or 0),
                semantic=float(hit.score),
                content=str(p.get("content") or ""),
                payload=dict(p),
            )
        )
    return out


def _fts(conn: sqlite3.Connection, query: str, top_k: int) -> list[_Cand]:
    q = _fts_query(query)
    if not q:
        return []
    try:
        rows = conn.execute(
            "SELECT message_id, session_id, content, bm25(diary_messages_fts) AS b "
            "FROM diary_messages_fts WHERE diary_messages_fts MATCH ? "
            "ORDER BY b ASC LIMIT ?",
            (q, top_k),
        ).fetchall()
    except sqlite3.OperationalError as e:
        log.warning("diary FTS 실패: %s", e)
        return []
    out: list[_Cand] = []
    for r in rows:
        b = float(r["b"]) if r["b"] is not None else 0.0
        norm = 1.0 / (1.0 + max(b, 0.0) / _BM25_NORM)
        out.append(
            _Cand(
                message_id=int(r["message_id"]),
                session_id=int(r["session_id"] or 0),
                fts=norm,
                content=str(r["content"] or ""),
            )
        )
    return out


def _substr(conn: sqlite3.Connection, query: str, top_k: int) -> list[_Cand]:
    """토큰 부분문자열(LIKE) 매칭. trigram FTS 가 못 잡는 1~2글자 한글 키워드(똥·꿈·비)
    회상을 보장하고, Qdrant 없이도 키워드 회상이 동작하게 한다(최신순).
    """
    toks = [t for t in re.split(r"[\s,.:;!?　、。・]+", query.strip()) if len(t) >= 1]
    toks = [t for t in toks if len(t) <= 2][:4]  # 짧은 토큰만(긴 토큰은 FTS 담당)
    if not toks:
        return []
    where = " OR ".join("content LIKE ?" for _ in toks)
    params: list[Any] = [f"%{t}%" for t in toks]
    rows = conn.execute(
        f"SELECT id, session_id, content FROM diary_messages "
        f"WHERE role = 'user' AND ({where}) ORDER BY id DESC LIMIT ?",
        (*params, top_k),
    ).fetchall()
    return [
        _Cand(
            message_id=int(r["id"]),
            session_id=int(r["session_id"] or 0),
            fts=0.5,  # FTS 와 동급 신호로 취급(RRF 는 순위 기반)
            content=str(r["content"] or ""),
        )
        for r in rows
    ]


def _rrf_merge(*lists: list[_Cand]) -> list[_Cand]:
    by_id: dict[int, _Cand] = {}
    for lst in lists:
        for rank, c in enumerate(lst):
            ex = by_id.setdefault(c.message_id, _Cand(message_id=c.message_id))
            ex.rrf += 1.0 / (RRF_K + rank + 1)
            ex.semantic = max(ex.semantic, c.semantic)
            ex.fts = max(ex.fts, c.fts)
            if not ex.session_id:
                ex.session_id = c.session_id
            if not ex.content:
                ex.content = c.content
    merged = list(by_id.values())
    merged.sort(key=lambda x: x.rrf, reverse=True)
    return merged


def recall(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 5,
    exclude_message_id: int | None = None,
) -> list[dict[str, Any]]:
    """과거 일기/대화에서 query 와 관련된 메시지를 RRF 로 찾아 반환(점수순).

    반환: [{message_id, session_id, score, semantic, fts, content}]
    exclude_message_id: 방금 입력한 질문 자신을 회상에서 제외.
    """
    if not query.strip():
        return []
    pool = max(top_k * 4, 20)
    sem = _semantic(query, pool)
    fts = _fts(conn, query, pool)
    sub = _substr(conn, query, pool)
    merged = _rrf_merge(sem, fts, sub)
    out: list[dict[str, Any]] = []
    for c in merged:
        if exclude_message_id is not None and c.message_id == exclude_message_id:
            continue
        out.append(
            {
                "message_id": c.message_id,
                "session_id": c.session_id,
                "score": round(c.rrf, 6),
                "semantic": round(c.semantic, 4),
                "fts": round(c.fts, 4),
                "content": c.content,
            }
        )
        if len(out) >= top_k:
            break
    return out


def recall_sessions(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 5,
    exclude_message_id: int | None = None,
) -> list[dict[str, Any]]:
    """회상 결과를 '세션 단위'로 묶어 그때 대화 전체(transcript)를 함께 반환.

    같은 세션의 여러 메시지가 매칭되면 한 번만(최고 점수) 표시.
    반환: [{session_id, score, matched: [content...], transcript: {session, messages}}]
    """
    hits = recall(conn, query, top_k=top_k * 3, exclude_message_id=exclude_message_id)
    seen: dict[int, dict[str, Any]] = {}
    for h in hits:
        sid = h["session_id"]
        if not sid:
            continue
        if sid not in seen:
            tr = get_session_transcript(conn, sid)
            if not tr:
                continue
            seen[sid] = {"session_id": sid, "score": h["score"], "matched": [], "transcript": tr}
        seen[sid]["matched"].append(h["content"])
        if len(seen) >= top_k and sid in seen:
            pass
    out = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    return out[:top_k]
