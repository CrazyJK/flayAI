"""자막 서브시스템 순수 로직 테스트(모델·GPU 무관).

- SRT 입출력: 타임스탬프 변환, 인코딩 자동감지 파싱, 라운드트립, 크레딧 제거
- 큐: 적재·중복방지·클레임 순서·진행·마감·삭제, 전사 캐시
- core: 출력 경로/형제 srt/opus 해소
"""

from __future__ import annotations

import pytest

from packages.indexer.db import connect, init_schema
from packages.subtitler import align, core, evaluate, srt_io, translate
from packages.subtitler import db as Q
from packages.subtitler.srt_io import Cue

# --- SRT 입출력 ---------------------------------------------------


def test_ts_roundtrip():
    assert srt_io.format_ts(0) == "00:00:00,000"
    assert srt_io.format_ts(3661.5) == "01:01:01,500"
    assert srt_io.format_ts(114.949) == "00:01:54,949"
    for sec in (0.0, 1.234, 59.999, 3600.0, 7325.678):
        assert abs(srt_io.parse_ts(srt_io.format_ts(sec)) - sec) < 0.001


_SAMPLE = (
    "1\n"
    "00:00:00,445 --> 00:00:06,718\n"
    "자막제공 : 아브자막\n"
    "(AVJAMAK.COM)\n"
    "\n"
    "2\n"
    "00:01:54,949 --> 00:01:56,598\n"
    "날씨가 좋아서 다행이네\n"
    "\n"
    "3\n"
    "00:02:00,911 --> 00:02:02,832\n"
    "- 오늘은 말이죠\n"
    "- 네에-\n"
)


def test_parse_srt_utf8(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text(_SAMPLE, encoding="utf-8")
    cues = srt_io.parse_srt(p)
    assert len(cues) == 3
    assert abs(cues[1].start - 114.949) < 0.001
    assert cues[2].text == "- 오늘은 말이죠\n- 네에-"  # 다중 라인 보존


def test_parse_srt_cp949(tmp_path):
    """한국어 팬자막은 CP949 인 경우가 많다 — 자동감지 디코딩."""
    p = tmp_path / "b.srt"
    p.write_bytes(_SAMPLE.encode("cp949"))
    cues = srt_io.parse_srt(p)
    assert len(cues) == 3
    assert cues[1].text == "날씨가 좋아서 다행이네"


def test_parse_srt_no_index_lines(tmp_path):
    """인덱스 숫자 줄이 없는 변형도 파싱."""
    text = "00:00:01,000 --> 00:00:02,000\n안녕\n\n00:00:03,000 --> 00:00:04,000\n잘가\n"
    p = tmp_path / "c.srt"
    p.write_text(text, encoding="utf-8")
    cues = srt_io.parse_srt(p)
    assert [c.text for c in cues] == ["안녕", "잘가"]


def test_write_roundtrip(tmp_path):
    p = tmp_path / "in.srt"
    p.write_text(_SAMPLE, encoding="utf-8")
    cues = srt_io.parse_srt(p)
    out = tmp_path / "out.srt"
    srt_io.write_srt(out, cues)
    again = srt_io.parse_srt(out)
    assert len(again) == len(cues)
    assert again[1].text == cues[1].text
    assert abs(again[1].start - cues[1].start) < 0.001


def test_strip_credits(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text(_SAMPLE, encoding="utf-8")
    cues = srt_io.parse_srt(p)
    kept = srt_io.strip_credit_cues(cues)
    assert len(kept) == 2  # 자막제공/AVJAMAK 큐 제거
    assert all(not srt_io.is_credit(c.text) for c in kept)


# --- SMI(SAMI) 입출력 ---------------------------------------------

_SMI_SAMPLE = (
    "<SAMI><HEAD><TITLE>x</TITLE></HEAD><BODY>\n"
    "<SYNC Start=1000><P Class=KRCC>안녕하세요\n"
    "<SYNC Start=3000><P Class=KRCC>&nbsp;\n"
    "<SYNC Start=5000><P Class=KRCC>두 번째 줄<br>이어서\n"
    "<SYNC Start=7000><P Class=KRCC>&nbsp;\n"
    "</BODY></SAMI>\n"
)


def test_parse_smi(tmp_path):
    p = tmp_path / "a.smi"
    p.write_text(_SMI_SAMPLE, encoding="utf-8")
    cues = srt_io.parse_smi(p)
    assert len(cues) == 2  # &nbsp;(지움) 은 큐 아님
    assert cues[0].text == "안녕하세요"
    assert abs(cues[0].start - 1.0) < 1e-6 and abs(cues[0].end - 3.0) < 1e-6
    assert cues[1].text == "두 번째 줄\n이어서"  # <br> → 줄바꿈


def test_parse_smi_cp949(tmp_path):
    """SMI 도 CP949 가 흔하다 — 자동감지."""
    p = tmp_path / "b.smi"
    p.write_bytes(_SMI_SAMPLE.encode("cp949"))
    assert srt_io.parse_smi(p)[0].text == "안녕하세요"


def test_smi_roundtrip(tmp_path):
    cues = [Cue(1, 1.0, 3.0, "가"), Cue(2, 5.0, 7.0, "나\n다")]
    p = tmp_path / "o.smi"
    srt_io.write_smi(p, cues)
    again = srt_io.parse_smi(p)
    assert [c.text for c in again] == ["가", "나\n다"]
    assert abs(again[0].start - 1.0) < 1e-6 and abs(again[1].end - 7.0) < 1e-6


def test_parse_subtitle_dispatch(tmp_path):
    s = tmp_path / "a.srt"
    s.write_text("1\n00:00:01,000 --> 00:00:02,000\nx\n", encoding="utf-8")
    m = tmp_path / "a.smi"
    m.write_text(_SMI_SAMPLE, encoding="utf-8")
    assert srt_io.parse_subtitle(s)[0].text == "x"
    assert srt_io.parse_subtitle(m)[0].text == "안녕하세요"


# --- 큐 -----------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    init_schema(c)      # posters 등 본체
    Q.init_schema(c)    # 자막 큐/캐시
    yield c
    c.close()


def test_enqueue_dedupe(conn):
    jid1, created1 = Q.enqueue(conn, "ABC-123", "generate")
    assert created1 is True
    jid2, created2 = Q.enqueue(conn, "ABC-123", "generate")
    assert created2 is False and jid2 == jid1  # 활성 중복은 재사용
    jid3, created3 = Q.enqueue(conn, "ABC-123", "resync")
    assert created3 is True and jid3 != jid1   # task 다르면 별개


def test_claim_order_and_finish(conn):
    a, _ = Q.enqueue(conn, "A-1", "generate")
    b, _ = Q.enqueue(conn, "B-2", "generate")
    j1 = Q.claim_next(conn)
    assert j1["id"] == a and j1["status"] == "running"
    # 한 번 claim 한 잡은 다시 안 잡힘
    j2 = Q.claim_next(conn)
    assert j2["id"] == b
    assert Q.claim_next(conn) is None

    Q.set_progress(conn, a, stage="transcribe", progress=42)
    assert Q.get_job(conn, a)["progress"] == 42

    Q.finish(conn, a, "done", result_path="/x/y.srt")
    fin = Q.get_job(conn, a)
    assert fin["status"] == "done" and fin["result_path"] == "/x/y.srt" and fin["progress"] == 100

    # 마감 후엔 같은 opus 재적재가 새 잡으로
    a2, created = Q.enqueue(conn, "A-1", "generate")
    assert created is True and a2 != a


def test_delete_and_list(conn):
    a, _ = Q.enqueue(conn, "A-1")
    Q.enqueue(conn, "B-2")
    assert len(Q.list_jobs(conn)) == 2
    assert Q.delete_job(conn, a) is True
    assert Q.delete_job(conn, 9999) is False
    assert len(Q.list_jobs(conn)) == 1


def test_transcript_cache(conn):
    segs = [{"start": 0.0, "end": 1.0, "text": "あ"}, {"start": 1.0, "end": 2.0, "text": "い"}]
    assert Q.get_transcript(conn, "A-1", "large-v3") is None
    Q.put_transcript(conn, "A-1", "large-v3", 1700000000, "ja", segs)
    got = Q.get_transcript(conn, "A-1", "large-v3")
    assert got["video_mtime"] == 1700000000
    assert got["language"] == "ja"
    assert got["segments"] == segs


# --- core 경로 해소 -----------------------------------------------


def test_out_and_sibling_paths(tmp_path):
    video = tmp_path / "[Studio][ABC-123][title][2020.05.08].mp4"
    video.write_bytes(b"x")
    assert core.out_srt_path(video).name == "[Studio][ABC-123][title][2020.05.08].srt"
    assert core.out_srt_path(video, "ko").name == "[Studio][ABC-123][title][2020.05.08].ko.srt"
    assert core.sibling_srt(video) is None
    srt = core.out_srt_path(video)
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8")
    assert core.sibling_srt(video) == srt


def test_resolve(conn, tmp_path):
    video = tmp_path / "[ABC-123][x].mp4"
    video.write_bytes(b"x")
    srt = video.with_name(video.stem + ".srt")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8")
    with conn:
        conn.execute(
            "INSERT INTO posters(opus, path, kind, video_path) VALUES (?,?,?,?)",
            ("ABC-123", str(video), "instance", str(video)),
        )
    vp, found_srt = core.resolve(conn, "ABC-123")
    assert vp == video and found_srt == srt

    # 영상 경로가 부재(오프라인)면 None
    with conn:
        conn.execute(
            "INSERT INTO posters(opus, path, kind, video_path) VALUES (?,?,?,?)",
            ("GONE-1", "/nope/x.jpg", "instance", "/nope/x.mp4"),
        )
    assert core.resolve(conn, "GONE-1") == (None, None)


# --- 정렬(phase 2 TM) ---------------------------------------------


def _seg(s, e, t):
    return {"start": s, "end": e, "text": t}


def test_align_by_time_basic():
    jp = [_seg(1.0, 2.0, "こんにちは"), _seg(3.0, 4.0, "さようなら")]
    ko = [Cue(1, 1.0, 2.0, "안녕하세요"), Cue(2, 3.0, 4.0, "잘 가요")]
    pairs = align.align_by_time(jp, ko)
    assert len(pairs) == 2
    assert pairs[0].jp == "こんにちは" and pairs[0].ko == "안녕하세요"
    assert pairs[1].jp == "さようなら"


def test_align_many_to_one():
    """한 KO 큐가 여러 JP 세그먼트를 덮으면 JP 를 합친다."""
    jp = [_seg(1.0, 2.0, "A"), _seg(2.0, 3.0, "B")]
    ko = [Cue(1, 1.0, 3.0, "에이비")]
    pairs = align.align_by_time(jp, ko)
    assert len(pairs) == 1 and pairs[0].jp == "A B"


def test_align_drops_gap_cue():
    """JP 발화와 안 겹치는(드리프트/무음) KO 큐는 후보에서 빠진다."""
    jp = [_seg(1.0, 2.0, "A")]
    ko = [Cue(1, 1.0, 2.0, "맞음"), Cue(2, 50.0, 51.0, "동떨어진큐")]
    pairs = align.align_by_time(jp, ko)
    assert [p.ko for p in pairs] == ["맞음"]


def test_filter_by_similarity_drops_mismatch():
    pairs = [
        align.Pair(jp="あいうえお", ko="아이우에오", ko_start=0, ko_end=1, overlap=1.0),
        align.Pair(jp="まったく違う文", ko="전혀 다른 문장", ko_start=1, ko_end=2, overlap=1.0),
    ]
    vmap = {
        "あいうえお": [1.0, 0.0], "아이우에오": [1.0, 0.0],          # 동일 의미 → 코사인 1
        "まったく違う文": [1.0, 0.0], "전혀 다른 문장": [0.0, 1.0],   # 오정렬 → 코사인 0
    }

    def embed(texts):
        return [vmap[t] for t in texts]

    kept, dropped = align.filter_by_similarity(pairs, embed, min_sim=0.5)
    assert len(kept) == 1 and kept[0].ko == "아이우에오" and kept[0].sim > 0.99
    assert len(dropped) == 1


def test_filter_by_similarity_drops_length_outlier():
    p = align.Pair(jp="あ" * 100, ko="짧음", ko_start=0, ko_end=1, overlap=1.0)

    def embed(texts):
        return [[1.0, 0.0] for _ in texts]  # 의미는 동일하다 쳐도

    kept, dropped = align.filter_by_similarity([p], embed, min_sim=0.0)
    assert len(kept) == 0 and len(dropped) == 1  # 길이비 0.02 < 0.15 → 탈락


# --- LLM 번역 헬퍼(phase 2 ②) -------------------------------------


def test_parse_numbered_formats():
    assert translate.parse_numbered("1. 안녕\n2. 잘가", 2) == ["안녕", "잘가"]
    assert translate.parse_numbered("1) 가\n2) 나\n3: 다", 3) == ["가", "나", "다"]


def test_parse_numbered_partial_and_fail():
    assert translate.parse_numbered("1. 가\n3. 다", 3) == ["가", "", "다"]  # 빠진 2번=빈칸
    assert translate.parse_numbered("번호 없는 텍스트", 2) is None        # 폴백 신호


def test_build_messages_structure():
    msgs = translate.build_messages("SYS", [("JPex", "KOex")], [("用語", "용어")], ["あ", "い"])
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert "용어" in msgs[0]["content"] and "KOex" in msgs[0]["content"]
    assert "1. あ" in msgs[1]["content"] and "2. い" in msgs[1]["content"]


def test_looks_bad_guard():
    assert translate._looks_bad("어싸łoADING") is True   # 라틴 문자 누출
    assert translate._looks_bad("") is True               # 빈 줄
    assert translate._looks_bad("근육이 엄청 커졌네") is False
    assert translate._looks_bad("OK 좋아") is False        # 짧은 라틴(2자)은 통과
    assert translate._looks_bad("좋은 旅馆이네") is True     # 한자 2자 누출 → 폴백


# --- 평가 chrF(phase 2 ③) -----------------------------------------


def test_chrf():
    assert evaluate.chrf("안녕하세요", "안녕하세요") > 0.99    # 동일 → ~1
    assert evaluate.chrf("", "무언가") == 0.0
    # 같은 문장이 다른 문장보다 점수 높다
    assert evaluate.chrf("비슷한 문장입니다", "비슷한 문장입니다") > evaluate.chrf(
        "완전히 다른 내용", "비슷한 문장입니다"
    )


# --- 싱크 수정 정렬(phase 3) --------------------------------------


def test_align_semantic_identity():
    ko = [[1.0, 0.0], [0.0, 1.0]]
    jp = [[1.0, 0.0], [0.0, 1.0]]
    assert align.align_semantic(ko, jp, floor=0.5) == [(0, 0), (1, 1)]


def test_align_semantic_skips_extra_jp():
    """KO 와 안 맞는 JP 세그먼트는 건너뛴다(순서 보존)."""
    ko = [[1.0, 0.0], [0.0, 1.0]]
    jp = [[1.0, 0.0], [0.7, 0.7], [0.0, 1.0]]  # 가운데는 양쪽과 0.71 — 최적은 0→0, 1→2
    assert align.align_semantic(ko, jp, floor=0.6) == [(0, 0), (1, 2)]


def test_retime_anchor_and_interpolate():
    cues = [Cue(1, 100.0, 101.0, "a"), Cue(2, 101.0, 102.0, "b"), Cue(3, 102.0, 103.0, "c")]
    jp = [{"start": 0.0, "end": 1.0, "text": "A"}, {"start": 5.0, "end": 6.0, "text": "C"}]
    out = align.retime(cues, jp, [(0, 0), (2, 1)])  # b(idx1)는 미매칭 → 보간
    starts = [round(c.start, 2) for c in out]
    assert starts == [0.0, 2.5, 5.0]              # 앵커 0·5, 가운데 보간 2.5
    assert abs((out[0].end - out[0].start) - 1.0) < 1e-6  # 읽기 길이 보존


def test_retime_clamps_overlap():
    """원래 길이가 길어 다음 큐와 겹치면 끝을 다음 시작 앞으로 클램프."""
    cues = [Cue(1, 0.0, 10.0, "a"), Cue(2, 1.0, 11.0, "b")]  # 둘 다 10초(겹침)
    jp = [{"start": 0.0, "end": 1.0, "text": "A"}, {"start": 3.0, "end": 4.0, "text": "B"}]
    out = align.retime(cues, jp, [(0, 0), (1, 1)])  # a→0s, b→3s
    assert out[0].end <= out[1].start  # 겹침 없음
    assert out[1].start == 3.0
