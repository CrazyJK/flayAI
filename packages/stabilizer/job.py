"""안정화 잡 모델 — 잡 디렉토리 + status.json(단일 진실 소스).

인덱서의 메모리 전용 _running_jobs 와 달리, 안정화 잡은 길고 다운로드 산출물이 있어
잡당 status.json 을 디스크에 원자적으로 기록한다(API 재시작 후에도 폴링·결과 복구).

레이아웃: {work_dir}/{job_id}/  ── in.mp4, work/, out.mp4, status.json
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from packages.settings import repo_path

from .config import stabilize_config


def _work_root() -> Path:
    p = repo_path(stabilize_config()["work_dir"])
    p.mkdir(parents=True, exist_ok=True)
    return p


def job_path(job_id: str) -> Path:
    return _work_root() / job_id


def status_path(job_id: str) -> Path:
    return job_path(job_id) / "status.json"


def input_path(job_id: str) -> Path:
    return job_path(job_id) / "in.mp4"


def _write(job_id: str, st: dict[str, Any]) -> None:
    sp = status_path(job_id)
    sp.parent.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, sp)  # 원자적 교체


def new_job(mode: str, strength: str, options: dict | None = None) -> str:
    job_id = uuid.uuid4().hex[:16]
    job_path(job_id).mkdir(parents=True, exist_ok=True)
    now = time.time()
    _write(job_id, {
        "job_id": job_id, "status": "queued", "mode": mode, "strength": strength,
        "options": options or {}, "stage": None, "progress": 0,
        "created_at": now, "updated_at": now,
        "input": None, "outputs": [], "error": None, "note": None,
    })
    return job_id


def get_status(job_id: str) -> dict[str, Any] | None:
    sp = status_path(job_id)
    if not sp.exists():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def set_status(job_id: str, **updates: Any) -> dict[str, Any] | None:
    st = get_status(job_id)
    if st is None:
        return None
    st.update(updates)
    st["updated_at"] = time.time()
    _write(job_id, st)
    return st


def list_jobs() -> list[dict[str, Any]]:
    root = _work_root()
    out: list[dict[str, Any]] = []
    for d in root.iterdir():
        if d.is_dir() and (d / "status.json").exists():
            st = get_status(d.name)
            if st:
                out.append(st)
    out.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return out


def cleanup_old_jobs(retain_hours: float | None = None) -> int:
    """보존기간 지난 완료/실패/취소 잡 디렉토리를 삭제. 삭제 개수 반환.

    - status.json 없는 디렉토리(_analysis 등)·파일(sample.mp4)은 건드리지 않는다.
    - 진행 중(queued/running)은 나이와 무관하게 보존.
    best-effort — 디렉토리 잠김 등은 무시.
    """
    if retain_hours is None:
        retain_hours = float(stabilize_config().get("retain_hours", 48) or 0)
    if retain_hours <= 0:
        return 0
    cutoff = time.time() - retain_hours * 3600
    removed = 0
    for d in _work_root().iterdir():
        if not d.is_dir():
            continue
        st = get_status(d.name)
        if st is None or st.get("status") not in ("done", "failed", "canceled"):
            continue
        if st.get("updated_at", 0) < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
