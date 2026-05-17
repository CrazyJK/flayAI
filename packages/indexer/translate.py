"""JP -> KO 번역.

AI_PLAN.md §6.1 [4], §7.4.
- facebook/nllb-200-distilled-600M (jpn_Jpan -> kor_Hang)
- 결과 캐시: translations 테이블 (hash = sha1(model|src|tgt|text))
- 품질 필터: 결과/원문 길이 비율이 [translate_min_ratio, translate_max_ratio]
  벗어나면 Ollama LLM 폴백
- title 통째로, desc 는 문장 단위 분할 -> 번역 -> 결합
- run() : videos.title_ko / desc_ko 채움 + state.translate.completed 갱신
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from collections.abc import Iterable

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
    h.update(f"{model}|{src}|{tgt}|".encode())
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


# CJK Unified Ideographs (한자) — 일본 한자(漢字)도 포함되지만, 한국어 번역
# 결과에 한자가 다수 섞이면 중국어/일본어 오염으로 간주.
_HAN_RE = re.compile(r"[\u4E00-\u9FFF]")
_HANGUL_RE = re.compile(r"[\uAC00-\uD7A3]")


def _looks_corrupted(text: str) -> bool:
    """번역 결과의 품질 이상 감지.

    트리거 조건:
    - 같은 토큰(공백 분리)이 5회 이상 연속 반복 → NLLB repetition collapse
    - 길이가 충분(>=20자)한데 한자 비율이 한글 비율보다 높음 → 중국어 오염
    """
    if not text:
        return False
    tokens = text.split()
    run = 1
    for i in range(1, len(tokens)):
        if tokens[i] == tokens[i - 1]:
            run += 1
            if run >= 5:
                return True
        else:
            run = 1
    han = len(_HAN_RE.findall(text))
    kor = len(_HANGUL_RE.findall(text))
    # 한자가 3자 이상 + 한글보다 많거나 같으면 중국어 오염으로 간주.
    # (한국어 정상 번역에는 한자가 거의 안 섞이며, 섞이더라도 1~2자 수준)
    if han >= 3 and han >= kor:
        return True
    return False


# --- 모델 로딩 ----------------------------------------------------


def _load_model() -> None:
    global _MODEL, _TOKENIZER, _DEVICE
    if _MODEL is not None:
        return
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    cfg = load_config()
    name = cfg["models"]["translator"]
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("loading translator %s on %s", name, _DEVICE)
    _TOKENIZER = AutoTokenizer.from_pretrained(name, src_lang="jpn_Jpan")
    _MODEL = AutoModelForSeq2SeqLM.from_pretrained(name).to(_DEVICE)
    _MODEL.eval()


def _translate_batch(texts: list[str], target: str = "ko") -> list[str]:
    """NLLB-200 배치 번역 (jpn_Jpan -> {target})."""
    if not texts:
        return []
    _load_model()
    import torch

    tgt_token = {"ko": "kor_Hang", "en": "eng_Latn"}.get(target, "kor_Hang")
    forced_bos = _TOKENIZER.convert_tokens_to_ids(tgt_token)
    batch = _TOKENIZER(
        texts, return_tensors="pt", padding=True, truncation=True, max_length=512
    ).to(_DEVICE)
    with torch.no_grad():
        # greedy + 반복 억제. no_repeat_ngram_size=3 으로 "어 어 어" 같은 토큰
        # collapse 차단, repetition_penalty 로 logit-level 추가 억제.
        out = _MODEL.generate(
            **batch,
            forced_bos_token_id=forced_bos,
            max_new_tokens=256,
            num_beams=1,
            no_repeat_ngram_size=3,
            repetition_penalty=1.3,
        )
    return [_TOKENIZER.decode(t, skip_special_tokens=True) for t in out]


# --- LLM 폴백 -----------------------------------------------------


def _llm_translate(text: str, target: str = "ko") -> str | None:
    """Ollama generate 로 번역 폴백. 실패 시 None.

    Qwen 의 중국어 관성 때문에 영어 프롬프트로 "into Korean" 만 지시하면
    중국어로 응답하는 사례 발견. 프롬프트를 한국어로 강하게 작성하고,
    응답 후 _looks_corrupted 로 한 번 더 검증.
    """
    cfg = load_config()
    try:
        url = cfg["server"]["ollama"].rstrip("/") + "/api/generate"
        if target == "ko":
            prompt = (
                "다음 일본어 문장을 한국어(한글)로만 번역하세요. "
                "중국어 한자(简体/繁体), 영어 문장, 설명 금지. "
                "고유명사(인명/제목)는 원문 그대로 두어도 됩니다. "
                "번역문만 한 줄로 출력하세요.\n\n"
                f"원문: {text}\n번역:"
            )
        else:
            prompt = (
                f"Translate the following Japanese text into {target}. "
                "Return only the translation, no explanations.\n\n"
                f"---\n{text}\n---"
            )
        r = httpx.post(
            url,
            json={
                "model": cfg["models"]["llm"],
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "repeat_penalty": 1.2,
                    "num_predict": 512,
                },
            },
            timeout=120.0,
        )
        r.raise_for_status()
        out = (r.json().get("response") or "").strip()
        if not out:
            return None
        if target == "ko" and _looks_corrupted(out):
            log.warning("LLM fallback produced corrupted output: %r", out[:80])
            return None
        return out
    except Exception as e:
        log.warning("LLM fallback failed: %s", e)
        return None


# --- 캐시 입출력 --------------------------------------------------


def _cache_get(conn: sqlite3.Connection, h: str) -> str | None:
    row = conn.execute("SELECT tgt_text FROM translations WHERE hash = ?", (h,)).fetchone()
    return row["tgt_text"] if row else None


def _cache_put(
    conn: sqlite3.Connection, h: str, src: str, tgt: str, src_lang: str, tgt_lang: str
) -> None:
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
        translations = _translate_batch([c for _, c in todo], target=target)
        for (i, src), tgt in zip(todo, translations):
            tgt = (tgt or "").strip()
            # 폴백 트리거: (a) 길이 비율 이상 (b) 반복/언어 오염
            needs_fb = bool(tgt) and (not _ratio_ok(src, tgt, lo, hi) or _looks_corrupted(tgt))
            if needs_fb:
                fb = _llm_translate(src, target)
                # LLM 결과도 검증; 통과 못 하면 NLLB 결과 유지 (또는 원문)
                if fb and _ratio_ok(src, fb, lo, hi) and not _looks_corrupted(fb):
                    tgt = fb
                elif _looks_corrupted(tgt):
                    # 둘 다 오염이면 차라리 원문(JP) 을 보존 — 빈 값보다 정보량 많음
                    log.warning("translate corrupted; keep src for: %r", src[:60])
                    tgt = src
            out_chunks[i] = tgt
            _cache_put(conn, _hash(model_name, "ja", target, src), src, tgt, "ja", target)

    return " ".join(c for c in out_chunks if c)


def _iter_pending_videos(
    conn: sqlite3.Connection, limit: int | None, force: bool
) -> Iterable[sqlite3.Row]:
    sql = "SELECT opus, title_jp, desc_jp FROM videos"
    if not force:
        sql += (
            " WHERE (title_jp IS NOT NULL AND (title_ko IS NULL OR title_ko = ''))"
            "    OR (desc_jp  IS NOT NULL AND (desc_ko  IS NULL OR desc_ko  = ''))"
        )
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
    descs_done = 0

    for row in rows:
        opus = row["opus"]
        try:
            with conn:  # row-level transaction (캐시 + 갱신 atomic)
                title_ko = (
                    translate_text(conn, row["title_jp"] or "", sentencewise=False)
                    if row["title_jp"]
                    else ""
                )
                desc_ko = (
                    translate_text(conn, row["desc_jp"] or "", sentencewise=True)
                    if row["desc_jp"]
                    else ""
                )
                conn.execute(
                    "UPDATE videos SET title_ko = ?, desc_ko = ? WHERE opus = ?",
                    (title_ko or None, desc_ko or None, opus),
                )
                if title_ko:
                    titles_done += 1
                if desc_ko:
                    descs_done += 1
                completed += 1
        except Exception as e:
            log.exception("translate failed opus=%s: %s", opus, e)
            continue

        if completed % 100 == 0:
            update_stage("translate", completed=completed, cursor_opus=opus)
            log.info("translate %d / %d (last=%s)", completed, total, opus)

    update_stage(
        "translate",
        done=True,
        completed=completed,
        cursor_opus=rows[-1]["opus"] if rows else None,
        titles=titles_done,
        descs=descs_done,
        total=total,
    )
    conn.close()
    return {"total": total, "completed": completed, "titles": titles_done, "descs": descs_done}
