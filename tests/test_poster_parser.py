"""포스터 파일명 파서 테스트."""
from packages.indexer.poster_parser import parse_filename


def test_parse_basic_korean_title():
    name = "[StudioA][ABC-001][샘플 타이틀 .... - 무삭제 특별판][Alice Smith][2014.10.07].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.studio == "StudioA"
    assert p.opus == "ABC-001"
    assert p.title.startswith("샘플 타이틀")
    assert "무삭제 특별판" in p.title
    assert p.actresses_raw == "Alice Smith"
    assert p.actresses == ["Alice", "Smith"]
    assert p.release_date == "2014-10-07"
    assert (p.release_year, p.release_month) == (2014, 10)


def test_parse_multi_actress_space_separated():
    name = "[StudioB][DEF-002][두 사람의 특별한 하루][Alice Bob Carol Dave][2010.05.01].jpg"
    p = parse_filename(name)
    assert p is not None
    # raw 보존
    assert p.actresses_raw == "Alice Bob Carol Dave"
    assert p.actresses == ["Alice", "Bob", "Carol", "Dave"]


def test_parse_with_path_prefix():
    full = r"K:\Crazy\Storage\StudioA\[StudioA][ABC-001][T][N][2014.10.07].png"
    p = parse_filename(full.split("\\")[-1])
    assert p is not None
    assert p.studio == "StudioA"


def test_parse_empty_actresses():
    name = "[X][AB-1][title][][2020.01.01].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.actresses_raw == ""
    assert p.actresses == []


def test_parse_japanese_studio():
    name = "[スタジオA][GHI-003][평범한 일상 이야기][Alice Smith][2004.08.20].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.studio == "スタジオA"
    assert p.opus == "GHI-003"


def test_parse_invalid_returns_none():
    assert parse_filename("not_a_poster.jpg") is None
    assert parse_filename("[only][two].jpg") is None
    assert parse_filename("[X][AB-1][T][N][2020-01-01].jpg") is None  # 잘못된 date sep


def test_parse_handles_extra_dots_in_title():
    name = "[X][AB-1][a....b][N][2020.01.01].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.title == "a....b"
