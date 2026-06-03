"""일기형 대화 API 라우터.

- POST /api/diary/chat          (SSE) 일상 대화 + 회상. 세션 자동 이어가기/생성.
- GET  /api/diary/sessions      세션 목록(히스토리)
- GET  /api/diary/sessions/{id} 세션 transcript(회상 카드·열람 공용)
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from packages.diary import store
from packages.diary.chat import route_diary_chat
from packages.indexer.db import connect
from packages.settings import load_config

log = logging.getLogger(__name__)
router = APIRouter()


class DiaryChatRequest(BaseModel):
    query: str = Field(..., description="사용자 발화")
    session_id: int | None = Field(None, description="이어쓸 세션. 없으면 자동 결정")


def _recent_history(conn, session_id: int, limit: int) -> list[dict]:
    """현재 세션 최근 메시지를 LLM 컨텍스트용 [{role, content}] 로(시간순)."""
    rows = conn.execute(
        "SELECT role, content FROM diary_messages WHERE session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


@router.post("/api/diary/chat")
async def diary_chat(req: DiaryChatRequest):
    cfg = load_config()
    ctx_n = int(cfg.get("diary", {}).get("context_messages", 12))

    conn = connect()
    # 세션 확보(이어가기/생성) + 직전 컨텍스트 + 사용자 메시지 저장(임베딩까지)
    session_id = req.session_id or store.get_or_create_session(conn)
    history = _recent_history(conn, session_id, ctx_n)
    user_msg_id = store.add_message(conn, session_id, "user", req.query, embed=True)

    async def sse() -> AsyncGenerator[bytes, None]:
        def _emit(ev: dict[str, Any]) -> bytes:
            return ("data: " + json.dumps(ev, ensure_ascii=False, default=str) + "\n\n").encode(
                "utf-8"
            )

        # 세션 식별자를 먼저 알려 프론트가 이어쓰기 가능하게
        yield _emit({"type": "session", "session_id": session_id})
        full = ""
        try:
            async for ev in route_diary_chat(
                conn, req.query, history=history, exclude_message_id=user_msg_id
            ):
                if ev.get("type") == "token":
                    full += str(ev.get("text") or "")
                yield _emit(ev)
        except Exception as e:
            log.exception("diary chat error: %s", e)
            yield _emit({"type": "error", "message": str(e)})
        finally:
            # 어시스턴트 응답 저장(임베딩 안 함 — 회상 대상은 내 말 위주)
            if full.strip():
                store.add_message(conn, session_id, "assistant", full, embed=False)
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
