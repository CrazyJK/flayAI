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
import hashlib
import json
import logging
import random
import re
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.diary import prompts, store
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

# 출력 노이즈 정리: 모델이 컨텍스트의 '[사진]' 마커를 'image1' 등으로 받아 코드스위칭하는
# 잔재(_image1, [사진], 떠도는 밑줄, 끝의 +/· 등)와 이모지를 제거한다.
_MARKER_RE = re.compile(r"\[\s*사진[^\]]*\]")
_IMG_NOISE_RE = re.compile(r"_?image\s*\d*", re.IGNORECASE)
# 이모지/그림문자(친구 톤에 안 맞음 — 글자로만)
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "\U00002b00-\U00002bff\U00002190-\U000021ff️‍♀♂]"
)
# 깨진 조합 자모(ᄏᄏ 같은 degenerate ㅋ/ㅎ) — 일반 'ㅋㅋ'(U+314B)는 보존
_JAMO_RE = re.compile(r"[ᄀ-ᇿ]+")
def _sanitize(text: str) -> str:
    # 영어는 지우지 않는다(번역 없이 제거하면 문맥만 깨짐) — 마커·이모지·깨진 자모 등
    # 명백한 쓰레기만 정리.
    s = text or ""
    s = _MARKER_RE.sub("", s)
    s = _IMG_NOISE_RE.sub("", s)
    s = _EMOJI_RE.sub("", s)
    s = _JAMO_RE.sub("", s)
    s = s.replace("_", " ")  # 떠도는 밑줄(마크다운 잔재)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([,.!?…])", r"\1", s)
    return s.strip(" \t\n+·-*_~`")


def _crudify(text: str) -> str:
    """diary_prompts.yaml 의 person_subs 규칙으로 사람 지칭 등을 거칠게 치환.

    거친 표현 자체는 코드(git)에 두지 않고 gitignore 된 yaml 에서 주입(공개 저장소 보호).
    """
    s = text or ""
    for pat, repl in prompts.person_subs():
        try:
            if isinstance(repl, list):
                if repl:
                    s = re.sub(pat, lambda m, r=repl: random.choice(r), s)  # 매칭마다 무작위
            else:
                s = re.sub(pat, lambda m, r=repl: r, s)  # 리터럴(그룹참조 해석 방지)
        except re.error:
            continue
    return s


def _clean_context(text: str) -> str:
    """회상 컨텍스트로 넣을 일기 발췌 정리 — '[사진]' 마커 제거(사진은 비전 묘사로 대체)."""
    s = _MARKER_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", s).strip()


def _caption_sig() -> str:
    """캡션 캐시 무효화 키: 비전 모델 + 묘사 프롬프트 + person_subs 해시.
    이 중 하나라도 바뀌면 sig 가 달라져 기존 캡션은 미스 → 자동 재생성(수동 DELETE 불필요).
    """
    cfg = load_config()
    parts = [
        str(cfg["models"].get("vision") or ""),
        prompts.vision_describe_prompt(),
        json.dumps(prompts.person_subs(), ensure_ascii=False, sort_keys=True, default=str),
    ]
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


async def _recall_image_context(
    conn: sqlite3.Connection, sessions: list[dict], max_new: int = 4
) -> dict[int, str]:
    """회상된 세션의 첨부 사진을 비전 모델로 묘사(캐시 우선) → {session_id: '묘사 / 묘사'}.

    같은 사진은 한 번만 생성해 diary_image_captions 에 캐시(다음 회상은 즉시). 한 요청에서
    새로 생성하는 사진 수는 max_new 로 제한(첫 회상 지연 억제).
    DB 접근은 메인 스레드, 블로킹인 비전 호출만 to_thread 로(SQLite 는 스레드 공유 불가).
    """
    assets_dir = repo_path(load_config()["data"].get("diary_assets", "data/diary_assets"))
    sig = _caption_sig()  # 설정(모델·프롬프트·치환) 바뀌면 자동 재생성
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
        cached = store.get_image_captions(conn, assets, sig)
        descs: list[str] = []
        for a in assets:
            cap = cached.get(a)
            if not cap and new_count < max_new:
                cap = _crudify(await asyncio.to_thread(describe_image_file, str(assets_dir / a)))
                if cap:
                    store.save_image_caption(conn, a, cap, sig)
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
                    prompts.recall_answer_prompt()
                    + f"\n\n[질문]\n{user_query}\n\n[찾은 기록]\n{found}"
                )
                answer_msgs = [
                    {"role": "system", "content": prompts.system_prompt()},
                    {"role": "user", "content": ctx},
                ]
            else:
                # 못 찾음 — 안내 후 종료
                msg = prompts.not_found_message()
                yield {"type": "token", "text": msg}
                yield {"type": "done", "message": msg}
                return
        else:
            # --- 맞장구 경로 ---
            answer_msgs = [
                {"role": "system", "content": prompts.system_prompt()},
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
        # 노이즈 제거(_sanitize) + 사람 지칭 거칠게(_crudify) 한 최종본 — 저장·표시에 사용
        clean = _crudify(_sanitize(full)) or "응, 듣고 있어."
        yield {"type": "done", "message": clean}
