"""자막 생성 API — 외부에서 opus 로 신청 → 큐 적재 → 야간 드레인이 처리.

설계: docs/subtitle-plan.md. 신청(POST)은 외부 진입점이라 개방(opus 검증)하고,
제어(드레인 트리거/삭제)는 admin 과 동일하게 localhost 전용.

엔드포인트(prefix=/api/subtitle):
  POST   /requests           {opus, task} -> 큐 적재 (외부 신청)
  POST   /requests/bulk      {opuses[], task} -> 여러 건 적재 (목록 다중 선택)
  GET    /requests           큐/이력 목록
  GET    /requests/{id}      상태(폴링)
  GET    /candidates         무자막 instance 목록(생성 대상) + 검색/정렬/페이지
  GET    /subbed             자막 보유 영상 목록(resync 대상) + 최근 resync 결과
  POST   /scan               자막 유무 디스크 스캔(캐시 갱신) — localhost 전용
  POST   /enqueue-all        {task} -> 카테고리 전체 적재 — localhost 전용
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
from packages.subtitler import candidates as C
from packages.subtitler import db as Q

router = APIRouter(prefix="/api/subtitle", tags=["subtitle"])
log = logging.getLogger(__name__)

_VALID_TASKS = ("generate", "resync", "both")

# 실행 중 드레인 서브프로세스(동시 1개 — JSON 직렬화 대상 아님)
_drain_proc: dict[str, subprocess.Popen] = {}


class SubtitleRequest(BaseModel):
    opus: str = Field(..., description="자막을 만들 영상의 opus")
    task: str = Field("generate", description="generate | resync | both")


class BulkRequest(BaseModel):
    opuses: list[str] = Field(default_factory=list, description="신청할 opus 목록")
    task: str = Field("generate", description="generate | resync | both")


class EnqueueAllRequest(BaseModel):
    task: str = Field("generate", description="generate(무자막 전체) | resync(자막보유 전체)")
    only_reverted: bool = Field(False, description="resync 시 원본복원분만")
    q: str | None = Field(None, description="generate 시 검색어로 범위 제한(선택)")


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


# --- 목록(생성·resync 대상 선택) ----------------------------------


@router.post("/requests/bulk")
def create_bulk(req: BulkRequest) -> dict[str, Any]:
    """목록에서 다중 선택한 opus 들을 한 번에 큐 적재(중복은 건너뜀)."""
    if req.task not in _VALID_TASKS:
        raise HTTPException(400, f"task 는 {' | '.join(_VALID_TASKS)}")
    conn = _conn()
    try:
        created = skipped = invalid = 0
        for raw in req.opuses:
            op = (raw or "").strip()
            if not op:
                continue
            row = conn.execute("SELECT video_path FROM posters WHERE opus=?", (op,)).fetchone()
            if row is None or not row["video_path"]:
                invalid += 1
                continue
            _jid, was_new = Q.enqueue(conn, op, req.task)
            created += int(was_new)
            skipped += int(not was_new)
        return {"created": created, "skipped": skipped, "invalid": invalid}
    finally:
        conn.close()


@router.get("/candidates")
def list_candidates(
    q: str | None = None, sort: str = "like", limit: int = 60, offset: int = 0
) -> dict[str, Any]:
    """무자막 instance 목록(생성 대상). sort: like|play|recent|opus."""
    conn = _conn()
    try:
        res = C.list_candidates(conn, q=q, sort=sort, limit=limit, offset=offset)
        res["last_scan"] = C.last_scan_at(conn)
        return res
    finally:
        conn.close()


@router.get("/subbed")
def list_subbed(
    q: str | None = None, only_reverted: bool = False, limit: int = 60, offset: int = 0
) -> dict[str, Any]:
    """자막 보유 영상 목록(resync 대상) + 최근 resync 결과."""
    conn = _conn()
    try:
        return C.list_subbed(conn, only_reverted=only_reverted, q=q, limit=limit, offset=offset)
    finally:
        conn.close()


@router.post("/scan")
def scan_status(request: Request) -> dict[str, Any]:
    """자막 유무를 디스크에서 스캔해 캐시 갱신(드라이브 온라인 필요). localhost 전용."""
    _localhost_only(request)
    conn = _conn()
    try:
        return C.scan_status(conn)
    finally:
        conn.close()


@router.post("/enqueue-all")
def enqueue_all(req: EnqueueAllRequest, request: Request) -> dict[str, Any]:
    """카테고리 전체 일괄 신청 — generate(무자막 전체) 또는 resync(자막보유 전체). localhost 전용."""
    _localhost_only(request)
    if req.task not in ("generate", "resync"):
        raise HTTPException(400, "task 는 generate | resync")
    conn = _conn()
    try:
        if req.task == "generate":
            opuses = C.all_candidate_opuses(conn, q=req.q)
        else:
            opuses = C.all_subbed_opuses(conn, only_reverted=req.only_reverted)
        created = skipped = 0
        for op in opuses:
            _jid, was_new = Q.enqueue(conn, op, req.task)
            created += int(was_new)
            skipped += int(not was_new)
        return {"created": created, "skipped": skipped, "total": len(opuses)}
    finally:
        conn.close()
