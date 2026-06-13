"""Ollama 채팅 LLM 의 VRAM 적재/해제 — 인덱싱과 GPU 공존 조율.

정책: 채팅 LLM(config.models.llm, 예: qwen)은 **상주시키지 않는다**. Ollama 기본
keep_alive(5분 유휴 후 해제)를 따라 첫 사용 시 로드되고 안 쓰면 자동 하차한다 →
영상 시청 등 다른 GPU 작업에 VRAM 을 양보. 단 GPU 를 크게 쓰는 인덱싱 단계
(embed/embed-clip/extract-faces/ocr-posters/caption-posters) 진입 시 적재된 Ollama
모델을 **전부 언로드**해 VRAM 을 최대 확보한다.

- unload_all_models(): 인덱싱 진입 훅(cli) 에서 호출 — 자동.
- warm_resident_llm(): keep_alive=-1 로 핀. **자동 호출 안 함** — cli warm-llm 수동 전용.
모두 best-effort. 번역(translate)은 LLM 폴백에 qwen 을 쓰므로 언로드 대상에서 제외.
"""

from __future__ import annotations

import logging

import httpx

from packages.settings import load_config

log = logging.getLogger(__name__)


def resident_models() -> list[str]:
    """상주시킬 채팅 모델 목록. config.models.resident_llm(문자열|리스트) 우선, 없으면 models.llm."""
    m = load_config().get("models", {})
    r = m.get("resident_llm") or m.get("llm")
    if not r:
        return []
    return [r] if isinstance(r, str) else list(r)


def _set_keep_alive(model: str, keep_alive: int) -> None:
    """프롬프트 없이 /api/generate 호출 → keep_alive 만 적용(=-1 적재 / =0 해제)."""
    cfg = load_config()
    url = cfg["server"]["ollama"].rstrip("/") + "/api/generate"
    try:
        httpx.post(url, json={"model": model, "keep_alive": keep_alive}, timeout=120.0)
    except Exception as e:  # noqa: BLE001 — best-effort
        log.warning("ollama keep_alive=%s (%s) 실패(무시): %s", keep_alive, model, e)


def unload_resident_llm() -> None:
    """상주 채팅 모델을 VRAM 에서 내림(인덱싱 VRAM 확보). best-effort."""
    for m in resident_models():
        log.info("VRAM 양보: 상주 LLM 언로드 %s", m)
        _set_keep_alive(m, 0)


def unload_all_models() -> None:
    """현재 Ollama 에 적재된 **모든** 모델을 VRAM 에서 내림(인덱싱 VRAM 최대 확보).

    OLLAMA_KEEP_ALIVE=-1 전역 설정 시 채팅 qwen 뿐 아니라 caption 의 비전 모델(gemma)도
    영구 상주하므로, GPU 중량 단계 진입 전 전부 비운다. best-effort.
    """
    cfg = load_config()
    base = cfg["server"]["ollama"].rstrip("/")
    try:
        loaded = httpx.get(base + "/api/ps", timeout=10.0).json().get("models", [])
    except Exception as e:  # noqa: BLE001
        log.warning("적재 모델 조회 실패(상주 모델만 언로드): %s", e)
        unload_resident_llm()
        return
    names = [m.get("name") or m.get("model") for m in loaded]
    names = [n for n in names if n]
    if not names:
        return
    for n in names:
        log.info("VRAM 양보: Ollama 모델 언로드 %s", n)
        _set_keep_alive(n, 0)


def warm_resident_llm() -> None:
    """상주 채팅 모델을 keep_alive=-1 로 다시 적재. best-effort."""
    for m in resident_models():
        log.info("상주 LLM 재워밍 %s", m)
        _set_keep_alive(m, -1)
