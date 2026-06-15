"""phase 2 ③ 평가 — NLLB vs LLM+TM 를 사람 팬자막(정답)과 대조.

subtitle_tm 의 (jp, 사람 ko) 쌍이 정답셋. 그 jp 를 두 엔진으로 번역해 사람 ko 와 chrF
비교. LLM 은 해당 opus 를 retrieval 에서 제외(leakage 방지)하고 번역한다.

chrF: 문자 n-gram(1..6) F-score(β=2) — sacrebleu 의존 없이 자체 구현(상대 비교용).
LLM-judge 는 후속(여기선 chrF 자동 점수).
"""

from __future__ import annotations

import logging
import random
import sqlite3
from collections import Counter
from typing import Any

from packages.settings import load_config

from .config import subtitle_config
from .translate import _ollama_chat, translate_segments

log = logging.getLogger(__name__)


def _ngrams(s: str, n: int) -> Counter:
    s = "".join(s.split())  # 공백 무시(문자 단위 비교)
    if len(s) < n:
        return Counter()
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def chrf(hyp: str, ref: str, *, max_n: int = 6, beta: float = 2.0) -> float:
    """문자 n-gram F-score(0~1). 상대 비교용 근사 chrF."""
    if not hyp or not ref:
        return 0.0
    b2 = beta * beta
    fs: list[float] = []
    for n in range(1, max_n + 1):
        h, r = _ngrams(hyp, n), _ngrams(ref, n)
        if not h or not r:
            continue
        overlap = sum((h & r).values())
        if overlap == 0:
            fs.append(0.0)
            continue
        p = overlap / sum(h.values())
        rec = overlap / sum(r.values())
        fs.append((1 + b2) * p * rec / (b2 * p + rec))
    return sum(fs) / len(fs) if fs else 0.0


def judge_pair(jp: str, nllb: str, llm: str, *, model: str) -> str:
    """LLM 에게 두 번역 중 나은 쪽을 묻는다. 반환 'llm'|'nllb'|'tie'.

    chrF 가 의역체 정답엔 박하므로, 원문 충실도+자연스러움은 LLM 판정으로 본다.
    위치 편향 방지로 A/B 배치를 무작위화한다.
    """
    swap = random.random() < 0.5
    a, b = (llm, nllb) if swap else (nllb, llm)  # swap 이면 A=llm
    msgs = [
        {
            "role": "system",
            "content": "일본어 원문을 한국어로 옮긴 두 번역 A, B 중 원문 뜻에 더 충실하고 "
            "자연스러운 쪽을 고른다. 'A' 또는 'B' 또는 'tie' 한 단어만 출력한다.",
        },
        {"role": "user", "content": f"JP: {jp}\nA: {a}\nB: {b}\n답(A/B/tie):"},
    ]
    r = (_ollama_chat(model, msgs, temperature=0.0) or "").strip().upper()
    if r.startswith("A"):
        return "llm" if swap else "nllb"
    if r.startswith("B"):
        return "nllb" if swap else "llm"
    return "tie"


def evaluate_opus(
    conn: sqlite3.Connection,
    opus: str,
    *,
    n: int | None = None,
    with_llm: bool = True,
    judge_n: int = 0,
) -> dict[str, Any]:
    """opus 의 subtitle_tm 정답쌍으로 NLLB·LLM 번역 품질(chrF) 측정."""
    rows = conn.execute(
        "SELECT jp, ko FROM subtitle_tm WHERE opus=? ORDER BY ko_start", (opus,)
    ).fetchall()
    if n:
        rows = rows[:n]
    if not rows:
        return {"opus": opus, "n": 0, "error": "subtitle_tm 비어 있음(build-tm 먼저)"}
    jp = [r["jp"] for r in rows]
    ref = [r["ko"] for r in rows]

    nllb = translate_segments(conn, list(jp), cfg={"translator": "nllb"})
    chrf_nllb = sum(chrf(h, r) for h, r in zip(nllb, ref)) / len(ref)

    result: dict[str, Any] = {
        "opus": opus,
        "n": len(rows),
        "chrf_nllb": round(chrf_nllb, 4),
    }
    llm = None
    if with_llm:
        cfg = dict(subtitle_config())
        cfg["translator"] = "llm"
        cfg["exclude_opus"] = opus  # leakage 방지
        llm = translate_segments(conn, list(jp), cfg=cfg)
        chrf_llm = sum(chrf(h, r) for h, r in zip(llm, ref)) / len(ref)
        result["chrf_llm"] = round(chrf_llm, 4)
        result["delta"] = round(chrf_llm - chrf_nllb, 4)
        if judge_n > 0:
            model = cfg.get("translator_llm") or load_config()["models"]["llm"]
            wins = {"llm": 0, "nllb": 0, "tie": 0}
            for i in range(min(judge_n, len(rows))):
                wins[judge_pair(jp[i], nllb[i], llm[i], model=model)] += 1
            result["judge"] = wins

    result["samples"] = [
        {"jp": jp[i], "ref": ref[i], "nllb": nllb[i], "llm": (llm[i] if llm else None)}
        for i in range(min(8, len(rows)))
    ]
    return result


def evaluate(
    conn: sqlite3.Connection, opuses: list[str] | None = None, *, n_per: int | None = 40
) -> dict[str, Any]:
    """여러 opus 평가 후 집계. opuses 미지정 시 subtitle_tm 의 전체 opus."""
    if not opuses:
        rows = conn.execute("SELECT DISTINCT opus FROM subtitle_tm ORDER BY opus").fetchall()
        opuses = [r["opus"] for r in rows]
    per_opus = []
    for op in opuses:
        r = evaluate_opus(conn, op, n=n_per)
        per_opus.append(r)
        log.info(
            "eval %s: chrf nllb=%.3f llm=%.3f (n=%s)",
            op, r.get("chrf_nllb", 0), r.get("chrf_llm", 0), r.get("n"),
        )
    valid = [r for r in per_opus if r.get("n")]
    agg = {"opuses": len(valid)}
    if valid:
        agg["chrf_nllb"] = round(sum(r["chrf_nllb"] for r in valid) / len(valid), 4)
        if all("chrf_llm" in r for r in valid):
            agg["chrf_llm"] = round(sum(r["chrf_llm"] for r in valid) / len(valid), 4)
            agg["delta"] = round(agg["chrf_llm"] - agg["chrf_nllb"], 4)
    return {"aggregate": agg, "per_opus": per_opus}
