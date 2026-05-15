"""JP -> KO 번역.

AI_PLAN.md §6.1 [4], §7.4.
- Helsinki-NLP/opus-mt-ja-ko (transformers MarianMT) CPU
- 결과 캐시: translations 테이블 (hash = sha1(src_lang|tgt_lang|src_text|model))
- 품질 필터: 결과 길이 / 원문 길이 비율이 [translate_min_ratio, translate_max_ratio]
  벗어나면 Ollama LLM 폴백
- title 통째로, desc 는 문장 단위 분할(., 。, ！, ？, 改행) -> 번역 -> 결합
- run() : videos.title_ko / desc_ko 채움 + state.translate.completed 갱신
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from typing import Iterable

import httpx

from packages.indexer.db import connect, init_schema
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

_MODEL = None
_TOKENIZER = None
_DEVICE = None

# 일/한 문장 분할 - 끝나는 문장부호 뒤 분리. lookbehind 로 부호 보존.
_SENT_SPLIT = re.compile(r"(?<=[。．\.！\!？\?])\s+|\n+")


# --- 유틸 ---------------------------------------------------------

def _hash(model: str, src: str, tgt: str, text: str) -> str:
    h = hashlib.sha1()
    h.update(f"{model}|{src}|{tgt}|".encode("utf-8"))
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    return parts or [text.strip()]


def _ratio_ok(src: str, tgt: str, lo: float, hi: float) -> bool:
    if not src:
        return True
    r = len(tgt) / len(src)
    return lo <= r <= hi


# --- 모델 로딩 ----------------------------------------------------

def _load_model() -> None:
    global _MODEL, _TOKENIZER, _DEVICE
    if _MODEL is not None:
        return
    import torch
    from transformers import MarianMTModel, MarianTokenizer

    cfg = load_config()
    name = cfg["models"]["translator"]
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("loading translator %s on %s", name, _DEVICE)
    _TOKENIZER = MarianTokenizer.from_pretrained(name)
    _MODEL = MarianMTModel.from_pretrained(name).to(_DEVICE)
    _MODEL.eval()


def _translate_batch(texts: list[str]) -> list[str]:
    """opus-mt 배치 번역."""
    if not texts:
        return []
    _load_model()
    import torch

    batch = _TOKENIZER(texts, return_tensors="pt", padding=True, truncation=True,
                       max_length=512).to(_DEVICE)
    with torch.no_grad():
        out = _MODEL.generate(**batch, max_new_tokens=512, num_beams=4)
    return [_TOKENIZER.decode(t, skip_special_tokens=True) for t in out]


# --- LLM 폴백 -----------------------------------------------------

def _llm_translate(text: str, target: str = "ko") -> str | None:
    """Ollama generate 로 번역 폴백. 실패 시 None."""
    cfg = load_config()
    try:
        url = cfg["server"]["ollama"].rstrip("/") + "/api/generate"
        prompt = (
            f"Translate the following Japanese text into {('Korean' if target == 'ko' else target)}. "
            "Return only the translation, no explanations.\n\n"
            f"---\n{text}\n---"
        )
        r = httpx.post(url, json={
            "model": cfg["models"]["llm"],
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }, timeout=120.0)
        r.raise_for_status()
        out = (r.json().get("response") or "").strip()
        return out or None
    except Exception as e:
        log.warning("LLM fallback failed: %s", e)
        return None


# --- 캐시 입출력 --------------------------------------------------

def _cache_get(conn: sqlite3.Connection, h: str) -> str | None:
    row = conn.execute("SELECT tgt_text FROM translations WHERE hash = ?", (h,)).fetchone()
    return row["tgt_text"] if row else None


def _cache_put(conn: sqlite3.Connection, h: str, src: str, tgt: str,
               src_lang: str, tgt_lang: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO translations(hash, src_lang, tgt_lang, src_text, tgt_text) "
        "VALUES (?, ?, ?, ?, ?)",
        (h, src_lang, tgt_lang, src, tgt),
    )


# --- 공개 API -----------------------------------------------------

def translate_text(
    conn: sqlite3.Connection,
    text: str,
    *,
    target: str = "ko",
    sentencewise: bool = False,
) -> str:
    """캐시 -> opus-mt -> (필요시) LLM 폴백. 빈 입력은 그대로 반환."""
    text = (text or "").strip()
    if not text:
        return ""
    cfg = load_config()
    model_name = cfg["models"]["translator"]
    lo = float(cfg["indexing"]["translate_min_ratio"])
    hi = float(cfg["indexing"]["translate_max_ratio"])

    chunks = split_sentences(text) if sentencewise else [text]

    # 캐시 hit/miss 분리
    out_chunks: list[str | None] = [None] * len(chunks)
    todo: list[tuple[int, str]] = []
    for i, c in enumerate(chunks):
        h = _hash(model_name, "ja", target, c)
        cached = _cache_get(conn, h)
        if cached is not None:
            out_chunks[i] = cached
        else:
            todo.append((i, c))

    if todo:
        translations = _translate_batch([c for _, c in todo])
        for (i, src), tgt in zip(todo, translations):
            tgt = (tgt or "").strip()
            if tgt and not _ratio_ok(src, tgt, lo, hi):
                fb = _llm_translate(src, target)
                if fb and _ratio_ok(src, fb, lo, hi):
                    tgt = fb
            out_chunks[i] = tgt
            _cache_put(conn, _hash(model_name, "ja", target, src), src, tgt, "ja", target)

    return " ".join(c for c in out_chunks if c)


def _iter_pending_videos(conn: sqlite3.Connection, limit: int | None,
                         force: bool) -> Iterable[sqlite3.Row]:
    sql = "SELECT opus, title_jp, desc_jp FROM videos"
    if not force:
        sql += " WHERE (title_jp IS NOT NULL AND (title_ko IS NULL OR title_ko = ''))" \
               "    OR (desc_jp  IS NOT NULL AND (desc_ko  IS NULL OR desc_ko  = ''))"
    sql += " ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def run(limit: int | None = None, force: bool = False) -> dict:
    """videos 의 title/desc JP -> KO. limit=N 으로 일부만 돌릴 수 있음."""
    conn = connect()
    init_schema(conn)
    rows = _iter_pending_videos(conn, limit, force)
    total = len(rows)
    completed = 0
    titles_done = 0
    descs_done  = 0

    for row in rows:
        opus = row["opus"]
        try:
            with conn:                       # row-level transaction (캐시 + 갱신 atomic)
                title_ko = translate_text(conn, row["title_jp"] or "", sentencewise=False) \
                    if row["title_jp"] else ""
                desc_ko  = translate_text(conn, row["desc_jp"] or "", sentencewise=True) \
                    if row["desc_jp"]  else ""
                conn.execute(
                    "UPDATE videos SET title_ko = ?, desc_ko = ? WHERE opus = ?",
                    (title_ko or None, desc_ko or None, opus),
                )
                if title_ko: titles_done += 1
                if desc_ko:  descs_done  += 1
                completed += 1
        except Exception as e:
            log.exception("translate failed opus=%s: %s", opus, e)
            continue

        if completed % 100 == 0:
            update_stage("translate", completed=completed, cursor_opus=opus)
            log.info("translate %d / %d (last=%s)", completed, total, opus)

    update_stage("translate", done=True, completed=completed,
                 cursor_opus=rows[-1]["opus"] if rows else None,
                 titles=titles_done, descs=descs_done, total=total)
    conn.close()
    return {"total": total, "completed": completed,
            "titles": titles_done, "descs": descs_done}
