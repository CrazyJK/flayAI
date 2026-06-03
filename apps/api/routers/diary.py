"""일기형 대화 API 라우터.

- POST /api/diary/chat          (SSE) 일상 대화 + 회상. 세션 자동 이어가기/생성.
- GET  /api/diary/sessions      세션 목록(히스토리)
- GET  /api/diary/sessions/{id} 세션 transcript(회상 카드·열람 공용)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from packages.diary import store
from packages.diary.chat import _looks_like_recall, route_diary_chat
from packages.diary.htmlutil import build_message_html, save_upload_image
from packages.diary.vision import describe_images
from packages.indexer.db import connect
from packages.settings import load_config, repo_path

log = logging.getLogger(__name__)
router = APIRouter()

# 한 메시지당 첨부 이미지 상한
MAX_IMAGES = 8


class DiaryChatRequest(BaseModel):
    query: str = Field("", description="사용자 발화(이미지만 보낼 땐 비어도 됨)")
    session_id: int | None = Field(None, description="이어쓸 세션. 없으면 자동 결정")
    images: list[str] = Field(
        default_factory=list, description="첨부 이미지(data URL 또는 base64), 최대 8장"
    )


def _recent_history(conn, session_id: int, limit: int) -> list[dict]:
    """현재 세션 최근 메시지를 LLM 컨텍스트용 [{role, content}] 로(시간순)."""
    rows = conn.execute(
        "SELECT role, content FROM diary_messages WHERE session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def _prepare_images(
    cfg: dict, text: str, images: list[str]
) -> tuple[str, str | None, str]:
    """첨부 이미지 처리 → (저장용 content, raw_html, 응답 컨텍스트용 query).

    - 이미지를 data/diary_assets 로 추출(raw_html 의 <img>).
    - 비전 모델로 한국어 묘사 → content('[사진: ...]')에 합류(회상 가능) + 응답 컨텍스트.
    """
    imgs = images[:MAX_IMAGES]
    assets_dir = repo_path(cfg["data"].get("diary_assets", "data/diary_assets"))
    urls: list[str] = []
    for img in imgs:
        u = save_upload_image(img, assets_dir)
        if u:
            urls.append(u)
    raw_html = build_message_html(text, urls) if urls else None
    # 비전 묘사는 블로킹 httpx → 이벤트 루프 막지 않게 스레드로
    caption = await asyncio.to_thread(describe_images, imgs)

    photo = f"[사진: {caption}]" if caption else ("[사진]" if urls else "")
    store_content = "\n".join(p for p in (text, photo) if p) or "[사진]"

    if caption:
        reply_query = (
            f"{text}\n(방금 첨부한 사진 내용: {caption})"
            if text
            else f"(방금 사진을 한 장 올렸어. 사진 내용: {caption})"
        )
    else:
        reply_query = text or "(방금 사진을 올렸어.)"
    return store_content, raw_html, reply_query


@router.post("/api/diary/chat")
async def diary_chat(req: DiaryChatRequest):
    cfg = load_config()
    ctx_n = int(cfg.get("diary", {}).get("context_messages", 12))

    conn = connect()
    # 세션 확보(이어가기/생성) + 직전 컨텍스트
    session_id = req.session_id or store.get_or_create_session(conn)
    history = _recent_history(conn, session_id, ctx_n)

    text = (req.query or "").strip()
    if req.images:
        store_content, raw_html, reply_query = await _prepare_images(cfg, text, req.images)
    else:
        store_content, raw_html, reply_query = text, None, text

    # 회상 질문(이미지 없는 순수 회상 요청)은 '기억'이 아니라 '물음'이므로 색인 제외
    # — 색인하면 과거 질문이 새 질문과 매칭돼 회상을 오염시킨다.
    index = not (not req.images and _looks_like_recall(text))
    # 사용자 메시지 저장(임베딩까지). 이미지 묘사가 content 에 합류해 회상 가능.
    user_msg_id = store.add_message(
        conn, session_id, "user", store_content, raw_html=raw_html, embed=True, index=index
    )

    async def sse() -> AsyncGenerator[bytes, None]:
        def _emit(ev: dict[str, Any]) -> bytes:
            return ("data: " + json.dumps(ev, ensure_ascii=False, default=str) + "\n\n").encode(
                "utf-8"
            )

        # 세션 식별자를 먼저 알려 프론트가 이어쓰기 가능하게
        yield _emit({"type": "session", "session_id": session_id})
        full = ""
        final = ""
        try:
            async for ev in route_diary_chat(
                conn, reply_query, history=history, exclude_message_id=user_msg_id
            ):
                t = ev.get("type")
                if t == "token":
                    full += str(ev.get("text") or "")
                elif t == "done":
                    final = str(ev.get("message") or "")
                yield _emit(ev)
        except Exception as e:
            log.exception("diary chat error: %s", e)
            yield _emit({"type": "error", "message": str(e)})
        finally:
            # 어시스턴트 응답 저장 — 정리된 최종본(done) 우선(임베딩 안 함: 회상 대상은 내 말 위주)
            saved = (final or full).strip()
            if saved:
                store.add_message(conn, session_id, "assistant", saved, embed=False)
            conn.close()

    return StreamingResponse(
        sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.get("/api/diary/sessions")
def diary_sessions(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    conn = connect()
    try:
        return {"items": store.list_sessions(conn, limit=limit, offset=offset)}
    finally:
        conn.close()


@router.get("/api/diary/sessions/{session_id}")
def diary_session_detail(session_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        tr = store.get_session_transcript(conn, session_id)
        if not tr:
            raise HTTPException(404, "session not found")
        return tr
    finally:
        conn.close()
