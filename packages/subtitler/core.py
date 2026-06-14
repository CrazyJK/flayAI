"""자막 잡 오케스트레이션 — opus → 전사 → 생성/싱크수정 → .srt.

phase 1 은 generate(생성)만 구현. resync(싱크수정)는 phase 3.
report(stage, pct) 콜백으로 진행률을 큐에 흘린다.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import db, whisper_stt
from .srt_io import Cue, write_srt
from .translate import translate_segments

log = logging.getLogger(__name__)

Report = Callable[[str, int], None]


def _noop(_stage: str, _pct: int) -> None:
    pass


def out_srt_path(video_path: Path, suffix: str = "") -> Path:
    """출력 자막 경로. suffix='' → <stem>.srt, 'ko' → <stem>.ko.srt."""
    name = f"{video_path.stem}.{suffix}.srt" if suffix else f"{video_path.stem}.srt"
    return video_path.parent / name


def sibling_srt(video_path: Path) -> Path | None:
    """영상과 같은 stem 의 기존 .srt (사람 팬자막). 없으면 None."""
    cand = out_srt_path(video_path, "")
    return cand if cand.exists() else None


def resolve(conn: sqlite3.Connection, opus: str) -> tuple[Path | None, Path | None]:
    """opus → (재생 영상 경로, 기존 .srt). 영상이 오프라인/부재면 video_path=None."""
    row = conn.execute("SELECT video_path FROM posters WHERE opus=?", (opus,)).fetchone()
    vp = Path(row["video_path"]) if row and row["video_path"] else None
    if vp is not None and not vp.exists():
        vp = None
    srt = sibling_srt(vp) if vp else None
    return vp, srt


def _transcribe_cached(
    conn: sqlite3.Connection, opus: str, video_path: Path, cfg: dict[str, Any], report: Report
) -> tuple[str | None, list[dict[str, Any]]]:
    """전사(캐시 우선). 영상 mtime 이 캐시와 같으면 재실행 생략."""
    mtime = int(video_path.stat().st_mtime)
    cached = db.get_transcript(conn, opus, cfg["model"])
    if cached and cached.get("video_mtime") == mtime:
        log.info("transcript cache hit opus=%s", opus)
        return cached.get("language"), cached["segments"]

    def cb(cur: float, total: float) -> None:
        report("transcribe", int(100 * cur / total) if total else 0)

    lang, segments = whisper_stt.transcribe(
        video_path,
        model=cfg["model"],
        device=cfg["device"],
        compute_type=cfg["compute_type"],
        language=cfg["language"],
        vad_filter=cfg["vad_filter"],
        beam_size=cfg["beam_size"],
        progress_cb=cb,
    )
    db.put_transcript(conn, opus, cfg["model"], mtime, lang, segments)
    return lang, segments


def generate(
    conn: sqlite3.Connection,
    opus: str,
    video_path: Path,
    existing_srt: Path | None,
    cfg: dict[str, Any],
    report: Report = _noop,
) -> dict[str, Any]:
    """일본어 음성 → 한국어 자막 생성. 기존 자막이 있으면 보호(건너뜀)."""
    if existing_srt and cfg.get("skip_if_exists", True):
        return {
            "status": "skipped",
            "note": f"기존 자막 존재({existing_srt.name}) — 싱크수정은 resync(phase 3)",
        }

    report("transcribe", 0)
    lang, segments = _transcribe_cached(conn, opus, video_path, cfg, report)
    if not segments:
        return {"status": "failed", "error": "발화 세그먼트 없음(무음/VAD 전부 제거)"}

    note = None
    if lang and lang != cfg.get("language"):
        note = f"감지 언어 {lang} != {cfg.get('language')} — 번역 품질 저하 가능"

    report("translate", 0)

    def tcb(done: int, total: int) -> None:
        report("translate", int(100 * done / total) if total else 0)

    kos = translate_segments(
        conn, [s["text"] for s in segments], mode=cfg["translator"], progress_cb=tcb
    )
    cues = [
        Cue(0, s["start"], s["end"], ko.strip())
        for s, ko in zip(segments, kos)
        if ko and ko.strip()
    ]
    if not cues:
        return {"status": "failed", "error": "번역 결과 비어 있음"}

    report("write", 95)
    out = out_srt_path(video_path, cfg.get("out_suffix", ""))
    if out.exists() and cfg.get("backup_existing", True):
        bak = out.with_name(f"{video_path.stem}.orig.srt")
        if not bak.exists():
            shutil.copy2(out, bak)
    write_srt(out, cues)
    report("write", 100)
    return {"status": "done", "result_path": str(out), "note": note, "segments": len(cues)}


def resync(
    conn: sqlite3.Connection,
    opus: str,
    video_path: Path,
    existing_srt: Path | None,
    cfg: dict[str, Any],
    report: Report = _noop,
) -> dict[str, Any]:
    """기존 자막 싱크 수정 — Whisper 발화구간에 KO 대사 재정렬(phase 3)."""
    raise NotImplementedError("resync(싱크 수정)는 phase 3")


def process(
    conn: sqlite3.Connection, job: dict[str, Any], cfg: dict[str, Any], report: Report = _noop
) -> dict[str, Any]:
    """잡 1건 처리. 반환 dict 의 status 로 큐를 마감한다."""
    opus = job["opus"]
    task = job.get("task", "generate")
    video_path, existing_srt = resolve(conn, opus)
    if video_path is None:
        return {"status": "failed", "error": "재생 영상 없음(오프라인 드라이브/미존재)"}

    if task == "generate":
        return generate(conn, opus, video_path, existing_srt, cfg, report)
    if task in ("resync", "both"):
        return {"status": "failed", "error": "resync/both 미구현 — phase 3"}
    return {"status": "failed", "error": f"알 수 없는 task: {task}"}
