"""Qdrant payload 동기화 — kind / playable 변경 자동 반영.

SQLite 가 진실 소스 (`videos.kind` + `posters.video_path`).
4개 Qdrant 컬렉션 모두 같은 키(`opus`, `kind`, `playable`) payload 사용.

전략:
1. SQLite 에서 (opus → kind, playable) 맵 구성 = truth.
2. 각 컬렉션을 scroll 로 훑으며 (opus, current_payload) 수집.
3. 다른 것만 골라 `set_payload` 호출 (벡터는 건드리지 않음).
   - videos / poster_ocr : opus 당 1 point → point id 로 갱신.
   - posters_clip (7타일) / faces : opus 당 다수 point → opus 필터로 일괄 갱신.

이미지/얼굴/OCR 풀 재처리 대비 수십~수백배 빠름.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _qdrant

log = logging.getLogger(__name__)

# (컬렉션 이름, opus 당 다중 point 여부)
COLLECTIONS = [
    ("videos", False),
    ("posters_clip", True),
    ("poster_ocr", False),
    ("faces", True),
]


def _sqlite_truth(conn) -> dict[str, tuple[str | None, bool]]:
    """{opus: (kind, playable)} — SQLite 가 진실."""
    rows = conn.execute("""
        SELECT v.opus,
               COALESCE(v.kind, p.kind)                                          AS kind,
               CASE WHEN p.video_path IS NOT NULL AND p.video_path != '' THEN 1
                    ELSE 0 END                                                   AS playable
          FROM videos v
          LEFT JOIN posters p ON p.opus = v.opus
    """).fetchall()
    return {r["opus"]: (r["kind"], bool(r["playable"])) for r in rows}


def _scroll_all(qc, collection: str) -> Iterable[tuple]:
    """yield (point_id, opus, kind, playable)."""
    offset = None
    while True:
        try:
            points, offset = qc.scroll(
                collection_name=collection,
                with_payload=["opus", "kind", "playable"],
                with_vectors=False,
                limit=1000,
                offset=offset,
            )
        except Exception as e:
            log.warning("scroll %s failed: %s", collection, e)
            return
        if not points:
            return
        for p in points:
            pl = p.payload or {}
            yield (p.id, pl.get("opus"), pl.get("kind"), pl.get("playable"))
        if offset is None:
            return


def _sync_collection(
    qc, collection: str, multi_point: bool, truth: dict[str, tuple[str | None, bool]]
) -> dict:
    scanned = 0
    diff_opus: dict[str, tuple[str | None, bool]] = {}
    diff_points_by_opus: dict[str, list] = {}

    for pid, opus, cur_kind, cur_playable in _scroll_all(qc, collection):
        scanned += 1
        if opus is None or opus not in truth:
            continue
        new_kind, new_playable = truth[opus]
        if cur_kind == new_kind and bool(cur_playable) == new_playable:
            continue
        diff_opus[opus] = (new_kind, new_playable)
        diff_points_by_opus.setdefault(opus, []).append(pid)

    if not diff_opus:
        log.info("[%s] scanned=%d  changed=0", collection, scanned)
        return {"scanned": scanned, "changed_opus": 0, "updated_points": 0}

    updated_points = 0
    for opus, (kind, playable) in diff_opus.items():
        payload = {"kind": kind, "playable": playable}
        try:
            if multi_point:
                qc.set_payload(
                    collection_name=collection,
                    payload=payload,
                    points=qm.Filter(
                        must=[qm.FieldCondition(key="opus", match=qm.MatchValue(value=opus))]
                    ),
                    wait=False,
                )
                updated_points += len(diff_points_by_opus[opus])
            else:
                ids = diff_points_by_opus[opus]
                qc.set_payload(
                    collection_name=collection,
                    payload=payload,
                    points=ids,
                    wait=False,
                )
                updated_points += len(ids)
        except Exception as e:
            log.warning("set_payload %s opus=%s failed: %s", collection, opus, e)

    log.info(
        "[%s] scanned=%d  changed_opus=%d  updated_points=%d",
        collection,
        scanned,
        len(diff_opus),
        updated_points,
    )
    return {"scanned": scanned, "changed_opus": len(diff_opus), "updated_points": updated_points}


def run() -> dict:
    conn = connect()
    init_schema(conn)
    truth = _sqlite_truth(conn)
    conn.close()
    qc = _qdrant()

    t = time.time()
    by_col: dict[str, dict] = {}
    total_changed = 0
    total_updated = 0
    for name, multi in COLLECTIONS:
        try:
            r = _sync_collection(qc, name, multi, truth)
        except Exception as e:
            log.warning("collection %s skipped: %s", name, e)
            r = {"scanned": 0, "changed_opus": 0, "updated_points": 0, "error": str(e)}
        by_col[name] = r
        total_changed += r.get("changed_opus", 0)
        total_updated += r.get("updated_points", 0)

    return {
        "sqlite_opus": len(truth),
        "changed_opus": total_changed,
        "updated_points": total_updated,
        "by_collection": by_col,
        "elapsed_sec": round(time.time() - t, 2),
    }
