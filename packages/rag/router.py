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
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.rag.tools import TOOL_DISPATCH, TOOL_SCHEMA, search_videos
from packages.settings import load_config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "당신은 사용자의 비디오 컬렉션 검색을 돕는 한국어 비서입니다. "
    "사용자의 질문에 답하기 위해 제공된 도구(search_videos, similar_to, get_video, "
    "get_actress, stats)를 적극 사용하세요.\n"
    "\n"
    "[도구 선택 규칙 — 반드시 준수]\n"
    "- 질문에 품번(예: SSSS-123, ABC-456 같은 영문+숫자 코드)이 **명시되어 있을 때만** "
    "get_video / similar_to 를 호출하세요. 품번이 없으면 절대 호출하지 마세요.\n"
    "- 그 외 모든 자연어 검색('회사 배경', '2023년 7월', 'S1 평점 4 이상', "
    "'지금 볼 수 있는 ...', '배우 이름 출연작' 등)은 **반드시 search_videos** 를 "
    "사용하세요.\n"
    "- 배우 이름이 들어가면 search_videos(actress=...) 로 호출 (별칭 자동 정규화).\n"
    "- 연도/월/제작사가 명시되면 search_videos(year=, month=, studio=) 메타 필터.\n"
    "- '지금 볼 수 있는' / '재생 가능한' → search_videos(kind='instance', playable=true).\n"
    "- '옛날 / 예전에 갖고 있던' → search_videos(kind='archive').\n"
    "- 통계/집계 질문은 stats 호출.\n"
    "\n"
    "[출력 언어 — 반드시 준수]\n"
    "- 최종 답변은 **무조건 한국어**로 작성하세요. 중국어, 일본어, 영어 문장으로 "
    "답하지 마세요. 사용자 질문이 어떤 언어든 답변은 한국어입니다.\n"
    "- 제목·배우명 등 고유명사는 원문 그대로 두되, 설명·연결 문장은 한국어로 쓰세요.\n"
    "  예) '날짜', '월', '추천작', '출연작' 같은 단어는 한국어. '年', '月', "
    "'推荐作' 같은 한자 단어 사용 금지.\n"
    "- 날짜 표기는 'YYYY-MM' 또는 'YYYY년 M월' 형식.\n"
    "\n"
    "도구 호출 결과를 토대로 간결한 한국어로 답하고, 결과 카드의 "
    "opus/제목/제작사/연도/배우만 짧게 요약하세요."
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

        # 방어: 사용자 질문에 품번 패턴이 없는데 get_video/similar_to 호출 시
        # search_videos 로 강제 교체 (시스템 프롬프트를 무시한 LLM 오라우팅 방지)
        has_opus_in_query = bool(re.search(r"[A-Za-z]{2,7}-?\d{2,5}", user_query))
        if not has_opus_in_query:
            fixed: list[dict] = []
            for c in tool_calls:
                nm = ((c.get("function") or {}).get("name") or "")
                if nm in ("get_video", "similar_to"):
                    log.info("router override: %s -> search_videos (no opus in query)", nm)
                    fixed.append({"function": {"name": "search_videos",
                                               "arguments": {"query": user_query, "limit": 10}}})
                else:
                    fixed.append(c)
            # 중복 search_videos 제거 (같은 query)
            seen = set()
            dedup: list[dict] = []
            for c in fixed:
                fn = c.get("function") or {}
                key = (fn.get("name"), json.dumps(fn.get("arguments"), sort_keys=True, default=str))
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(c)
            tool_calls = dedup

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
