"""자막 대상 목록 — 무자막 instance(생성 대상) · 자막 보유(resync 대상) 조회.

화면(=/subtitle)이 opus 를 일일이 입력하지 않고 목록에서 골라 신청하도록 데이터를 만든다.

- scan_status: instance 영상 옆 사이드카 자막(.srt/.smi) 존재 여부를 디스크에서 확인해
  subtitle_status 캐시에 적재(드라이브 온라인 필요). 목록 조회는 이 캐시에서 읽어 빠르다.
- list_candidates: 무자막 instance(생성 대상). videos 메타 + 정렬(인기/재생/최신).
- list_subbed: 자막 보유 영상(resync 대상). subtitle_corpus(TM 쌍수) + 최근 resync 결과.

무거운 모듈(core→whisper)은 scan 에서만 지연 임포트한다 — 목록 조회는 순수 SQL.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from . import db

log = logging.getLogger(__name__)

_SORTS = {
    "like": "v.like_count DESC, v.rank DESC, p.opus",
    "play": "v.play DESC, p.opus",
    "recent": "v.release_year DESC, v.release_month DESC, p.opus",
    "opus": "p.opus",
}


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    db.init_schema(conn)  # subtitle_jobs/transcripts/subtitle_status (멱등)


# --- 스캔(디스크) -------------------------------------------------


def scan_status(conn: sqlite3.Connection, *, limit: int | None = None) -> dict[str, int]:
    """instance 영상별 사이드카 자막 유무를 디스크에서 확인해 subtitle_status 갱신.

    영상 파일이 안 보이면(드라이브 오프라인) 그 행은 건드리지 않는다(기존 캐시 유지).
    반환: {seen, has_sub, none, offline}.
    """
    from pathlib import Path

    from . import core  # 지연 임포트(whisper 등 무거운 의존)

    ensure_schema(conn)
    rows = conn.execute(
        "SELECT opus, video_path FROM posters "
        "WHERE video_path IS NOT NULL AND length(video_path) > 0 ORDER BY opus"
    ).fetchall()
    if limit:
        rows = rows[:limit]

    seen = has = none = offline = 0
    now = int(time.time())
    pending: list[tuple] = []
    for r in rows:
        vp = Path(r["video_path"])
        if not vp.exists():
            offline += 1
            continue
        sub = core.sibling_sub(vp)
        seen += 1
        if sub is not None:
            has += 1
            pending.append((r["opus"], 1, sub.suffix.lower().lstrip("."), str(sub), 1, now))
        else:
            none += 1
            pending.append((r["opus"], 0, None, None, 1, now))
        if len(pending) >= 200:
            _flush(conn, pending)
            pending = []
    if pending:
        _flush(conn, pending)
    log.info("subtitle scan: seen=%d has=%d none=%d offline=%d", seen, has, none, offline)
    return {"seen": seen, "has_sub": has, "none": none, "offline": offline}


def _flush(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO subtitle_status(opus, has_sub, fmt, sub_path, video_seen, "
            "checked_at) VALUES (?,?,?,?,?,?)",
            rows,
        )


def last_scan_at(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MAX(checked_at) AS t FROM subtitle_status").fetchone()
    return int(row["t"]) if row and row["t"] is not None else None


# --- 무자막 목록(생성 대상) ---------------------------------------


def _candidate_where(conn: sqlite3.Connection, q: str | None) -> tuple[str, list]:
    where = ["p.video_path IS NOT NULL", "length(p.video_path) > 0", "COALESCE(s.has_sub, 0) = 0"]
    args: list[Any] = []
    if _has_table(conn, "subtitle_corpus"):
        where.append("c.opus IS NULL")  # 팬자막 보유분 제외(스캔 전이라도)
    if q:
        where.append("(p.opus LIKE ? OR v.title_ko LIKE ? OR v.title_jp LIKE ? OR v.studio LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like, like]
    return " AND ".join(where), args


def _candidate_from(conn: sqlite3.Connection) -> str:
    corpus_join = (
        " LEFT JOIN subtitle_corpus c ON c.opus = p.opus" if _has_table(conn, "subtitle_corpus") else ""
    )
    return (
        "FROM posters p JOIN videos v ON v.opus = p.opus "
        "LEFT JOIN subtitle_status s ON s.opus = p.opus" + corpus_join
    )


def list_candidates(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    sort: str = "like",
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    """무자막 instance 목록(생성 대상). 반환: {total, items}."""
    ensure_schema(conn)
    where_sql, args = _candidate_where(conn, q)
    frm = _candidate_from(conn)
    total = conn.execute(f"SELECT COUNT(*) {frm} WHERE {where_sql}", args).fetchone()[0]
    order = _SORTS.get(sort, _SORTS["like"])
    rows = conn.execute(
        "SELECT p.opus, v.title_ko, v.title_jp, v.studio, v.release_year, v.play, v.like_count, "
        "(p.caption IS NOT NULL AND length(p.caption) > 0) AS has_caption "
        f"{frm} WHERE {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
        (*args, int(limit), int(offset)),
    ).fetchall()
    items = [
        {
            "opus": r["opus"],
            "title": r["title_ko"] or r["title_jp"] or "",
            "studio": r["studio"],
            "year": r["release_year"],
            "play": r["play"],
            "like_count": r["like_count"],
            "has_caption": bool(r["has_caption"]),
        }
        for r in rows
    ]
    return {"total": int(total), "items": items}


def all_candidate_opuses(conn: sqlite3.Connection, q: str | None = None) -> list[str]:
    """무자막 instance 전체 opus(일괄 신청용)."""
    ensure_schema(conn)
    where_sql, args = _candidate_where(conn, q)
    frm = _candidate_from(conn)
    rows = conn.execute(f"SELECT p.opus {frm} WHERE {where_sql} ORDER BY p.opus", args).fetchall()
    return [r["opus"] for r in rows]


# --- 자막 보유 목록(resync 대상) ----------------------------------


def list_subbed(
    conn: sqlite3.Connection,
    *,
    only_reverted: bool = False,
    q: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    """자막 보유 영상(resync 대상) — subtitle_corpus + 최근 resync 잡 결과. 반환: {total, items}."""
    ensure_schema(conn)
    if not _has_table(conn, "subtitle_corpus"):
        return {"total": 0, "items": []}
    where = ["1=1"]
    args: list[Any] = []
    if only_reverted:
        where.append("j.rstatus = 'skipped'")
    if q:
        where.append("(c.opus LIKE ? OR v.title_ko LIKE ? OR v.title_jp LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like]
    where_sql = " AND ".join(where)
    frm = (
        "FROM subtitle_corpus c LEFT JOIN videos v ON v.opus = c.opus "
        "LEFT JOIN (SELECT opus, status AS rstatus, note AS rnote, finished_at, "
        "ROW_NUMBER() OVER (PARTITION BY opus ORDER BY id DESC) AS rn "
        "FROM subtitle_jobs WHERE task IN ('resync','both')) j ON j.opus = c.opus AND j.rn = 1"
    )
    total = conn.execute(f"SELECT COUNT(*) {frm} WHERE {where_sql}", args).fetchone()[0]
    rows = conn.execute(
        "SELECT c.opus, c.srt_path, c.n_pairs, v.title_ko, v.title_jp, "
        "j.rstatus, j.rnote, j.finished_at "
        f"{frm} WHERE {where_sql} ORDER BY (j.rstatus IS NULL), j.finished_at DESC, c.opus "
        "LIMIT ? OFFSET ?",
        (*args, int(limit), int(offset)),
    ).fetchall()
    items = [
        {
            "opus": r["opus"],
            "title": r["title_ko"] or r["title_jp"] or "",
            "fmt": "smi" if (r["srt_path"] or "").lower().endswith(".smi") else "srt",
            "n_pairs": r["n_pairs"],
            "resync_status": r["rstatus"],  # done | skipped | None(미시도)
            "resync_note": r["rnote"],
        }
        for r in rows
    ]
    return {"total": int(total), "items": items}


def all_subbed_opuses(conn: sqlite3.Connection, *, only_reverted: bool = False) -> list[str]:
    ensure_schema(conn)
    if not _has_table(conn, "subtitle_corpus"):
        return []
    if only_reverted:
        rows = conn.execute(
            "SELECT c.opus FROM subtitle_corpus c LEFT JOIN (SELECT opus, status, "
            "ROW_NUMBER() OVER (PARTITION BY opus ORDER BY id DESC) rn FROM subtitle_jobs "
            "WHERE task IN ('resync','both')) j ON j.opus=c.opus AND j.rn=1 "
            "WHERE j.status='skipped' ORDER BY c.opus"
        ).fetchall()
    else:
        rows = conn.execute("SELECT opus FROM subtitle_corpus ORDER BY opus").fetchall()
    return [r["opus"] for r in rows]
