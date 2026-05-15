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
    get_actress, get_video, search_videos, similar_to, stats,
)
from packages.settings import load_config

log = logging.getLogger(__name__)


# --- 모델 --------------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., description="사용자 자연어 질의")
    history: list[dict] = Field(default_factory=list)


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

@asynccontextmanager
async def _lifespan(app: FastAPI):
    cfg = load_config()
    host = cfg["server"]["host"]
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.error("FastAPI must bind to localhost only. config.server.host=%s", host)
        sys.exit(1)
    yield


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="flayAI", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg["server"]["cors_origins"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ---- health ----
    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    # ---- chat (SSE) ----
    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        async def sse() -> "anyio.abc.ByteStream":
            try:
                async for ev in route_chat(req.query, history=req.history):
                    line = "data: " + json.dumps(ev, ensure_ascii=False, default=str) + "\n\n"
                    yield line.encode("utf-8")
            except Exception as e:
                log.exception("chat error: %s", e)
                yield ("data: " + json.dumps(
                    {"type": "error", "message": str(e)}, ensure_ascii=False
                ) + "\n\n").encode("utf-8")

        return StreamingResponse(sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    # ---- search/videos ----
    @app.post("/api/search/videos")
    def search_videos_route(req: SearchVideosRequest):
        return {
            "items": search_videos(
                query=req.query, year=req.year, month=req.month,
                actress=req.actress, tag=req.tag, studio=req.studio,
                kind=req.kind, playable=req.playable, min_rank=req.min_rank,
                limit=req.limit,
            )
        }

    # ---- translate ----
    @app.post("/api/translate")
    def translate_route(req: TranslateRequest):
        conn = connect()
        try:
            with conn:
                out = translate_text(conn, req.text, target=req.target,
                                     sentencewise=req.sentencewise)
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
        client_host = (request.client.host if request.client else "")
        if client_host not in ("127.0.0.1", "localhost", "::1"):
            raise HTTPException(403, "admin endpoints are localhost-only")
        return stats()

    # ---- 포스터 파일 서빙 ----
    @app.get("/static/posters/{opus}")
    def poster_file(opus: str):
        conn = connect()
        try:
            row = conn.execute(
                "SELECT path FROM posters WHERE opus = ?", (opus,)).fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(404, "poster not found")
        p = Path(row["path"])
        if not p.exists():
            raise HTTPException(404, "poster file missing on disk")
        return FileResponse(str(p))

    return app


app = create_app()


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg["logging"]["level"],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "apps.api.main:app",
        host=cfg["server"]["host"],
        port=int(cfg["server"]["api_port"]),
        reload=False,
        log_level=cfg["logging"]["level"].lower(),
    )


if __name__ == "__main__":
    main()
