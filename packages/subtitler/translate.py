"""자막 세그먼트 번역 — JP→KO.

mode="nllb": 기존 인덱서 NLLB(translate_text) 재사용 — 빠름(phase 1 기본).
mode="llm" : 무검열 LLM + 번역메모리 few-shot + 문맥(phase 2) — 야간 품질 우선.
  세그먼트를 청크(기본 12개)로 묶어 번역(문맥·속도). 각 청크는 subtitle_tm 에서 유사
  예시 K개를 검색해 프롬프트에 주입 → 팬자막 말투 모방. 줄 누락분은 NLLB 로 폴백.

캐시(translations) 쓰기는 호출자 트랜잭션에 의존하지 않게 끝에서 commit.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Callable

import httpx

from packages.settings import load_config

from . import prompts

log = logging.getLogger(__name__)

# "1. ko" / "1) ko" / "1: ko" / "1 ko"
_NUM_RE = re.compile(r"^\s*(\d+)\s*[.)\]:]?\s+(.*)$")

# LLM 출력 오염 감지 — 라틴문자 4+ 연속(예: "어싸łoADING") 또는 한자 누출.
_LATIN_RUN = re.compile(r"[A-Za-zÀ-ɏ]{4,}")
_HAN_RE = re.compile(r"[一-鿿]")


def _looks_bad(ko: str) -> bool:
    """번역 결과가 깨졌으면 True → 그 줄은 NLLB 로 폴백."""
    if not ko or not ko.strip():
        return True
    if _LATIN_RUN.search(ko):
        return True
    # 한국어 자막에 한자 2+ 연속/다수면 미번역 한자어(예: 旅馆) 누출로 간주.
    if len(_HAN_RE.findall(ko)) >= 2:
        return True
    return False


def translate_segments(
    conn: sqlite3.Connection,
    texts: list[str],
    *,
    cfg: dict | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[str]:
    """세그먼트 텍스트 목록을 번역. cfg['translator'] 로 엔진 선택."""
    cfg = cfg or {}
    mode = cfg.get("translator", "nllb")
    if mode == "nllb":
        return _translate_nllb(conn, texts, progress_cb=progress_cb)
    if mode == "llm":
        return _translate_llm(conn, texts, cfg, progress_cb=progress_cb)
    raise ValueError(f"unknown translator mode: {mode}")


# --- NLLB (phase 1 / 폴백) ----------------------------------------


def _translate_nllb(
    conn: sqlite3.Connection,
    texts: list[str],
    *,
    target: str = "ko",
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[str]:
    from packages.indexer.translate import translate_text

    out: list[str] = []
    n = len(texts)
    for i, t in enumerate(texts, 1):
        out.append(translate_text(conn, t, target=target, sentencewise=False))
        if progress_cb:
            progress_cb(i, n)
    conn.commit()
    return out


# --- LLM few-shot (phase 2) — 순수 헬퍼 ----------------------------


def build_messages(
    system: str,
    examples: list[tuple[str, str]],
    glossary: list[tuple[str, str]],
    lines: list[str],
) -> list[dict[str, str]]:
    """Ollama chat 메시지 구성. 용어집·검색예시는 system 에, 번역 대상은 user 에."""
    sys = system
    if glossary:
        sys += "\n\n[용어]\n" + "\n".join(f"- {jp} = {ko}" for jp, ko in glossary)
    if examples:
        sys += "\n\n[참고 번역 예시 — 이 말투·어휘를 따르세요]\n" + "\n".join(
            f"JP: {jp}\nKO: {ko}" for jp, ko in examples
        )
    user = "다음 일본어 대사를 한국어로 번역하세요. 같은 번호로 한국어만:\n" + "\n".join(
        f"{i}. {t}" for i, t in enumerate(lines, 1)
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def parse_numbered(text: str | None, n: int) -> list[str] | None:
    """'1. ...' 형식 응답 → n개 리스트. 하나도 못 읽으면 None(폴백 신호).

    부분 파싱 허용 — 빠진 번호는 빈 문자열(호출자가 NLLB 로 메움).
    """
    got: dict[int, str] = {}
    for line in (text or "").splitlines():
        m = _NUM_RE.match(line)
        if m:
            idx = int(m.group(1))
            val = m.group(2).strip()
            if 1 <= idx <= n and val and idx not in got:
                got[idx] = val
    if not got:
        return None
    return [got.get(i, "") for i in range(1, n + 1)]


def _ollama_chat(
    model: str, messages: list[dict[str, str]], *, temperature: float = 0.3, timeout: float = 180.0
) -> str | None:
    cfg = load_config()
    url = cfg["server"]["ollama"].rstrip("/") + "/api/chat"
    try:
        r = httpx.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 1024},
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return ((r.json().get("message") or {}).get("content") or "").strip()
    except Exception as e:  # noqa: BLE001 — 실패 시 None → NLLB 폴백
        log.warning("ollama chat 실패: %s", e)
        return None


def _translate_llm(
    conn: sqlite3.Connection,
    texts: list[str],
    cfg: dict,
    *,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[str]:
    from . import tm

    model = cfg.get("translator_llm") or load_config()["models"]["llm"]
    k = int(cfg.get("llm_fewshot_k", 6))
    chunk = max(1, int(cfg.get("llm_chunk_size", 12)))
    system = prompts.system_prompt()
    glossary = prompts.glossary()

    qc = None
    try:
        from packages.indexer.embed_text import _qdrant

        qc = _qdrant()
        tm.ensure_tm_collection(qc)
    except Exception as e:  # noqa: BLE001 — TM 없거나 Qdrant 미가용이면 few-shot 없이
        log.warning("TM 검색 불가(%s) — few-shot 없이 진행", e)
        qc = None

    n = len(texts)
    out: list[str | None] = [None] * n
    exclude_opus = cfg.get("exclude_opus")  # 평가 시 자기 opus 제외(leakage 방지)
    for start in range(0, n, chunk):
        block = texts[start : start + chunk]
        examples = (
            tm.retrieve_examples(qc, block, k, exclude_opus=exclude_opus)
            if qc is not None
            else []
        )
        resp = _ollama_chat(model, build_messages(system, examples, glossary, block))
        parsed = parse_numbered(resp, len(block))
        for i in range(len(block)):
            v = parsed[i] if parsed else None
            out[start + i] = v if (v and not _looks_bad(v)) else None
        if progress_cb:
            progress_cb(min(start + chunk, n), n)

    missing = [i for i, v in enumerate(out) if not v]
    if missing:
        log.info("LLM 미해결 %d/%d → NLLB 폴백", len(missing), n)
        fb = _translate_nllb(conn, [texts[i] for i in missing])
        for j, i in enumerate(missing):
            out[i] = fb[j]
    conn.commit()
    return [v or "" for v in out]
