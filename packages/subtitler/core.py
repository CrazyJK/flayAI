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
from .srt_io import Cue, parse_subtitle, write_srt, write_subtitle
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
    """영상과 같은 stem 의 기존 .srt. 없으면 None."""
    cand = out_srt_path(video_path, "")
    return cand if cand.exists() else None


def sibling_sub(video_path: Path) -> Path | None:
    """영상과 같은 stem 의 기존 자막(.srt 우선, 없으면 .smi). 사람 팬자막."""
    for ext in (".srt", ".smi"):
        cand = video_path.parent / (video_path.stem + ext)
        if cand.exists():
            return cand
    return None


def resolve(conn: sqlite3.Connection, opus: str) -> tuple[Path | None, Path | None]:
    """opus → (재생 영상 경로, 기존 자막 .srt/.smi). 영상이 오프라인/부재면 video_path=None."""
    row = conn.execute("SELECT video_path FROM posters WHERE opus=?", (opus,)).fetchone()
    vp = Path(row["video_path"]) if row and row["video_path"] else None
    if vp is not None and not vp.exists():
        vp = None
    sub = sibling_sub(vp) if vp else None
    return vp, sub


def transcribe_cached(
    conn: sqlite3.Connection, opus: str, video_path: Path, cfg: dict[str, Any], report: Report = _noop
) -> tuple[str | None, list[dict[str, Any]]]:
    """전사(캐시 우선). 영상 mtime 이 캐시와 같으면 재실행 생략.

    generate(신규 자막)·tm(번역메모리)·resync(싱크수정)가 공유 — Whisper 1패스 재사용.
    """
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
    lang, segments = transcribe_cached(conn, opus, video_path, cfg, report)
    if not segments:
        return {"status": "failed", "error": "발화 세그먼트 없음(무음/VAD 전부 제거)"}

    note = None
    if lang and lang != cfg.get("language"):
        note = f"감지 언어 {lang} != {cfg.get('language')} — 번역 품질 저하 가능"

    report("translate", 0)

    def tcb(done: int, total: int) -> None:
        report("translate", int(100 * done / total) if total else 0)

    kos = translate_segments(conn, [s["text"] for s in segments], cfg=cfg, progress_cb=tcb)
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
    """기존 자막 싱크 수정 — KO 대사를 Whisper 발화구간에 의미 정렬 후 재타이밍.

    텍스트(사람 번역)는 보존하고 타이밍만 교정한다. 원본은 <stem>.orig.srt 로 백업.
    """
    if existing_srt is None:
        return {"status": "failed", "error": "기존 자막 없음 — resync 대상 아님"}
    from . import align, tm

    # 소스는 항상 원본(<stem>.orig.srt) 우선 — 여러 번 resync 해도 타이밍이 누적 오염되지
    # 않게(멱등). 최초 1회 원본 백업. 포맷(.srt/.smi) 보존.
    ext = existing_srt.suffix.lower()
    bak = existing_srt.with_name(f"{video_path.stem}.orig{ext}")
    if cfg.get("backup_existing", True) and not bak.exists():
        shutil.copy2(existing_srt, bak)
    source = bak if bak.exists() else existing_srt

    report("transcribe", 0)
    _lang, segs = transcribe_cached(conn, opus, video_path, cfg, report)
    if not segs:
        return {"status": "failed", "error": "발화 세그먼트 없음(무음/VAD)"}
    cues = parse_subtitle(source)
    if not cues:
        return {"status": "failed", "error": "기존 자막 파싱 결과 없음"}

    report("align", 60)
    ko_vecs = tm.bge_embed([c.text for c in cues])
    jp_vecs = tm.bge_embed([s["text"] for s in segs])
    matches = align.align_semantic(ko_vecs, jp_vecs, floor=float(cfg.get("resync_floor", 0.35)))
    rate = len(matches) / max(1, len(cues))

    min_match = float(cfg.get("resync_min_match", 0.30))
    if rate < min_match:
        # 앵커 부족 → 보간이 자막을 좁은 구간에 몰아 오히려 나빠진다. 원본 타이밍 유지/복원.
        if source != existing_srt:
            shutil.copy2(source, existing_srt)
        return {
            "status": "skipped",
            "result_path": str(existing_srt),
            "matched": len(matches),
            "note": f"매칭률 {rate:.0%} < {min_match:.0%} — 앵커 부족, 원본 유지",
        }

    new_cues = align.retime(cues, segs, matches)
    report("write", 95)
    write_subtitle(existing_srt, new_cues)  # 입력 포맷(.srt/.smi) 그대로 작성
    report("write", 100)
    return {
        "status": "done",
        "result_path": str(existing_srt),
        "matched": len(matches),
        "note": f"{len(matches)}/{len(cues)} 큐 오디오 매칭({rate:.0%})",
    }


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
    if task == "resync":
        return resync(conn, opus, video_path, existing_srt, cfg, report)
    if task == "both":
        # 기존 자막 있으면 싱크 수정, 없으면 신규 생성.
        if existing_srt is not None:
            return resync(conn, opus, video_path, existing_srt, cfg, report)
        return generate(conn, opus, video_path, existing_srt, cfg, report)
    return {"status": "failed", "error": f"알 수 없는 task: {task}"}
