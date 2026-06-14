"""자막 세그먼트 번역 — JP→KO.

phase 1: 기존 인덱서 번역기(NLLB + LLM 폴백, translations 캐시)를 그대로 재사용.
phase 2: mode="llm" — 159개 팬자막에서 만든 번역메모리(few-shot)+용어집으로 품질 보정.

세그먼트는 이미 짧은 발화 단위라 sentencewise=False 로 통째 번역한다.
캐시(translations 테이블) 덕에 반복 대사("네에-", "기분 좋아" 등)는 1회만 번역된다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable


def translate_segments(
    conn: sqlite3.Connection,
    texts: list[str],
    *,
    mode: str = "nllb",
    target: str = "ko",
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[str]:
    """세그먼트 텍스트 목록을 번역. progress_cb(done, total)."""
    if mode == "nllb":
        from packages.indexer.translate import translate_text

        out: list[str] = []
        n = len(texts)
        for i, t in enumerate(texts, 1):
            out.append(translate_text(conn, t, target=target, sentencewise=False))
            if progress_cb:
                progress_cb(i, n)
        # translate_text 의 캐시(translations) 쓰기를 확정 — 호출자 트랜잭션에 의존하지 않게.
        conn.commit()
        return out
    if mode == "llm":
        # phase 2 — 번역메모리 few-shot + 용어집 LLM 번역.
        raise NotImplementedError("translator mode 'llm' 는 phase 2 (번역메모리)")
    raise ValueError(f"unknown translator mode: {mode}")
