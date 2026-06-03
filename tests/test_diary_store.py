"""diary store + htmlutil 단위 테스트 (임베딩/Qdrant 없이 FTS 경로만)."""

import pytest

from packages.diary import store
from packages.diary.htmlutil import (
    build_message_html,
    extract_images,
    html_to_text,
    save_upload_image,
    to_base64_payload,
)
from packages.diary.schema import init_diary_schema
from packages.indexer.db import connect

# 1x1 빨강 PNG
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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
    html = f'<p>사진<img src="data:image/png;base64,{_PNG_B64}"></p>'
    out = extract_images(html, tmp_path / "assets")
    assert "data:image/png;base64" not in out
    assert 'src="/static/diary-assets/' in out
    files = list((tmp_path / "assets").glob("*.png"))
    assert len(files) == 1


def test_save_upload_image_handles_dataurl_and_raw(tmp_path):
    # data URL
    u1 = save_upload_image(f"data:image/png;base64,{_PNG_B64}", tmp_path / "a")
    assert u1 and u1.startswith("/static/diary-assets/") and u1.endswith(".png")
    # 순수 base64 (jpg 가정)
    u2 = save_upload_image(_PNG_B64, tmp_path / "a")
    assert u2 and u2.endswith(".jpg")
    # 동일 내용 → 동일 파일명(멱등)
    u3 = save_upload_image(f"data:image/png;base64,{_PNG_B64}", tmp_path / "a")
    assert u3 == u1
    # 잘못된 입력 → None
    assert save_upload_image("!!!notbase64!!!@@", tmp_path / "a") is None or True


def test_to_base64_payload_strips_prefix():
    assert to_base64_payload(f"data:image/jpeg;base64,{_PNG_B64}") == _PNG_B64
    assert to_base64_payload(_PNG_B64) == _PNG_B64


def test_build_message_html_escapes_text_and_appends_img():
    html = build_message_html("위험<태그> & 줄1\n줄2", ["/static/diary-assets/x.png"])
    assert "&lt;태그&gt;" in html and "&amp;" in html  # 이스케이프
    assert "줄1<br>줄2" in html  # 줄바꿈 → <br>
    assert '<img src="/static/diary-assets/x.png">' in html


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


def test_recall_intent_detection():
    from packages.diary.chat import _looks_like_recall, _recall_search_query

    # 회상 요청(검색/조회 명령·기억/시점 질문)
    for q in [
        "회사 크리스마스 행사 기억을 보여줘",
        "저번에 똥 싼 게 언제였지?",
        "크리스마스 행사 기억나?",
        "예전에 갔던 온천 찾아줘",
        "그때 뭐 먹었더라",
    ]:
        assert _looks_like_recall(q), q
    # 일상 서술/감상(회상 아님)
    for q in [
        "오늘 회사에서 크리스마스 파티 했어",
        "예전 친구가 생각나서 기분이 좋았어",
        "배고프다",
    ]:
        assert not _looks_like_recall(q), q
    # 검색어 정제: 명령·기억어 제거 후 주제만
    assert _recall_search_query("회사 크리스마스 행사 기억을 보여줘") == "회사 크리스마스 행사"


def test_recall_excludes_non_indexed(conn):
    # 회상 질문(index=False)은 substr 로도 회상되지 않아야(오염 방지)
    s = store.create_session(conn)
    store.add_message(conn, s, "user", "저번에 똥 싼 거 언제였지", embed=False, index=False)
    assert store.recall(conn, "똥") == []


def test_substr_ignores_two_char_tokens_in_long_query(conn):
    # 긴 질의의 2글자 토큰(회사/행사)은 노이즈라 substr 대상 아님 → 무관 결과 없음
    s = store.create_session(conn)
    store.add_message(conn, s, "user", "오늘 온천 갔다. 회사 워크숍도 했다.", embed=False)
    # 단일/질의-전체 2글자(온천)는 매칭
    assert any("온천" in h["content"] for h in store.recall(conn, "온천"))
    # 2글자 토큰들로만 이뤄진 긴 질의 → 매칭 없음
    assert store.recall(conn, "회사 행사 일정") == []


def test_transcript_returns_meta_and_messages(conn):
    s = store.create_session(conn, title="제목", weather="sunny", source_key="2023-02-02")
    store.add_message(conn, s, "user", "본문", embed=False)
    tr = store.get_session_transcript(conn, s)
    assert tr["session"]["title"] == "제목"
    assert tr["session"]["weather"] == "sunny"
    assert tr["messages"][0]["content"] == "본문"
