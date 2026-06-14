"""자막 큐/전사캐시 스키마 + CRUD. 인덱서 DB(data/sqlite/flay.db)를 공유한다.

- subtitle_jobs: 외부 신청 큐 + 처리 상태(야간 드레인이 소비).
- transcripts: Whisper 전사 캐시(opus+model 시그니처). resync/재번역에서 재사용해
  비싼 Whisper 재실행을 피한다.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

SUBTITLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS subtitle_jobs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  opus         TEXT NOT NULL,
  task         TEXT NOT NULL DEFAULT 'generate',  -- generate | resync | both
  status       TEXT NOT NULL DEFAULT 'queued',    -- queued|running|done|failed|skipped|canceled
  stage        TEXT,
  progress     INTEGER DEFAULT 0,
  requested_at INTEGER,
  started_at   INTEGER,
  finished_at  INTEGER,
  result_path  TEXT,
  error        TEXT,
  note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_subjobs_status ON subtitle_jobs(status, requested_at);
CREATE INDEX IF NOT EXISTS idx_subjobs_opus   ON subtitle_jobs(opus);

CREATE TABLE IF NOT EXISTS transcripts (
  opus         TEXT NOT NULL,
  model        TEXT NOT NULL,
  video_mtime  INTEGER,
  language     TEXT,
  segments     TEXT,        -- JSON: [{"start":float,"end":float,"text":str}]
  created_at   INTEGER,
  PRIMARY KEY (opus, model)
);
"""

_ACTIVE = ("queued", "running")


def init_schema(conn: sqlite3.Connection) -> None:
    """자막 테이블 멱등 생성."""
    conn.executescript(SUBTITLE_SCHEMA)
    conn.commit()


# --- 큐 -----------------------------------------------------------


def enqueue(conn: sqlite3.Connection, opus: str, task: str = "generate") -> tuple[int, bool]:
    """신청 적재. 같은 (opus, task) 가 이미 대기/실행 중이면 그 id 재사용.

    반환: (job_id, created) — created=False 면 기존 잡 재사용.
    """
    with conn:
        row = conn.execute(
            "SELECT id FROM subtitle_jobs WHERE opus=? AND task=? AND status IN (?,?) "
            "ORDER BY id LIMIT 1",
            (opus, task, *_ACTIVE),
        ).fetchone()
        if row:
            return int(row["id"]), False
        cur = conn.execute(
            "INSERT INTO subtitle_jobs(opus, task, status, requested_at) VALUES (?,?, 'queued', ?)",
            (opus, task, int(time.time())),
        )
        return int(cur.lastrowid), True


def claim_next(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """가장 오래된 queued 잡을 running 으로 전환하고 dict 로 반환. 없으면 None."""
    with conn:
        row = conn.execute(
            "SELECT * FROM subtitle_jobs WHERE status='queued' ORDER BY requested_at, id LIMIT 1"
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE subtitle_jobs SET status='running', started_at=?, stage='start', progress=1 "
            "WHERE id=?",
            (int(time.time()), row["id"]),
        )
    job = dict(row)
    job["status"] = "running"
    return job


def set_progress(
    conn: sqlite3.Connection, job_id: int, *, stage: str | None = None, progress: int | None = None
) -> None:
    sets, args = [], []
    if stage is not None:
        sets.append("stage=?")
        args.append(stage)
    if progress is not None:
        sets.append("progress=?")
        args.append(int(progress))
    if not sets:
        return
    args.append(job_id)
    with conn:
        conn.execute(f"UPDATE subtitle_jobs SET {', '.join(sets)} WHERE id=?", args)


def finish(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    *,
    result_path: str | None = None,
    error: str | None = None,
    note: str | None = None,
) -> None:
    with conn:
        conn.execute(
            "UPDATE subtitle_jobs SET status=?, finished_at=?, progress=?, result_path=?, "
            "error=?, note=? WHERE id=?",
            (
                status,
                int(time.time()),
                100 if status in ("done", "skipped") else None,
                result_path,
                (error or "")[:500] or None,
                note,
                job_id,
            ),
        )


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM subtitle_jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM subtitle_jobs ORDER BY requested_at DESC, id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_job(conn: sqlite3.Connection, job_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM subtitle_jobs WHERE id=?", (job_id,))
    return cur.rowcount > 0


# --- 전사 캐시 ----------------------------------------------------


def get_transcript(conn: sqlite3.Connection, opus: str, model: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM transcripts WHERE opus=? AND model=?", (opus, model)
    ).fetchone()
    if not row:
        return None
    return {
        "opus": row["opus"],
        "model": row["model"],
        "video_mtime": row["video_mtime"],
        "language": row["language"],
        "segments": json.loads(row["segments"] or "[]"),
    }


def put_transcript(
    conn: sqlite3.Connection,
    opus: str,
    model: str,
    video_mtime: int,
    language: str | None,
    segments: list[dict[str, Any]],
) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO transcripts(opus, model, video_mtime, language, segments, "
            "created_at) VALUES (?,?,?,?,?,?)",
            (opus, model, video_mtime, language, json.dumps(segments, ensure_ascii=False),
             int(time.time())),
        )
