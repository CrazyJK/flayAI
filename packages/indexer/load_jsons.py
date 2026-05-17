"""K:\\Crazy\\Info\\*.json → SQLite ETL.

AI_PLAN.md §6.1 [1] 단계.
- studio.json   → studios
- tagGroup.json → tag_groups
- tag.json      → tags          (group_id 추론: tagGroup 매칭 안되면 NULL)
- actress.json  → actresses + actress_aliases (build_actress_master 적용)
- video.json    → videos        (title→title_jp, desc→desc_jp, tags inline → tags + video_tags)
                + likes 시계열
주의:
- video.json 안의 tags 는 nested full record (id/name/group/description) 이므로
  여기서 tags 테이블에 upsert 한다 (tag.json 만으로 누락된 태그 보강).
- studio/release_date/actresses 는 video.json 에 없음 → 포스터 스캔 단계에서 채움.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from packages.indexer.actress_merge import build_actress_master
from packages.indexer.db import connect, init_schema
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _info_path(name: str) -> Path:
    cfg = load_config()
    return Path(cfg["data"]["info_dir"]) / name


# --- 개별 로더 ---------------------------------------------------------


def load_studios(conn) -> int:
    rows = _read_json(_info_path("studio.json"))
    conn.execute("DELETE FROM studios")
    conn.executemany(
        "INSERT OR REPLACE INTO studios(name, company, homepage) VALUES (?, ?, ?)",
        [(r["name"], r.get("company") or None, r.get("homepage") or None) for r in rows],
    )
    return len(rows)


def load_tag_groups(conn) -> int:
    rows = _read_json(_info_path("tagGroup.json"))
    conn.execute("DELETE FROM tag_groups")
    conn.executemany(
        "INSERT OR REPLACE INTO tag_groups(id, name, desc) VALUES (?, ?, ?)",
        [(r["id"], r.get("name"), r.get("desc")) for r in rows],
    )
    return len(rows)


def load_tags(conn) -> int:
    rows = _read_json(_info_path("tag.json"))
    conn.execute("DELETE FROM tags")
    # group 이 string id 거나 None
    conn.executemany(
        "INSERT OR REPLACE INTO tags(id, name, group_id, description) VALUES (?, ?, ?, ?)",
        [
            (r["id"], r.get("name"), r.get("group") or None, r.get("description") or None)
            for r in rows
        ],
    )
    return len(rows)


def load_actresses(conn) -> tuple[int, int]:
    """actresses + aliases. 반환 = (canonical 수, alias 수)."""
    rows = _read_json(_info_path("actress.json"))
    actresses, aliases = build_actress_master(rows)

    conn.execute("DELETE FROM actress_aliases")
    conn.execute("DELETE FROM actresses")

    conn.executemany(
        """INSERT INTO actresses(
            canonical_name, display_name, local_name, favorite,
            birth, body, height, debut, comment, last_modified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                a.canonical_name,
                a.display_name,
                a.local_name,
                int(a.favorite),
                a.birth,
                a.body,
                a.height,
                a.debut,
                a.comment,
                a.last_modified,
            )
            for a in actresses
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO actress_aliases(alias_norm, alias_raw, canonical_name) VALUES (?, ?, ?)",
        [(al.alias_norm, al.alias_raw, al.canonical_name) for al in aliases],
    )
    return len(actresses), len(aliases)


def load_videos(conn) -> tuple[int, int, int]:
    """videos + tags(보강) + video_tags + likes.
    반환 = (videos, video_tags, likes)."""
    rows = _read_json(_info_path("video.json"))

    # 기존 데이터 wipe (video_actresses 는 포스터 스캔 단계가 채우므로 여기서 비움)
    conn.execute("DELETE FROM likes")
    conn.execute("DELETE FROM video_tags")
    conn.execute("DELETE FROM video_actresses")
    conn.execute("DELETE FROM videos")

    video_rows: list[tuple] = []
    tag_upsert: dict[int, tuple] = {}
    vt_rows: list[tuple] = []
    like_rows: list[tuple] = []

    for r in rows:
        opus = r["opus"]
        likes = r.get("likes") or []
        video_rows.append(
            (
                opus,
                r.get("title") or None,  # title_jp
                r.get("desc") or None,  # desc_jp
                r.get("comment") or None,
                int(r.get("play") or 0),
                int(r.get("rank") or 0),
                int(r.get("lastPlay") or 0) or None,
                int(r.get("lastAccess") or 0) or None,
                int(r.get("lastModified") or 0) or None,
                len(likes),
            )
        )
        for tg in r.get("tags") or []:
            tid = tg.get("id")
            if tid is None:
                continue
            tag_upsert[tid] = (
                tid,
                tg.get("name"),
                tg.get("group") or None,
                tg.get("description") or None,
            )
            vt_rows.append((opus, tid))
        for ts in likes:
            like_rows.append((opus, int(ts)))

    conn.executemany(
        """INSERT INTO videos(
            opus, title_jp, desc_jp, comment, play, rank,
            last_play, last_access, last_modified, like_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        video_rows,
    )
    if tag_upsert:
        conn.executemany(
            "INSERT OR REPLACE INTO tags(id, name, group_id, description) VALUES (?, ?, ?, ?)",
            list(tag_upsert.values()),
        )
    if vt_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO video_tags(opus, tag_id) VALUES (?, ?)",
            vt_rows,
        )
    if like_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO likes(opus, ts) VALUES (?, ?)",
            like_rows,
        )
    return len(video_rows), len(vt_rows), len(like_rows)


# --- 오케스트레이션 ---------------------------------------------------


def run() -> dict[str, int]:
    """전체 ETL. 반환 = 통계 dict."""
    conn = connect()
    try:
        init_schema(conn)

        with conn:
            n_studios = load_studios(conn)
            n_groups = load_tag_groups(conn)
            n_tags = load_tags(conn)
            n_actr, n_alias = load_actresses(conn)
            n_vid, n_vt, n_likes = load_videos(conn)

        stats = {
            "studios": n_studios,
            "tag_groups": n_groups,
            "tags": n_tags,
            "actresses": n_actr,
            "actress_aliases": n_alias,
            "videos": n_vid,
            "video_tags": n_vt,
            "likes": n_likes,
        }
        update_stage("load_jsons", done=True, rows=n_vid, **stats)
        return stats
    finally:
        conn.close()
