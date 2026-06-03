"""레거시 일기 HTML 처리: 평문화 + base64 인라인 이미지 추출.

레거시 일기 content 는 리치텍스트 HTML(<p>,<br>,<h3>,<span style>...)이며,
사진이 `<img src="data:image/jpeg;base64,...">` 로 인라인 박혀 있다.

- html_to_text: 검색·임베딩·FTS 용 평문 추출(태그 제거, 이미지는 '[사진]' 표식).
- extract_images: base64 이미지를 디스크로 추출하고 src 를 서빙 URL 로 치환한 HTML 반환.
  → DB 에는 가벼운 HTML 만 남고(거대한 base64 제거), 웹은 추출된 파일을 <img> 로 렌더.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html as _html
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# data:image/<subtype>;base64,<payload>  (img src 안)
_DATA_IMG_RE = re.compile(
    r'src\s*=\s*"data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<data>[^"]+)"',
    re.IGNORECASE,
)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_BLOCK_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_BLOCK_END_RE = re.compile(r"</\s*(p|div|h[1-6]|li|tr)\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_NL_RE = re.compile(r"\n{3,}")

# 확장자 정규화(서브타입 → 파일 확장자)
_EXT_MAP = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "gif": "gif", "webp": "webp", "svg+xml": "svg"}


def html_to_text(html: str) -> str:
    """HTML → 검색/임베딩용 평문. 이미지는 '[사진]' 으로, 블록 경계는 줄바꿈으로."""
    if not html:
        return ""
    s = _IMG_TAG_RE.sub(" [사진] ", html)
    s = _BLOCK_BR_RE.sub("\n", s)
    s = _BLOCK_END_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    # 줄 단위 공백 정리 + 과도한 빈 줄 축약
    s = "\n".join(line.strip() for line in s.splitlines())
    s = _MULTI_NL_RE.sub("\n\n", s)
    return s.strip()


def extract_images(html: str, assets_dir: Path, url_prefix: str = "/static/diary-assets") -> str:
    """base64 인라인 이미지를 assets_dir 로 추출하고 src 를 '{url_prefix}/{name}' 로 치환.

    파일명은 내용 해시(SHA1) 기반 → 같은 이미지 중복 저장 방지(멱등). 추출 실패한
    src 는 원본 그대로 둔다. 추출된 HTML(가벼움)을 반환.
    """
    if not html or "data:image" not in html:
        return html
    assets_dir.mkdir(parents=True, exist_ok=True)

    def _repl(m: re.Match) -> str:
        ext = _EXT_MAP.get(m.group("ext").lower(), "bin")
        raw = m.group("data").strip()
        try:
            blob = base64.b64decode(raw, validate=False)
        except (binascii.Error, ValueError) as e:
            log.warning("base64 이미지 디코드 실패(원본 유지): %s", e)
            return m.group(0)
        name = f"{hashlib.sha1(blob).hexdigest()}.{ext}"
        out = assets_dir / name
        if not out.exists():
            out.write_bytes(blob)
        return f'src="{url_prefix}/{name}"'

    return _DATA_IMG_RE.sub(_repl, html)
