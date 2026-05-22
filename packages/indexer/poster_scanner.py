"""포스터 스캐너 + instance/archive 분류.

AI_PLAN.md §5.6, §6.1 [2].
- config.data.poster_roots 재귀 탐색
- 파일명 파싱 → posters / videos.studio,release_*,has_poster,kind,title_ko(비어있을 때만) / video_actresses
- archive_root 하위 = kind=archive
  외부 + same-stem 영상파일 존재 = kind=instance, video_path=설정
  외부 + 영상 없음                 = kind=instance, video_path=NULL
- 매칭 실패 → unmatched_posters.log 기록
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from packages.indexer.actress_merge import normalize_actress
from packages.indexer.db import connect, init_schema
from packages.indexer.poster_parser import parse_filename
from packages.indexer.state import update_stage
from packages.settings import load_config, repo_path

log = logging.getLogger(__name__)

UNMATCHED_LOG = "logs/unmatched_posters.log"


@dataclass
class ScanStats:
    scanned: int = 0
    matched: int = 0
    unmatched: int = 0
    instance: int = 0
    archive: int = 0
    actress_links: int = 0


def classify_poster(
    poster_path: Path,
    archive_root: Path,
    video_exts: set[str],
) -> tuple[str, Path | None]:
    """반환: (kind, video_path or None)."""
    try:
        resolved = poster_path.resolve()
    except OSError:
        resolved = poster_path
    # archive 판정: archive_root 가 부모 체인에 있으면 archive
    try:
        archive_root_resolved = archive_root.resolve()
    except OSError:
        archive_root_resolved = archive_root
    parents = list(resolved.parents)
    if archive_root_resolved in parents or resolved == archive_root_resolved:
        return "archive", None

    # instance: same-stem 영상 파일 탐색
    for ext in video_exts:
        cand = poster_path.with_suffix(ext)
        if cand.exists():
            return "instance", cand
    return "instance", None


def _load_alias_map(conn: sqlite3.Connection) -> dict[str, str]:
    """SQLite actress_aliases → {alias_norm: canonical_name}."""
    cur = conn.execute("SELECT alias_norm, canonical_name FROM actress_aliases")
    return {row["alias_norm"]: row["canonical_name"] for row in cur}


def _resolve_actresses(raw: str, alias_map: dict[str, str]) -> list[str]:
    """공백 split → 단일/2단어/3단어 매칭 시도 (greedy left-to-right).

    파일명은 'Akari Hoshino Ren Serizawa' 처럼 공백으로 합쳐져 있으므로
    토큰을 1~3개씩 묶어 alias 사전에서 가장 긴 매칭 선택.
    """
    tokens = [t for t in (raw or "").split() if t.strip()]
    out: list[str] = []
    i = 0
    while i < len(tokens):
        matched_canonical: str | None = None
        matched_len = 0
        for span in (3, 2, 1):
            if i + span > len(tokens):
                continue
            cand = " ".join(tokens[i : i + span])
            canonical = alias_map.get(normalize_actress(cand))
            if canonical:
                matched_canonical = canonical
                matched_len = span
                break
        if matched_canonical:
            if matched_canonical not in out:
                out.append(matched_canonical)
            i += matched_len
        else:
            # 미매칭 단일 토큰은 normalize 해서 그대로 link (canonical 없음)
            # 이 경우 actresses 테이블엔 없는 신규 → SKIP. 로그만.
            log.debug("unresolved actress token: %r", tokens[i])
            i += 1
    return out


def run() -> ScanStats:
    cfg = load_config()
    poster_exts = {f".{e.lower()}" for e in cfg["data"]["poster_extensions"]}
    video_exts = {f".{e.lower()}" for e in cfg["data"]["video_extensions"]}
    archive_root = Path(cfg["data"]["archive_root"])
    roots = [Path(p) for p in cfg["data"]["poster_roots"]]
    # archive_root 도 스캔 대상에 포함 (이미 poster_roots 안에 있으면 dedupe)
    if not any(Path(r).resolve() == archive_root.resolve() for r in roots if Path(r).exists()):
        roots.append(archive_root)

    unmatched_path = repo_path(UNMATCHED_LOG)
    unmatched_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect()
    init_schema(conn)
    alias_map = _load_alias_map(conn)

    stats = ScanStats()

    # 기존 포스터/연결 wipe (full re-scan)
    with conn:
        conn.execute("DELETE FROM posters")
        conn.execute("DELETE FROM video_actresses")
        conn.execute(
            "UPDATE videos SET has_poster = 0, studio = NULL, "
            "release_date = NULL, release_year = NULL, release_month = NULL, kind = NULL"
        )

    poster_rows: list[tuple] = []
    va_rows: list[tuple] = []
    video_updates: dict[str, tuple] = {}  # opus -> (studio, date, year, month, kind)

    with unmatched_path.open("w", encoding="utf-8") as ulog:
        for root in roots:
            if not root.exists():
                log.warning("poster root not found, skip: %s", root)
                continue
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in poster_exts:
                    continue
                stats.scanned += 1
                parsed = parse_filename(p.name)
                if parsed is None:
                    stats.unmatched += 1
                    ulog.write(f"{p}\n")
                    continue
                stats.matched += 1
                kind, video_path = classify_poster(p, archive_root, video_exts)
                if kind == "instance":
                    stats.instance += 1
                else:
                    stats.archive += 1

                try:
                    st = p.stat()
                    size, mtime = st.st_size, int(st.st_mtime * 1000)
                except OSError:
                    size, mtime = 0, 0

                poster_rows.append(
                    (
                        parsed.opus,
                        str(p),
                        p.suffix.lower().lstrip("."),
                        size,
                        mtime,
                        kind,
                        str(video_path) if video_path else None,
                    )
                )
                video_updates[parsed.opus] = (
                    parsed.studio,
                    parsed.release_date,
                    parsed.release_year,
                    parsed.release_month,
                    kind,
                    parsed.title or None,  # 파일명의 한글 제목 (빈 값이면 None)
                )
                # 배우 링크
                for canonical in _resolve_actresses(parsed.actresses_raw, alias_map):
                    va_rows.append((parsed.opus, canonical))

    with conn:
        # posters: opus PK 충돌 시 (같은 opus 가 여러 폴더에 있는 경우) 마지막 우선
        conn.executemany(
            """INSERT OR REPLACE INTO posters(
                 opus, path, ext, size, mtime, kind, video_path
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            poster_rows,
        )
        if va_rows:
            conn.executemany(
                "INSERT OR IGNORE INTO video_actresses(opus, canonical_name) VALUES (?, ?)",
                va_rows,
            )
            stats.actress_links = len(va_rows)

        # videos 갱신: video.json 에 없는 opus 는 INSERT 로 stub 생성.
        # title_ko 는 비어 있을 때만 파일명 제목으로 백필 — 기존 번역은 보존한다
        # (COALESCE(NULLIF(기존,''), 파일명제목)).
        for opus, (studio, rdate, year, month, kind, title) in video_updates.items():
            conn.execute(
                """INSERT INTO videos(opus, studio, release_date, release_year, release_month,
                                       has_poster, kind, title_ko)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT(opus) DO UPDATE SET
                     studio=excluded.studio,
                     release_date=excluded.release_date,
                     release_year=excluded.release_year,
                     release_month=excluded.release_month,
                     has_poster=1,
                     kind=excluded.kind,
                     title_ko=COALESCE(NULLIF(videos.title_ko, ''), excluded.title_ko)""",
                (opus, studio, rdate, year, month, kind, title),
            )

    update_stage(
        "scan_posters",
        done=True,
        scanned=stats.scanned,
        matched=stats.matched,
        unmatched=stats.unmatched,
        instance=stats.instance,
        archive=stats.archive,
        actress_links=stats.actress_links,
    )
    conn.close()
    return stats
