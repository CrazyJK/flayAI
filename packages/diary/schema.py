"""일기 서브시스템 스키마: SQLite 테이블/FTS + Qdrant 컬렉션.

영상 검색 스키마(packages/indexer/db.py)와 같은 flay.db 를 공유하되 테이블은 완전히 분리.
멱등(IF NOT EXISTS) — init_diary_schema 를 매 기동마다 호출해도 안전.
"""

from __future__ import annotations

import logging
import sqlite3

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

log = logging.getLogger(__name__)

# Qdrant 회상용 컬렉션 (bge-m3, 영상 컬렉션과 동일 차원)
DIARY_COLLECTION = "diary_messages"
DIARY_VECTOR_DIM = 1024

DIARY_SCHEMA = """
-- 일기 세션: '한 자리 대화' 또는 레거시 일기 하루치 ------------------------
CREATE TABLE IF NOT EXISTS diary_sessions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT NOT NULL,           -- ISO8601
  ended_at    TEXT,                    -- 마지막 메시지 시각(갱신)
  title       TEXT,                    -- 레거시 일기 제목 / 자동 요약 제목(nullable)
  weather     TEXT,                    -- 레거시 일기 날씨(nullable)
  summary     TEXT,                    -- 세션 요약(nullable)
  source_key  TEXT UNIQUE              -- 임포트 멱등 키(레거시 일기 date). 라이브 챗은 NULL
);

-- 일기 메시지: user(내 말) / assistant(맞장구·회상 답) ----------------------
CREATE TABLE IF NOT EXISTS diary_messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  INTEGER NOT NULL REFERENCES diary_sessions(id),
  role        TEXT NOT NULL,           -- 'user' | 'assistant'
  content     TEXT NOT NULL,           -- 검색·임베딩용 평문
  raw_html    TEXT,                    -- 풍부 표시용 원본 HTML(레거시 일기·이미지 포함, nullable)
  created_at  TEXT NOT NULL,           -- ISO8601
  source      TEXT NOT NULL DEFAULT 'chat',  -- 'chat' | 'diary_import'
  indexed     INTEGER NOT NULL DEFAULT 1     -- 회상 대상 여부(회상 질문은 0 — 오염 방지)
);
CREATE INDEX IF NOT EXISTS idx_diary_msg_session ON diary_messages(session_id);

-- 회상용 키워드 검색(한글 부분매칭): trigram FTS5 -------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS diary_messages_fts USING fts5(
  content, message_id UNINDEXED, session_id UNINDEXED, tokenize='trigram'
);
"""


def init_diary_schema(conn: sqlite3.Connection) -> None:
    """일기 테이블/FTS 생성(멱등) + 마이그레이션."""
    conn.executescript(DIARY_SCHEMA)
    # 기존 DB 마이그레이션: indexed 컬럼 추가(CREATE TABLE IF NOT EXISTS 는 컬럼 추가 안 함)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(diary_messages)")}
    if "indexed" not in cols:
        conn.execute("ALTER TABLE diary_messages ADD COLUMN indexed INTEGER NOT NULL DEFAULT 1")
    conn.commit()


def ensure_diary_collection(client: QdrantClient) -> None:
    """Qdrant diary_messages 컬렉션 생성(멱등) + payload 인덱스."""
    existing = {c.name for c in client.get_collections().collections}
    if DIARY_COLLECTION in existing:
        return
    log.info("creating qdrant collection %s (size=%d, cosine)", DIARY_COLLECTION, DIARY_VECTOR_DIM)
    client.create_collection(
        collection_name=DIARY_COLLECTION,
        vectors_config=qm.VectorParams(size=DIARY_VECTOR_DIM, distance=qm.Distance.COSINE),
    )
    for field, ftype in [
        ("session_id", qm.PayloadSchemaType.INTEGER),
        ("message_id", qm.PayloadSchemaType.INTEGER),
        ("created_at_epoch", qm.PayloadSchemaType.INTEGER),
        ("role", qm.PayloadSchemaType.KEYWORD),
    ]:
        try:
            client.create_payload_index(DIARY_COLLECTION, field, field_schema=ftype)
        except Exception as e:
            log.debug("diary index create skipped %s: %s", field, e)
