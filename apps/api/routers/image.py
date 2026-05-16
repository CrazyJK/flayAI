"""이미지/얼굴 검색 라우터 (AI_PLAN.md §10 M4).

엔드포인트:
- POST /api/image/search/text   {query, limit}                -> CLIP text -> posters_clip
- POST /api/image/search        (multipart: file)              -> CLIP image -> posters_clip
- POST /api/face/search         (multipart: file)              -> InsightFace -> faces 클러스터 집계
"""
from __future__ import annotations

import io
import logging
import time
from collections import Counter
from typing import Any

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from PIL import Image
from pydantic import BaseModel
from qdrant_client.http import models as qm

from packages.indexer.db import connect
from packages.indexer.embed_clip import COLLECTION as POSTERS_CLIP, _load_model as _load_clip
from packages.indexer.embed_text import _qdrant
from packages.indexer.faces import COLLECTION as FACES, _load_face_app
from packages.rag.tools import _video_to_hit

log = logging.getLogger(__name__)
router = APIRouter()


# --- 모델 ---------------------------------------------------------

class ImageTextSearchRequest(BaseModel):
    query: str
    limit: int = 12
    kind: str | None = None  # 'instance' | 'archive' | None


def _kind_filter(kind: str | None) -> qm.Filter | None:
    if kind not in ("instance", "archive"):
        return None
    return qm.Filter(must=[
        qm.FieldCondition(key="kind", match=qm.MatchValue(value=kind))
    ])


def _hits_from_posters(points) -> list[dict[str, Any]]:
    """posters_clip 검색 결과 → video hit 형식 (RAG tool과 동일)."""
    conn = connect()
    out = []
    try:
        for p in points:
            opus = p.payload.get("opus") if p.payload else None
            if not opus:
                continue
            hit = _video_to_hit(conn, opus)
            if hit:
                hit["score"] = round(float(p.score), 4)
                out.append(hit)
    finally:
        conn.close()
    return out


# --- CLIP text ---------------------------------------------------

@router.post("/api/image/search/text")
def image_search_text(req: ImageTextSearchRequest) -> dict[str, Any]:
    import open_clip
    import torch

    model, _, device = _load_clip()
    # text tokenizer는 모델 이름 기반
    from packages.settings import load_config
    cfg = load_config()
    tokenizer = open_clip.get_tokenizer(cfg["models"]["clip_model"])
    toks = tokenizer([req.query]).to(device)
    with torch.no_grad():
        feats = model.encode_text(toks)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    vec = feats[0].cpu().tolist()

    qc = _qdrant()
    res = qc.query_points(
        collection_name=POSTERS_CLIP,
        query=vec,
        limit=req.limit,
        query_filter=_kind_filter(req.kind),
        with_payload=True,
    ).points
    return {"items": _hits_from_posters(res)}


# --- CLIP image upload -------------------------------------------

def _read_image(file: UploadFile) -> Image.Image:
    try:
        data = file.file.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"invalid image: {e}") from None


@router.post("/api/image/search")
def image_search(
    file: UploadFile = File(...),
    limit: int = Query(12, ge=1, le=50),
    kind: str | None = Query(None),
) -> dict[str, Any]:
    import torch
    im = _read_image(file)
    model, preprocess, device = _load_clip()
    batch = preprocess(im).unsqueeze(0).to(device)
    with torch.no_grad():
        feats = model.encode_image(batch)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    vec = feats[0].cpu().tolist()
    qc = _qdrant()
    res = qc.query_points(
        collection_name=POSTERS_CLIP,
        query=vec,
        limit=limit,
        query_filter=_kind_filter(kind),
        with_payload=True,
    ).points
    return {"items": _hits_from_posters(res)}


# --- Face upload --------------------------------------------------

@router.post("/api/face/search")
def face_search(
    file: UploadFile = File(...),
    top_k: int = Query(5, ge=1, le=20, description="반환 배우 수"),
    face_neighbors: int = Query(50, ge=10, le=200,
                                description="가까운 얼굴 N개를 끌어와 다수결"),
) -> dict[str, Any]:
    t0 = time.time()
    im = _read_image(file)
    arr = np.array(im)[:, :, ::-1]  # BGR

    fa = _load_face_app()
    faces = fa.get(arr)
    if not faces:
        return {"actresses": [], "neighbors": [], "elapsed_ms": int((time.time() - t0) * 1000),
                "message": "no face detected"}

    # 가장 큰(면적) 얼굴 사용
    def _area(f) -> float:
        x1, y1, x2, y2 = f.bbox.tolist()
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    f0 = max(faces, key=_area)
    emb = getattr(f0, "normed_embedding", None)
    if emb is None:
        emb = f0.embedding / (np.linalg.norm(f0.embedding) + 1e-9)
    vec = emb.tolist()

    qc = _qdrant()
    res = qc.query_points(
        collection_name=FACES,
        query=vec,
        limit=face_neighbors,
        with_payload=True,
    ).points

    # 1) 클러스터 다수결 → face_clusters.canonical_name 로 조회
    cluster_votes: Counter[int] = Counter()
    cluster_scores: dict[int, float] = {}
    actress_votes: Counter[str] = Counter()
    actress_scores: dict[str, float] = {}
    neighbors_out: list[dict[str, Any]] = []
    for p in res:
        pl = p.payload or {}
        cid = pl.get("cluster_id")
        score = float(p.score)
        if isinstance(cid, int):
            cluster_votes[cid] += 1
            cluster_scores[cid] = max(cluster_scores.get(cid, 0.0), score)
        # actresses payload 활용 (단독 출연만 의미있는 신호)
        actrs = pl.get("canonical_actresses") or []
        if isinstance(actrs, list) and len(actrs) == 1 and actrs[0]:
            a = actrs[0]
            actress_votes[a] += 1
            actress_scores[a] = max(actress_scores.get(a, 0.0), score)
        if len(neighbors_out) < 10:
            neighbors_out.append({
                "opus": pl.get("opus"),
                "face_idx": pl.get("face_idx"),
                "cluster_id": cid,
                "score": round(score, 4),
                "actresses": actrs,
            })

    # 클러스터 → canonical_name 조회
    actress_from_cluster: Counter[str] = Counter()
    actress_from_cluster_score: dict[str, float] = {}
    if cluster_votes:
        conn = connect()
        try:
            placeholders = ",".join("?" for _ in cluster_votes)
            rows = conn.execute(
                f"SELECT cluster_id, canonical_name FROM face_clusters "
                f"WHERE cluster_id IN ({placeholders})",
                list(cluster_votes.keys()),
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            name = r["canonical_name"]
            if not name:
                continue
            cid = int(r["cluster_id"])
            actress_from_cluster[name] += cluster_votes[cid]
            actress_from_cluster_score[name] = max(
                actress_from_cluster_score.get(name, 0.0),
                cluster_scores.get(cid, 0.0),
            )

    # 융합: 클러스터 매핑 우선, 부족하면 단독 출연 다수결로 보강
    fused: Counter[str] = Counter()
    fused_score: dict[str, float] = {}
    for a, v in actress_from_cluster.items():
        fused[a] += v * 2  # 클러스터 가중치
        fused_score[a] = max(fused_score.get(a, 0.0), actress_from_cluster_score[a])
    for a, v in actress_votes.items():
        fused[a] += v
        fused_score[a] = max(fused_score.get(a, 0.0), actress_scores[a])

    top = []
    for a, v in fused.most_common(top_k):
        top.append({"name": a, "votes": int(v), "best_score": round(fused_score[a], 4)})

    return {
        "actresses": top,
        "neighbors": neighbors_out,
        "faces_detected": len(faces),
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


# --- 얼굴 클러스터 조회/라벨링 ----------------------------------

class ClusterLabelRequest(BaseModel):
    canonical_name: str | None  # null → 라벨 해제
    confidence: float | None = None


@router.get("/api/face/clusters")
def list_clusters(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    only_unlabeled: bool = Query(False),
    min_size: int = Query(2, ge=1),
) -> dict[str, Any]:
    conn = connect()
    try:
        where = ["sample_count >= ?"]
        params: list[Any] = [min_size]
        if only_unlabeled:
            where.append("canonical_name IS NULL")
        where_sql = " AND ".join(where)
        rows = conn.execute(
            f"SELECT cluster_id, canonical_name, sample_count, confidence "
            f"FROM face_clusters WHERE {where_sql} "
            f"ORDER BY sample_count DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM face_clusters WHERE {where_sql}",
            params,
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "items": [dict(r) for r in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/face/clusters/{cluster_id}/samples")
def cluster_samples(cluster_id: int, limit: int = Query(12, ge=1, le=50)) -> dict[str, Any]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT pf.poster_opus, pf.face_idx, pf.bbox, "
            "       v.title, v.studio, v.year, "
            "       (SELECT GROUP_CONCAT(canonical_name) FROM video_actresses "
            "        WHERE opus = pf.poster_opus) AS actresses "
            "FROM poster_faces pf "
            "LEFT JOIN videos v ON v.opus = pf.poster_opus "
            "WHERE pf.cluster_id = ? "
            "ORDER BY pf.poster_opus LIMIT ?",
            (cluster_id, limit),
        ).fetchall()
        cluster = conn.execute(
            "SELECT cluster_id, canonical_name, sample_count, confidence "
            "FROM face_clusters WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()
    finally:
        conn.close()
    if not cluster:
        raise HTTPException(404, "cluster not found")
    items = []
    for r in rows:
        d = dict(r)
        d["actresses"] = (d.get("actresses") or "").split(",") if d.get("actresses") else []
        items.append(d)
    return {"cluster": dict(cluster), "samples": items}


@router.post("/api/face/clusters/{cluster_id}/label")
def label_cluster(cluster_id: int, req: ClusterLabelRequest) -> dict[str, Any]:
    name = req.canonical_name.strip() if req.canonical_name else None
    if name == "":
        name = None
    conf = req.confidence if req.confidence is not None else (1.0 if name else None)
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE face_clusters SET canonical_name = ?, confidence = ? "
                "WHERE cluster_id = ?",
                (name, conf, cluster_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "cluster not found")
    finally:
        conn.close()
    return {"cluster_id": cluster_id, "canonical_name": name, "confidence": conf}