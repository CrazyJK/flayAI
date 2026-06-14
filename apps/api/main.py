"""flayAI FastAPI app.

AI_PLAN.md §8.1, §9.1.
- 127.0.0.1 only (binding 검증)
- CORS 화이트리스트
- 엔드포인트:
    POST /api/chat               (SSE 스트리밍)
    POST /api/search/videos      (필터 + 검색)
    POST /api/translate          (단일 텍스트)
    GET  /api/videos/{opus}
    GET  /api/actresses/{name}
    GET  /static/posters/{opus}  (포스터 파일 서빙)
    GET  /api/admin/stats        (운영 요약)
    GET  /healthz
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from packages.indexer.db import connect
from packages.indexer.translate import translate_text
from packages.rag.router import route_chat
from packages.rag.tools import (
    get_actress,
    get_video,
    search_videos,
    similar_to,
    stats,
)
from packages.settings import load_config

log = logging.getLogger(__name__)


# --- 모델 --------------------------------------------------------


class ChatRequest(BaseModel):
    query: str = Field(..., description="사용자 자연어 질의")
    history: list[dict] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=100, description="검색 결과 최대 개수")
    kind: str | None = Field(None, description="instance/archive 필터 (None/빈값 = 전체)")


class SearchVideosRequest(BaseModel):
    query: str = ""
    year: int | None = None
    month: int | None = None
    actress: str | None = None
    tag: str | None = None
    studio: str | None = None
    kind: str = "any"
    playable: bool | None = None
    min_rank: int | None = None
    limit: int = 10


class TranslateRequest(BaseModel):
    text: str
    target: str = "ko"
    sentencewise: bool = False


# --- 앱 ----------------------------------------------------------


async def _warmup_face_model() -> None:
    """InsightFace buffalo_l 모델을 백그라운드로 미리 로드해 첫 요청 지연(10~30초)을 제거한다.

    - 이벤트 루프 차단 방지 위해 to_thread 사용
    - 실패해도 API 기동에는 영향 없음 (첫 호출 시 다시 시도)
    """
    import asyncio

    try:
        from packages.indexer.faces import _load_face_app

        await asyncio.to_thread(_load_face_app)
        log.info("InsightFace warmup done")
    except Exception as e:
        log.warning("InsightFace warmup failed (will retry on first request): %s", e)


def _quiet_exception_handler(loop, context):
    """Windows ProactorEventLoop에서 클라이언트 연결 종료 시 발생하는
    ConnectionResetError 콜백 로그를 억제한다."""
    exc = context.get("exception")
    if isinstance(exc, ConnectionResetError):
        return
    loop.default_exception_handler(context)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    import asyncio

    asyncio.get_running_loop().set_exception_handler(_quiet_exception_handler)

    cfg = load_config()
    host = cfg["server"]["host"]
    # hosts 파일로 127.0.0.1에 매핑된 로컬 도메인도 허용
    if host not in ("127.0.0.1", "localhost", "::1", "ai.kamoru.jk"):
        log.error("FastAPI must bind to localhost only. config.server.host=%s", host)
        sys.exit(1)
    # 일기 서브시스템 스키마/컬렉션 준비(멱등)
    try:
        from packages.diary.schema import ensure_diary_collection, init_diary_schema
        from packages.indexer.db import connect as _connect

        _c = _connect()
        init_diary_schema(_c)
        _c.close()
        from packages.indexer.embed_text import _qdrant

        ensure_diary_collection(_qdrant())
    except Exception as e:
        log.warning("diary 초기화 건너뜀(첫 요청 때 재시도): %s", e)
    # 백그라운드 워밍업 — 기동을 막지 않음
    asyncio.create_task(_warmup_face_model())
    # 채팅 LLM(qwen)은 상주시키지 않는다 — 첫 사용 시 로드되고 Ollama 기본(5분) 유휴 후 해제.
    # (영상 시청 등 다른 GPU 작업에 VRAM 양보. 인덱싱 진입 시엔 ollama_vram 훅이 언로드.)
    yield


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="flayAI", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg["server"]["cors_origins"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # ---- health ----
    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    # ---- chat (SSE) ----
    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        async def sse() -> AsyncGenerator[bytes, None]:
            try:
                async for ev in route_chat(
                    req.query, history=req.history, limit=req.limit, kind=req.kind
                ):
                    line = "data: " + json.dumps(ev, ensure_ascii=False, default=str) + "\n\n"
                    yield line.encode("utf-8")
            except Exception as e:
                log.exception("chat error: %s", e)
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
                    + "\n\n"
                ).encode("utf-8")

        return StreamingResponse(
            sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    # ---- search/videos ----
    @app.post("/api/search/videos")
    def search_videos_route(req: SearchVideosRequest):
        return {
            "items": search_videos(
                query=req.query,
                year=req.year,
                month=req.month,
                actress=req.actress,
                tag=req.tag,
                studio=req.studio,
                kind=req.kind,
                playable=req.playable,
                min_rank=req.min_rank,
                limit=req.limit,
            )
        }

    # ---- translate ----
    @app.post("/api/translate")
    def translate_route(req: TranslateRequest):
        conn = connect()
        try:
            with conn:
                out = translate_text(
                    conn, req.text, target=req.target, sentencewise=req.sentencewise
                )
            return {"text": out}
        finally:
            conn.close()

    # ---- video / actress 상세 ----
    @app.get("/api/videos/{opus}")
    def video_detail(opus: str):
        v = get_video(opus)
        if not v:
            raise HTTPException(404, "video not found")
        return v

    @app.get("/api/actresses/{name}")
    def actress_detail(name: str):
        a = get_actress(name)
        if not a:
            raise HTTPException(404, "actress not found")
        return a

    @app.get("/api/similar/{opus}")
    def similar_route(opus: str, exclude_watched: bool = True, limit: int = 10):
        return {"items": similar_to(opus, exclude_watched=exclude_watched, limit=limit)}

    @app.get("/api/admin/stats")
    def admin_stats(request: Request):
        # localhost-only
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "localhost", "::1", "ai.kamoru.jk"):
            raise HTTPException(403, "admin endpoints are localhost-only")
        return stats()

    # ---- 포스터 파일 서빙 ----
    @app.get("/static/posters/{opus}")
    def poster_file(opus: str):
        conn = connect()
        try:
            row = conn.execute("SELECT path FROM posters WHERE opus = ?", (opus,)).fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(404, "poster not found")
        p = Path(row["path"])
        if not p.exists():
            raise HTTPException(404, "poster file missing on disk")
        return FileResponse(str(p))

    # ---- 이미지/얼굴 검색 (M4) ----
    from apps.api.routers.image import router as image_router

    app.include_router(image_router)

    # ---- 포스터 OCR 검색 (M5) ----
    from apps.api.routers.ocr import router as ocr_router

    app.include_router(ocr_router)

    # ---- 관리자 대시보드 ----
    from apps.api.routers.admin import router as admin_router

    app.include_router(admin_router)

    # ---- 일기형 대화 ----
    from apps.api.routers.diary import router as diary_router

    app.include_router(diary_router)

    # ---- 영상 안정화 ----
    from apps.api.routers.stabilize import router as stabilize_router

    app.include_router(stabilize_router)

    # ---- 자막 생성(STT→번역) ----
    from apps.api.routers.subtitle import router as subtitle_router

    app.include_router(subtitle_router)

    # ---- 일기 첨부 이미지 서빙 (레거시 base64 추출분) ----
    @app.get("/static/diary-assets/{name}")
    def diary_asset(name: str):
        from packages.settings import repo_path

        # 경로 탈출 방지: 파일명만 허용
        if "/" in name or "\\" in name or ".." in name:
            raise HTTPException(400, "bad name")
        p = repo_path(cfg["data"].get("diary_assets", "data/diary_assets")) / name
        if not p.exists():
            raise HTTPException(404, "asset not found")
        return FileResponse(str(p))

    return app


app = create_app()


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg["logging"]["level"],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ssl_keyfile = cfg["server"].get("ssl_keyfile")
    ssl_certfile = cfg["server"].get("ssl_certfile")
    uvicorn.run(
        "apps.api.main:app",
        host=cfg["server"]["host"],
        port=int(cfg["server"]["api_port"]),
        reload=False,
        log_level=cfg["logging"]["level"].lower(),
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )


if __name__ == "__main__":
    main()
