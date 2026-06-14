"""flay-stab CLI — 안정화 워커 진입점.

API 라우터가 서브프로세스로 실행: `python -m packages.stabilizer.cli run <job_id>`.
(typer 단일 커맨드의 인자 흡수 모호성을 피해 argv 를 직접 파싱한다.)
"""

from __future__ import annotations

import logging
import sys


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    if len(argv) >= 2 and argv[0] == "run":
        from packages.stabilizer.pipeline import run_job
        run_job(argv[1])
        return
    sys.stderr.write("usage: python -m packages.stabilizer.cli run <job_id>\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
