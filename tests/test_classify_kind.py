"""classify_poster (instance/archive) 테스트."""
from pathlib import Path

import pytest

from packages.indexer.poster_scanner import classify_poster

VIDEO_EXTS = {".mp4", ".mkv", ".avi"}


@pytest.fixture
def tmp_dirs(tmp_path: Path):
    archive = tmp_path / "Archive"
    storage = tmp_path / "Storage"
    archive.mkdir()
    storage.mkdir()
    return tmp_path, archive, storage


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")


def test_archive_root_subpath(tmp_dirs):
    _root, archive, _ = tmp_dirs
    poster = archive / "sub" / "[X][AB-1][t][n][2020.01.01].jpg"
    _touch(poster)
    kind, vp = classify_poster(poster, archive, VIDEO_EXTS)
    assert kind == "archive"
    assert vp is None


def test_instance_with_video(tmp_dirs):
    _root, archive, storage = tmp_dirs
    poster = storage / "[X][AB-1][t][n][2020.01.01].jpg"
    _touch(poster)
    video = poster.with_suffix(".mp4")
    _touch(video)
    kind, vp = classify_poster(poster, archive, VIDEO_EXTS)
    assert kind == "instance"
    assert vp is not None and vp.name.endswith(".mp4")


def test_instance_without_video(tmp_dirs):
    _root, archive, storage = tmp_dirs
    poster = storage / "[X][AB-1][t][n][2020.01.01].jpg"
    _touch(poster)
    kind, vp = classify_poster(poster, archive, VIDEO_EXTS)
    assert kind == "instance"
    assert vp is None


def test_archive_takes_precedence_over_video(tmp_dirs):
    """archive 폴더 내부면 같은 stem mp4 가 있어도 archive."""
    _root, archive, _ = tmp_dirs
    poster = archive / "[X][AB-1][t][n][2020.01.01].jpg"
    _touch(poster)
    _touch(poster.with_suffix(".mp4"))
    kind, vp = classify_poster(poster, archive, VIDEO_EXTS)
    assert kind == "archive"
    assert vp is None
