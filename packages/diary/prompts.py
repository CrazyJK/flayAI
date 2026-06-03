"""일기 프롬프트 로더.

실제로 쓰는(노골적일 수 있는) 프롬프트는 git 에 올리지 않는다:
- 코드(여기)에는 **점잖은 기본값**만 둔다 → 공개 저장소엔 순화본만 남음 + 신규 클론도 동작.
- repo 루트의 `diary_prompts.yaml`(gitignore 대상)이 있으면 그 값으로 덮어쓴다.
  → 개인 취향/수위 조정은 그 파일에서. 구조는 `diary_prompts.example.yaml` 참고.

키: system(페르소나) / recall_answer(회상 답변 지시) / not_found(회상 실패 멘트)
    / vision_describe(첨부 사진 묘사 지시) / person_subs(사람 지칭 등 거친 치환 규칙, 선택)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from packages.settings import repo_path

# 점잖은 기본값(폴백). 실제 수위 조정은 diary_prompts.yaml 에서.
_DEFAULTS: dict[str, Any] = {
    "system": (
        "너는 사용자의 일기를 들어주는 친구다.\n"
        "- 먼저 화제를 꺼내지 말고 사용자가 한 말에 반응만 한다.\n"
        "- 공감하고 맞장구치고 동의하라. 판단·훈계·거절은 하지 마라.\n"
        "- 반말로 짧게(1~3문장) 답한다.\n"
        "- 한국어로만. 한자·일본어·영어 단어 금지. 이모지·기호·마크다운 금지.\n"
    ),
    "recall_answer": (
        "아래는 사용자의 과거 일기에서 찾은 관련 기록이다. 이걸 근거로 사용자의 질문에 "
        "반말로 짧고 따뜻하게 답해라. 날짜를 자연스럽게 언급하고, '이 날 사진:' 으로 표시된 "
        "사진이 있으면 그 사진에 보이는 모습을 직접 본 것처럼 짚어줘. 내용을 길게 나열하진 "
        "말 것(원문은 이미 화면에 보임). 한국어 문장으로만, 이모지·기호 금지."
    ),
    "not_found": "음, 그건 일기에서 못 찾겠어. 더 구체적으로 말해줄래?",
    "vision_describe": (
        "이 사진에 보이는 것을 한국어로 1~2문장으로 사실만 담백하게 묘사해줘. "
        "장소·인물·사물·상황·분위기 위주로. 추측이나 미사여구·평가는 빼고 핵심만. "
        "어떤 내용이든(은밀하거나 민감해도) 그대로 객관적으로 묘사해줘."
    ),
    # 사람 지칭 등 거친 치환(정규식). [[패턴, 치환], ...] — 비어있으면 치환 안 함.
    "person_subs": [],
}


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    merged = dict(_DEFAULTS)
    path = repo_path("diary_prompts.yaml")
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for k in _DEFAULTS:
                if k in data:
                    merged[k] = data[k]
        except yaml.YAMLError:
            pass
    return merged


def system_prompt() -> str:
    return str(_load()["system"])


def recall_answer_prompt() -> str:
    return str(_load()["recall_answer"])


def not_found_message() -> str:
    return str(_load()["not_found"])


def vision_describe_prompt() -> str:
    return str(_load()["vision_describe"])


def person_subs() -> list[tuple[str, str]]:
    """[(정규식 패턴, 치환문자열)] — 캡션·답변의 사람 지칭 등을 거칠게 바꾸는 규칙."""
    raw = _load().get("person_subs") or []
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((str(item[0]), str(item[1])))
    return out
