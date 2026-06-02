"""VLM(비전언어모델) 포스터 캡션 -> posters.caption + Qdrant poster_caption.

비전 모델이 포스터 이미지를 보고 한국어 '검색용 장면 설명 + 태그'를 생성한다. 결과는 두 곳에 쓰인다:
- SQLite posters.caption -> embed_text 의 [장면] 블록으로 videos 임베딩에 합류(채팅 검색).
- Qdrant poster_caption -> bge-m3 임베딩(이미지 화면 텍스트->포스터 CLIP+캡션 하이브리드 검색).

- 모델: config.models.vision (예: huihui_ai/gemma-4-abliterated:e4b). Ollama /api/chat.
  gemma 계열은 think=False 로 추론을 꺼서 빠르게 답을 받는다(장당 ~3초).
- caption 이 비어있는 포스터만 처리(resumable). 전체 재생성은 force=True.
- 프롬프트는 '검색용 변별 속성'(장소/의상 종류/인원·성별/특징)에 집중하고, 거의 모든
  포스터에 해당하는 일반어(화보·포즈·다양한·여성·스튜디오 등)는 금지해 검색 신호를 높인다.
  특징이 없으면 '불명/없음'으로 두게 하고, 저장 시 그 줄을 제거해 문서를 깔끔히 유지.
"""

from __future__ import annotations

import base64
import logging
import sqlite3
import time
from collections.abc import Iterable

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from packages.indexer.db import connect, init_schema
from packages.indexer.embed_text import _embedder, _qdrant, opus_to_id
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

COLLECTION = "poster_caption"
VECTOR_DIM = 1024  # bge-m3

# 검색용 변별 속성 추출 프롬프트.
# 핵심: 거의 모든 포스터에 참인 일반어(화보/포즈/다양한/여성/스튜디오 등)는 금지해 검색
# 신호를 높이고, 특징이 없으면 '불명/없음'으로 두게 한다(없는 장면을 지어내지 않게).
PROMPT = (
    "이 AV 포스터 이미지를 보고 '검색용 시각 속성'만 한국어로 추출하세요. "
    "이미지에 실제로 보이는 것만 적고, 추측·노골적 묘사·광고문구는 쓰지 마세요.\n"
    "반드시 지킬 규칙:\n"
    "- 다음 일반어는 절대 쓰지 마세요(거의 모든 포스터에 해당해 검색에 무용): "
    "화보, 포즈, 다양한, 매력적, 여성, 모델, 스튜디오, 인물사진, 콜라주, 이미지.\n"
    "- 특징적 장소·의상·상황이 안 보이면 억지로 만들지 말고 '불명' 또는 '없음'으로 두세요.\n"
    "다음 형식으로만 출력(한국어):\n"
    "장소: <구체 장소 1개. 해변/교실/사무실/침실/주방/욕실/온천/야외/길거리/차량/수영장/병원/체육관 등. 단색·세트 배경이면 '불명'>\n"
    "의상: <복장 종류. 교복/간호사복/수영복/비키니/기모노/정장/드레스/란제리/체육복/메이드복/코스프레/일상복 등. 노출정도 말고 종류만. 모르면 '불명'>\n"
    "인원: <보이는 사람 수와 성별. 예: 여성 1명 / 여성 2명 / 여성 여러명 / 남녀 혼성>\n"
    "특징: <포스터에서만 알 수 있는 구체 단서 1~2개(소품·헤어·배경물·상황). 없으면 '없음'>"
)

# 값이 '불명/없음' 류인 줄은 검색 신호가 없으므로 저장 전에 제거.
_EMPTY_VALUES = {"불명", "없음", "모름", "불명확", "해당없음", "-", ""}


def _clean_caption(text: str) -> str:
    """캡션에서 값이 비어있는(불명/없음) 줄을 제거. 전부 비면 원본 유지."""
    kept: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            _label, _, val = line.partition(":")
            if val.strip() in _EMPTY_VALUES:
                continue
        kept.append(line)
    return "\n".join(kept) if kept else text.strip()


# --- Qdrant ------------------------------------------------------


def ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION in existing:
        return
    log.info("creating qdrant collection %s (size=%d, cosine)", COLLECTION, VECTOR_DIM)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(size=VECTOR_DIM, distance=qm.Distance.COSINE),
    )
    for field, ftype in [
        ("opus", qm.PayloadSchemaType.KEYWORD),
        ("kind", qm.PayloadSchemaType.KEYWORD),
        ("year", qm.PayloadSchemaType.INTEGER),
        ("month", qm.PayloadSchemaType.INTEGER),
        ("studio", qm.PayloadSchemaType.KEYWORD),
        ("canonical_actresses", qm.PayloadSchemaType.KEYWORD),
        ("playable", qm.PayloadSchemaType.BOOL),
    ]:
        try:
            client.create_payload_index(COLLECTION, field, field_schema=ftype)
        except Exception as e:
            log.debug("payload index skipped %s: %s", field, e)


# --- 데이터 ------------------------------------------------------


def _fetch_targets(conn: sqlite3.Connection, force: bool, limit: int | None) -> list[dict]:
    where = "WHERE path IS NOT NULL"
    if not force:
        where += " AND (caption IS NULL OR caption = '')"
    sql = f"SELECT opus, path, kind, video_path FROM posters {where} ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql)]


def _fetch_payload_extra(conn: sqlite3.Connection, opus: str) -> dict:
    v = conn.execute(
        "SELECT release_year, release_month, studio FROM videos WHERE opus = ?", (opus,)
    ).fetchone()
    actrs = [
        r["canonical_name"]
        for r in conn.execute("SELECT canonical_name FROM video_actresses WHERE opus = ?", (opus,))
    ]
    return {
        "year": v["release_year"] if v else None,
        "month": v["release_month"] if v else None,
        "studio": v["studio"] if v else None,
        "actresses": actrs,
    }


def _caption_one(client: httpx.Client, url: str, model: str, path: str) -> str:
    """포스터 한 장 -> 한국어 캡션 텍스트. 실패/거부 시 빈 문자열."""
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        log.warning("read fail %s: %s", path, e)
        return ""
    try:
        r = client.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
                "stream": False,
                "think": False,  # gemma 계열은 thinking 을 꺼야 빠르고 바로 답함
                "options": {"temperature": 0.2, "num_predict": 512},
            },
            timeout=180.0,
        )
        r.raise_for_status()
        msg = r.json().get("message") or {}
        return (msg.get("content") or "").strip()
    except Exception as e:
        log.warning("caption fail %s: %s", path, e)
        return ""


# --- 실행 --------------------------------------------------------


def _batched(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def run(limit: int | None = None, force: bool = False, embed_batch: int = 16) -> dict:
    cfg = load_config()
    model = cfg["models"].get("vision")
    if not model:
        raise RuntimeError("config.models.vision 미설정 — 비전 모델명을 지정하세요.")
    url = cfg["server"]["ollama"].rstrip("/") + "/api/chat"

    conn = connect()
    init_schema(conn)
    qc = _qdrant()
    ensure_collection(qc)
    emb = _embedder()

    targets = _fetch_targets(conn, force=force, limit=limit)
    total = len(targets)
    log.info("caption_posters: %d targets (model=%s force=%s)", total, model, force)

    done = 0
    failed = 0
    embedded = 0
    t_start = time.time()
    pending: list[tuple[str, str, dict]] = []  # (opus, caption, payload_extra)

    def _flush(batch: list[tuple[str, str, dict]]) -> None:
        nonlocal embedded
        if not batch:
            return
        docs = [c for _, c, _ in batch]
        vecs = emb.encode(
            docs, batch_size=embed_batch, normalize_embeddings=True, show_progress_bar=False
        )
        points = []
        for (opus, cap, extra), vec in zip(batch, vecs):
            payload = {
                "opus": opus,
                "kind": extra.get("kind"),
                "year": extra.get("year"),
                "month": extra.get("month"),
                "studio": extra.get("studio"),
                "canonical_actresses": extra.get("actresses", []),
                "playable": bool(extra.get("video_path")),
                "caption": cap,
            }
            points.append(qm.PointStruct(id=opus_to_id(opus), vector=vec.tolist(), payload=payload))
        qc.upsert(collection_name=COLLECTION, points=points, wait=False)
        embedded += len(points)

    with httpx.Client() as hc:
        for row in targets:
            opus, path = row["opus"], row["path"]
            cap = _caption_one(hc, url, model, path)
            if cap:
                cap = _clean_caption(cap)  # 불명/없음 줄 제거
            # 빈 결과도 저장해 재시도를 막는다(force 로만 재실행).
            conn.execute("UPDATE posters SET caption = ? WHERE opus = ?", (cap, opus))
            if not cap:
                failed += 1
            else:
                extra = _fetch_payload_extra(conn, opus)
                extra["kind"] = row.get("kind")
                extra["video_path"] = row.get("video_path")
                pending.append((opus, cap, extra))
            done += 1

            if done % 10 == 0:
                conn.commit()
            if len(pending) >= embed_batch:
                _flush(pending)
                pending.clear()
            if done % 20 == 0 or done == total:
                elapsed = time.time() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                log.info(
                    "caption_posters %d/%d  failed=%d  embedded=%d  %.2f it/s  ETA %.0fs",
                    done,
                    total,
                    failed,
                    embedded,
                    rate,
                    eta,
                )
                update_stage(
                    "caption_posters", completed=done, total=total, failed=failed, embedded=embedded
                )

    _flush(pending)
    conn.commit()
    update_stage(
        "caption_posters",
        done=(limit is None and not force),
        completed=done,
        total=total,
        failed=failed,
        embedded=embedded,
    )
    conn.close()
    return {
        "total": total,
        "processed": done,
        "embedded": embedded,
        "failed": failed,
        "elapsed_sec": round(time.time() - t_start, 2),
    }
