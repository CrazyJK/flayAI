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

    def _scaled(lo, hi):
        # '둘 다' 모드: 각 엔진의 0~100 진행을 [lo,hi] 구간으로 매핑해 단조 진행
        def f(**kw):
            if "progress" in kw and kw["progress"] is not None:
                kw["progress"] = lo + int((hi - lo) * kw["progress"] / 100)
            J.set_status(job_id, **kw)
        return f

    try:
        from .engines.person import run_person
        from .engines.vidstab import run_background

        mode = st.get("mode", "background")
        strength = st.get("strength", cfg["default_strength"])
        opts = st.get("options") or {}
        jdir = J.job_path(job_id)
        outputs = []
        if mode == "background":
            outputs.append(run_background(jdir, strength, opts, cfg, _set))
        elif mode == "person":
            outputs.append(run_person(jdir, strength, opts, cfg, _set))
        elif mode == "both":
            outputs.append(run_background(jdir, strength, opts, cfg, _scaled(0, 50),
                                          out_name="out_background.mp4"))
            outputs.append(run_person(jdir, strength, opts, cfg, _scaled(50, 100),
                                       out_name="out_person.mp4"))
        else:
            raise ValueError(f"알 수 없는 mode: {mode}")
        _set(status="done", stage="encode", progress=100, outputs=outputs)
    except Exception as e:  # noqa: BLE001 — 실패를 status 에 남기고 종료
        log.exception("stabilize job 실패: %s", job_id)
        _set(status="failed", error=str(e)[:500])
