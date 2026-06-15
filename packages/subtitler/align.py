"""자막 정렬 — Whisper(JP) 발화구간 ↔ 기존 KO 자막 큐.

phase 2(번역메모리): 타임스탬프로 JP↔KO 쌍을 만든다.
phase 3(싱크 수정): 같은 정렬을 앵커로 KO 큐를 재타이밍한다(후속).

순수 로직. 의미 유사도 필터는 임베딩 함수를 주입받아(테스트 시 모델 불필요)
드리프트로 잘못 짝지어진 쌍을 걸러낸다 — bge-m3 는 multilingual 이라 의미가 같은
JP/KO 는 교차언어 코사인이 높다(번역 없이 오정렬 탐지).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .srt_io import Cue


@dataclass
class Pair:
    jp: str
    ko: str
    ko_start: float
    ko_end: float
    overlap: float        # KO 구간 중 JP 발화로 덮인 비율 (0~1+)
    sim: float = 0.0       # JP↔KO 교차언어 코사인 (필터 통과 시 채움)


def _norm_ws(text: str) -> str:
    """줄바꿈·연속공백 정리(few-shot 예시는 한 줄이 깔끔)."""
    return " ".join((text or "").split())


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def align_by_time(
    jp_segments: Sequence[dict[str, Any]],
    ko_cues: Sequence[Cue],
    *,
    min_overlap_ratio: float = 0.2,
) -> list[Pair]:
    """시간 겹침으로 (JP, KO) 후보 쌍 생성.

    각 KO 큐에 대해 시간이 겹치는 JP 세그먼트를 모아 JP 텍스트를 합친다.
    두 목록 모두 시간순이라 base 포인터로 선형 스윕(O(n+m)).
    드리프트가 있으면 잘못된 JP 와 겹칠 수 있으나, 그건 의미 유사도 필터가 떨어뜨린다.
    """
    pairs: list[Pair] = []
    n = len(jp_segments)
    base = 0
    for cue in ko_cues:
        ks, ke = cue.start, cue.end
        dur = max(1e-6, ke - ks)
        while base < n and jp_segments[base]["end"] <= ks:
            base += 1
        parts: list[str] = []
        covered = 0.0
        k = base
        while k < n and jp_segments[k]["start"] < ke:
            ov = _overlap(jp_segments[k]["start"], jp_segments[k]["end"], ks, ke)
            if ov > 0:
                parts.append(jp_segments[k]["text"])
                covered += ov
            k += 1
        if parts and covered / dur >= min_overlap_ratio:
            pairs.append(
                Pair(
                    jp=_norm_ws(" ".join(parts)),
                    ko=_norm_ws(cue.text),
                    ko_start=ks,
                    ko_end=ke,
                    overlap=covered / dur,
                )
            )
    return pairs


def _cosine(a: Any, b: Any) -> float:
    import numpy as np

    a = np.asarray(a, dtype="float32")
    b = np.asarray(b, dtype="float32")
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(a.dot(b) / (na * nb))


def filter_by_similarity(
    pairs: list[Pair],
    embed_fn: Callable[[list[str]], Any],
    *,
    min_sim: float = 0.50,
    min_len_ratio: float = 0.15,
    max_len_ratio: float = 6.0,
) -> tuple[list[Pair], list[tuple[Pair, float]]]:
    """의미 유사도 + 길이비로 쌍을 거른다. 반환: (통과, 탈락[(pair, sim)]).

    embed_fn(texts) -> 행벡터(정규화 여부 무관, 코사인으로 재정규화).
    드리프트로 JP/KO 가 다른 내용이면 교차언어 코사인이 낮아 탈락한다.
    """
    if not pairs:
        return [], []
    jp_vecs = embed_fn([p.jp for p in pairs])
    ko_vecs = embed_fn([p.ko for p in pairs])
    kept: list[Pair] = []
    dropped: list[tuple[Pair, float]] = []
    for p, a, b in zip(pairs, jp_vecs, ko_vecs):
        sim = _cosine(a, b)
        lr = len(p.ko) / max(1, len(p.jp))
        if sim >= min_sim and min_len_ratio <= lr <= max_len_ratio:
            p.sim = sim
            kept.append(p)
        else:
            dropped.append((p, sim))
    return kept, dropped
