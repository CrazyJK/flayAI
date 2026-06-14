"""잡 오케스트레이션 — 모드별 엔진 디스패치. cli(서브프로세스)가 호출."""

from __future__ import annotations

import logging

from . import job as J
from .config import stabilize_config

log = logging.getLogger(__name__)


def run_job(job_id: str) -> None:
    st = J.get_status(job_id)
    if st is None:
        raise SystemExit(f"job not found: {job_id}")
    cfg = stabilize_config()
    J.set_status(job_id, status="running", stage="start", progress=1)

    def _set(**kw):
        J.set_status(job_id, **kw)

    try:
        mode = st.get("mode", "background")
        strength = st.get("strength", cfg["default_strength"])
        if mode == "background":
            from .engines.vidstab import run_background
            run_background(J.job_path(job_id), strength, cfg, _set)
        elif mode == "person":
            # API/잡 모델은 준비됨. 엔진은 SAM2(클릭→전파) 연동 예정.
            raise NotImplementedError("인물 모드는 아직 미구현(SAM2 클릭 지정 연동 예정)")
        else:
            raise ValueError(f"알 수 없는 mode: {mode}")
    except Exception as e:  # noqa: BLE001 — 실패를 status 에 남기고 종료
        log.exception("stabilize job 실패: %s", job_id)
        _set(status="failed", error=str(e)[:500])
