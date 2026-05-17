"""랭킹 보정.

AI_PLAN.md §7.2.
final_score = 0.70 * semantic_sim
            + 0.15 * fts_score
            + 0.10 * usage_boost      # log(1+play) + 0.5*rank/5 + 0.3*log(1+like_count)
            + 0.05 * recency_boost    # exp(-Δdays/180), last_play 기준

가중치는 config.yaml.ranking 에서 조정.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from packages.rag.retriever import Candidate
from packages.settings import load_config

MS_PER_DAY = 86400 * 1000.0


@dataclass
class Scored:
    opus: str
    final_score: float
    semantic: float
    fts: float
    usage: float
    recency: float
    payload: dict


def _usage_boost(payload: dict) -> float:
    play = float(payload.get("play") or 0)
    rank = float(payload.get("rank") or 0)
    like = float(payload.get("like_count") or 0)
    return math.log1p(play) + 0.5 * (rank / 5.0) + 0.3 * math.log1p(like)


def _recency_boost(payload: dict, half_life_days: float) -> float:
    last = payload.get("last_play")
    if not last:
        return 0.0
    delta_days = max(0.0, (time.time() * 1000.0 - float(last)) / MS_PER_DAY)
    return math.exp(-delta_days / max(half_life_days, 1.0))


def _normalize_max1(values: list[float]) -> list[float]:
    m = max(values) if values else 0.0
    if m <= 0:
        return [0.0] * len(values)
    return [v / m for v in values]


def rank(candidates: list[Candidate]) -> list[Scored]:
    if not candidates:
        return []
    cfg = load_config()["ranking"]
    w_sem = float(cfg["semantic_weight"])
    w_fts = float(cfg["fts_weight"])
    w_use = float(cfg["usage_weight"])
    w_rec = float(cfg["recency_weight"])
    half = float(cfg["recency_half_life_days"])

    sem_raw = [max(0.0, c.semantic_score) for c in candidates]
    fts_raw = [c.fts_score for c in candidates]
    use_raw = [_usage_boost(c.payload) for c in candidates]
    rec_raw = [_recency_boost(c.payload, half) for c in candidates]

    sem_n = _normalize_max1(sem_raw)
    fts_n = _normalize_max1(fts_raw)
    use_n = _normalize_max1(use_raw)
    # recency 는 이미 [0,1]

    out: list[Scored] = []
    for c, s, f, u, r in zip(candidates, sem_n, fts_n, use_n, rec_raw):
        score = w_sem * s + w_fts * f + w_use * u + w_rec * r
        out.append(
            Scored(
                opus=c.opus,
                final_score=score,
                semantic=s,
                fts=f,
                usage=u,
                recency=r,
                payload=c.payload,
            )
        )
    out.sort(key=lambda x: x.final_score, reverse=True)
    return out
