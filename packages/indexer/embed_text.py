"""bge-m3 -> Qdrant `videos` 컬렉션.

AI_PLAN.md §6.1 [5], §5.2.
- 컬렉션: vector size=1024 (bge-m3), distance=Cosine
- payload: opus, year, month, canonical_actresses[], tag_ids[], tag_names[],
           studio, rank, play, like_count, last_play, kind, video_path_present
- 문서 템플릿: §6.1 [5] 그대로
- 멱등: 같은 opus 는 같은 point id (SHA1(opus) -> uint64) 로 upsert
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema, load_embed_sigs, save_embed_sigs
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "videos"
VECTOR_DIM = 1024

_EMB = None


# --- 헬퍼 ---------------------------------------------------------


def _qdrant() -> QdrantClient:
    cfg = load_config()
    url = cfg["server"]["qdrant"].rstrip("/")
    return QdrantClient(url=url, prefer_grpc=False, timeout=60.0)


def opus_to_id(opus: str) -> int:
    """SHA1(opus) 의 첫 8바이트 -> 양의 int64."""
    h = hashlib.sha1(opus.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


def ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION in existing:
        return
    log.info("creating qdrant collection %s (size=%d, cosine)", COLLECTION, VECTOR_DIM)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(size=VECTOR_DIM, distance=qm.Distance.COSINE),
    )
    # payload 인덱스 (필터 빠르게)
    for field, ftype in [
        ("opus", qm.PayloadSchemaType.KEYWORD),
        ("year", qm.PayloadSchemaType.INTEGER),
        ("month", qm.PayloadSchemaType.INTEGER),
        ("studio", qm.PayloadSchemaType.KEYWORD),
        ("kind", qm.PayloadSchemaType.KEYWORD),
        ("canonical_actresses", qm.PayloadSchemaType.KEYWORD),
        ("tag_ids", qm.PayloadSchemaType.INTEGER),
        ("rank", qm.PayloadSchemaType.INTEGER),
        ("like_count", qm.PayloadSchemaType.INTEGER),
        ("play", qm.PayloadSchemaType.INTEGER),
        ("playable", qm.PayloadSchemaType.BOOL),
    ]:
        try:
            client.create_payload_index(COLLECTION, field, field_schema=ftype)
        except Exception as e:
            log.debug("index create skipped %s: %s", field, e)


def _embedder():
    global _EMB
    if _EMB is None:
        from sentence_transformers import SentenceTransformer

        cfg = load_config()
        log.info("loading embedding model %s", cfg["models"]["embedding"])
        _EMB = SentenceTransformer(cfg["models"]["embedding"])
    return _EMB


# --- 문서 빌드 ----------------------------------------------------


def _fetch_video_bundle(conn: sqlite3.Connection, opus: str) -> dict | None:
    v = conn.execute(
        """
        SELECT opus, title_jp, title_ko, desc_jp, desc_ko, comment,
               studio, release_year, release_month, kind,
               play, rank, last_play, like_count
        FROM videos WHERE opus = ?
    """,
        (opus,),
    ).fetchone()
    if not v:
        return None
    actrs = [
        r["canonical_name"]
        for r in conn.execute("SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))
    ]
    tags = list(
        conn.execute(
            """
        SELECT t.id, t.name, t.description, t.group_id
        FROM video_tags vt JOIN tags t ON t.id = vt.tag_id
        WHERE vt.opus = ?
    """,
            (opus,),
        )
    )
    poster = conn.execute(
        "SELECT video_path, caption FROM posters WHERE opus = ?", (opus,)
    ).fetchone()
    return {
        "video": dict(v),
        "actresses": actrs,
        "tags": tags,
        "video_path": (poster["video_path"] if poster else None),
        "caption": (poster["caption"] if poster else None),
    }


def _build_document(b: dict) -> str:
    v = b["video"]
    tag_block = ", ".join(
        f"{t['name']}{('('+t['description']+')') if t['description'] else ''}" for t in b["tags"]
    )
    ym = ""
    if v["release_year"]:
        ym = (
            f"{v['release_year']:04d}-{v['release_month']:02d}"
            if v["release_month"]
            else f"{v['release_year']:04d}"
        )
    return (
        f"[제목 JP] {v['title_jp'] or ''}\n"
        f"[제목 KO] {v['title_ko'] or ''}\n"
        f"[설명] {v['desc_ko'] or v['desc_jp'] or ''}\n"
        f"[장면] {b.get('caption') or ''}\n"  # 포스터 VLM 캡션(장소/의상/분위기 등 시각 속성)
        f"출연: {', '.join(b['actresses'])}\n"
        f"태그: {tag_block}\n"
        f"제작: {v['studio'] or ''}\n"
        f"발매: {ym}\n"
        f"코멘트: {v['comment'] or ''}\n"
        f"종류: {v['kind'] or ''}"
    )


def _build_payload(b: dict) -> dict:
    v = b["video"]
    return {
        "opus": v["opus"],
        "year": v["release_year"],
        "month": v["release_month"],
        "studio": v["studio"],
        "kind": v["kind"],
        "canonical_actresses": b["actresses"],
        "tag_ids": [t["id"] for t in b["tags"]],
        "tag_names": [t["name"] for t in b["tags"]],
        "rank": v["rank"] or 0,
        "play": v["play"] or 0,
        "like_count": v["like_count"] or 0,
        "last_play": v["last_play"],
        "playable": bool(b["video_path"]),
        "video_path_present": bool(b["video_path"]),
    }


# --- 실행 ---------------------------------------------------------


def _opus_iter(conn: sqlite3.Connection, limit: int | None) -> list[str]:
    sql = "SELECT opus FROM videos ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r["opus"] for r in conn.execute(sql)]


def _batched(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _existing_ids(qc: QdrantClient, collection: str) -> set[int]:
    """컬렉션에 이미 존재하는 point id 집합(증분 시드용). 실패/부재 시 빈 set."""
    ids: set[int] = set()
    try:
        offset = None
        while True:
            points, offset = qc.scroll(
                collection_name=collection,
                limit=10000,
                with_payload=False,
                with_vectors=False,
                offset=offset,
            )
            ids.update(int(p.id) for p in points)
            if offset is None:
                break
    except Exception as e:  # 컬렉션이 막 생성됐거나 비었을 때
        log.debug("scroll %s ids skipped: %s", collection, e)
    return ids


def _doc_sig(document: str) -> str:
    return hashlib.sha1(document.encode("utf-8")).hexdigest()


def run(limit: int | None = None, batch_size: int | None = None, force: bool = False) -> dict:
    """증분: 문서(벡터 입력) 해시가 직전과 같으면 스킵. payload 갱신은 sync-payload 담당.

    force=True 면 시그니처 무시하고 전량 재임베딩(clean 재구축용).
    """
    cfg = load_config()
    bs = int(batch_size or cfg["indexing"]["embed_batch_size"])
    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    ensure_collection(qc)
    emb = _embedder()

    all_opus = _opus_iter(conn, limit)
    total = len(all_opus)
    upserted = 0
    skipped = 0
    unchanged = 0

    sigs = {} if force else load_embed_sigs(conn, COLLECTION)
    existing = set() if force else _existing_ids(qc, COLLECTION)
    new_sigs: list[tuple[str, str]] = []

    for chunk in _batched(all_opus, bs):
        to_embed: list[tuple[dict, str, str]] = []  # (bundle, document, sig)
        for opus in chunk:
            b = _fetch_video_bundle(conn, opus)
            if b is None:
                skipped += 1
                continue
            doc = _build_document(b)
            sig = _doc_sig(doc)
            if not force:
                prev = sigs.get(opus)
                if prev == sig:
                    unchanged += 1
                    continue
                if prev is None and opus_to_id(opus) in existing:
                    # 첫 실행 시드: 기존 점은 유효하다고 보고 sig 만 기록(재임베딩 X)
                    new_sigs.append((opus, sig))
                    unchanged += 1
                    continue
            to_embed.append((b, doc, sig))
        if to_embed:
            vecs = emb.encode(
                [d for (_b, d, _s) in to_embed],
                batch_size=bs,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            points = [
                qm.PointStruct(
                    id=opus_to_id(b["video"]["opus"]),
                    vector=v.tolist(),
                    payload=_build_payload(b),
                )
                for (b, _d, _s), v in zip(to_embed, vecs)
            ]
            qc.upsert(collection_name=COLLECTION, points=points, wait=False)
            upserted += len(points)
            new_sigs.extend((b["video"]["opus"], s) for (b, _d, s) in to_embed)
            if upserted % (bs * 8) == 0:
                update_stage("embed_text", completed=upserted)
                log.info("embed_text %d / %d (unchanged %d)", upserted, total, unchanged)
        if len(new_sigs) >= 1000:
            save_embed_sigs(conn, COLLECTION, new_sigs)
            new_sigs = []

    save_embed_sigs(conn, COLLECTION, new_sigs)
    update_stage(
        "embed_text", done=True, completed=upserted, total=total, skipped=skipped + unchanged
    )
    conn.close()
    return {"total": total, "upserted": upserted, "skipped": skipped, "unchanged": unchanged}
