r"""레거시 .diary 파일 일회성 임포트 → diary 세션/메시지.

기존 일기 앱이 남긴 K:/Crazy/Diary/*.diary (JSON) 를 과거 기억으로 적재한다.

- 정본만 임포트: 정확히 'YYYY-MM-DD.diary' 형식만. '.diary.N'(자동저장 버전) 은 스킵.
- 한 파일 = 하나의 세션 + user 메시지 1개.
    · 세션: started_at=meta.created, ended_at=meta.lastModified, title, weather, source_key=meta.date
    · 메시지: content=HTML 평문(검색용), raw_html=이미지 추출된 원본(표시용), source='diary_import'
- 멱등: source_key(=date) 가 이미 있으면 스킵 → 재실행 안전.
- base64 인라인 이미지는 data/diary_assets/ 로 추출하고 src 를 /static/diary-assets/ 로 치환.

실행:
    .\.venv\Scripts\python.exe -m packages.diary.import_legacy
    .\.venv\Scripts\python.exe -m packages.diary.import_legacy --no-embed   # 임베딩 생략(FTS만)
    .\.venv\Scripts\python.exe -m packages.diary.import_legacy --dir K:/Crazy/Diary
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.diary import store
from packages.diary.htmlutil import extract_images, html_to_text
from packages.diary.schema import ensure_diary_collection, init_diary_schema
from packages.indexer.db import connect
from packages.settings import load_config, repo_path

log = logging.getLogger(__name__)

# 정확히 YYYY-MM-DD.diary (.diary.N 변형 제외)
_BASE_DIARY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.diary$")


def _epoch_ms_to_iso(ms: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000).isoformat(timespec="seconds")
    except (ValueError, TypeError, OSError):
        return None


def _base_diary_files(diary_dir: Path) -> list[Path]:
    if not diary_dir.exists():
        return []
    return sorted(p for p in diary_dir.iterdir() if _BASE_DIARY_RE.match(p.name))


def import_one(
    conn,
    path: Path,
    assets_dir: Path,
    embed: bool = True,
) -> str:
    """한 .diary 파일을 임포트. 반환: 'imported' | 'skipped' | 'empty' | 'error'."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        log.warning("일기 파싱 실패 %s: %s", path.name, e)
        return "error"

    meta = data.get("meta") or {}
    content_html = data.get("content") or ""
    date = meta.get("date") or path.stem  # source_key 겸 표시 날짜
    source_key = str(date)

    if store.session_by_source_key(conn, source_key) is not None:
        return "skipped"  # 멱등

    text = html_to_text(content_html)
    if not text.strip():
        return "empty"  # 빈 일기(자동저장 잔재 등)

    raw_html = extract_images(content_html, assets_dir)
    created_iso = _epoch_ms_to_iso(meta.get("created")) or f"{source_key}T00:00:00"
    modified_iso = _epoch_ms_to_iso(meta.get("lastModified")) or created_iso
    title = (meta.get("title") or "").strip()

    # 검색용 content 에는 제목을 포함(제목은 고신호인데 본문엔 없을 수 있음 — 회상 정확도↑).
    # 표시는 raw_html(본문) + 카드 헤더의 title 로 따로 보이므로 중복 노출 아님.
    search_content = f"{title}\n{text}" if title else text

    session_id = store.create_session(
        conn,
        started_at=created_iso,
        ended_at=modified_iso,
        title=meta.get("title"),
        weather=meta.get("weather"),
        source_key=source_key,
    )
    store.add_message(
        conn,
        session_id,
        role="user",
        content=search_content,
        raw_html=raw_html,
        created_at=created_iso,
        source="diary_import",
        embed=embed,
    )
    return "imported"


def run(diary_dir: str | None = None, embed: bool = True, reset: bool = False) -> dict[str, int]:
    cfg = load_config()
    ddir = Path(diary_dir or cfg["data"].get("diary_dir", "K:/Crazy/Diary"))
    assets_dir = repo_path(cfg["data"].get("diary_assets", "data/diary_assets"))

    conn = connect()
    init_diary_schema(conn)
    if reset:
        log.info("기존 일기 데이터 초기화(reset) — 전량 재임포트")
        store.reset_diary(conn)
    if embed:
        try:
            from packages.indexer.embed_text import _qdrant

            ensure_diary_collection(_qdrant())
        except Exception as e:
            log.warning("Qdrant diary 컬렉션 준비 실패(임베딩 없이 계속): %s", e)
            embed = False

    files = _base_diary_files(ddir)
    stats = {"total": len(files), "imported": 0, "skipped": 0, "empty": 0, "error": 0}
    for p in files:
        result = import_one(conn, p, assets_dir, embed=embed)
        stats[result] = stats.get(result, 0) + 1
        log.info("%-14s %s", result, p.name)
    conn.close()
    log.info(
        "일기 임포트 완료: 총 %(total)d, 적재 %(imported)d, 스킵 %(skipped)d, "
        "빈것 %(empty)d, 오류 %(error)d",
        stats,
    )
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="레거시 .diary 일회성 임포트")
    ap.add_argument("--dir", default=None, help="일기 디렉토리(기본: config.data.diary_dir)")
    ap.add_argument("--no-embed", action="store_true", help="임베딩/Qdrant 생략(FTS만)")
    ap.add_argument("--reset", action="store_true", help="기존 일기 데이터 전량 삭제 후 재임포트")
    args = ap.parse_args()
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run(diary_dir=args.dir, embed=not args.no_embed, reset=args.reset)


if __name__ == "__main__":
    main()
