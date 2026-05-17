"""포스터 파일명 파서.

AI_PLAN.md §5.5.
파일명 패턴: `[studio][opus][title][actresses][YYYY.MM.DD].ext`
- title 은 ',', '....' 등 특수문자 포함 가능 → greedy
- actresses 는 공백 separated (예: "Akari Hoshino Ren Serizawa")
  → 파일명만으로는 정확한 분리 불가 → 일단 raw 보관, alias_map 매칭은 호출측이
- date: 'YYYY.MM.DD' → date(year, month, day)

본 모듈은 IO 없이 순수 함수만.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# title 은 greedy. 마지막 [actresses][date] 두 묶음을 끝에서 anchor.
_PATTERN = re.compile(
    r"^\[(?P<studio>[^\[\]]+)\]"
    r"\[(?P<opus>[^\[\]]+)\]"
    r"\[(?P<title>.+)\]"
    r"\[(?P<actresses>[^\[\]]*)\]"
    r"\[(?P<release>\d{4}\.\d{2}\.\d{2})\]$"
)

POSTER_EXTS_DEFAULT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@dataclass(frozen=True)
class ParsedPoster:
    studio: str
    opus: str
    title: str
    actresses_raw: str  # 공백 separated 원문
    release_date: str  # 'YYYY-MM-DD'
    release_year: int
    release_month: int

    @property
    def actresses(self) -> list[str]:
        """공백 split → trim → 빈 토큰 제거. 진짜 분리는 alias 단계에서 검증."""
        return [t for t in (self.actresses_raw or "").split() if t.strip()]


def parse_filename(name: str) -> ParsedPoster | None:
    """파일명(또는 경로)을 받아 파싱. 매칭 실패 시 None.

    확장자가 있으면 stem 만 사용.
    """
    stem = Path(name).stem if "." in name and not name.startswith("[") else name
    # 확장자가 stem 끝에 없는 경우(이미 stem) 그대로
    if "." in stem and stem.rfind(".") > stem.rfind("]"):
        stem = stem[: stem.rfind(".")]
    m = _PATTERN.match(stem)
    if not m:
        return None
    g = m.groupdict()
    y, mo, d = g["release"].split(".")
    try:
        year, month = int(y), int(mo)
    except ValueError:
        return None
    return ParsedPoster(
        studio=g["studio"].strip(),
        opus=g["opus"].strip(),
        title=g["title"].strip(),
        actresses_raw=g["actresses"].strip(),
        release_date=f"{y}-{mo}-{d}",
        release_year=year,
        release_month=month,
    )
