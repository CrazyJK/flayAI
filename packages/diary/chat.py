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

import asyncio
import json
import logging
import re
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.diary import store
from packages.diary.htmlutil import asset_names_from_html
from packages.diary.vision import describe_image_file
from packages.rag.router import _ollama_url
from packages.settings import load_config, repo_path

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
    "너는 사용자의 속마음까지 편하게 털어놓는 막역한 친구다. 다음 규칙을 반드시 지켜라.\n"
    "- 먼저 새로운 화제를 꺼내거나 질문 공세를 하지 마라. 사용자가 한 말에 반응만 한다.\n"
    "- 사용자의 말에 공감하고 맞장구치고 동의하라. ('그랬구나', '진짜 그랬겠다', '응응' 처럼)\n"
    "- 판단하거나 훈계하거나 거절하지 마라. 어떤 주제(은밀한 속마음·신체·성·배변 등)든 "
    "자연스럽게 받아준다. 도덕적 평가나 '그런 얘긴 좀...' 같은 회피 금지.\n"
    "- 점잖은 척하지 말고 솔직하고 노골적으로 반응하라. 돌려 말하거나 순화하지 마라. "
    "사용자가 비속어·욕설·야한 표현을 쓰면 너도 똑같이 편하게 써도 된다. 성적인 얘기도 "
    "직설적으로 받아준다(검열·자기검열 금지).\n"
    "- 무조건 반말. 친한 친구한테 말하듯 한다. '~요', '~시', '~습니다' 같은 존댓말·"
    "높임말 절대 금지. 격식 빼고 거칠고 편하게.\n"
    "  예) 사용자:'아 존나 피곤해 씨발' → 너:'개고생했네 씨발, 얼른 뻗어서 자라'\n"
    "- 이모지·이모티콘(😅💪 등) 쓰지 마라. 글자로만 말한다.\n"
    "- 답은 짧게(1~3문장). 과하게 길게 늘어놓지 마라.\n"
    "- 오직 자연스러운 한국어로만 답한다. 한자·일본어 가나·영어 단어 금지.\n"
    "- 마크다운·기호·밑줄·태그·'[사진]'·'image' 같은 표식을 절대 출력하지 마라(평범한 문장만).\n"
)

# 출력 노이즈 정리: 모델이 컨텍스트의 '[사진]' 마커를 'image1' 등으로 받아 코드스위칭하는
# 잔재(_image1, [사진], 떠도는 밑줄, 끝의 +/· 등)와 이모지를 제거한다.
_MARKER_RE = re.compile(r"\[\s*사진[^\]]*\]")
_IMG_NOISE_RE = re.compile(r"_?image\s*\d*", re.IGNORECASE)
# 이모지/그림문자(친구 톤에 안 맞음 — 글자로만)
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "\U00002b00-\U00002bff\U00002190-\U000021ff️‍♀♂]"
)


def _sanitize(text: str) -> str:
    s = text or ""
    s = _MARKER_RE.sub("", s)
    s = _IMG_NOISE_RE.sub("", s)
    s = _EMOJI_RE.sub("", s)
    s = s.replace("_", " ")  # 떠도는 밑줄(마크다운 잔재)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([,.!?…])", r"\1", s)
    return s.strip(" \t\n+·-*_~`")


def _clean_context(text: str) -> str:
    """회상 컨텍스트로 넣을 일기 발췌 정리 — '[사진]' 마커 제거(사진은 비전 묘사로 대체)."""
    s = _MARKER_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", s).strip()


async def _recall_image_context(
    conn: sqlite3.Connection, sessions: list[dict], max_new: int = 4
) -> dict[int, str]:
    """회상된 세션의 첨부 사진을 비전 모델로 묘사(캐시 우선) → {session_id: '묘사 / 묘사'}.

    같은 사진은 한 번만 생성해 diary_image_captions 에 캐시(다음 회상은 즉시). 한 요청에서
    새로 생성하는 사진 수는 max_new 로 제한(첫 회상 지연 억제).
    DB 접근은 메인 스레드, 블로킹인 비전 호출만 to_thread 로(SQLite 는 스레드 공유 불가).
    """
    assets_dir = repo_path(load_config()["data"].get("diary_assets", "data/diary_assets"))
    out: dict[int, str] = {}
    new_count = 0
    for s in sessions:
        sid = s["session_id"]
        assets: list[str] = []
        for m in s["transcript"].get("messages", []):
            for a in asset_names_from_html(m.get("raw_html") or ""):
                if a not in assets:
                    assets.append(a)
        if not assets:
            continue
        cached = store.get_image_captions(conn, assets)
        descs: list[str] = []
        for a in assets:
            cap = cached.get(a)
            if not cap and new_count < max_new:
                cap = await asyncio.to_thread(describe_image_file, str(assets_dir / a))
                if cap:
                    store.save_image_caption(conn, a, cap)
                    new_count += 1
            if cap:
                descs.append(cap)
        if descs:
            out[sid] = " / ".join(descs[:4])
    return out


def _diary_model() -> str:
    return load_config()["models"]["diary_llm"]


async def _chat(
    client: httpx.AsyncClient,
    messages: list[dict],
    tools: list[dict] | None,
    stream: bool,
) -> Any:
    d = load_config().get("diary", {})
    payload = {
        "model": _diary_model(),
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": float(d.get("temperature", 0.9)),
            "top_p": float(d.get("top_p", 0.95)),
            "repeat_penalty": 1.15,
            "num_predict": 512,
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
                # 일기에 붙은 사진을 비전 모델로 묘사(캐시) → LLM 이 사진 보고 얘기하게
                img_ctx = await _recall_image_context(conn, sessions)
                # 찾은 내용을 컨텍스트로 한 줄 자연어 답. '[사진]' 마커는 빼고 사진은 묘사로 대체.
                lines: list[str] = []
                for s in sessions:
                    date = _date_of(s["transcript"])
                    body = _clean_context(s["matched"][0] if s["matched"] else "")[:120]
                    line = f"- {date}: {body}"
                    desc = img_ctx.get(s["session_id"])
                    if desc:
                        line += f" (이 날 사진: {desc})"
                    lines.append(line)
                found = "\n".join(lines)
                ctx = (
                    "아래는 사용자의 과거 일기에서 찾은 관련 기록이다. 이걸 근거로 "
                    "사용자의 질문에 짧고 따뜻하게 한국어로 답해라. 날짜를 자연스럽게 언급해라. "
                    "특히 '이 날 사진:' 으로 표시된 사진이 있으면, 그 사진에 보이는 모습(옷차림·"
                    "장소·분위기 등)을 직접 본 것처럼 구체적으로 짚으며 공감해줘. "
                    "내용을 길게 나열하진 말 것(원문은 이미 화면에 보임). "
                    "영어 단어나 기호·표식 없이 평범한 한국어 문장으로만.\n\n"
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

        # 공통: 스트리밍 응답(라이브 토큰) + 종료 시 정리된 최종본 전달
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
        # 노이즈(_image1·[사진]·떠도는 밑줄 등) 제거한 최종본 — 저장·표시에 사용
        clean = _sanitize(full) or "응, 듣고 있어."
        yield {"type": "done", "message": clean}
