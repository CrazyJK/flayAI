"""SRT 입출력 — 인코딩 자동감지 파싱 + 작성.

기존 팬자막(아브자막 등)은 UTF-8/CP949 가 섞여 있어 디코딩을 자동 판별한다.
순수 로직(모델·GPU 무관) — 단위 테스트 대상.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# "00:01:54,949 --> 00:01:56,598" (쉼표/마침표 ms 구분자 모두 허용)
_TS_LINE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{1,3})"
)

# 광고/크레딧 라인(번역메모리 구축 시 제외). 보수적으로만.
_CREDIT_RE = re.compile(r"자막제공|AVJAMAK|\.COM|\.com|www\.", re.IGNORECASE)


@dataclass
class Cue:
    index: int
    start: float  # 초
    end: float    # 초
    text: str     # 여러 줄 가능(\n 구분)


def format_ts(seconds: float) -> str:
    """초 → 'HH:MM:SS,mmm'."""
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_ts(text: str) -> float:
    """'HH:MM:SS,mmm' → 초."""
    m = re.match(r"\s*(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{1,3})", text)
    if not m:
        raise ValueError(f"bad timestamp: {text!r}")
    h, mi, s, ms = (int(g) for g in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def read_text_auto(path: str | Path) -> str:
    """인코딩 자동감지 텍스트 읽기. utf-8(BOM) → cp949 → euc-kr → (charset-normalizer) → 대체."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    try:  # 마지막 보루: charset-normalizer(설치돼 있으면)
        from charset_normalizer import from_bytes

        best = from_bytes(raw).best()
        if best is not None:
            return str(best)
    except Exception:  # noqa: BLE001
        pass
    return raw.decode("cp949", errors="replace")


def parse_srt(path: str | Path) -> list[Cue]:
    """SRT 파일 → Cue 목록. 인덱스 라인 유무/빈 줄 변형에 관대."""
    text = read_text_auto(path).replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    cues: list[Cue] = []
    idx = 0
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n")]
        # 타임코드 라인 위치 찾기(앞에 인덱스 숫자 줄이 있을 수도, 없을 수도)
        ts_pos = next((i for i, ln in enumerate(lines) if _TS_LINE.search(ln)), None)
        if ts_pos is None:
            continue
        m = _TS_LINE.search(lines[ts_pos])
        start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000.0
        end = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000.0
        body = "\n".join(lines[ts_pos + 1 :]).strip()
        if not body:
            continue
        idx += 1
        cues.append(Cue(idx, start, end, body))
    return cues


def dumps_srt(cues: list[Cue]) -> str:
    """Cue 목록 → SRT 문자열."""
    out: list[str] = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{format_ts(c.start)} --> {format_ts(c.end)}")
        out.append(c.text.strip())
        out.append("")  # 블록 구분 빈 줄
    return "\n".join(out).strip() + "\n"


def write_srt(path: str | Path, cues: list[Cue], encoding: str = "utf-8") -> None:
    """SRT 작성(원자적 — 임시파일 후 교체)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(dumps_srt(cues), encoding=encoding)
    tmp.replace(p)


def is_credit(text: str) -> bool:
    """광고/크레딧 라인 여부(번역메모리에서 제외용)."""
    return bool(_CREDIT_RE.search(text))


def strip_credit_cues(cues: list[Cue]) -> list[Cue]:
    """크레딧/광고 큐 제거. 재인덱싱하지 않고 원본 순서 보존."""
    return [c for c in cues if not is_credit(c.text)]
