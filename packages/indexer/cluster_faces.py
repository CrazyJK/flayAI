"""GPU 가속 NN + Union-Find 기반 얼굴 클러스터링.

AI_PLAN.md §10 M4 / §5.2 — HDBSCAN은 200K+ 데이터에서 단일 코어로 수 시간 걸리므로
torch GPU(cosine matmul, block-wise)로 각 face의 top-K 이웃을 구한 뒤
threshold 이상이면 Union-Find 로 연결하는 방식으로 대체.

- 입력: Qdrant `faces` 컬렉션의 512-d 임베딩(L2-normalized) + payload
- 알고리즘:
    1) GPU에서 X @ X.T 의 block을 계산해 각 행의 top-K 이웃을 얻음
    2) sim >= threshold 인 (i, j) 쌍을 Union-Find로 묶음
    3) component size >= min_cluster_size 인 것만 유효 클러스터
    4) 각 클러스터의 단독 출연 actresses 다수결 → canonical_name (≥ conf_thr)
- 출력:
    - SQLite face_clusters: cluster_id, canonical_name, sample_count, confidence
    - SQLite poster_faces.cluster_id 채움
    - Qdrant `faces` payload.cluster_id 갱신
"""
from __future__ import annotations

import logging
from collections import Counter

import numpy as np

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _qdrant
from packages.indexer.faces import COLLECTION as FACES_COLLECTION
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)


# ----- 데이터 로드 -----------------------------------------------

def _scroll_all(qc) -> tuple[np.ndarray, list[dict]]:
    vectors: list[list[float]] = []
    metas: list[dict] = []
    next_page = None
    while True:
        points, next_page = qc.scroll(
            collection_name=FACES_COLLECTION,
            limit=2048,
            offset=next_page,
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            break
        for p in points:
            vectors.append(p.vector if isinstance(p.vector, list) else list(p.vector))
            metas.append({
                "id": p.id,
                "opus": p.payload.get("opus") if p.payload else None,
                "face_idx": p.payload.get("face_idx") if p.payload else None,
                "actresses": p.payload.get("canonical_actresses", []) if p.payload else [],
            })
        if next_page is None:
            break
    arr = np.asarray(vectors, dtype=np.float32)
    log.info("loaded %d face vectors (dim=%d)", len(arr), arr.shape[1] if len(arr) else 0)
    return arr, metas


# ----- Union-Find -----------------------------------------------

class _UF:
    __slots__ = ("p", "r")

    def __init__(self, n: int) -> None:
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x: int) -> int:
        p = self.p
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1


# ----- top-K NN (GPU block matmul) ------------------------------

def _topk_neighbors_gpu(
    X: np.ndarray, k: int, threshold: float, block: int = 4096,
    mutual: bool = True,
) -> list[tuple[int, int, float]]:
    """X(L2-normalized) 의 각 행에 대해 top-k 이웃 중 sim>=threshold 인 (i,j,sim) 반환.

    mutual=True 면 i∈topK(j) AND j∈topK(i) 인 쌍만 유지 (false edge 억제).
    """
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("topk-NN: n=%d k=%d threshold=%.3f mutual=%s device=%s",
             len(X), k, threshold, mutual, device)

    dtype = torch.float16 if device == "cuda" else torch.float32
    Xt = torch.from_numpy(X).to(device=device, dtype=dtype)
    N = Xt.shape[0]

    # 1) 각 노드의 top-K 이웃 집합 + score
    nbrs: list[list[tuple[int, float]]] = [[] for _ in range(N)]

    for bi, start in enumerate(range(0, N, block)):
        end = min(start + block, N)
        q = Xt[start:end]
        sims = q @ Xt.T
        ar = torch.arange(start, end, device=device)
        sims[torch.arange(end - start, device=device), ar] = -1.0
        topv, topi = torch.topk(sims, k=k, dim=1)
        topv_cpu = topv.float().cpu().numpy()
        topi_cpu = topi.cpu().numpy()
        for r in range(end - start):
            gi = start + r
            row: list[tuple[int, float]] = []
            for c in range(k):
                s = float(topv_cpu[r, c])
                if s < threshold:
                    break
                row.append((int(topi_cpu[r, c]), s))
            nbrs[gi] = row
        if bi % 5 == 0 or end == N:
            log.info("  topk-NN %d/%d", end, N)

    # 2) edge 후보 수집 (i<j 정규화)
    edges: dict[tuple[int, int], float] = {}
    if mutual:
        nbr_sets = [set(j for j, _ in row) for row in nbrs]
        for i, row in enumerate(nbrs):
            for j, s in row:
                if i in nbr_sets[j]:           # mutual
                    a, b = (i, j) if i < j else (j, i)
                    if a == b:
                        continue
                    prev = edges.get((a, b))
                    if prev is None or prev < s:
                        edges[(a, b)] = s
    else:
        for i, row in enumerate(nbrs):
            for j, s in row:
                if i == j:
                    continue
                a, b = (i, j) if i < j else (j, i)
                prev = edges.get((a, b))
                if prev is None or prev < s:
                    edges[(a, b)] = s

    return [(a, b, s) for (a, b), s in edges.items()]


# ----- main -----------------------------------------------------

def run(
    min_cluster_size: int | None = None,
    min_samples: int | None = None,           # 호환용 (미사용)
    confidence_threshold: float | None = None,
    sim_threshold: float = 0.6,
    knn: int = 16,
) -> dict:
    cfg = load_config()
    mcs = int(min_cluster_size or cfg["indexing"]["hdbscan_min_cluster_size"])
    conf_thr = float(confidence_threshold
                     or cfg["indexing"]["face_mapping_confidence_threshold"])
    _ = min_samples

    qc = _qdrant()
    vectors, metas = _scroll_all(qc)
    if len(vectors) == 0:
        log.warning("no faces; run extract-faces first")
        return {"faces": 0, "clusters": 0, "labeled": 0, "noise": 0}

    norms = np.linalg.norm(vectors, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-3):
        log.info("re-normalizing (median norm=%.4f)", float(np.median(norms)))
        vectors = vectors / np.clip(norms[:, None], 1e-9, None)

    edges = _topk_neighbors_gpu(vectors, k=knn, threshold=sim_threshold)
    log.info("graph edges=%d (sim>=%.2f)", len(edges), sim_threshold)

    n = len(vectors)
    uf = _UF(n)
    for i, j, _s in edges:
        uf.union(i, j)

    comp_members: dict[int, list[int]] = {}
    for i in range(n):
        comp_members.setdefault(uf.find(i), []).append(i)

    labels = np.full(n, -1, dtype=np.int64)
    cluster_id = 0
    valid_clusters: dict[int, list[int]] = {}
    for _root, members in comp_members.items():
        if len(members) < mcs:
            continue
        for m in members:
            labels[m] = cluster_id
        valid_clusters[cluster_id] = members
        cluster_id += 1

    noise = int((labels == -1).sum())
    log.info("components=%d clusters>=%d=%d noise=%d",
             len(comp_members), mcs, len(valid_clusters), noise)

    cluster_rows: list[tuple[int, str | None, int, float]] = []
    for cid, members in valid_clusters.items():
        votes: Counter[str] = Counter()
        for i in members:
            actrs = metas[i]["actresses"]
            if isinstance(actrs, list) and len(actrs) == 1 and actrs[0]:
                votes[actrs[0]] += 1
        sample_count = len(members)
        if not votes:
            cluster_rows.append((cid, None, sample_count, 0.0))
            continue
        top_name, top_count = votes.most_common(1)[0]
        confidence = top_count / sum(votes.values())
        name = top_name if confidence >= conf_thr else None
        cluster_rows.append((cid, name, sample_count, round(float(confidence), 4)))

    conn = connect()
    init_schema(conn)
    with conn:
        conn.execute("DELETE FROM face_clusters")
        conn.executemany(
            "INSERT INTO face_clusters (cluster_id, canonical_name, sample_count, confidence) "
            "VALUES (?, ?, ?, ?)", cluster_rows,
        )
        conn.execute("UPDATE poster_faces SET cluster_id = NULL")
        rows = [
            (int(lbl) if lbl != -1 else None, m["opus"], m["face_idx"])
            for lbl, m in zip(labels, metas)
        ]
        conn.executemany(
            "UPDATE poster_faces SET cluster_id = ? "
            "WHERE poster_opus = ? AND face_idx = ?",
            rows,
        )

    by_cid: dict[int | None, list[int]] = {}
    for lbl, m in zip(labels, metas):
        cid = int(lbl) if lbl != -1 else None
        by_cid.setdefault(cid, []).append(m["id"])

    log.info("updating Qdrant payload for %d cluster groups", len(by_cid))
    for cid, ids in by_cid.items():
        for off in range(0, len(ids), 1000):
            chunk = ids[off:off + 1000]
            qc.set_payload(
                collection_name=FACES_COLLECTION,
                payload={"cluster_id": cid},
                points=chunk,
                wait=False,
            )

    labeled = sum(1 for r in cluster_rows if r[1])
    update_stage("cluster_faces", done=True,
                 faces=int(len(vectors)),
                 clusters=int(len(valid_clusters)),
                 labeled=int(labeled),
                 noise=int(noise))
    conn.close()
    return {
        "faces": int(len(vectors)),
        "edges": int(len(edges)),
        "clusters": int(len(valid_clusters)),
        "labeled": int(labeled),
        "noise": int(noise),
        "sim_threshold": sim_threshold,
        "knn": knn,
    }
