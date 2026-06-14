"""자막 생성 API — 외부에서 opus 로 신청 → 큐 적재 → 야간 드레인이 처리.

설계: docs/subtitle-plan.md. 신청(POST)은 외부 진입점이라 개방(opus 검증)하고,
제어(드레인 트리거/삭제)는 admin 과 동일하게 localhost 전용.

엔드포인트(prefix=/api/subtitle):
  POST   /requests           {opus, task} -> 큐 적재 (외부 신청)
  GET    /requests           큐/이력 목록
  GET    /requests/{id}      상태(폴링)
  POST   /drain              지금 드레인(서브프로세스) — 보통은 야간 스케줄러
  DELETE /requests/{id}      신청 삭제
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from packages.indexer.db import connect
from packages.settings import REPO_ROOT
from packages.subtitler import db as Q

router = APIRouter(prefix="/api/subtitle", tags=["subtitle"])
log = logging.getLogger(__name__)

_VALID_TASKS = ("generate", "resync", "both")

# 실행 중 드레인 서브프로세스(동시 1개 — JSON 직렬화 대상 아님)
_drain_proc: dict[str, subprocess.Popen] = {}


class SubtitleRequest(BaseModel):
    opus: str = Field(..., description="자막을 만들 영상의 opus")
    task: str = Field("generate", description="generate | resync | both")


def _localhost_only(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "localhost", "::1", "ai.kamoru.jk"):
        raise HTTPException(403, "this subtitle endpoint is localhost-only")


def _conn():
    conn = connect()
    Q.init_schema(conn)  # 자막 큐/캐시 스키마(멱등)
    return conn


@router.post("/requests")
def create_request(req: SubtitleRequest) -> dict[str, Any]:
    """외부 신청 — opus 검증 후 큐 적재(즉시 처리하지 않음)."""
    if req.task not in _VALID_TASKS:
        raise HTTPException(400, f"task 는 {' | '.join(_VALID_TASKS)}")
    conn = _conn()
    try:
        # instance(재생영상 보유) 인지 검증 — 드라이브가 지금 오프라인이어도 경로만 있으면 통과
        row = conn.execute(
            "SELECT video_path FROM posters WHERE opus=?", (req.opus,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"opus 없음: {req.opus}")
        if not row["video_path"]:
            raise HTTPException(400, f"재생 영상 없는 opus(instance 아님): {req.opus}")
        jid, created = Q.enqueue(conn, req.opus, req.task)
        return {
            "id": jid,
            "opus": req.opus,
            "task": req.task,
            "status": "queued",
            "created": created,
        }
    finally:
        conn.close()


@router.get("/requests")
def list_requests(limit: int = 100) -> dict[str, Any]:
    conn = _conn()
    try:
        return {"jobs": Q.list_jobs(conn, limit=limit)}
    finally:
        conn.close()


@router.get("/requests/{job_id}")
def request_status(job_id: int) -> dict[str, Any]:
    conn = _conn()
    try:
        job = Q.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "request not found")
        return job
    finally:
        conn.close()


@router.delete("/requests/{job_id}")
def delete_request(job_id: int, request: Request) -> dict[str, Any]:
    _localhost_only(request)
    conn = _conn()
    try:
        ok = Q.delete_job(conn, job_id)
        if not ok:
            raise HTTPException(404, "request not found")
        return {"status": "deleted", "id": job_id}
    finally:
        conn.close()


@router.post("/drain")
def drain_now(request: Request) -> dict[str, Any]:
    """지금 큐를 드레인(서브프로세스). 보통은 야간 스케줄러가 CLI 로 직접 호출."""
    _localhost_only(request)
    p = _drain_proc.get("drain")
    if p and p.poll() is None:
        raise HTTPException(409, "드레인이 이미 실행 중입니다")
    conn = _conn()
    try:
        pending = sum(
            1 for j in Q.list_jobs(conn, limit=10000) if j["status"] in ("queued", "running")
        )
    finally:
        conn.close()
    venv_python = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    proc = subprocess.Popen(
        [venv_python, "-m", "packages.subtitler.cli", "drain"],
        cwd=str(REPO_ROOT),
    )
    _drain_proc["drain"] = proc
    return {"status": "draining", "pending": pending}
