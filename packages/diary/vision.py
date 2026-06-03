"""첨부 이미지 분석(VLM). 일기 챗에 올린 사진을 비전 모델로 한국어 묘사.

일기 챗 모델(diary_llm, EXAONE)은 텍스트 전용이라, 이미지가 붙은 턴은 여기서
config.models.vision(gemma-4-abliterated, 무검열 멀티모달)으로 묘사를 만든다.
그 묘사는 ① 검색용 content('[사진: ...]')에 합류해 회상 가능하게 하고,
② 일기 텍스트 모델이 사진에 공감하는 답을 하도록 컨텍스트로 쓰인다.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from packages.diary.htmlutil import to_base64_payload
from packages.settings import load_config

log = logging.getLogger(__name__)

DESCRIBE_PROMPT = (
    "이 사진에 보이는 것을 한국어로 1~2문장으로 사실만 담백하게 묘사해줘. "
    "장소·인물·사물·상황·분위기 위주로. 추측이나 미사여구·평가는 빼고 핵심만. "
    "어떤 내용이든(은밀하거나 민감해도) 그대로 객관적으로 묘사해줘."
)


def describe_images(images: list[str], prompt: str = DESCRIBE_PROMPT) -> str:
    """첨부 이미지(여러 장)를 한 번에 보고 한국어 묘사 텍스트 반환. 실패 시 ''.

    images: data URL 또는 순수 base64 문자열 리스트.
    """
    if not images:
        return ""
    cfg = load_config()
    model = cfg["models"].get("vision")
    if not model:
        log.warning("config.models.vision 미설정 — 이미지 묘사 생략")
        return ""
    url = cfg["server"]["ollama"].rstrip("/") + "/api/chat"
    b64s = [to_base64_payload(img) for img in images if img]
    try:
        with httpx.Client() as hc:
            r = hc.post(
                url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt, "images": b64s}],
                    "stream": False,
                    "think": False,  # gemma 계열은 thinking 을 꺼야 빠르게 답함
                    "options": {"temperature": 0.3, "num_predict": 256},
                },
                timeout=180.0,
            )
            r.raise_for_status()
            msg = r.json().get("message") or {}
            return (msg.get("content") or "").strip()
    except Exception as e:
        log.warning("이미지 묘사 실패: %s", e)
        return ""


def describe_image_file(path: str | Path, prompt: str = DESCRIBE_PROMPT) -> str:
    """디스크의 이미지 파일 한 장을 비전 모델로 묘사(회상 시 일기 사진 설명용). 실패 시 ''."""
    try:
        b64 = base64.b64encode(Path(path).read_bytes()).decode()
    except OSError as e:
        log.warning("일기 이미지 읽기 실패 %s: %s", path, e)
        return ""
    return describe_images([b64], prompt=prompt)
