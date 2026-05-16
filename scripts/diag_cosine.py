"""Self-search top-1 cosine 분포 측정.

전체 videos 컬렉션에서 N개 샘플을 뽑아 자기 자신을 query 로 검색했을 때
top-1 (자기 자신 제외 top-1) cosine 점수의 분포를 본다. 자기-자신은 1.0이라
의미가 없고, 의미적 유사 영상의 top-1 가 ≥0.5 비율이 acceptance 지표.
"""
from __future__ import annotations

import random
import sys

from packages.settings import load_config
from qdrant_client import QdrantClient


def main() -> int:
    cfg = load_config()
    url = cfg["server"]["qdrant"].rstrip("/")
    qc = QdrantClient(url=url)
    coll = "videos"
    info = qc.get_collection(coll)
    total = info.points_count
    print(f"collection={coll} points={total}")
    sample_n = min(200, total)

    # 랜덤 offset 으로 N 개 fetch
    pts, _ = qc.scroll(coll, limit=sample_n, with_vectors=True, with_payload=False)
    random.seed(42)
    random.shuffle(pts)
    pts = pts[:sample_n]

    scores = []
    for p in pts:
        vec = p.vector
        if vec is None:
            continue
        res = qc.query_points(coll, query=vec, limit=2, with_payload=False).points
        # res[0] 자기자신, res[1] 두번째
        if len(res) >= 2:
            scores.append(res[1].score)

    scores.sort(reverse=True)
    n = len(scores)
    if not n:
        print("no scores")
        return 1
    ge_05 = sum(1 for s in scores if s >= 0.5)
    ge_07 = sum(1 for s in scores if s >= 0.7)
    print(f"sampled={n}")
    print(f"top-1 (excl self) cosine >= 0.5 : {ge_05}/{n} = {ge_05*100/n:.1f}%")
    print(f"top-1 (excl self) cosine >= 0.7 : {ge_07}/{n} = {ge_07*100/n:.1f}%")
    print(f"min={scores[-1]:.3f} median={scores[n//2]:.3f} max={scores[0]:.3f}")
    return 0 if ge_05 * 100 / n > 70 else 1


if __name__ == "__main__":
    sys.exit(main())
