"""레거시 .diary 임포트 단위 테스트 (임베딩 없이)."""

import json

import pytest

from packages.diary import import_legacy, store
from packages.diary.schema import init_diary_schema
from packages.indexer.db import connect


@pytest.fixture
def conn(tmp_path):
    c = connect(path=tmp_path / "diary_test.db")
    init_diary_schema(c)
    yield c
    c.close()


def _write_diary(path, date, title, content, created=1672914606044):
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "date": date,
                    "weather": "sunny",
                    "title": title,
                    "created": created,
                    "lastModified": created,
                },
                "content": content,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_import_one_creates_session_and_message(conn, tmp_path):
    f = tmp_path / "2023-01-04.diary"
    _write_diary(f, "2023-01-04", "꿈을 꿨다", "<p>꿈을 꿨다</p><p><br></p><p>오랜만에</p>")
    result = import_legacy.import_one(conn, f, tmp_path / "assets", embed=False)
    assert result == "imported"

    sid = store.session_by_source_key(conn, "2023-01-04")
    assert sid is not None
    tr = store.get_session_transcript(conn, sid)
    assert tr["session"]["title"] == "꿈을 꿨다"
    msg = tr["messages"][0]
    assert msg["source"] == "diary_import"
    assert "꿈을 꿨다" in msg["content"] and "오랜만에" in msg["content"]
    assert "<p>" not in msg["content"]  # 평문
    assert msg["raw_html"] and "<p>" in msg["raw_html"]  # 원본 보존


def test_import_is_idempotent(conn, tmp_path):
    f = tmp_path / "2023-01-04.diary"
    _write_diary(f, "2023-01-04", "제목", "<p>내용</p>")
    assert import_legacy.import_one(conn, f, tmp_path / "assets", embed=False) == "imported"
    assert import_legacy.import_one(conn, f, tmp_path / "assets", embed=False) == "skipped"
    # 세션은 하나만
    n = conn.execute("SELECT COUNT(*) AS n FROM diary_sessions").fetchone()["n"]
    assert n == 1


def test_empty_diary_skipped(conn, tmp_path):
    f = tmp_path / "2023-01-05.diary"
    _write_diary(f, "2023-01-05", "빈것", "<p><br></p>")
    assert import_legacy.import_one(conn, f, tmp_path / "assets", embed=False) == "empty"


def test_base_diary_files_excludes_variants(tmp_path):
    (tmp_path / "2023-01-06.diary").write_text("{}", encoding="utf-8")
    (tmp_path / "2023-01-06.diary.1").write_text("{}", encoding="utf-8")
    (tmp_path / "2023-01-06.diary.9").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    files = import_legacy._base_diary_files(tmp_path)
    names = [p.name for p in files]
    assert names == ["2023-01-06.diary"]
