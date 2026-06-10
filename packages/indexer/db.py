"""SQLite 스키마 정의 + 연결 헬퍼.

AI_PLAN.md §5.1 의 스키마를 그대로 구현.
- 단일 connection 함수 `connect()` — pragma 자동 적용
- `init_schema()` 호출 시 모든 테이블/인덱스/FTS 가상 테이블 생성 (멱등)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from packages.settings import load_config, repo_path

log = logging.getLogger(__name__)

SCHEMA = """
-- 영상 ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS videos (
  opus           TEXT PRIMARY KEY,
  title_jp       TEXT,
  title_ko       TEXT,
  desc_jp        TEXT,
  desc_ko        TEXT,
  studio         TEXT,
  release_date   TEXT,
  release_year   INTEGER,
  release_month  INTEGER,
  comment        TEXT,
  play           INTEGER DEFAULT 0,
  rank           INTEGER DEFAULT 0,
  last_play      INTEGER,
  last_access    INTEGER,
  last_modified  INTEGER,
  like_count     INTEGER DEFAULT 0,
  has_poster     INTEGER DEFAULT 0,
  kind           TEXT
);
CREATE INDEX IF NOT EXISTS idx_videos_year_month ON videos(release_year, release_month);
CREATE INDEX IF NOT EXISTS idx_videos_rank       ON videos(rank DESC, last_play DESC);
CREATE INDEX IF NOT EXISTS idx_videos_kind       ON videos(kind);

-- FTS5 trigram (한/일 부분매칭) ----------------------------------------
-- caption: 포스터 VLM 캡션(장소/의상/소품 등 시각 속성)도 인덱싱 → "소파/수영복/교실"
-- 같은 시각 키워드를 BM25 정확 매칭으로 검색(의미검색 희석 보완). posters.caption 에서 채움.
CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
  opus UNINDEXED, title_jp, title_ko, desc_jp, desc_ko, comment, caption,
  tokenize = 'trigram'
);

-- 배우 (canonical) ----------------------------------------------------
CREATE TABLE IF NOT EXISTS actresses (
  canonical_name TEXT PRIMARY KEY,
  display_name   TEXT,
  local_name     TEXT,
  favorite       INTEGER DEFAULT 0,
  birth          TEXT,
  body           TEXT,
  height         INTEGER,
  debut          INTEGER,
  comment        TEXT,
  last_modified  INTEGER,
  cluster_id     INTEGER
);

CREATE TABLE IF NOT EXISTS actress_aliases (
  alias_norm     TEXT PRIMARY KEY,
  alias_raw      TEXT,
  canonical_name TEXT NOT NULL REFERENCES actresses(canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_alias_canonical ON actress_aliases(canonical_name);

CREATE TABLE IF NOT EXISTS video_actresses (
  opus            TEXT,
  canonical_name  TEXT,
  PRIMARY KEY (opus, canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_va_actress ON video_actresses(canonical_name);

-- 제작사 -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS studios (
  name      TEXT PRIMARY KEY,
  company   TEXT,
  homepage  TEXT
);

-- 태그 ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tag_groups (
  id    TEXT PRIMARY KEY,
  name  TEXT,
  desc  TEXT
);
CREATE TABLE IF NOT EXISTS tags (
  id          INTEGER PRIMARY KEY,
  name        TEXT,
  group_id    TEXT,
  description TEXT
);
CREATE TABLE IF NOT EXISTS video_tags (
  opus    TEXT,
  tag_id  INTEGER,
  PRIMARY KEY (opus, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_vt_tag ON video_tags(tag_id);

-- 좋아요 시계열 ------------------------------------------------------
CREATE TABLE IF NOT EXISTS likes (
  opus  TEXT,
  ts    INTEGER,
  PRIMARY KEY (opus, ts)
);

-- 히스토리 -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS history (
  ts       INTEGER,
  opus     TEXT,
  action   TEXT,
  payload  TEXT,
  PRIMARY KEY (ts, opus, action)
);
CREATE INDEX IF NOT EXISTS idx_history_opus ON history(opus);

-- 포스터 -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS posters (
  opus       TEXT PRIMARY KEY,
  path       TEXT NOT NULL,
  ext        TEXT,
  size       INTEGER,
  mtime      INTEGER,
  ocr_text   TEXT,
  caption    TEXT,
  kind       TEXT,
  video_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_posters_kind ON posters(kind);

-- 얼굴 클러스터 → 배우 매핑 ------------------------------------------
CREATE TABLE IF NOT EXISTS face_clusters (
  cluster_id     INTEGER PRIMARY KEY,
  canonical_name TEXT,
  sample_count   INTEGER,
  confidence     REAL
);
CREATE TABLE IF NOT EXISTS poster_faces (
  poster_opus  TEXT,
  face_idx     INTEGER,
  cluster_id   INTEGER,
  bbox         TEXT,
  PRIMARY KEY (poster_opus, face_idx)
);

-- 번역 캐시 ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS translations (
  hash      TEXT PRIMARY KEY,
  src_lang  TEXT,
  tgt_lang  TEXT,
  src_text  TEXT,
  tgt_text  TEXT
);

-- 운영 로그 ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER,
  endpoint    TEXT,
  query       TEXT,
  tool_calls  TEXT,
  latency_ms  INTEGER,
  result_n    INTEGER,
  user_rating INTEGER
);

-- 임베딩 시그니처 (증분 인덱싱: opus 당 '벡터 입력' 해시) ----------------
-- sig 가 동일하면 재임베딩 스킵. videos=문서 해시, posters_clip=path|mtime|타일구성 해시.
CREATE TABLE IF NOT EXISTS embed_state (
  collection TEXT NOT NULL,
  opus       TEXT NOT NULL,
  sig        TEXT NOT NULL,
  PRIMARY KEY (collection, opus)
);
"""


def db_path() -> Path:
    cfg = load_config()
    return repo_path(cfg["data"]["db_path"])


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """SQLite 연결 (Row factory + 외래키 + WAL).

    동시 쓰기(예: extract-faces 배치)와 라벨링/API 쓰기가 겹치면
    'database is locked' 가 발생할 수 있어 timeout 과 busy_timeout 을 늘림.
    """
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # timeout=30: connect 단계에서 lock 대기 시간 (초)
    conn = sqlite3.connect(str(target), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    # busy_timeout=30000ms: 실행 중 lock 발생 시 재시도 대기 (ms)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    """기존 DB 에 신규 컬럼을 멱등 추가 (CREATE TABLE IF NOT EXISTS 는 컬럼 추가 안 됨)."""
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # 마이그레이션 (기존 DB 대비)
    _ensure_column(conn, "posters", "caption", "TEXT")  # 포스터 VLM 캡션
    # videos_fts 에 caption 컬럼 추가 — FTS5 는 ALTER 불가라 드롭 후 재생성(다음 fts_rebuild 로 채움).
    fts_cols = {r[1] for r in conn.execute("PRAGMA table_info(videos_fts)")}
    if fts_cols and "caption" not in fts_cols:
        conn.execute("DROP TABLE IF EXISTS videos_fts")
        conn.executescript(SCHEMA)  # IF NOT EXISTS — 빠진 videos_fts 만 새 스키마로 재생성
        log.info("videos_fts 재생성(caption 컬럼 추가) — fts 재구축 필요")
    conn.commit()


def load_embed_sigs(conn: sqlite3.Connection, collection: str) -> dict[str, str]:
    """증분 인덱싱용: 컬렉션의 opus→sig 시그니처 맵."""
    return {
        r["opus"]: r["sig"]
        for r in conn.execute(
            "SELECT opus, sig FROM embed_state WHERE collection = ?", (collection,)
        )
    }


def save_embed_sigs(conn: sqlite3.Connection, collection: str, items: list[tuple[str, str]]) -> None:
    """(opus, sig) 다수를 upsert. 임베딩된 항목만 기록해 다음 실행 때 스킵 판단."""
    if not items:
        return
    conn.executemany(
        "INSERT INTO embed_state(collection, opus, sig) VALUES(?, ?, ?) "
        "ON CONFLICT(collection, opus) DO UPDATE SET sig = excluded.sig",
        [(collection, o, s) for o, s in items],
    )
    conn.commit()


def fts_rebuild(conn: sqlite3.Connection) -> None:
    """videos_fts 를 videos + posters.caption 기반으로 재구축."""
    conn.execute("DELETE FROM videos_fts")
    conn.execute("""
        INSERT INTO videos_fts (opus, title_jp, title_ko, desc_jp, desc_ko, comment, caption)
        SELECT v.opus,
               COALESCE(v.title_jp, ''), COALESCE(v.title_ko, ''),
               COALESCE(v.desc_jp,  ''), COALESCE(v.desc_ko,  ''),
               COALESCE(v.comment,  ''),
               COALESCE(p.caption,  '')
        FROM videos v
        LEFT JOIN posters p ON p.opus = v.opus
        """)
    conn.commit()
