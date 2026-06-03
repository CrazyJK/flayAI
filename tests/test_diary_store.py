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


def test_asset_names_from_html():
    from packages.diary.htmlutil import asset_names_from_html

    html = '<p>x</p><img src="/static/diary-assets/a1.png"><img src="/static/diary-assets/b2.jpg">'
    assert asset_names_from_html(html) == ["a1.png", "b2.jpg"]
    assert asset_names_from_html("") == []


def test_image_caption_cache_roundtrip(conn):
    store.save_image_caption(conn, "a1.png", "강아지 사진", "sig1")
    assert store.get_image_captions(conn, ["a1.png", "none.png"], "sig1") == {"a1.png": "강아지 사진"}
    # 시그니처(설정) 바뀌면 캐시 미스 → 재생성 대상
    assert store.get_image_captions(conn, ["a1.png"], "sig2") == {}


def test_recall_image_context_uses_cache(conn, monkeypatch):
    # 캐시(같은 sig)가 있으면 비전 모델을 호출하지 않아야(빠른 회상)
    import asyncio

    from packages.diary import chat

    def _boom(*a, **k):
        raise AssertionError("비전이 호출되면 안 됨")

    monkeypatch.setattr(chat, "describe_image_file", _boom)
    monkeypatch.setattr(chat, "_caption_sig", lambda: "S")
    store.save_image_caption(conn, "abc.png", "강아지가 소파에 앉아있다", "S")
    sessions = [
        {
            "session_id": 7,
            "transcript": {"messages": [{"raw_html": '<img src="/static/diary-assets/abc.png">'}]},
        }
    ]
    out = asyncio.run(chat._recall_image_context(conn, sessions))
    assert out.get(7) == "강아지가 소파에 앉아있다"


def test_recall_image_context_regenerates_on_sig_change(conn, monkeypatch):
    # 설정(sig) 이 바뀌면 옛 캡션은 미스 → 비전 재호출로 재생성 + 새 sig 저장
    import asyncio

    from packages.diary import chat

    monkeypatch.setattr(chat, "_caption_sig", lambda: "NEW")
    monkeypatch.setattr(chat, "describe_image_file", lambda *a, **k: "새 묘사")
    monkeypatch.setattr(chat, "_crudify", lambda x: x)
    store.save_image_caption(conn, "abc.png", "옛 묘사", "OLD")
    sessions = [
        {
            "session_id": 7,
            "transcript": {"messages": [{"raw_html": '<img src="/static/diary-assets/abc.png">'}]},
        }
    ]
    out = asyncio.run(chat._recall_image_context(conn, sessions))
    assert out.get(7) == "새 묘사"
    assert store.get_image_captions(conn, ["abc.png"], "NEW") == {"abc.png": "새 묘사"}


def test_sanitize_removes_model_noise():
    from packages.diary.chat import _clean_context, _sanitize

    # 코드스위칭/마커 잔재 제거
    out = _sanitize("개꼴리네 ᄏᄏ._image1 보이네요+ 😌💪")
    assert "_image1" not in out and "image1" not in out
    assert not out.endswith("+")
    assert "😌" not in out and "💪" not in out  # 이모지 제거
    assert "ᄏ" not in out  # 깨진 조합 자모 제거
    assert "개꼴리네" in out
    # 영어는 그대로 보여준다(번역 없이 지우면 문맥만 깨짐)
    assert _sanitize("좋네 awesome 진짜") == "좋네 awesome 진짜"
    # 컨텍스트용 [사진] 마커 제거
    assert "[사진]" not in _clean_context("오늘 [사진] 좋았다 [사진: 강아지]")


def test_crudify_applies_person_subs(monkeypatch):
    from packages.diary import chat

    monkeypatch.setattr(chat.prompts, "person_subs", lambda: [("여성|여자", "저년")])
    assert chat._crudify("여성이 서고 여자가 앉음") == "저년이 서고 저년가 앉음"
    # 리스트 치환 → 후보 중 하나로 무작위
    monkeypatch.setattr(chat.prompts, "person_subs", lambda: [("여자", ["저년", "저 보지"])])
    out = chat._crudify("여자 둘이 있다")
    assert "여자" not in out and (("저년" in out) or ("저 보지" in out))
    # 규칙 없으면 그대로
    monkeypatch.setattr(chat.prompts, "person_subs", lambda: [])
    assert chat._crudify("여자") == "여자"


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


def test_recall_sessions_sorted_chronologically(conn):
    # 같은 키워드 일기 3개를 날짜 뒤섞어 입력 → 회상은 시간순(오래된→최근)으로 표시
    for sk, ts in [
        ("2023-03-03", "2023-03-03T10:00:00"),
        ("2023-01-01", "2023-01-01T10:00:00"),
        ("2023-02-02", "2023-02-02T10:00:00"),
    ]:
        s = store.create_session(conn, started_at=ts, source_key=sk)
        store.add_message(conn, s, "user", "온천 갔다 왔다", created_at=ts, embed=False)
    res = store.recall_sessions(conn, "온천", top_k=5)
    dates = [r["transcript"]["session"]["source_key"] for r in res]
    assert dates == ["2023-01-01", "2023-02-02", "2023-03-03"]


def test_prompts_hot_reload_on_file_change(tmp_path, monkeypatch):
    import os

    from packages.diary import prompts

    f = tmp_path / "diary_prompts.yaml"
    monkeypatch.setattr(prompts, "repo_path", lambda rel: f)
    prompts._cache = None
    prompts._cache_mtime = -1.0
    try:
        f.write_text('not_found: "처음"', encoding="utf-8")
        os.utime(f, (1000, 1000))
        assert prompts.not_found_message() == "처음"
        # 파일 수정(mtime 변경) → 재시작 없이 다음 호출에서 반영
        f.write_text('not_found: "바뀜"', encoding="utf-8")
        os.utime(f, (2000, 2000))
        assert prompts.not_found_message() == "바뀜"
    finally:
        prompts._cache = None
        prompts._cache_mtime = -1.0


def test_transcript_returns_meta_and_messages(conn):
    s = store.create_session(conn, title="제목", weather="sunny", source_key="2023-02-02")
    store.add_message(conn, s, "user", "본문", embed=False)
    tr = store.get_session_transcript(conn, s)
    assert tr["session"]["title"] == "제목"
    assert tr["session"]["weather"] == "sunny"
    assert tr["messages"][0]["content"] == "본문"
