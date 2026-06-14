"""faster-whisper 전사 — 일본어 음성 → 타임스탬프 세그먼트.

- 모델은 모듈 싱글톤(lazy 로드). drain 한 배치 동안 한 번만 로드.
- VAD 필터로 무음/비발화 구간 제거(이 도메인은 비발화 구간이 많아 환각 방지에 필수).
- faster-whisper 가 영상 파일에서 오디오를 직접 디코딩(PyAV) → 별도 ffmpeg 추출 불필요.
- CTranslate2 백엔드가 자체 CUDA12 libs 를 끌어옴. uv sync 후 GPU 인식 검증 필요.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MODEL = None
_MODEL_KEY: tuple[str, str, str] | None = None


def _load(model_name: str, device: str, compute_type: str):
    global _MODEL, _MODEL_KEY
    key = (model_name, device, compute_type)
    if _MODEL is not None and _MODEL_KEY == key:
        return _MODEL
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # 미설치 — 명확한 메시지로 안내
        raise RuntimeError(
            "faster-whisper 미설치. pyproject 에 추가 후 `uv sync` 하세요."
        ) from e
    log.info("loading faster-whisper %s on %s (%s)", model_name, device, compute_type)
    _MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
    _MODEL_KEY = key
    return _MODEL


def transcribe(
    video_path: str | Path,
    *,
    model: str,
    device: str = "cuda",
    compute_type: str = "float16",
    language: str = "ja",
    vad_filter: bool = True,
    beam_size: int = 5,
    progress_cb: Callable[[float, float], None] | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """반환: (감지언어, [{start, end, text}]). progress_cb(current_sec, total_sec)."""
    m = _load(model, device, compute_type)
    segments, info = m.transcribe(
        str(video_path),
        language=language,
        vad_filter=vad_filter,
        beam_size=beam_size,
    )
    total = float(getattr(info, "duration", 0.0) or 0.0)
    out: list[dict[str, Any]] = []
    # segments 는 제너레이터 — 순회해야 실제 추론이 진행된다.
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            out.append({"start": float(seg.start), "end": float(seg.end), "text": text})
        if progress_cb and total:
            progress_cb(float(seg.end), total)
    return getattr(info, "language", None), out


def unload() -> None:
    """모델 해제 + VRAM 반환(배치 종료 시)."""
    global _MODEL, _MODEL_KEY
    _MODEL = None
    _MODEL_KEY = None
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 — torch 없거나 CUDA 미사용이면 무시
        pass
