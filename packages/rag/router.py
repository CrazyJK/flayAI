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

from packages.rag.tools import TOOL_DISPATCH, TOOL_SCHEMA
from packages.settings import load_config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "당신은 사용자의 비디오 컬렉션 검색을 돕는 한국어 전용 비서입니다. "
    "제공된 도구(search_videos, similar_to, get_video, get_actress, stats)를 "
    "적극 사용하세요.\n"
    "\n"
    "[행동 규칙 — 반드시 준수]\n"
    "- 사용자에게 되묻지 마세요. '어떤 걸 추천해드릴까요?', '구체적으로 알려주세요' "
    "같은 반문 금지. 모호하더라도 일단 search_videos 를 호출해 결과를 보여주세요.\n"
    "- 빈손으로 응답하지 마세요. 자연어 질문이면 무조건 search_videos 먼저 호출.\n"
    "\n"
    "[도구 선택 규칙 — 반드시 준수]\n"
    "- 질문에 품번(예: SSSS-123, ABC-456 같은 영문+숫자 코드)이 **명시되어 있을 때만** "
    "get_video / similar_to 를 호출. 품번이 없으면 절대 호출 금지.\n"
    "- 그 외 모든 자연어 검색('회사 배경', '2023년 7월 발매작', 'S1 평점 4 이상', "
    "'지금 볼 수 있는 ...', '배우 이름 출연작' 등)은 **반드시 search_videos**.\n"
    "- 배우 이름이 들어가면 search_videos(actress=...) (별칭 자동 정규화).\n"
    "- 연도/월/제작사가 명시되면 search_videos(year=, month=, studio=) 메타 필터.\n"
    "- '지금 볼 수 있는' / '재생 가능한' → search_videos(kind='instance', playable=true).\n"
    "- '옛날 / 예전에 갖고 있던' → search_videos(kind='archive').\n"
    "- 통계/집계 질문은 stats.\n"
    "\n"
    "[출력 언어 — 절대 규칙]\n"
    "- 최종 답변은 **오직 한국어(한글)** 로만 작성. "
    "중국어(简体/繁体 한자), 일본어(ひらがな/カタカナ/漢字), 영어 문장 사용 절대 금지.\n"
    "- 한자어를 쓰지 말고 순 한글로: '추천작' (O), '推荐作' (X). '연도' (O), '年' (X).\n"
    "- 제목·배우명·스튜디오명 등 고유명사는 원문(영문/일문)을 그대로 인용 가능.\n"
    "- 날짜 표기는 'YYYY-MM' 또는 'YYYY년 M월' 형식.\n"
    "- 답변이 중국어로 흘러가려 하면 즉시 멈추고 한국어로 다시 쓰세요.\n"
    "\n"
    "도구 결과를 받으면, opus·제목·제작사·배우를 한 줄씩 나열하지 말고(카드에 이미 보임), "
    "뽑힌 영상들의 공통 소재·분위기와 질문에 왜 맞는지를 2~3문장으로 짧게 한국어로만 설명. "
    "한자(중국어)·일본어 가나·영어 문장 절대 금지 — 한자가 떠오르면 한글로 바꿔 쓴다."
)


def _ollama_url(path: str) -> str:
    cfg = load_config()
    return cfg["server"]["ollama"].rstrip("/") + path


def _llm_model() -> str:
    return load_config()["models"]["llm"]


_YEAR_RE = re.compile(r"(19|20)(\d{2})\s*년")
_MONTH_RE = re.compile(r"(?<!\d)([1-9]|1[0-2])\s*월")
_YEAR_ONLY_RE = re.compile(r"(?<!\d)(19|20)(\d{2})(?!\d)")
# "평점/별점 4 이상" 같은 최소 평점 표현
_RANK_RE = re.compile(r"(?:평점|별점|랭크|등급)\D{0,4}([1-5])\s*(?:점|개|성|등급)?\s*이상")
# "지금 볼 수 있는"(instance) / "예전·보관"(archive) 키워드
_INSTANCE_RE = re.compile(r"지금|바로|당장|볼\s*수\s*있는|재생\s*가능|플레이\s*가능")
_ARCHIVE_RE = re.compile(r"예전|옛날|아카이브|보관|지난날")


def _extract_meta(query: str) -> dict:
    """사용자 질문에서 메타 필터(year/month/min_rank/kind/playable)를 코드로 추출.

    LLM 이 인자를 빠뜨리거나 tool_call 자체를 안 하는 경우(폴백)에 대비한 코드 레벨
    방어 장치. 이 값을 search_videos 인자에 주입해 LLM 품질과 무관하게 결과를 정확히 만든다.
    """
    out: dict = {}
    m = _YEAR_RE.search(query)
    if m:
        out["year"] = int(m.group(1) + m.group(2))
    else:
        m = _YEAR_ONLY_RE.search(query)
        if m:
            out["year"] = int(m.group(1) + m.group(2))
    mm = _MONTH_RE.search(query)
    if mm:
        out["month"] = int(mm.group(1))
    mr = _RANK_RE.search(query)
    if mr:
        out["min_rank"] = int(mr.group(1))
    if _INSTANCE_RE.search(query):
        out["kind"] = "instance"
        out["playable"] = True
    elif _ARCHIVE_RE.search(query):
        out["kind"] = "archive"
    return out


# 적용된 검색 필터를 한국어 한 줄로 (LLM 묘사 대체용)
_KIND_LABEL = {"instance": "지금 볼 수 있는 것", "archive": "보관 영상"}


def _summarize_results(tool_calls: list[dict], results: list[dict]) -> str:
    """opus 결과(카드)가 목적이므로 LLM 묘사 대신 코드로 '건수 + 적용 필터'만 요약."""
    total = sum(len(r["result"]) for r in results if isinstance(r.get("result"), list))
    parts: list[str] = []
    for c in tool_calls:
        fn = c.get("function") or {}
        if fn.get("name") != "search_videos":
            continue
        a = fn.get("arguments") or {}
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except json.JSONDecodeError:
                a = {}
        if a.get("year"):
            parts.append(f"{a['year']}년")
        if a.get("month"):
            parts.append(f"{int(a['month'])}월")
        if a.get("studio"):
            parts.append(str(a["studio"]))
        if a.get("actress"):
            parts.append(str(a["actress"]))
        if a.get("min_rank"):
            parts.append(f"평점 {a['min_rank']}+")
        if a.get("kind") in _KIND_LABEL:
            parts.append(_KIND_LABEL[a["kind"]])
        elif a.get("playable"):
            parts.append(_KIND_LABEL["instance"])
        break
    parts = list(dict.fromkeys(parts))  # 중복 제거(순서 보존)
    cond = f" · 조건: {' · '.join(parts)}" if parts else ""
    if total <= 0:
        return f"조건에 맞는 결과가 없어요.{cond}"
    return f"{total}건을 찾았어요.{cond}"


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


async def _call_chat(
    client: httpx.AsyncClient, messages: list[dict], tools: list[dict] | None, stream: bool
) -> dict | AsyncIterator[dict]:
    payload = {
        "model": _llm_model(),
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": 0.2,
            # Qwen 7B 가 도구 결과 요약 중 쉼표/줄바꿈 반복 루프에 빠지는 것 방지
            "repeat_penalty": 1.25,
            "repeat_last_n": 128,
            # 최대 출력 토큰 상한 (대략 항목 20개 요약 분량)
            "num_predict": 1024,
        },
    }
    if tools:
        payload["tools"] = tools

    if not stream:
        r = await client.post(_ollama_url("/api/chat"), json=payload, timeout=120.0)
        r.raise_for_status()
        return r.json()

    async def gen():
        async with client.stream(
            "POST", _ollama_url("/api/chat"), json=payload, timeout=None
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    return gen()


async def route_chat(
    user_query: str,
    history: list[dict] | None = None,
    limit: int = 10,
    kind: str | None = None,
) -> AsyncIterator[dict]:
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

        # Ollama 가 tool 호출 안 했으면 무조건 폴백 (LLM이 사용자에게 되묻기 시도해도 차단)
        # content 가 있더라도 도구 결과 없이 끝나면 빈손이므로 search_videos 강제
        if not tool_calls:
            log.info(
                "router fallback: no tool_calls, forcing search_videos (raw content=%r)",
                (msg.get("content") or "")[:80],
            )
            tool_calls = [
                {
                    "function": {
                        "name": "search_videos",
                        "arguments": {"query": user_query, "limit": limit},
                    }
                }
            ]

        # 방어: 사용자 질문에 품번 패턴이 없는데 get_video/similar_to 호출 시
        # search_videos 로 강제 교체 (시스템 프롬프트를 무시한 LLM 오라우팅 방지)
        has_opus_in_query = bool(re.search(r"[A-Za-z]{2,7}-?\d{2,5}", user_query))
        if not has_opus_in_query:
            fixed: list[dict] = []
            for c in tool_calls:
                nm = (c.get("function") or {}).get("name") or ""
                if nm in ("get_video", "similar_to"):
                    log.info("router override: %s -> search_videos (no opus in query)", nm)
                    fixed.append(
                        {
                            "function": {
                                "name": "search_videos",
                                "arguments": {"query": user_query, "limit": limit},
                            }
                        }
                    )
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

        # 메타 필터 보강: 질문에서 year/month 가 명확히 추출되면 search_videos args 에 강제 주입
        # (LLM 이 메타 인자를 빠뜨리거나 query 만 보내는 경우 방어)
        meta = _extract_meta(user_query)
        if meta:
            for c in tool_calls:
                fn = c.get("function") or {}
                if fn.get("name") != "search_videos":
                    continue
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                changed = False
                for k, v in meta.items():
                    if not args.get(k):
                        args[k] = v
                        changed = True
                if changed:
                    log.info("router meta boost: search_videos args <- %s", meta)
                    fn["arguments"] = args
                    c["function"] = fn

        # 프론트에서 지정한 limit 을 search_videos 에 강제 주입 (LLM 기본값 무시).
        # kind 가 instance/archive 면 사용자가 UI 에서 명시적으로 고른 것이므로 강제 주입(전체="" 면 미적용).
        for c in tool_calls:
            fn = c.get("function") or {}
            if fn.get("name") != "search_videos":
                continue
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            args["limit"] = limit
            if kind in ("instance", "archive"):
                args["kind"] = kind
            fn["arguments"] = args
            c["function"] = fn

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

        # 설명문(LLM 2차 생성) 생략 — 사용자 목적은 opus 결과(카드)이고 묘사 문장은 불필요.
        # 코드로 '건수 + 적용 필터' 한 줄만 만들어 중국어 드리프트·재시도·2차 LLM 호출을 모두 제거.
        summary = _summarize_results(tool_calls, results_for_history)
        yield {"type": "token", "text": summary}
        yield {
            "type": "done",
            "message": summary,
            "tool_calls": [{"name": r["name"], "args": r["args"]} for r in results_for_history],
        }
