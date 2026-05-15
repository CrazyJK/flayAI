"""LLM 기반 라우터 (Ollama tool calling).

AI_PLAN.md §7.1.
- 1차: Ollama /api/chat with tools=TOOL_SCHEMA
- 폴백: tool 호출 안 했으면 search_videos(query=...) 직접 호출
- 결과를 LLM 에 다시 넣어 자연어 응답 생성 (스트리밍)

사용:
    async for chunk in route_chat(messages):
        yield chunk
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.rag.tools import TOOL_DISPATCH, TOOL_SCHEMA, search_videos
from packages.settings import load_config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "당신은 사용자의 비디오 컬렉션 검색을 돕는 한국어 비서입니다. "
    "사용자의 질문에 답하기 위해 제공된 도구(search_videos, similar_to, get_video, "
    "get_actress, stats)를 적극 사용하세요. 배우 별칭(예: '葵' / 'Aoi' / 'Sora Aoi')은 "
    "search_videos(actress=...) 가 자동 정규화합니다. 연도/월/제작사가 명시되면 메타 "
    "필터로 넘기세요. '지금 볼 수 있는'은 kind='instance', playable=true 로, "
    "'옛날에 갖고 있던'은 kind='archive' 로 매핑하세요. 도구 호출 결과를 토대로 "
    "간결한 한국어로 답하고, 결과 카드의 opus/제목/제작사/연도/배우만 짧게 요약하세요."
)


def _ollama_url(path: str) -> str:
    cfg = load_config()
    return cfg["server"]["ollama"].rstrip("/") + path


def _llm_model() -> str:
    return load_config()["models"]["llm"]


def _exec_tool(name: str, args: dict) -> Any:
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"bad args: {e}"}
    except Exception as e:
        log.exception("tool %s failed", name)
        return {"error": str(e)}


async def _call_chat(client: httpx.AsyncClient, messages: list[dict],
                     tools: list[dict] | None, stream: bool) -> dict | AsyncIterator[dict]:
    payload = {
        "model": _llm_model(),
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.2},
    }
    if tools:
        payload["tools"] = tools

    if not stream:
        r = await client.post(_ollama_url("/api/chat"), json=payload, timeout=120.0)
        r.raise_for_status()
        return r.json()

    async def gen():
        async with client.stream("POST", _ollama_url("/api/chat"),
                                 json=payload, timeout=None) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    return gen()


async def route_chat(user_query: str,
                     history: list[dict] | None = None) -> AsyncIterator[dict]:
    """async generator. event dict 시리즈를 yield.

    이벤트 타입:
        {"type": "tool_call",   "name": str, "args": dict}
        {"type": "tool_result", "name": str, "result": Any}
        {"type": "token",       "text": str}
        {"type": "done",        "message": str, "tool_calls": list, "results": list}
    """
    history = history or []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_query},
    ]

    async with httpx.AsyncClient() as client:
        # 1차: tool 결정
        first = await _call_chat(client, messages, tools=TOOL_SCHEMA, stream=False)
        msg = first.get("message", {}) or {}
        tool_calls = msg.get("tool_calls") or []

        # Ollama 가 tool 호출 안 했고 응답도 없으면 폴백
        if not tool_calls and not (msg.get("content") or "").strip():
            tool_calls = [{
                "function": {
                    "name": "search_videos",
                    "arguments": {"query": user_query, "limit": 10},
                }
            }]

        results_for_history: list[dict] = []
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}
            yield {"type": "tool_call", "name": name, "args": raw_args}
            result = _exec_tool(name, raw_args)
            yield {"type": "tool_result", "name": name, "result": result}
            results_for_history.append({"name": name, "args": raw_args, "result": result})

        # 도구 결과를 메시지로 추가 후 최종 답변 스트리밍
        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for r in results_for_history:
                messages.append({
                    "role": "tool",
                    "name": r["name"],
                    "content": json.dumps(r["result"], ensure_ascii=False, default=str),
                })
        else:
            # tool 안 쓴 경우 첫 응답이 곧 답
            text = msg.get("content") or ""
            yield {"type": "token", "text": text}
            yield {"type": "done", "message": text, "tool_calls": [], "results": []}
            return

        full = ""
        gen = await _call_chat(client, messages, tools=None, stream=True)
        async for chunk in gen:
            piece = (chunk.get("message") or {}).get("content") or ""
            if piece:
                full += piece
                yield {"type": "token", "text": piece}
            if chunk.get("done"):
                break

        yield {"type": "done", "message": full,
               "tool_calls": [{"name": r["name"], "args": r["args"]} for r in results_for_history],
               "results": results_for_history}
