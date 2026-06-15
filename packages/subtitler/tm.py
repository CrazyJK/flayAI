"""번역메모리(TM) 구축 — 기존 KO 팬자막 + Whisper(JP) → JP↔KO 대역 쌍.

phase 2 ①: 사람이 만든 137편 자막을 LLM 번역의 few-shot 예시·용어집·평가셋으로 쓰기 위해
JP↔KO 코퍼스를 만든다. 흐름(영상 1편):
  Whisper(JP, 캐시) + KO 자막 parse → 시간정렬(align) → 의미유사도 필터(bge-m3) → subtitle_tm

증분: subtitle_corpus(opus, srt_mtime) 로 이미 구축한 편은 스킵. 자막이 바뀌면 재구축.
정렬은 phase 3(싱크 수정)에서 재사용한다.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import align, core
from .srt_io import parse_srt, strip_credit_cues

log = logging.getLogger(__name__)

Report = Callable[[str, int], None]

SCHEMA = """
CREATE TABLE IF NOT EXISTS subtitle_tm (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  opus      TEXT NOT NULL,
  jp        TEXT NOT NULL,
  ko        TEXT NOT NULL,
  ko_start  REAL,
  ko_end    REAL,
  sim       REAL,
  overlap   REAL
);
CREATE INDEX IF NOT EXISTS idx_tm_opus ON subtitle_tm(opus);

CREATE TABLE IF NOT EXISTS subtitle_corpus (
  opus      TEXT PRIMARY KEY,
  srt_path  TEXT,
  srt_mtime INTEGER,
  n_pairs   INTEGER,
  n_dropped INTEGER,
  built_at  INTEGER
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def discover(conn: sqlite3.Connection) -> list[tuple[str, Path, Path]]:
    """팬자막(.srt)이 영상 옆에 있는 instance 목록 → [(opus, video_path, srt_path)]."""
    out: list[tuple[str, Path, Path]] = []
    for r in conn.execute(
        "SELECT opus, video_path FROM posters WHERE video_path IS NOT NULL AND video_path != ''"
    ):
        vp = Path(r["video_path"])
        if not vp.exists():
            continue
        srt = core.sibling_srt(vp)
        if srt is None:
            continue
        out.append((r["opus"], vp, srt))
    out.sort(key=lambda t: t[0])
    return out


def bge_embed(texts: list[str]) -> Any:
    """bge-m3 정규화 임베딩(인덱서 로더 재사용). multilingual → JP/KO 교차언어 비교."""
    from packages.indexer.embed_text import _embedder

    return _embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False)


def _corpus_row(conn: sqlite3.Connection, opus: str):
    return conn.execute(
        "SELECT srt_mtime, n_pairs FROM subtitle_corpus WHERE opus = ?", (opus,)
    ).fetchone()


def build_one(
    conn: sqlite3.Connection,
    opus: str,
    video_path: Path,
    srt_path: Path,
    cfg: dict[str, Any],
    embed_fn: Callable[[list[str]], Any],
    report: Report = lambda *_: None,
) -> dict[str, Any]:
    """영상 1편의 JP↔KO 쌍 구축·저장. 반환: 통계 dict."""
    srt_mtime = int(srt_path.stat().st_mtime)

    lang, jp_segments = core.transcribe_cached(conn, opus, video_path, cfg, report)
    ko_cues = strip_credit_cues(parse_srt(srt_path))

    pairs = align.align_by_time(
        jp_segments, ko_cues, min_overlap_ratio=float(cfg.get("tm_min_overlap", 0.2))
    )
    kept, dropped = align.filter_by_similarity(
        pairs, embed_fn, min_sim=float(cfg.get("tm_min_sim", 0.50))
    )

    with conn:
        conn.execute("DELETE FROM subtitle_tm WHERE opus = ?", (opus,))
        conn.executemany(
            "INSERT INTO subtitle_tm(opus, jp, ko, ko_start, ko_end, sim, overlap) "
            "VALUES (?,?,?,?,?,?,?)",
            [(opus, p.jp, p.ko, p.ko_start, p.ko_end, p.sim, p.overlap) for p in kept],
        )
        conn.execute(
            "INSERT OR REPLACE INTO subtitle_corpus(opus, srt_path, srt_mtime, n_pairs, "
            "n_dropped, built_at) VALUES (?,?,?,?,?,?)",
            (opus, str(srt_path), srt_mtime, len(kept), len(dropped), int(time.time())),
        )
    return {
        "opus": opus,
        "lang": lang,
        "jp_segments": len(jp_segments),
        "ko_cues": len(ko_cues),
        "aligned": len(pairs),
        "kept": len(kept),
        "dropped": len(dropped),
    }


def build_all(
    conn: sqlite3.Connection,
    cfg: dict[str, Any],
    *,
    limit: int | None = None,
    rebuild: bool = False,
    report: Report = lambda *_: None,
) -> dict[str, Any]:
    """팬자막 보유 instance 전체의 TM 구축(증분). rebuild=True 면 srt_mtime 무시 전량."""
    init_schema(conn)
    items = discover(conn)
    todo: list[tuple[str, Path, Path, int]] = []
    for opus, vp, srt in items:
        mt = int(srt.stat().st_mtime)
        if not rebuild:
            row = _corpus_row(conn, opus)
            if row and row["srt_mtime"] == mt:
                continue
        todo.append((opus, vp, srt, mt))
    if limit:
        todo = todo[:limit]

    log.info("TM build: %d total fan-subbed, %d to build", len(items), len(todo))
    if not todo:
        return {"total": len(items), "built": 0, "pairs": 0, "stats": []}

    embed_fn = bge_embed  # bge-m3 1회 로드(첫 호출 시)
    stats: list[dict[str, Any]] = []
    total_pairs = 0
    for i, (opus, vp, srt, _mt) in enumerate(todo, 1):
        def rep(stage: str, pct: int, _i: int = i, _o: str = opus) -> None:
            report(f"[{_i}/{len(todo)}] {_o}:{stage}", pct)

        try:
            s = build_one(conn, opus, vp, srt, cfg, embed_fn, rep)
            stats.append(s)
            total_pairs += s["kept"]
            log.info(
                "TM %d/%d %s: kept=%d dropped=%d (jp=%d ko=%d)",
                i, len(todo), opus, s["kept"], s["dropped"], s["jp_segments"], s["ko_cues"],
            )
        except Exception as e:  # noqa: BLE001 — 한 편 실패가 배치를 멈추지 않게
            log.exception("TM build 실패 opus=%s", opus)
            stats.append({"opus": opus, "error": str(e)[:200]})
    return {"total": len(items), "built": len(stats), "pairs": total_pairs, "stats": stats}


# --- Qdrant 검색(phase 2 ② few-shot) -----------------------------

TM_COLLECTION = "subtitle_tm"
TM_DIM = 1024  # bge-m3


def ensure_tm_collection(qc) -> None:
    from qdrant_client.http import models as qm

    names = {c.name for c in qc.get_collections().collections}
    if TM_COLLECTION in names:
        return
    qc.create_collection(
        TM_COLLECTION,
        vectors_config=qm.VectorParams(size=TM_DIM, distance=qm.Distance.COSINE),
    )
    try:
        qc.create_payload_index(TM_COLLECTION, "opus", field_schema=qm.PayloadSchemaType.KEYWORD)
    except Exception:  # noqa: BLE001
        pass


def _vec_list(v: Any) -> list[float]:
    return v.tolist() if hasattr(v, "tolist") else list(v)


def embed_tm(conn: sqlite3.Connection, qc=None, *, opus: str | None = None) -> int:
    """subtitle_tm 의 JP 를 bge-m3 로 임베딩해 Qdrant 에 upsert(검색용). 반환: 점 수."""
    from qdrant_client.http import models as qm

    if qc is None:
        from packages.indexer.embed_text import _qdrant

        qc = _qdrant()
    ensure_tm_collection(qc)
    if opus:
        rows = conn.execute(
            "SELECT id, opus, jp, ko FROM subtitle_tm WHERE opus = ?", (opus,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT id, opus, jp, ko FROM subtitle_tm").fetchall()
    if not rows:
        return 0
    vecs = bge_embed([r["jp"] for r in rows])
    points = [
        qm.PointStruct(
            id=int(r["id"]),
            vector=_vec_list(v),
            payload={"opus": r["opus"], "jp": r["jp"], "ko": r["ko"]},
        )
        for r, v in zip(rows, vecs)
    ]
    for i in range(0, len(points), 256):
        qc.upsert(TM_COLLECTION, points[i : i + 256])
    return len(points)


def retrieve_examples(qc, query_lines: list[str], k: int, per_line: int = 3) -> list[tuple[str, str]]:
    """청크의 각 JP 줄과 유사한 (jp, ko) 예시를 모아 중복 제거 후 최대 k개."""
    if qc is None or not query_lines:
        return []
    qvecs = bge_embed(query_lines)
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, float, str]] = []  # (jp, score, ko) — score 로 정렬
    for v in qvecs:
        try:
            hits = qc.search(TM_COLLECTION, query_vector=_vec_list(v), limit=per_line)
        except Exception:  # noqa: BLE001
            continue
        for h in hits:
            jp = (h.payload or {}).get("jp")
            ko = (h.payload or {}).get("ko")
            if jp and ko and (jp, ko) not in seen:
                seen.add((jp, ko))
                out.append((jp, float(h.score), ko))
    out.sort(key=lambda t: t[1], reverse=True)
    return [(jp, ko) for jp, _s, ko in out[:k]]


def sample(conn: sqlite3.Connection, opus: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    if opus:
        rows = conn.execute(
            "SELECT opus, jp, ko, sim, overlap FROM subtitle_tm WHERE opus=? "
            "ORDER BY ko_start LIMIT ?", (opus, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT opus, jp, ko, sim, overlap FROM subtitle_tm ORDER BY RANDOM() LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
