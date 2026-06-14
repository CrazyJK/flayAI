"""영상 안정화 API 라우터 — 업로드 → 비동기 잡 → 폴링 → 결과 다운로드.

설계: docs/video-stabilization-plan.md. 인덱서 admin 과 동일하게 localhost-only,
잡은 서브프로세스(packages.stabilizer.cli)로 실행하고 status.json 으로 추적한다.

엔드포인트(prefix=/api/stabilize):
  POST /jobs                  업로드 + 옵션 -> 잡 생성
  GET  /jobs                  잡 목록
  GET  /jobs/{id}             잡 상태(폴링)
  GET  /jobs/{id}/result      결과 mp4 다운로드/재생
  POST /jobs/{id}/cancel      취소(서브프로세스 terminate)
  DELETE /jobs/{id}           잡 삭제
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from packages.settings import REPO_ROOT
from packages.stabilizer import job as J

router = APIRouter(prefix="/api/stabilize", tags=["stabilize"])
log = logging.getLogger(__name__)

# 실행 중 워커 서브프로세스 (취소/삭제용 — JSON 직렬화 대상 아님)
_procs: dict[str, subprocess.Popen] = {}


def _localhost_only(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "localhost", "::1", "ai.kamoru.jk"):
        raise HTTPException(403, "stabilize endpoints are localhost-only")


def _busy() -> str | None:
    """동시 1잡 + 인덱싱과 상호배제. 실행 중이면 사유 문자열, 아니면 None."""
    for s in J.list_jobs():
        if s.get("status") == "running":
            return f"안정화 잡 {s['job_id']} 가 실행 중입니다(동시 1개)."
    try:
        from apps.api.routers.admin import PIPELINE_DEFS, _running_jobs
        for pj in PIPELINE_DEFS:
            info = _running_jobs.get(pj)
            if info and info.get("status") == "running":
                return f"인덱싱 '{pj}' 파이프라인 실행 중 — 완료 후 시도하세요."
    except Exception:  # noqa: BLE001 — admin 미가용이어도 진행
        pass
    return None


def _wait(job_id: str, proc: subprocess.Popen) -> None:
    proc.wait()
    _procs.pop(job_id, None)
    st = J.get_status(job_id)
    if st and st.get("status") == "running":
        J.set_status(job_id, status="failed",
                     error=f"워커 비정상 종료(exit {proc.returncode})")


@router.post("/jobs")
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("background"),
    strength: str = Form("smooth"),
    subject: str | None = Form(None),  # 인물 모드 지정(클릭 좌표/박스 등) — JSON 문자열
) -> dict[str, Any]:
    _localhost_only(request)
    if mode not in ("background", "person"):
        raise HTTPException(400, "mode 는 background | person")
    busy = _busy()
    if busy:
        raise HTTPException(409, busy)

    options: dict[str, Any] = {}
    if subject:
        options["subject"] = subject
    job_id = J.new_job(mode, strength, options)

    dest = J.input_path(job_id)
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    venv_python = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    proc = subprocess.Popen(
        [venv_python, "-m", "packages.stabilizer.cli", "run", job_id],
        cwd=str(REPO_ROOT),
    )
    _procs[job_id] = proc
    asyncio.get_event_loop().run_in_executor(None, _wait, job_id, proc)
    return {"job_id": job_id, "status": "queued", "mode": mode, "strength": strength}


@router.get("/jobs")
def list_jobs(request: Request) -> dict[str, Any]:
    _localhost_only(request)
    return {"jobs": J.list_jobs()}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, request: Request) -> dict[str, Any]:
    _localhost_only(request)
    st = J.get_status(job_id)
    if not st:
        raise HTTPException(404, "job not found")
    return st


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str, request: Request) -> FileResponse:
    _localhost_only(request)
    st = J.get_status(job_id)
    if not st:
        raise HTTPException(404, "job not found")
    out = J.job_path(job_id) / "out.mp4"
    if st.get("status") != "done" or not out.exists():
        raise HTTPException(409, "아직 결과가 준비되지 않았습니다")
    return FileResponse(str(out), media_type="video/mp4", filename=f"stabilized_{job_id}.mp4")


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    _localhost_only(request)
    if not J.get_status(job_id):
        raise HTTPException(404, "job not found")
    p = _procs.get(job_id)
    if p and p.poll() is None:
        p.terminate()
    J.set_status(job_id, status="canceled")
    return {"status": "canceled", "job_id": job_id}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, request: Request) -> dict[str, Any]:
    _localhost_only(request)
    p = _procs.get(job_id)
    if p and p.poll() is None:
        p.terminate()
    _procs.pop(job_id, None)
    d = J.job_path(job_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return {"status": "deleted", "job_id": job_id}
