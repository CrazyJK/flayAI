"""flay-sub CLI — 자막 큐/워커 진입점.

  python -m packages.subtitler.cli enqueue <opus> [task]      # 신청 적재(보통은 API)
  python -m packages.subtitler.cli enqueue-all <task> [limit] # 후보 전체 적재(resync=기존자막 전체)
  python -m packages.subtitler.cli run <opus> [task]          # 단건 즉시 처리(테스트/수동)
  python -m packages.subtitler.cli drain                      # 야간 배치: 큐를 비울 때까지
  python -m packages.subtitler.cli build-tm [limit]           # phase2: 팬자막 → JP↔KO 번역메모리

drain 은 Windows 작업 스케줄러가 야간에 호출(scripts/nightly_subtitle.ps1).
(typer 인자 흡수 모호성을 피해 argv 를 직접 파싱 — stabilizer.cli 와 동일 패턴.)
"""

from __future__ import annotations

import logging
import sys

from packages.indexer.db import connect, init_schema

from . import core, db, whisper_stt
from .config import subtitle_config

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )


def _conn():
    conn = connect()
    init_schema(conn)       # posters 등 본체 스키마(멱등)
    db.init_schema(conn)    # 자막 큐/캐시 스키마(멱등)
    return conn


def cmd_enqueue(opus: str, task: str) -> None:
    conn = _conn()
    try:
        jid, created = db.enqueue(conn, opus, task)
        sys.stderr.write(f"{'queued' if created else 'exists'} job#{jid} opus={opus} task={task}\n")
    finally:
        conn.close()


def cmd_enqueue_all(task: str, limit: int | None) -> None:
    """후보 opus 전체를 큐에 적재(중복은 자동 스킵).

    resync   = 기존 자막(.srt) 보유 영상 전체(일회성 일괄 싱크 수정).
    generate = 자막 없는 재생영상 전체(주의: 대량 — limit 권장).
    """
    from pathlib import Path

    from . import tm

    conn = _conn()
    try:
        if task == "resync":
            candidates = [opus for opus, _vp, _srt in tm.discover(conn)]
        elif task == "generate":
            candidates = []
            for r in conn.execute(
                "SELECT opus, video_path FROM posters "
                "WHERE video_path IS NOT NULL AND video_path != ''"
            ):
                vp = Path(r["video_path"])
                if vp.exists() and core.sibling_srt(vp) is None:
                    candidates.append(r["opus"])
        else:
            sys.stderr.write(f"task 는 generate | resync (got: {task})\n")
            sys.exit(2)
        if limit:
            candidates = candidates[: int(limit)]
        added = 0
        for opus in candidates:
            _jid, created = db.enqueue(conn, opus, task)
            if created:
                added += 1
        sys.stderr.write(f"enqueue-all {task}: {added} new / {len(candidates)} candidates\n")
    finally:
        conn.close()


def cmd_run(opus: str, task: str) -> None:
    """큐를 거치지 않고 단건 즉시 처리(수동 테스트)."""
    conn = _conn()
    cfg = subtitle_config()
    try:
        def report(stage: str, pct: int) -> None:
            sys.stderr.write(f"\r[{stage}] {pct:3d}%   ")
            sys.stderr.flush()

        res = core.process(conn, {"opus": opus, "task": task}, cfg, report)
        sys.stderr.write("\n" + repr(res) + "\n")
    finally:
        whisper_stt.unload()
        conn.close()


def cmd_drain() -> None:
    """큐의 queued 잡을 순차 처리. 야간 무인 배치 진입점."""
    conn = _conn()
    cfg = subtitle_config()
    done = failed = skipped = 0
    try:
        while True:
            job = db.claim_next(conn)
            if job is None:
                break
            jid = int(job["id"])
            log.info("job#%s start opus=%s task=%s", jid, job["opus"], job.get("task"))

            def report(stage: str, pct: int, _jid: int = jid) -> None:
                db.set_progress(conn, _jid, stage=stage, progress=pct)

            try:
                res = core.process(conn, job, cfg, report)
                status = res.get("status", "done")
                db.finish(
                    conn, jid, status,
                    result_path=res.get("result_path"),
                    error=res.get("error"),
                    note=res.get("note"),
                )
                if status == "done":
                    done += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1
                log.info("job#%s -> %s %s", jid, status, res.get("note") or res.get("error") or "")
            except Exception as e:  # noqa: BLE001 — 한 잡 실패가 배치를 멈추지 않게
                log.exception("job#%s 실패", jid)
                db.finish(conn, jid, "failed", error=str(e))
                failed += 1
    finally:
        whisper_stt.unload()  # 배치 끝나면 VRAM 반환
        conn.close()
    log.info("drain done: %d done, %d skipped, %d failed", done, skipped, failed)


def cmd_build_tm(limit: int | None) -> None:
    """phase 2: 팬자막 보유 instance → JP↔KO 번역메모리 구축(증분)."""
    from . import tm

    conn = _conn()
    cfg = subtitle_config()
    try:
        def report(stage: str, pct: int) -> None:
            sys.stderr.write(f"\r{stage} {pct:3d}%        ")
            sys.stderr.flush()

        res = tm.build_all(conn, cfg, limit=limit, report=report)
        sys.stderr.write("\n")
        # 새로 구축한 편을 Qdrant 에 임베딩(검색 few-shot 용)
        embedded = 0
        for s in res.get("stats", []):
            if s.get("error") or not s.get("kept"):
                continue
            try:
                embedded += tm.embed_tm(conn, opus=s["opus"])
            except Exception as e:  # noqa: BLE001 — Qdrant 미가용이어도 TM 테이블은 남음
                log.warning("TM 임베딩 스킵 opus=%s: %s", s["opus"], e)
        log.info(
            "build-tm done: total=%d built=%d pairs=%d embedded=%d",
            res["total"], res["built"], res["pairs"], embedded,
        )
    finally:
        whisper_stt.unload()
        conn.close()


def cmd_eval(opus: str | None, n: int | None) -> None:
    """phase 2 ③: NLLB vs LLM+TM 를 사람 자막과 chrF 비교."""
    from . import evaluate

    conn = _conn()
    try:
        if opus:
            res = evaluate.evaluate_opus(conn, opus, n=n, judge_n=min(n or 12, 20))
            sys.stderr.write(
                f"{opus}: n={res.get('n')} chrf nllb={res.get('chrf_nllb')} "
                f"llm={res.get('chrf_llm')} delta={res.get('delta')} "
                f"judge(LLM 우세/NLLB 우세/무승부)={res.get('judge')}\n"
            )
            for s in res.get("samples", [])[:6]:
                sys.stderr.write(
                    f"  JP  {s['jp']}\n  REF {s['ref']}\n  NLLB {s['nllb']}\n  LLM {s['llm']}\n\n"
                )
        else:
            res = evaluate.evaluate(conn, n_per=n or 40)
            agg = res["aggregate"]
            sys.stderr.write(
                f"집계 {agg.get('opuses')}편: chrf nllb={agg.get('chrf_nllb')} "
                f"llm={agg.get('chrf_llm')} delta={agg.get('delta')}\n"
            )
    finally:
        conn.close()


_USAGE = (
    "usage: python -m packages.subtitler.cli "
    "enqueue <opus> [task] | enqueue-all <task> [limit] | run <opus> [task] | "
    "drain | build-tm [limit] | eval [opus] [n]\n"
)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    _setup_logging()
    if not argv:
        sys.stderr.write(_USAGE)
        sys.exit(2)
    cmd = argv[0]
    if cmd == "drain":
        cmd_drain()
        return
    if cmd == "build-tm":
        limit = int(argv[1]) if len(argv) >= 2 else None
        cmd_build_tm(limit)
        return
    if cmd == "eval":
        a1 = argv[1] if len(argv) >= 2 else None
        a2 = argv[2] if len(argv) >= 3 else None
        if a1 and a1.isdigit():
            cmd_eval(None, int(a1))
        else:
            cmd_eval(a1, int(a2) if a2 else None)
        return
    if cmd == "enqueue-all" and len(argv) >= 2:
        cmd_enqueue_all(argv[1], int(argv[2]) if len(argv) >= 3 else None)
        return
    if cmd in ("enqueue", "run") and len(argv) >= 2:
        opus = argv[1]
        task = argv[2] if len(argv) >= 3 else "generate"
        (cmd_enqueue if cmd == "enqueue" else cmd_run)(opus, task)
        return
    sys.stderr.write(_USAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
