"""Orphan 정리 — SQLite/Qdrant 에 남은 고아 row/point 삭제.

탐지 대상:
1. posters.path 가 실제 파일 없음 → posters row 삭제 + 관련 Qdrant 포인트 삭제
2. video.json 원본에 opus 가 없음 → videos row 삭제
   + 의존 row(video_actresses, video_tags, posters, poster_faces, history, likes)
   + Qdrant 4 컬렉션 포인트 삭제
3. Qdrant 에는 있는데 SQLite videos 에 없는 opus → Qdrant 포인트 삭제

기본은 dry-run. --apply 로 실제 삭제.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _qdrant
from packages.indexer.sync_payload import COLLECTIONS, _scroll_all
from packages.settings import load_config

log = logging.getLogger(__name__)


def _missing_poster_files(conn) -> list[str]:
    """파일이 실제로 사라진 posters.opus 목록."""
    out = []
    for r in conn.execute("SELECT opus, path FROM posters WHERE path IS NOT NULL"):
        if not Path(r["path"]).exists():
            out.append(r["opus"])
    return out


def _missing_video_jsons(conn, info_dir: Path) -> list[str]:
    """video.json 원본에서 사라진 videos.opus 목록."""
    vj = info_dir / "video.json"
    if not vj.exists():
        log.warning("video.json 없음: %s — skip", vj)
        return []
    with vj.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    src_opus = {(r.get("opus") or "").upper() for r in rows if r.get("opus")}
    out = []
    for r in conn.execute("SELECT opus FROM videos"):
        opus = r["opus"]
        if opus and opus.upper() not in src_opus:
            out.append(opus)
    return out


def _qdrant_opus_set(qc, collection: str) -> set[str]:
    seen = set()
    try:
        for _pid, opus, _k, _p in _scroll_all(qc, collection):
            if opus:
                seen.add(opus)
    except Exception as e:
        log.warning("scroll %s failed: %s", collection, e)
    return seen


def _delete_qdrant_opus(qc, collection: str, opuses: list[str]) -> int:
    if not opuses:
        return 0
    try:
        qc.delete(
            collection_name=collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(key="opus", match=qm.MatchAny(any=list(opuses))),
                    ]
                )
            ),
            wait=False,
        )
        return len(opuses)
    except Exception as e:
        log.warning("delete %s failed: %s", collection, e)
        return 0


def run(apply: bool = False) -> dict:
    cfg = load_config()
    info_dir = Path(cfg["data"]["info_dir"])
    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    t = time.time()

    # 1) 파일 사라진 포스터
    missing_posters = _missing_poster_files(conn)
    log.info("missing poster files: %d", len(missing_posters))

    # 2) JSON 사라진 영상
    missing_videos = _missing_video_jsons(conn, info_dir)
    log.info("missing video JSONs: %d", len(missing_videos))

    # 3) Qdrant 만 있는 opus (SQLite videos 에 없음)
    sqlite_opus = {r["opus"] for r in conn.execute("SELECT opus FROM videos")}
    qdrant_orphans: dict[str, list[str]] = {}
    for name, _multi in COLLECTIONS:
        qopus = _qdrant_opus_set(qc, name)
        orphan = sorted(qopus - sqlite_opus)
        qdrant_orphans[name] = orphan
        log.info("qdrant[%s] orphan opus: %d", name, len(orphan))

    summary = {
        "missing_poster_files": len(missing_posters),
        "missing_video_jsons": len(missing_videos),
        "qdrant_orphans": {k: len(v) for k, v in qdrant_orphans.items()},
        "applied": apply,
    }

    if not apply:
        log.warning("dry-run: 실제 삭제 안 함. --apply 추가 시 적용.")
        summary["elapsed_sec"] = round(time.time() - t, 2)
        conn.close()
        return summary

    # ---- 실제 적용 ----
    deleted_rows = 0

    # 포스터 정리
    if missing_posters:
        ph = ",".join("?" * len(missing_posters))
        conn.execute(f"DELETE FROM posters       WHERE opus IN ({ph})", missing_posters)
        conn.execute(f"DELETE FROM poster_faces  WHERE poster_opus IN ({ph})", missing_posters)
        deleted_rows += len(missing_posters)
        for name, _ in COLLECTIONS:
            _delete_qdrant_opus(qc, name, missing_posters)

    # 비디오 정리 (의존 row 모두)
    if missing_videos:
        ph = ",".join("?" * len(missing_videos))
        for tbl, col in [
            ("video_actresses", "opus"),
            ("video_tags", "opus"),
            ("posters", "opus"),
            ("poster_faces", "poster_opus"),
            ("history", "opus"),
            ("likes", "opus"),
            ("videos", "opus"),
        ]:
            conn.execute(f"DELETE FROM {tbl} WHERE {col} IN ({ph})", missing_videos)
        deleted_rows += len(missing_videos)
        for name, _ in COLLECTIONS:
            _delete_qdrant_opus(qc, name, missing_videos)

    # Qdrant 단독 고아
    for name, opuses in qdrant_orphans.items():
        _delete_qdrant_opus(qc, name, opuses)

    conn.commit()
    conn.close()
    summary["deleted_sqlite_rows"] = deleted_rows
    summary["elapsed_sec"] = round(time.time() - t, 2)
    return summary
