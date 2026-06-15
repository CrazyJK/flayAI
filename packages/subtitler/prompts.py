"""자막 번역 프롬프트 로더 (diary/prompts 패턴).

실제 수위 있는 지침/용어집은 git 에 올리지 않는다:
- 코드(여기)엔 **점잖은 기본값**만 → 공개본 순화 + 신규 클론도 동작.
- repo 루트 `subtitle_prompts.yaml`(gitignore) 이 있으면 그 값으로 덮어쓴다.
  구조는 `subtitle_prompts.example.yaml` 참고. 저장 시 다음 호출에서 자동 반영(mtime 캐시).

키: system(번역 지침/말투) · glossary([[jp, ko], ...] 강제 용어).
실제 말투(거친 표현 등)는 system 오버라이드 + few-shot 예시(기존 팬자막)가 함께 만든다.
"""

from __future__ import annotations

from typing import Any

import yaml

from packages.settings import repo_path

_DEFAULTS: dict[str, Any] = {
    "system": (
        "당신은 일본어 영상 대사를 한국어 자막으로 옮기는 전문 번역가입니다.\n"
        "규칙:\n"
        "- 자연스러운 한국어 구어체로 옮긴다. 기계적 직역 금지.\n"
        "- 입력은 번호가 매겨진 일본어 대사 줄이다. 각 번호에 한국어 번역만 같은 번호로 출력한다.\n"
        "- 입력 줄 수와 출력 줄 수를 정확히 맞춘다. 줄을 합치거나 빠뜨리지 않는다.\n"
        "- 설명·원문 반복·부연 금지. 번역문만 출력한다.\n"
        "- 참고 예시가 주어지면 그 말투와 어휘를 따른다.\n"
        "- 한국어로만 출력한다. 한자·중국어 금지.\n"
    ),
    # [[jp, ko], ...] — 강제 용어(고유명사·은어 표기 통일). 비어 있으면 미적용.
    "glossary": [],
}

_cache: dict[str, Any] | None = None
_cache_mtime: float = -1.0


def _load() -> dict[str, Any]:
    global _cache, _cache_mtime
    path = repo_path("subtitle_prompts.yaml")
    try:
        mtime = path.stat().st_mtime if path.exists() else 0.0
    except OSError:
        mtime = 0.0
    if _cache is not None and mtime == _cache_mtime:
        return _cache
    merged = dict(_DEFAULTS)
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for k in _DEFAULTS:
                if k in data:
                    merged[k] = data[k]
        except (yaml.YAMLError, OSError):
            pass
    _cache, _cache_mtime = merged, mtime
    return merged


def system_prompt() -> str:
    return str(_load()["system"])


def glossary() -> list[tuple[str, str]]:
    """[(jp, ko)] 강제 용어 쌍."""
    raw = _load().get("glossary") or []
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((str(item[0]), str(item[1])))
    return out
