"""포스터 파일명 파서 테스트."""
from packages.indexer.poster_parser import parse_filename


def test_parse_basic_korean_title():
    name = "[Attackers][ADN-036][당신, 용서 .... - 이웃의 음욕 무수정][Rin Sakuragi][2014.10.07].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.studio == "Attackers"
    assert p.opus == "ADN-036"
    assert p.title.startswith("당신, 용서")
    assert "이웃의 음욕" in p.title
    assert p.actresses_raw == "Rin Sakuragi"
    assert p.actresses == ["Rin", "Sakuragi"]
    assert p.release_date == "2014-10-07"
    assert (p.release_year, p.release_month) == (2014, 10)


def test_parse_multi_actress_space_separated():
    name = "[S1][JUC-889][가장 위험한 두 사람의 유부녀 잠입 수사관][Akari Hoshino Ren Serizawa][2010.05.01].jpg"
    p = parse_filename(name)
    assert p is not None
    # raw 보존
    assert p.actresses_raw == "Akari Hoshino Ren Serizawa"
    assert p.actresses == ["Akari", "Hoshino", "Ren", "Serizawa"]


def test_parse_with_path_prefix():
    full = r"K:\Crazy\Storage\Attackers\[Attackers][ADN-036][T][N][2014.10.07].png"
    p = parse_filename(full.split("\\")[-1])
    assert p is not None
    assert p.studio == "Attackers"


def test_parse_empty_actresses():
    name = "[X][AB-1][title][][2020.01.01].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.actresses_raw == ""
    assert p.actresses == []


def test_parse_japanese_studio():
    name = "[アリスJAPAN][KR-9211][풍속에서 아오이 소라와][Sora Aoi][2004.08.20].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.studio == "アリスJAPAN"
    assert p.opus == "KR-9211"


def test_parse_invalid_returns_none():
    assert parse_filename("not_a_poster.jpg") is None
    assert parse_filename("[only][two].jpg") is None
    assert parse_filename("[X][AB-1][T][N][2020-01-01].jpg") is None  # 잘못된 date sep


def test_parse_handles_extra_dots_in_title():
    name = "[X][AB-1][a....b][N][2020.01.01].jpg"
    p = parse_filename(name)
    assert p is not None
    assert p.title == "a....b"
