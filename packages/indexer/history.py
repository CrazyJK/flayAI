"""K:\\Crazy\\Info\\history.csv → history 테이블.

AI_PLAN.md §6.1 [3].
포맷 (4 fields, comma+space):
  `YYYY-MM-DD HH:MM:SS, OPUS, ACTION, payload(나머지 전부)`
- payload 는 '[...]' 또는 '{json}' 임의 길이 → maxsplit=3 으로 안전 분리
- ts 는 epoch milliseconds 로 저장 (other 테이블과 통일)
- INSERT OR IGNORE (PK = ts,opus,action 중복 안전)
- 단일 패스, 누적 ts 최댓값 → state.history_csv.last_ts
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from packages.indexer.db import connect, init_schema
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

BATCH = 5000


@dataclass
class HistoryStats:
    rows_in_csv: int = 0
    inserted: int = 0
    last_ts: int = 0
    skipped: int = 0


def _parse_line(line: str) -> tuple[int, str, str, str] | None:
    """1줄 파싱. (ts_ms, opus, action, payload). 실패 시 None."""
    parts = line.rstrip("\r\n").split(", ", 3)
    if len(parts) < 3:
        return None
    ts_str = parts[0].strip()
    opus   = parts[1].strip()
    action = parts[2].strip()
    payload = parts[3] if len(parts) > 3 else ""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if not opus or not action:
        return None
    return int(dt.timestamp() * 1000), opus, action, payload


def run() -> HistoryStats:
    cfg = load_config()
    csv_path = Path(cfg["data"]["history_csv"])
    stats = HistoryStats()
    if not csv_path.exists():
        log.warning("history.csv not found: %s", csv_path)
        return stats

    conn = connect()
    init_schema(conn)
    batch: list[tuple] = []

    with csv_path.open("r", encoding="utf-8") as f, conn:
        # 기존 데이터 wipe (full rebuild)
        conn.execute("DELETE FROM history")
        for line in f:
            if not line.strip():
                continue
            stats.rows_in_csv += 1
            parsed = _parse_line(line)
            if parsed is None:
                stats.skipped += 1
                continue
            ts, opus, action, payload = parsed
            batch.append((ts, opus, action, payload))
            if ts > stats.last_ts:
                stats.last_ts = ts
            if len(batch) >= BATCH:
                cur = conn.executemany(
                    "INSERT OR IGNORE INTO history(ts, opus, action, payload) VALUES (?, ?, ?, ?)",
                    batch,
                )
                stats.inserted += cur.rowcount if cur.rowcount > 0 else 0
                batch.clear()
        if batch:
            cur = conn.executemany(
                "INSERT OR IGNORE INTO history(ts, opus, action, payload) VALUES (?, ?, ?, ?)",
                batch,
            )
            stats.inserted += cur.rowcount if cur.rowcount > 0 else 0

    update_stage(
        "history_csv",
        last_ts=stats.last_ts,
        rows_in_csv=stats.rows_in_csv,
        inserted=stats.inserted,
        skipped=stats.skipped,
    )
    conn.close()
    return stats
