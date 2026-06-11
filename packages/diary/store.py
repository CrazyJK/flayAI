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


def reset_diary(conn: sqlite3.Connection) -> None:
    """모든 일기 데이터 삭제(SQLite 테이블 + Qdrant 컬렉션 재생성). 재임포트용."""
    conn.executescript(
        "DELETE FROM diary_messages_fts; DELETE FROM diary_messages; DELETE FROM diary_sessions;"
    )
    conn.commit()
    try:
        from packages.diary.schema import DIARY_COLLECTION, ensure_diary_collection
        from packages.indexer.embed_text import _qdrant

        qc = _qdrant()
        try:
            qc.delete_collection(DIARY_COLLECTION)
        except Exception as e:
            log.debug("diary 컬렉션 삭제 스킵: %s", e)
        ensure_diary_collection(qc)
    except Exception as e:
        log.warning("Qdrant diary 컬렉션 초기화 실패: %s", e)


def get_image_captions(conn: sqlite3.Connection, assets: list[str], sig: str) -> dict[str, str]:
    """첨부 이미지 캡션 캐시 조회: {asset: caption}. sig 가 일치하는 것만(설정 바뀌면 미스)."""
    if not assets:
        return {}
    ph = ",".join("?" * len(assets))
    return {
        r["asset"]: r["caption"]
        for r in conn.execute(
            f"SELECT asset, caption FROM diary_image_captions WHERE sig = ? AND asset IN ({ph})",
            (sig, *assets),
        )
    }


def save_image_caption(conn: sqlite3.Connection, asset: str, caption: str, sig: str) -> None:
    conn.execute(
        "INSERT INTO diary_image_captions(asset, caption, sig) VALUES(?,?,?) "
        "ON CONFLICT(asset) DO UPDATE SET caption = excluded.caption, sig = excluded.sig",
        (asset, caption, sig),
    )
    conn.commit()


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
    index: bool = True,
) -> int:
    """메시지 저장. user 발화이고 index=True 면 FTS 인덱싱 + (embed 시) 임베딩·Qdrant upsert.

    - index=False: 저장하되 회상 '대상'에서 제외. (회상 질문은 라우터가 아예 저장하지
      않으므로 이 플래그는 그 외에 색인만 빼고 싶은 경우·테스트용.)
    - embed=False: 임베딩만 생략(테스트/오프라인 — FTS 경로만).
    """
    ts = created_at or _now_iso()
    indexable = role == "user" and index and bool(content.strip())
    cur = conn.execute(
        "INSERT INTO diary_messages(session_id, role, content, raw_html, created_at, source, indexed) "
        "VALUES(?,?,?,?,?,?,?)",
        (session_id, role, content, raw_html, ts, source, 1 if indexable else 0),
    )
    msg_id = int(cur.lastrowid)
    conn.execute(
        "UPDATE diary_sessions SET ended_at = ? WHERE id = ?",
        (ts, session_id),
    )
    if indexable:
        conn.execute(
            "INSERT INTO diary_messages_fts(content, message_id, session_id) VALUES(?,?,?)",
            (content, msg_id, session_id),
        )
    conn.commit()
    if indexable and embed:
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
    """짧은 한글 키워드 부분문자열(LIKE) 매칭. trigram FTS 가 못 잡는 1글자(똥·꿈·비)와
    질의 전체가 짧은 2글자(온천)만 대상 — 긴 질의의 2글자 토큰(회사·행사·여행)은 노이즈라
    제외. indexed=1(회상 대상) 메시지만. Qdrant 없이도 키워드 회상이 동작하게 한다.
    """
    q = query.strip()
    toks = [t for t in re.split(r"[\s,.:;!?　、。・]+", q) if t]
    # 단일 글자 토큰, 또는 질의 전체가 그 2글자일 때만
    keep = [t for t in toks if len(t) == 1 or (len(t) == 2 and t == q)][:4]
    if not keep:
        return []
    where = " OR ".join("content LIKE ?" for _ in keep)
    params: list[Any] = [f"%{t}%" for t in keep]
    rows = conn.execute(
        f"SELECT id, session_id, content FROM diary_messages "
        f"WHERE role = 'user' AND indexed = 1 AND ({where}) ORDER BY id DESC LIMIT ?",
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
    # 관련도 컷오프: 실제 키워드 매칭(fts>0=FTS/substr) 이 있거나, 의미 유사도가 임계 이상일 때만.
    # 의미검색은 무관해도 최근접을 항상 돌려주므로(낮은 점수로 채움) 이 컷이 없으면 무관한
    # 일기가 top_k 까지 채워진다.
    sem_min = float(load_config().get("diary", {}).get("recall_min_semantic", 0.5))
    out: list[dict[str, Any]] = []
    for c in merged:
        if exclude_message_id is not None and c.message_id == exclude_message_id:
            continue
        if c.fts <= 0 and c.semantic < sem_min:
            continue  # 키워드 매칭 없고 의미도 약함 → 무관
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


def _photo_session_ids(conn: sqlite3.Connection, session_ids: list[int]) -> set[int]:
    """주어진 세션 중 사진 첨부(<img> 가 든 raw_html) 메시지가 있는 세션 집합."""
    if not session_ids:
        return set()
    ph = ",".join("?" * len(session_ids))
    rows = conn.execute(
        f"SELECT DISTINCT session_id FROM diary_messages "
        f"WHERE session_id IN ({ph}) AND raw_html LIKE '%<img%'",
        session_ids,
    )
    return {int(r["session_id"]) for r in rows}


# 세션의 대표 날짜: 레거시 일기는 source_key(YYYY-MM-DD), 라이브 챗은 started_at 의 날짜부.
_SESSION_DATE_SQL = "COALESCE(s.source_key, substr(s.started_at, 1, 10))"


def _session_date(entry: dict[str, Any]) -> str:
    meta = entry["transcript"]["session"]
    return meta.get("source_key") or (meta.get("started_at") or "")[:10]


def _list_sessions_meta(
    conn: sqlite3.Connection,
    top_k: int,
    has_image: bool,
    date_from: str | None,
    date_to: str | None,
    date_like: str | None,
) -> list[dict[str, Any]]:
    """텍스트 검색 없이 메타 조건만으로 세션을 최근순 top_k 선별(표시는 시간순)."""
    where = [
        "EXISTS (SELECT 1 FROM diary_messages m "
        "WHERE m.session_id = s.id AND m.role = 'user' AND m.indexed = 1)"
    ]
    params: list[Any] = []
    if date_from:
        where.append(f"{_SESSION_DATE_SQL} BETWEEN ? AND ?")
        params += [date_from, date_to or date_from]
    if date_like:
        where.append(f"{_SESSION_DATE_SQL} LIKE ?")
        params.append(date_like)
    if has_image:
        where.append(
            "EXISTS (SELECT 1 FROM diary_messages mi "
            "WHERE mi.session_id = s.id AND mi.raw_html LIKE '%<img%')"
        )
    rows = conn.execute(
        f"SELECT s.id FROM diary_sessions s WHERE {' AND '.join(where)} "
        f"ORDER BY {_SESSION_DATE_SQL} DESC, s.id DESC LIMIT ?",
        (*params, top_k),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        tr = get_session_transcript(conn, int(r["id"]))
        if not tr:
            continue
        # matched 에 첫 user 발화를 채운다 — 비워두면 LLM 답변 컨텍스트([찾은 기록])가
        # 날짜만 있는 빈 줄이 되어 모델이 내용을 지어낸다(환각).
        first_user = next(
            (
                str(m.get("content") or "")
                for m in tr["messages"]
                if m.get("role") == "user" and str(m.get("content") or "").strip()
            ),
            "",
        )
        out.append(
            {
                "session_id": int(r["id"]),
                "score": 0.0,
                "matched": [first_user] if first_user else [],
                "transcript": tr,
            }
        )
    out.sort(key=lambda x: (x["transcript"]["session"].get("started_at") or ""))
    return out


def recall_sessions(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 5,
    exclude_message_id: int | None = None,
    has_image: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    date_like: str | None = None,
    recent: bool = False,
) -> list[dict[str, Any]]:
    """회상 결과를 '세션 단위'로 묶어 그때 대화 전체(transcript)를 함께 반환.

    같은 세션의 여러 메시지가 매칭되면 한 번만(최고 점수) 표시.
    선택은 관련도(top_k) 로 하되, 일기이므로 **표시는 시간순(오래된→최근)** 으로 정렬한다.
    메타 조건(chat 의 _extract_* 가 질의에서 분리):
    - has_image: 사진 첨부(<img>) 세션만.
    - date_from/date_to: 세션 날짜 범위. date_like: 연도 없는 날짜('____-06-09', _=한 글자).
    - recent: '최근/요즘' — 주제 없이 최근순 나열을 허용.
    주제(query)가 비면 텍스트 검색 없이 조건만으로 최근순 top_k 를 반환.
    반환: [{session_id, score, matched: [content...], transcript: {session, messages}}]
    """
    if not query.strip() and (has_image or date_from or date_like or recent):
        return _list_sessions_meta(conn, top_k, has_image, date_from, date_to, date_like)

    hits = recall(conn, query, top_k=top_k * 3, exclude_message_id=exclude_message_id)
    if has_image and hits:
        with_img = _photo_session_ids(conn, sorted({h["session_id"] for h in hits if h["session_id"]}))
        hits = [h for h in hits if h["session_id"] in with_img]
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
    entries = list(seen.values())
    # 주제 검색 결과에도 날짜 조건 적용(세션 대표 날짜 기준)
    if date_from:
        hi = date_to or date_from
        entries = [e for e in entries if date_from <= _session_date(e) <= hi]
    if date_like:
        pat = re.compile(date_like.replace("_", "."))
        entries = [e for e in entries if pat.fullmatch(_session_date(e))]
    # 관련도 상위 top_k 선별 → 시간순(세션 시작 시각 오름차순)으로 표시
    top = sorted(entries, key=lambda x: x["score"], reverse=True)[:top_k]
    top.sort(key=lambda x: (x["transcript"]["session"].get("started_at") or ""))
    return top
