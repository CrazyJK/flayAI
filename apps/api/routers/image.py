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

from packages.indexer.caption_posters import COLLECTION as POSTER_CAPTION
from packages.indexer.db import connect
from packages.indexer.embed_clip import COLLECTION as POSTERS_CLIP
from packages.indexer.embed_clip import _load_model as _load_clip
from packages.indexer.embed_text import _embedder, _qdrant
from packages.indexer.faces import COLLECTION as FACES
from packages.indexer.faces import _load_face_app
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
    return qm.Filter(must=[qm.FieldCondition(key="kind", match=qm.MatchValue(value=kind))])


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


def _hits_from_opus(opus_list: list[str], score_map: dict[str, float]) -> list[dict[str, Any]]:
    """opus 리스트 → video hit 형식 (RRF 결합 결과용)."""
    conn = connect()
    out = []
    try:
        for opus in opus_list:
            hit = _video_to_hit(conn, opus)
            if hit:
                hit["score"] = round(float(score_map.get(opus, 0.0)), 4)
                out.append(hit)
    finally:
        conn.close()
    return out


RRF_K = 60


def _rrf_merge(*point_lists) -> tuple[list[str], dict[str, float]]:
    """여러 검색 결과(points)를 RRF(rank 기반)로 결합. (정렬된 opus, opus별 최대 raw score)."""
    rrf: dict[str, float] = {}
    raw: dict[str, float] = {}
    for pts in point_lists:
        for rank, p in enumerate(pts):
            opus = (p.payload or {}).get("opus")
            if not opus:
                continue
            rrf[opus] = rrf.get(opus, 0.0) + 1.0 / (RRF_K + rank + 1)
            raw[opus] = max(raw.get(opus, 0.0), float(p.score))
    ordered = sorted(rrf, key=lambda o: rrf[o], reverse=True)
    return ordered, raw


def _caption_search(query: str, limit: int, kind: str | None):
    """bge-m3 로 질의 임베딩 → poster_caption 검색. 컬렉션 없으면(캡션 미실행) 빈 결과."""
    try:
        vec = _embedder().encode([query], normalize_embeddings=True)[0].tolist()
        return (
            _qdrant()
            .query_points(
                collection_name=POSTER_CAPTION,
                query=vec,
                limit=limit,
                query_filter=_kind_filter(kind),
                with_payload=True,
            )
            .points
        )
    except Exception as e:
        log.debug("caption search skipped (poster_caption 미존재 가능): %s", e)
        return []


# --- 텍스트 → 포스터 (CLIP + 캡션 하이브리드) --------------------


@router.post("/api/image/search/text")
def image_search_text(req: ImageTextSearchRequest) -> dict[str, Any]:
    import open_clip
    import torch

    from packages.settings import load_config

    pool = max(req.limit * 2, 20)  # RRF 결합 여유분

    # 1) CLIP 텍스트 → posters_clip (시각 유사)
    model, _, device = _load_clip()
    cfg = load_config()
    tokenizer = open_clip.get_tokenizer(cfg["models"]["clip_model"])
    toks = tokenizer([req.query]).to(device)
    with torch.no_grad():
        feats = model.encode_text(toks)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    clip_vec = feats[0].cpu().tolist()
    qc = _qdrant()
    clip_pts = qc.query_points(
        collection_name=POSTERS_CLIP,
        query=clip_vec,
        limit=pool,
        query_filter=_kind_filter(req.kind),
        with_payload=True,
    ).points

    # 2) bge-m3 캡션 → poster_caption (한국어 자연어 의미; 캡션 미실행 시 빈 결과)
    cap_pts = _caption_search(req.query, pool, req.kind)

    # 3) RRF 결합 후 상위 limit
    ordered, raw = _rrf_merge(clip_pts, cap_pts)
    return {"items": _hits_from_opus(ordered[: req.limit], raw)}


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
    face_neighbors: int = Query(50, ge=10, le=200, description="가까운 얼굴 N개를 끌어와 다수결"),
) -> dict[str, Any]:
    t0 = time.time()
    im = _read_image(file)
    arr = np.array(im)[:, :, ::-1]  # BGR

    fa = _load_face_app()
    faces = fa.get(arr)
    if not faces:
        return {
            "actresses": [],
            "neighbors": [],
            "elapsed_ms": int((time.time() - t0) * 1000),
            "message": "no face detected",
        }

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
            neighbors_out.append(
                {
                    "opus": pl.get("opus"),
                    "face_idx": pl.get("face_idx"),
                    "cluster_id": cid,
                    "score": round(score, 4),
                    "actresses": actrs,
                }
            )

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
    has_instance: bool = Query(False),
) -> dict[str, Any]:
    conn = connect()
    try:
        where = ["fc.sample_count >= ?"]
        params: list[Any] = [min_size]
        if only_unlabeled:
            where.append("fc.canonical_name IS NULL")
        if has_instance:
            where.append(
                "EXISTS (SELECT 1 FROM poster_faces pf "
                "        JOIN videos v ON v.opus = pf.poster_opus "
                "        WHERE pf.cluster_id = fc.cluster_id AND v.kind = 'instance')"
            )
        where_sql = " AND ".join(where)
        rows = conn.execute(
            f"SELECT fc.cluster_id, fc.canonical_name, fc.sample_count, fc.confidence "
            f"FROM face_clusters fc WHERE {where_sql} "
            f"ORDER BY fc.sample_count DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM face_clusters fc WHERE {where_sql}",
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
        # 한 poster_opus 내 같은 클러스터로 분류된 얼굴이 여러 개일 수 있어
        # 라벨링 표시용으로는 face_idx 최소값 한 건만 노출 (중복 카드 방지).
        rows = conn.execute(
            "SELECT pf.poster_opus, pf.face_idx, pf.bbox, "
            "       v.title_ko, v.title_jp, v.studio, "
            "       v.release_year, v.release_month, "
            "       (SELECT GROUP_CONCAT(canonical_name) FROM video_actresses "
            "        WHERE opus = pf.poster_opus) AS actresses "
            "FROM poster_faces pf "
            "JOIN ( "
            "    SELECT poster_opus, MIN(face_idx) AS face_idx "
            "    FROM poster_faces "
            "    WHERE cluster_id = ? "
            "    GROUP BY poster_opus "
            ") s ON s.poster_opus = pf.poster_opus AND s.face_idx = pf.face_idx "
            "LEFT JOIN videos v ON v.opus = pf.poster_opus "
            "WHERE pf.cluster_id = ? "
            "ORDER BY pf.poster_opus LIMIT ?",
            (cluster_id, cluster_id, limit),
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
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE face_clusters SET canonical_name = ?, confidence = ? "
                    "WHERE cluster_id = ?",
                    (name, conf, cluster_id),
                )
            # rowcount 체크는 with 블록 밖에서 (commit 완료 후)
            if cur.rowcount == 0:
                raise HTTPException(404, "cluster not found")
        except HTTPException:
            raise
        except Exception as e:
            log.error("label_cluster error cluster_id=%s: %s", cluster_id, e, exc_info=True)
            raise HTTPException(500, f"저장 실패: {e}") from e
    finally:
        conn.close()
    return {"cluster_id": cluster_id, "canonical_name": name, "confidence": conf}


@router.delete("/api/face/clusters/{cluster_id}/samples/{poster_opus}/{face_idx}")
def exclude_sample(cluster_id: int, poster_opus: str, face_idx: int) -> dict[str, Any]:
    """특정 포스터 얼굴을 클러스터에서 제외 (cluster_id = NULL 처리)."""
    conn = connect()
    try:
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE poster_faces SET cluster_id = NULL "
                    "WHERE cluster_id = ? AND poster_opus = ? AND face_idx = ?",
                    (cluster_id, poster_opus, face_idx),
                )
                if cur.rowcount > 0:
                    conn.execute(
                        "UPDATE face_clusters SET sample_count = MAX(0, sample_count - 1) "
                        "WHERE cluster_id = ?",
                        (cluster_id,),
                    )
        except Exception as e:
            log.error(
                "exclude_sample error cluster_id=%s opus=%s: %s",
                cluster_id,
                poster_opus,
                e,
                exc_info=True,
            )
            raise HTTPException(500, f"제외 실패: {e}") from e
    finally:
        conn.close()
    return {"ok": True, "cluster_id": cluster_id, "poster_opus": poster_opus, "face_idx": face_idx}
