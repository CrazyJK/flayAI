"""diary store + htmlutil 단위 테스트 (임베딩/Qdrant 없이 FTS 경로만)."""

import pytest

from packages.diary import store
from packages.diary.htmlutil import extract_images, html_to_text
from packages.diary.schema import init_diary_schema
from packages.indexer.db import connect


@pytest.fixture
def conn(tmp_path):
    c = connect(path=tmp_path / "diary_test.db")
    init_diary_schema(c)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _no_semantic(monkeypatch):
    # Qdrant/임베딩 없이 FTS 단독 경로로 회상 검증
    monkeypatch.setattr(store, "_semantic", lambda *a, **k: [])


# --- htmlutil ----------------------------------------------------


def test_html_to_text_strips_tags_and_marks_image():
    html = '<p>꿈을 꿨다</p><p><br></p><p><img src="data:image/jpeg;base64,AAAA"> 사진</p>'
    text = html_to_text(html)
    assert "꿈을 꿨다" in text
    assert "<p>" not in text and "<img" not in text
    assert "[사진]" in text


def test_extract_images_writes_file_and_rewrites_src(tmp_path):
    # 1x1 빨강 PNG (base64)
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    html = f'<p>사진<img src="data:image/png;base64,{b64}"></p>'
    out = extract_images(html, tmp_path / "assets")
    assert "data:image/png;base64" not in out
    assert 'src="/static/diary-assets/' in out
    files = list((tmp_path / "assets").glob("*.png"))
    assert len(files) == 1


# --- 세션/메시지 -------------------------------------------------


def test_session_continue_within_idle_and_split_after(conn):
    s1 = store.get_or_create_session(conn, idle_hours=6)
    store.add_message(conn, s1, "user", "안녕", embed=False)
    # idle 0 → 무조건 새 세션
    s2 = store.get_or_create_session(conn, idle_hours=0)
    assert s2 != s1
    # 큰 idle → 같은(최근) 세션 이어감
    store.add_message(conn, s2, "user", "또 왔어", embed=False)
    s3 = store.get_or_create_session(conn, idle_hours=99999)
    assert s3 == s2


def test_recall_finds_keyword_and_groups_session(conn):
    s = store.create_session(conn, source_key="2023-01-04")
    store.add_message(
        conn, s, "user", "오늘 똥을 시원하게 쌌다", created_at="2023-01-04T09:00:00",
        source="diary_import", embed=False,
    )
    store.add_message(conn, s, "user", "날씨가 좋다", embed=False)
    hits = store.recall(conn, "똥")
    assert hits and hits[0]["content"].startswith("오늘 똥")
    sessions = store.recall_sessions(conn, "똥")
    assert sessions and sessions[0]["session_id"] == s
    # 그때 세션 전체(2건)가 transcript 로 따라온다
    assert len(sessions[0]["transcript"]["messages"]) == 2


def test_recall_excludes_current_message(conn):
    s = store.create_session(conn)
    mid = store.add_message(conn, s, "user", "똥 얘기", embed=False)
    hits = store.recall(conn, "똥", exclude_message_id=mid)
    assert all(h["message_id"] != mid for h in hits)


def test_transcript_returns_meta_and_messages(conn):
    s = store.create_session(conn, title="제목", weather="sunny", source_key="2023-02-02")
    store.add_message(conn, s, "user", "본문", embed=False)
    tr = store.get_session_transcript(conn, s)
    assert tr["session"]["title"] == "제목"
    assert tr["session"]["weather"] == "sunny"
    assert tr["messages"][0]["content"] == "본문"
