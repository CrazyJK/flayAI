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


def align_semantic(
    ko_vecs: Any,
    jp_vecs: Any,
    *,
    floor: float = 0.35,
) -> list[tuple[int, int]]:
    """KO 큐 ↔ JP 세그먼트 단조 정렬(의미 기반 DP). 반환: [(ko_idx, jp_idx)] 매칭.

    드리프트된 자막은 시간이 틀렸으므로 시간이 아니라 bge-m3 교차언어 유사도로 정렬한다.
    Needleman-Wunsch 류: 대각=매칭(유사도>=floor), 위/왼=한쪽 건너뜀(무료). 순서 보존.
    """
    from array import array

    import numpy as np

    A = np.asarray(ko_vecs, dtype="float32")
    B = np.asarray(jp_vecs, dtype="float32")
    if A.ndim != 2 or B.ndim != 2 or len(A) == 0 or len(B) == 0:
        return []
    A = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-8)
    B = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-8)
    srows = (A @ B.T).tolist()  # K×J 유사도(행 단위 리스트 — 스칼라 접근 빠름)
    k = len(srows)
    j_n = len(srows[0])
    neg = -1e9

    tb = [array("b", bytes(j_n + 1)) for _ in range(k + 1)]  # 0=diag 1=up(skip ko) 2=left(skip jp)
    prev = array("d", bytes(8 * (j_n + 1)))  # f[i-1], 가장자리 0
    for i in range(1, k + 1):
        srow = srows[i - 1]
        cur = array("d", bytes(8 * (j_n + 1)))
        tbi = tb[i]
        for j in range(1, j_n + 1):
            s = srow[j - 1]
            diag = (prev[j - 1] + s) if s >= floor else neg
            up = prev[j]
            left = cur[j - 1]
            best, t = diag, 0
            if up > best:
                best, t = up, 1
            if left > best:
                best, t = left, 2
            cur[j] = best
            tbi[j] = t
        prev = cur

    i, j = k, j_n
    matches: list[tuple[int, int]] = []
    while i > 0 and j > 0:
        t = tb[i][j]
        if t == 0:
            matches.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif t == 1:
            i -= 1
        else:
            j -= 1
    matches.reverse()
    return matches


def _interp_start(
    old_start: float,
    cue_idx: int,
    ko_cues: Sequence[Cue],
    anchor: dict[int, tuple[float, float]],
    anchor_idx: list[int],
) -> float:
    """매칭 안 된 큐의 새 시작시각을 인접 앵커 사이 선형 보간으로 추정."""
    import bisect

    pos = bisect.bisect_left(anchor_idx, cue_idx)
    lo = anchor_idx[pos - 1] if pos > 0 else None
    hi = anchor_idx[pos] if pos < len(anchor_idx) else None
    if lo is not None and hi is not None:
        o_lo, o_hi = ko_cues[lo].start, ko_cues[hi].start
        n_lo, n_hi = anchor[lo][0], anchor[hi][0]
        if o_hi > o_lo:
            frac = min(1.0, max(0.0, (old_start - o_lo) / (o_hi - o_lo)))
            return n_lo + frac * (n_hi - n_lo)
        return n_lo
    if lo is not None:  # 마지막 앵커 이후 — 그 앵커의 오프셋 적용
        return old_start + (anchor[lo][0] - ko_cues[lo].start)
    if hi is not None:  # 첫 앵커 이전
        return old_start + (anchor[hi][0] - ko_cues[hi].start)
    return old_start


def retime(
    ko_cues: Sequence[Cue],
    jp_segments: Sequence[dict[str, Any]],
    matches: list[tuple[int, int]],
    *,
    gap: float = 0.04,
    min_dur: float = 0.7,
    max_dur: float = 7.0,
) -> list[Cue]:
    """매칭으로 KO 큐를 재타이밍. 텍스트는 보존, 시작시각만 오디오에 맞춤.

    끝시각은 다음 큐 시작 직전으로 클램프(겹침 방지) + 최소/최대 표시시간 보장.
    """
    anchor: dict[int, tuple[float, float]] = {}
    for ki, ji in matches:
        anchor[ki] = (jp_segments[ji]["start"], jp_segments[ji]["end"])
    if not anchor:
        return list(ko_cues)  # 매칭 0 — 원본 유지(고치지 못함)
    anchor_idx = sorted(anchor)
    out: list[Cue] = []
    for i, c in enumerate(ko_cues):
        dur = max(min_dur, c.end - c.start)  # 원래 읽기 길이 보존
        ns = anchor[i][0] if i in anchor else _interp_start(c.start, i, ko_cues, anchor, anchor_idx)
        out.append(Cue(i + 1, ns, ns + dur, c.text))
    out.sort(key=lambda x: x.start)
    # 끝시각 클램프: 항상 다음 큐 시작 직전까지(겹침 0 보장). 여유 있으면 원래 길이만큼,
    # 밀집 구간(저매칭 보간)은 짧게 깜빡 — 화면 가득 쌓이는 것보다 순차 표시가 낫다.
    for i, c in enumerate(out):
        end = min(c.end, c.start + max_dur)
        if i + 1 < len(out):
            end = min(end, out[i + 1].start - gap)
        if end <= c.start:
            end = c.start + 0.05  # 최소 양수 길이(겹침보다 짧은 표시 우선)
        c.end = end
        c.index = i + 1
    return out


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
