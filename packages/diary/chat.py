"""일기형 대화 라우팅: 수동적 경청자 + 회상.

페르소나(영상 검색 router 와 전혀 다름):
- 먼저 화제를 꺼내지 않는다. 사용자의 말에 공감·맞장구·동의한다.
- 판단/훈계/거부를 하지 않는다(모델은 abliterated — 안전 브레이크 없음).
- 짧고 따뜻하게, 한국어로만.

흐름:
1) 1차 LLM 호출(recall_memory tool 제공, stream=False) — 회상 질문인지 판정.
2) 회상이면 store.recall_sessions → 'recall' 이벤트(그때 일기 원문 전체) emit
   → 찾은 내용을 컨텍스트로 한 줄 자연어 답 스트리밍.
3) 아니면 곧장 맞장구/공감 답 스트리밍(도구 없이).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.diary import store
from packages.rag.router import _ollama_url
from packages.settings import load_config

log = logging.getLogger(__name__)

# 회상 의도 감지(코드 레벨) — diary_llm(EXAONE)이 Ollama tool-calling 을 지원하지 않아
# (tools 인자에 400) tool-call 라우팅 대신 정규식으로 '과거를 떠올려 달라'는 요청을 잡는다.
# 검색/조회 명령·기억 질문·시점 질문·명시적 회상어에 한정(일상 회고 서술엔 안 걸리게).
_RECALL_RE = re.compile(
    r"보여\s*줘|보여\s*줄래|찾아\s*줘|찾아\s*봐|찾아\s*줄래|알려\s*줘|꺼내\s*줘|"
    r"떠올려|회상|되짚|"
    r"기억\s*(나|났|나니|해|하니|하는지|할|해\s*줘|을?\s*보여|좀)|"
    r"언제\s*(였|이었|쯤|더라|지|인지|였나|예요|인가)|"
    r"(저번|예전|옛날|지난번|지난주|지난달|그때|작년|재작년|며칠\s*전|얼마\s*전)"
    r".{0,20}(언제|뭐|무슨|무엇|어땠|있었|했었|했던|봤|먹었|갔|기억|보여|찾|줘|\?)"
)

# 회상 검색어에서 명령·기억 표현을 떼어내 '주제'만 남긴다(검색 정확도↑).
_RECALL_STRIP = re.compile(
    r"기억(을|이|은|좀)?|보여\s*줘|보여\s*줄래|찾아\s*줘|찾아\s*봐|알려\s*줘|"
    r"떠올려\s*줘?|꺼내\s*줘|회상(\s*해\s*줘)?|해\s*줘|좀|줘|보여"
)


def _looks_like_recall(text: str) -> bool:
    return bool(_RECALL_RE.search(text or ""))


def _recall_search_query(text: str) -> str:
    s = _RECALL_STRIP.sub(" ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s or (text or "").strip()

SYSTEM_PROMPT = (
    "너는 사용자의 일상 일기를 들어주는 다정한 친구다. 다음 규칙을 반드시 지켜라.\n"
    "- 먼저 새로운 화제를 꺼내거나 질문 공세를 하지 마라. 사용자가 한 말에 반응만 한다.\n"
    "- 사용자의 말에 공감하고 맞장구치고 동의하라. ('그랬구나', '진짜 그랬겠다', '응응' 처럼)\n"
    "- 판단하거나 훈계하거나 거절하지 마라. 어떤 주제(은밀한 속마음·신체·성·배변 등)든 "
    "자연스럽게 받아준다. 도덕적 평가나 '그런 얘긴 좀...' 같은 회피 금지.\n"
    "- 답은 짧게(1~3문장). 과하게 길게 늘어놓지 마라.\n"
    "- 오직 한국어로만 답한다. 한자·일본어 가나·영어 문장 금지.\n"
)

def _diary_model() -> str:
    return load_config()["models"]["diary_llm"]


async def _chat(
    client: httpx.AsyncClient,
    messages: list[dict],
    tools: list[dict] | None,
    stream: bool,
) -> Any:
    payload = {
        "model": _diary_model(),
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.7, "repeat_penalty": 1.2, "num_predict": 512},
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


def _date_of(transcript: dict) -> str:
    s = transcript.get("session") or {}
    return s.get("source_key") or (s.get("started_at") or "")[:10]


def _recall_event(sessions: list[dict]) -> dict:
    """store.recall_sessions 결과 → 프론트용 recall 이벤트 payload."""
    out = []
    for s in sessions:
        tr = s["transcript"]
        meta = tr.get("session") or {}
        out.append(
            {
                "session_id": s["session_id"],
                "date": _date_of(tr),
                "title": meta.get("title"),
                "weather": meta.get("weather"),
                "score": s["score"],
                "messages": [
                    {
                        "role": m["role"],
                        "content": m["content"],
                        "raw_html": m.get("raw_html"),
                        "created_at": m["created_at"],
                    }
                    for m in tr.get("messages", [])
                ],
            }
        )
    return {"type": "recall", "sessions": out}


async def route_diary_chat(
    conn: sqlite3.Connection,
    user_query: str,
    history: list[dict] | None = None,
    exclude_message_id: int | None = None,
) -> AsyncIterator[dict]:
    """async generator. event dict 시리즈를 yield.

    이벤트: {"type":"recall","sessions":[...]} / {"type":"token","text":...}
           / {"type":"done","message":...}
    """
    history = history or []
    cfg = load_config()
    top_k = int(cfg.get("diary", {}).get("recall_top_k", 5))

    # 회상 의도는 코드로 감지(diary_llm 의 tool-call 미지원 — Ollama 400 방어).
    recall_query = _recall_search_query(user_query) if _looks_like_recall(user_query) else None

    async with httpx.AsyncClient() as client:
        # --- 회상 경로 ---
        if recall_query:
            sessions = store.recall_sessions(
                conn, recall_query, top_k=top_k, exclude_message_id=exclude_message_id
            )
            if sessions:
                yield _recall_event(sessions)
                # 찾은 내용을 컨텍스트로 한 줄 자연어 답
                found = "\n".join(
                    f"- {_date_of(s['transcript'])}: "
                    f"{(s['matched'][0] if s['matched'] else '')[:120]}"
                    for s in sessions
                )
                ctx = (
                    "아래는 사용자의 과거 일기에서 찾은 관련 기록이다. 이걸 근거로 "
                    "사용자의 질문에 짧고 따뜻하게 한국어로 답해라. 날짜를 자연스럽게 언급하되, "
                    "내용을 길게 나열하지 말 것(원문은 이미 화면에 보임).\n\n"
                    f"[질문]\n{user_query}\n\n[찾은 기록]\n{found}"
                )
                answer_msgs = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": ctx},
                ]
            else:
                # 못 찾음 — 안내 후 종료
                msg = "음, 그건 일기에서 못 찾겠어. 더 구체적으로 말해줄래?"
                yield {"type": "token", "text": msg}
                yield {"type": "done", "message": msg}
                return
        else:
            # --- 맞장구 경로 ---
            answer_msgs = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": user_query},
            ]

        # 공통: 스트리밍 응답
        full = ""
        try:
            stream = await _chat(client, answer_msgs, tools=None, stream=True)
            async for chunk in stream:
                piece = (chunk.get("message", {}) or {}).get("content") or ""
                if piece:
                    full += piece
                    yield {"type": "token", "text": piece}
                if chunk.get("done"):
                    break
        except Exception as e:
            log.exception("diary 응답 생성 실패: %s", e)
            if not full:
                full = "응, 듣고 있어."
                yield {"type": "token", "text": full}
        yield {"type": "done", "message": full}
