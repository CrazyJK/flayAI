"""flay-sub CLI — 자막 큐/워커 진입점.

  python -m packages.subtitler.cli enqueue <opus> [task]   # 신청 적재(보통은 API)
  python -m packages.subtitler.cli run <opus> [task]       # 단건 즉시 처리(테스트/수동)
  python -m packages.subtitler.cli drain                   # 야간 배치: 큐를 비울 때까지

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


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    _setup_logging()
    if not argv:
        sys.stderr.write(
            "usage: python -m packages.subtitler.cli "
            "enqueue <opus> [task] | run <opus> [task] | drain\n"
        )
        sys.exit(2)
    cmd = argv[0]
    if cmd == "drain":
        cmd_drain()
        return
    if cmd in ("enqueue", "run") and len(argv) >= 2:
        opus = argv[1]
        task = argv[2] if len(argv) >= 3 else "generate"
        (cmd_enqueue if cmd == "enqueue" else cmd_run)(opus, task)
        return
    sys.stderr.write(
        "usage: python -m packages.subtitler.cli "
        "enqueue <opus> [task] | run <opus> [task] | drain\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
