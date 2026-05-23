"""관리자 API 라우터 — 모니터링 대시보드 + 인덱서 작업 트리거.

엔드포인트:
  GET  /api/admin/dashboard          전체 시스템 현황 한 번에 조회
  GET  /api/admin/jobs               실행 중·완료 작업 목록
  POST /api/admin/jobs/{job}         인덱서 작업 시작
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from packages.indexer.db import connect
from packages.indexer.state import load_state
from packages.settings import REPO_ROOT, load_config

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = logging.getLogger(__name__)

# 허용된 인덱서 작업 목록
ALLOWED_JOBS: set[str] = {
    "load",
    "scan",
    "history",
    "fts",
    "all",
    "refresh",
    "rebuild",
    "translate",
    "embed",
    "embed-clip",
    "extract-faces",
    "cluster-faces",
    "ocr-posters",
    "caption-posters",
    "sync-payload",
}

# 일괄(파이프라인) 작업의 단계 정의 — 단계별 진행상황을 추적해 흐름도로 보여준다.
# refresh/rebuild 는 동일 순서이며, rebuild 만 load 가 --rebuild(전체 재적재).
PIPELINE_DEFS: dict[str, list[tuple[str, list[str]]]] = {
    "refresh": [
        ("load", []),
        ("scan", []),
        ("history", []),
        ("fts", []),
        ("sync-payload", []),
    ],
    "rebuild": [
        ("load", ["--rebuild"]),
        ("scan", []),
        ("history", []),
        ("fts", []),
        ("sync-payload", []),
    ],
}

# 실행 중·완료 작업 상태 (메모리 전용 — 재시작 시 초기화)
_running_jobs: dict[str, dict[str, Any]] = {}


def _localhost_only(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "localhost", "::1", "ai.kamoru.jk"):
        raise HTTPException(403, "admin endpoints are localhost-only")


# ---------------------------------------------------------------------------
# 대시보드
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    """Qdrant · SQLite · Ollama · 인덱서 현황을 한 번에 반환."""
    _localhost_only(request)
    qdrant_data, sqlite_data, ollama_data, indexer_data = await asyncio.gather(
        asyncio.to_thread(_qdrant_stats),
        asyncio.to_thread(_sqlite_stats),
        _ollama_stats(),
        asyncio.to_thread(_indexer_stats),
    )
    return {
        "qdrant": qdrant_data,
        "sqlite": sqlite_data,
        "ollama": ollama_data,
        "indexer": indexer_data,
        "jobs": dict(_running_jobs),
    }


@router.get("/monitor")
async def monitor(request: Request) -> dict[str, Any]:
    """실시간 모니터링용 경량 엔드포인트 — system(CPU/RAM/GPU) + qdrant + ollama.

    무거운 SQLite COUNT(*)·인덱서 집계는 제외해 자주(수초 간격) 폴링해도 부하가 적다.
    """
    _localhost_only(request)
    system_data, qdrant_data, ollama_data = await asyncio.gather(
        asyncio.to_thread(_system_stats),
        asyncio.to_thread(_qdrant_stats),
        _ollama_stats(),
    )
    return {"system": system_data, "qdrant": qdrant_data, "ollama": ollama_data}


# ---------------------------------------------------------------------------
# 인덱서 작업
# ---------------------------------------------------------------------------


@router.get("/jobs")
def list_jobs(request: Request) -> dict[str, Any]:
    """현재 메모리에 보관된 작업 상태 목록 반환."""
    _localhost_only(request)
    return {"jobs": dict(_running_jobs)}


@router.post("/jobs/{job}")
async def start_job(job: str, request: Request) -> dict[str, Any]:
    """인덱서 CLI 작업을 서브프로세스로 실행한다.

    이미 실행 중이면 중복 실행하지 않고 현재 상태를 반환한다.
    """
    _localhost_only(request)
    if job not in ALLOWED_JOBS:
        raise HTTPException(
            400,
            f"알 수 없는 작업: '{job}'. 허용 목록: {sorted(ALLOWED_JOBS)}",
        )

    info = _running_jobs.get(job)
    if info and info.get("status") == "running":
        return {"status": "already_running", "job": job, "pid": info.get("pid")}

    # sys.executable은 디버거/uv 환경에선 프로젝트 venv가 아닐 수 있으므로 명시적으로 지정
    venv_python = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")

    # 파이프라인(refresh/rebuild): 단계별 서브프로세스로 실행하며 진행상황을 추적
    if job in PIPELINE_DEFS:
        _running_jobs[job] = {
            "status": "running",
            "started_at": time.time(),
            "current": 0,
            "steps": [{"step": s, "args": a, "status": "pending"} for s, a in PIPELINE_DEFS[job]],
        }
        asyncio.get_event_loop().run_in_executor(None, _run_pipeline_sync, job, venv_python)
        return {"status": "started", "job": job, "pipeline": True}

    # 단일 작업
    # Windows 디버거 환경에서 asyncio.create_subprocess_exec가 NotImplementedError를
    # 발생시킬 수 있으므로 subprocess.Popen 사용
    proc = subprocess.Popen(
        [venv_python, "-m", "packages.indexer.cli", job],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    _running_jobs[job] = {
        "status": "running",
        "pid": proc.pid,
        "started_at": time.time(),
    }
    asyncio.get_event_loop().run_in_executor(None, _wait_job_sync, job, proc)
    return {"status": "started", "job": job, "pid": proc.pid}


def _wait_job_sync(job: str, proc: subprocess.Popen) -> None:
    """서브프로세스 완료를 동기적으로 기다리고 결과를 _running_jobs에 기록한다."""
    try:
        stdout, stderr = proc.communicate()
        _running_jobs[job].update(
            {
                "status": "done" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[-4000:],
                "stderr": stderr.decode("utf-8", errors="replace")[-4000:],
                "finished_at": time.time(),
            }
        )
    except Exception as e:
        _running_jobs[job].update({"status": "error", "error": str(e)})


def _run_pipeline_sync(job: str, venv_python: str) -> None:
    """파이프라인 단계를 순차 실행하며 _running_jobs[job]['steps'] 진행상황을 갱신한다.

    각 단계는 별도 서브프로세스(`cli <step>`)로 실행하고, 단계 상태를
    pending -> running -> done/failed 로 갱신한다. 한 단계가 실패하면 중단.
    """
    info = _running_jobs[job]
    steps = info["steps"]
    for i, st in enumerate(steps):
        info["current"] = i
        st["status"] = "running"
        st["started_at"] = time.time()
        try:
            proc = subprocess.Popen(
                [venv_python, "-m", "packages.indexer.cli", st["step"], *st["args"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(REPO_ROOT),
            )
            out, err = proc.communicate()
            st["finished_at"] = time.time()
            st["returncode"] = proc.returncode
            st["stdout"] = out.decode("utf-8", errors="replace")[-2000:]
            if proc.returncode == 0:
                st["status"] = "done"
            else:
                st["status"] = "failed"
                st["stderr"] = err.decode("utf-8", errors="replace")[-2000:]
                info["status"] = "failed"
                info["finished_at"] = time.time()
                return
        except Exception as e:
            st["status"] = "error"
            info["status"] = "error"
            info["error"] = str(e)
            info["finished_at"] = time.time()
            return
    info["status"] = "done"
    info["finished_at"] = time.time()


# ---------------------------------------------------------------------------
# 내부 수집 함수
# ---------------------------------------------------------------------------


def _qdrant_stats() -> dict[str, Any]:
    """Qdrant 컬렉션별 포인트 수·상태·벡터 차원을 조회한다.

    qdrant-client 버전마다 CollectionInfo 속성이 달라지므로 getattr 로 안전하게 접근한다.
    - vectors_count  : v1.7 이하 — 전체 벡터 수 (points × 벡터 수)
    - indexed_vectors_count : v1.7+ — HNSW 인덱스에 들어간 벡터 수
    둘 다 없으면 points_count 를 대신 사용한다.
    """
    try:
        from qdrant_client import QdrantClient

        cfg = load_config()
        url: str = cfg["server"]["qdrant"]
        qc = QdrantClient(url=url)
        cols = qc.get_collections().collections
        result: list[dict[str, Any]] = []
        for col in cols:
            try:
                info = qc.get_collection(col.name)
                points: int = getattr(info, "points_count", None) or 0
                # vectors_count 는 일부 버전에만 있음 — 없으면 points_count 로 대체
                vectors: int = (
                    getattr(info, "vectors_count", None)
                    or getattr(info, "indexed_vectors_count", None)
                    or points
                )
                # 벡터 차원 (named vectors 지원 고려)
                dim: int | None = None
                try:
                    params = info.config.params  # type: ignore[union-attr]
                    if hasattr(params, "vectors"):
                        v = params.vectors
                        if hasattr(v, "size"):
                            dim = int(v.size)
                        elif isinstance(v, dict):
                            first = next(iter(v.values()), None)
                            if first and hasattr(first, "size"):
                                dim = int(first.size)
                except Exception:
                    pass
                result.append(
                    {
                        "name": col.name,
                        "points_count": points,
                        "vectors_count": vectors,
                        "dim": dim,
                        "status": str(info.status),
                    }
                )
            except Exception as e:
                result.append({"name": col.name, "error": str(e)})
        return {"available": True, "collections": result}
    except Exception as e:
        log.warning("qdrant stats error: %s", e)
        return {"available": False, "error": str(e), "collections": []}


def _sqlite_stats() -> dict[str, Any]:
    """SQLite 테이블별 레코드 수를 조회한다.

    sqlite_master 에서 동적으로 테이블 목록을 가져오므로
    스키마가 바뀌어도 자동 반영된다.
    """
    try:
        conn = connect()
        try:
            raw_tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            tables: list[dict[str, Any]] = []
            for row in raw_tables:
                name: str = row["name"]
                # FTS 내부 보조 테이블은 제외
                if (
                    any(
                        name.startswith(p)
                        for p in (
                            "sqlite_",
                            "videos_fts_",
                            "videos_fts_content",
                            "videos_fts_data",
                            "videos_fts_docsize",
                            "videos_fts_idx",
                            "videos_fts_config",
                        )
                    )
                    or name == "videos_fts"
                ):
                    continue
                try:
                    count: int = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                    tables.append({"name": name, "count": count})
                except Exception:
                    tables.append({"name": name, "count": -1})

            # FTS5 가상 테이블은 별도로 추가
            try:
                fts_count: int = conn.execute("SELECT COUNT(*) FROM videos_fts").fetchone()[0]
                tables.append({"name": "videos_fts", "count": fts_count, "note": "FTS5"})
            except Exception:
                pass

            # 쿼리 로그 최근 24h 건수 추가 정보
            try:
                import time as _time

                cutoff = int(_time.time()) - 86400
                recent_queries: int = conn.execute(
                    "SELECT COUNT(*) FROM query_log WHERE ts >= ?", (cutoff,)
                ).fetchone()[0]
            except Exception:
                recent_queries = 0

            return {"available": True, "tables": tables, "recent_queries_24h": recent_queries}
        finally:
            conn.close()
    except Exception as e:
        log.warning("sqlite stats error: %s", e)
        return {"available": False, "error": str(e), "tables": []}


async def _ollama_stats() -> dict[str, Any]:
    """Ollama REST API로 설치된 모델 목록과 현재 로드된 모델을 조회한다.

    - /api/tags  : 설치된 모델 목록
    - /api/ps    : 현재 VRAM에 로드된 모델 (Ollama 0.1.33+)
    """
    try:
        cfg = load_config()
        base_url: str = cfg["server"]["ollama"]
        async with httpx.AsyncClient(timeout=5.0) as client:
            tags_resp = await client.get(f"{base_url}/api/tags")
            models: list[dict] = []
            if tags_resp.status_code == 200:
                models = tags_resp.json().get("models", [])

            running: list[dict] = []
            try:
                ps_resp = await client.get(f"{base_url}/api/ps")
                if ps_resp.status_code == 200:
                    running = ps_resp.json().get("models", [])
            except Exception:
                pass

        # 불필요한 대용량 필드 제거 (modelfile, template 등)
        # running 모델은 이름으로 빠르게 조회할 수 있게 dict로 변환
        running_map: dict[str, dict] = {}
        for m in running:
            name = m.get("name", "")
            running_map[name] = m
            # "model:tag" 형태일 때 태그 없는 이름도 등록
            base = name.split(":")[0]
            if base not in running_map:
                running_map[base] = m

        slim_models = []
        for m in models:
            mname: str = m.get("name", "")
            details: dict = m.get("details", {})
            # running 여부: 정확한 이름 또는 base 이름으로 매칭
            run_info = running_map.get(mname) or running_map.get(mname.split(":")[0])
            slim_models.append(
                {
                    "name": mname,
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                    # details 필드: parameter_size, quantization_level, family 등
                    "parameter_size": details.get("parameter_size"),
                    "quantization": details.get("quantization_level"),
                    "family": details.get("family"),
                    # VRAM 로드 상태
                    "loaded": run_info is not None,
                    "size_vram": run_info.get("size_vram") if run_info else None,
                    "expires_at": run_info.get("expires_at") if run_info else None,
                }
            )
        return {"available": True, "models": slim_models, "running_count": len(running)}
    except Exception as e:
        log.warning("ollama stats error: %s", e)
        return {"available": False, "error": str(e), "models": [], "running_count": 0}


def _system_stats() -> dict[str, Any]:
    """CPU/RAM(psutil) + GPU/VRAM/온도(nvidia-smi)를 수집한다. 경량·자주 폴링용.

    - CPU: psutil.cpu_percent(interval=None) — 직전 호출 이후 사용률(비차단).
    - GPU: nvidia-smi 1회 호출(util%, VRAM used/total MiB, 온도). 미설치 시 gpu_error.
    """
    out: dict[str, Any] = {"available": True}
    try:
        import psutil

        out["cpu_percent"] = psutil.cpu_percent(interval=None)
        out["cpu_count"] = psutil.cpu_count()
        vm = psutil.virtual_memory()
        out["ram_percent"] = vm.percent
        out["ram_used"] = int(vm.used)
        out["ram_total"] = int(vm.total)
    except Exception as e:
        out["cpu_error"] = str(e)
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
            if len(parts) >= 4:
                out["gpu_available"] = True
                out["gpu_percent"] = float(parts[0])
                out["vram_used_mib"] = float(parts[1])
                out["vram_total_mib"] = float(parts[2])
                out["gpu_temp"] = float(parts[3])
                if len(parts) >= 5:
                    out["gpu_name"] = parts[4]
    except Exception as e:
        out["gpu_error"] = str(e)
    return out


def _qdrant_points_counts() -> dict[str, int]:
    """Qdrant 컬렉션별 points_count를 {컬렉션명: 포인트수} 딕셔너리로 반환."""
    try:
        from qdrant_client import QdrantClient

        cfg = load_config()
        qc = QdrantClient(url=cfg["server"]["qdrant"])
        result: dict[str, int] = {}
        for name in ("videos", "posters_clip", "poster_ocr", "faces"):
            try:
                info = qc.get_collection(name)
                result[name] = getattr(info, "points_count", 0) or 0
            except Exception:
                result[name] = 0
        return result
    except Exception:
        return {}


def _indexer_stats() -> dict[str, Any]:
    """state.json + DB + Qdrant 집계로 인덱서 진행 현황을 반환한다.

    벡터 기반 단계(embed_text, embed_clip, ocr_posters, extract_faces)는
    Qdrant points_count를 신뢰할 수 있는 완료 수로 사용한다.
    state.json이나 SQLite 컬럼은 scan/load 재실행으로 초기화될 수 있기 때문.
    """
    try:
        state = load_state()
        conn = connect()
        try:
            total_videos: int = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            total_posters: int = conn.execute("SELECT COUNT(*) FROM posters").fetchone()[0]
            total_actresses: int = conn.execute("SELECT COUNT(*) FROM actresses").fetchone()[0]
            # 실제 번역 완료 수 (title_ko 가 있는 영상)
            translated: int = conn.execute(
                "SELECT COUNT(*) FROM videos WHERE title_ko IS NOT NULL AND title_ko != ''"
            ).fetchone()[0]
            # 얼굴 클러스터 수
            face_clusters: int = conn.execute("SELECT COUNT(*) FROM face_clusters").fetchone()[0]
            labeled_clusters: int = conn.execute(
                "SELECT COUNT(*) FROM face_clusters WHERE canonical_name IS NOT NULL"
            ).fetchone()[0]
            # 캡션 완료 수 (caption 이 비어있지 않은 포스터)
            captioned: int = conn.execute(
                "SELECT COUNT(*) FROM posters WHERE caption IS NOT NULL AND caption != ''"
            ).fetchone()[0]

        finally:
            conn.close()

        # Qdrant points_count를 벡터 단계 완료 수의 기준으로 사용
        qdrant_counts = _qdrant_points_counts()
        embed_done = qdrant_counts.get("videos", 0)
        embed_clip_done = qdrant_counts.get("posters_clip", 0)
        ocr_done = qdrant_counts.get("poster_ocr", 0)
        faces_done = state.get("stages", {}).get("extract_faces", {}).get("completed", 0)

        pending = {
            "translate": max(0, total_videos - translated),
            "embed_text": max(0, total_videos - embed_done),
            "embed_clip": max(0, total_posters - embed_clip_done),
            "ocr_posters": max(0, total_posters - ocr_done),
            "extract_faces": max(0, total_posters - faces_done),
            "caption_posters": max(0, total_posters - captioned),
        }

        return {
            "available": True,
            "state": state.get("stages", {}),
            "totals": {
                "videos": total_videos,
                "posters": total_posters,
                "actresses": total_actresses,
                "face_clusters": face_clusters,
                "labeled_clusters": labeled_clusters,
            },
            "completed": {
                "translate": translated,
                "embed_text": embed_done,
                "embed_clip": embed_clip_done,
                "ocr_posters": ocr_done,
                "extract_faces": faces_done,
                "caption_posters": captioned,
            },
            "pending": pending,
        }
    except Exception as e:
        log.warning("indexer stats error: %s", e)
        return {"available": False, "error": str(e)}
