"""안정화 설정 — config.yaml 의 `stabilize:` 블록 + 기본값 병합.

yaml 블록이 없거나 일부만 있어도 동작하도록 코드 기본값을 깐다.
"""

from __future__ import annotations

from typing import Any

from packages.settings import load_config

# 강도 프리셋 -> vidstab smoothing(프레임 수). 클수록 강하게 고정.
_DEFAULT_PRESETS = {
    "dejitter": 12,   # 흔들림만 제거(의도된 이동/추종 보존) — 트래블 샷용
    "smooth": 40,     # 부분 고정
    "lock": 250,      # 완전 고정(느린 드리프트까지 평탄화) — 정지형 구간용
}

_DEFAULTS: dict[str, Any] = {
    "work_dir": "data/stabilize",
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    "max_height": 1920,           # 처리/출력 세로 상한(4K 입력은 다운스케일). 0=원본유지
    "max_input_seconds": 120,
    "background_engine": "vidstab",  # vidstab(v1) | raft(후속)
    "segment_model": "yolo11x-seg.pt",  # 인물 모드 검출/추적용(YOLO11-seg). 클릭 시드 그리디 추적
    "segment_imgsz": 640,            # YOLO 추론 입력 긴변 px
    "track_denoise_sigma": 4,        # 인물 추적 측정노이즈 제거(프레임). 이보다 빠른 떨림은 보정 안 함
    #                                  → 추적 노이즈가 배경 미세 튐으로 새는 것 방지
    "default_mode": "background",    # background | person
    "default_strength": "smooth",    # dejitter | smooth | lock | auto
    "edge": "black",              # black | (후속: pad, temporal)
    "encoder": "h264_nvenc",      # 폴백 libx264
    "retain_hours": 48,
    "concurrency": 1,
    "smoothing_presets": dict(_DEFAULT_PRESETS),
}


def stabilize_config() -> dict[str, Any]:
    """병합된 안정화 설정 dict."""
    try:
        raw = load_config().get("stabilize") or {}
    except FileNotFoundError:
        raw = {}
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in raw.items() if k != "smoothing_presets"})
    presets = dict(_DEFAULT_PRESETS)
    presets.update(raw.get("smoothing_presets") or {})
    merged["smoothing_presets"] = presets
    return merged
