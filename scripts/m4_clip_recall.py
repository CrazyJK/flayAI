"""posters_clip self-search top-1 recall 측정.

이미 임베딩된 포스터에 대해, 각 포스터 이미지를 다시 인코딩 -> Qdrant search
-> top-1 hit 의 opus 가 자기 자신인지 비교.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import torch
from PIL import Image

from packages.indexer.db import connect
from packages.indexer.embed_clip import COLLECTION, _load_model
from packages.indexer.embed_text import _qdrant

log = logging.getLogger(__name__)


def run(sample: int) -> None:
    qc = _qdrant()
    conn = connect()
    model, preprocess, device = _load_model()

    # 임베딩된 opus 목록 (sample 갯수만)
    rows = conn.execute(
        "SELECT opus, path FROM posters WHERE path IS NOT NULL ORDER BY opus LIMIT ?",
        (sample,),
    ).fetchall()
    if not rows:
        print("no rows")
        return

    hits = 0
    misses = 0
    t0 = time.time()
    for r in rows:
        opus, path = r["opus"], r["path"]
        try:
            im = Image.open(Path(path)).convert("RGB")
        except Exception as e:
            log.warning("skip %s: %s", opus, e)
            misses += 1
            continue
        batch = preprocess(im).unsqueeze(0).to(device)
        with torch.no_grad():
            feats = model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        vec = feats[0].cpu().tolist()
        res = qc.query_points(
            collection_name=COLLECTION,
            query=vec,
            limit=1,
            with_payload=True,
        ).points
        if not res:
            misses += 1
            continue
        top = res[0]
        top_opus = top.payload.get("opus") if top.payload else None
        if top_opus == opus:
            hits += 1
        else:
            misses += 1
            print(f"MISS  {opus}  ->  {top_opus}  score={top.score:.4f}")

    total = hits + misses
    elapsed = time.time() - t0
    print(f"\nRECALL@1 = {hits}/{total} = {hits/total:.4f}  "
          f"(misses={misses}, elapsed={elapsed:.1f}s)")
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=20)
    args = p.parse_args()
    run(args.sample)
