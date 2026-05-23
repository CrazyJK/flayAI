"""VLM(비전언어모델) 포스터 캡션 -> posters.caption.

비전 모델이 포스터 이미지를 보고 한국어 '검색용 장면 설명 + 태그'를 생성해
posters.caption 에 저장한다. 이 텍스트는 embed_text 의 [장면] 블록으로 합류해
videos 임베딩에 포함되므로, 채팅 검색에서 시각/장면 질의("해변", "교복", "야외" 등)가
잡히게 된다.

- 모델: config.models.vision (예: huihui_ai/gemma-4-abliterated:e4b). Ollama /api/chat.
  gemma 계열은 think=False 로 추론을 꺼서 빠르게 답을 받는다(장당 ~3초).
- caption 이 비어있는 포스터만 처리(resumable). 전체 재생성은 force=True.
- 프롬프트는 '검색용 비노골 속성'(장소/의상 종류/분위기/인원/화면 텍스트)에 집중 — 노골적
  성적 묘사가 아니라 검색 키워드를 뽑는 것이 목적이고, 그게 검색 품질에도 유리하다.
"""

from __future__ import annotations

import base64
import logging
import sqlite3
import time

import httpx

from packages.indexer.db import connect, init_schema
from packages.indexer.state import update_stage
from packages.settings import load_config

log = logging.getLogger(__name__)

# 검색 메타데이터 목적의 비노골 속성 추출 프롬프트
PROMPT = (
    "이 포스터 이미지를 한국어로 분석해 '검색용 메타데이터'를 만드세요. "
    "성적·노골적 묘사는 하지 말고, 검색에 쓸 장면·속성 키워드만 뽑으세요.\n"
    "다음 항목 위주:\n"
    "- 장소/배경 (실내/실외, 구체적으로: 해변/교실/사무실/침실/야외 등)\n"
    "- 의상/복장 '종류' (교복/드레스/수영복/정장/유니폼 등 — 노출 정도가 아니라 종류)\n"
    "- 분위기/톤 (밝음/어두움/청량/차분/화려함 등)\n"
    "- 등장 인원 수\n"
    "- 화면에 보이는 텍스트/로고 (있으면 그대로)\n"
    "출력 형식(한국어만):\n"
    "설명: <1~2문장>\n"
    "태그: <쉼표로 구분된 키워드 5개 이내>"
)


def _fetch_targets(conn: sqlite3.Connection, force: bool, limit: int | None) -> list[dict]:
    where = "WHERE path IS NOT NULL"
    if not force:
        where += " AND (caption IS NULL OR caption = '')"
    sql = f"SELECT opus, path FROM posters {where} ORDER BY opus"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql)]


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


def run(limit: int | None = None, force: bool = False) -> dict:
    cfg = load_config()
    model = cfg["models"].get("vision")
    if not model:
        raise RuntimeError("config.models.vision 미설정 — 비전 모델명을 지정하세요.")
    url = cfg["server"]["ollama"].rstrip("/") + "/api/chat"

    conn = connect()
    init_schema(conn)
    targets = _fetch_targets(conn, force=force, limit=limit)
    total = len(targets)
    log.info("caption_posters: %d targets (model=%s force=%s)", total, model, force)

    done = 0
    failed = 0
    t_start = time.time()
    with httpx.Client() as client:
        for row in targets:
            opus, path = row["opus"], row["path"]
            cap = _caption_one(client, url, model, path)
            # 빈 결과도 저장해 재시도를 막는다(force 로만 재실행).
            conn.execute("UPDATE posters SET caption = ? WHERE opus = ?", (cap, opus))
            if not cap:
                failed += 1
            done += 1

            if done % 10 == 0:
                conn.commit()
            if done % 20 == 0 or done == total:
                elapsed = time.time() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                log.info(
                    "caption_posters %d/%d  failed=%d  %.2f it/s  ETA %.0fs",
                    done,
                    total,
                    failed,
                    rate,
                    eta,
                )
                update_stage("caption_posters", completed=done, total=total, failed=failed)

    conn.commit()
    update_stage(
        "caption_posters",
        done=(limit is None and not force),
        completed=done,
        total=total,
        failed=failed,
    )
    conn.close()
    return {
        "total": total,
        "processed": done,
        "failed": failed,
        "elapsed_sec": round(time.time() - t_start, 2),
    }
