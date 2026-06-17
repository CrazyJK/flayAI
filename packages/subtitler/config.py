"""자막 설정 — config.yaml 의 `subtitle:` 블록 + 기본값 병합.

yaml 블록이 없거나 일부만 있어도 동작하도록 코드 기본값을 깐다(stabilizer 와 동일 패턴).
야간 배치 + VRAM 양보 불필요 전제 → 최고 품질(large-v3) 기본.
"""

from __future__ import annotations

from typing import Any

from packages.settings import load_config

_DEFAULTS: dict[str, Any] = {
    "work_dir": "data/subtitle",      # 잡 로그/임시 산출물 루트 (.gitignore)
    # --- STT(faster-whisper) ---
    "model": "large-v3",              # 야간 배치라 최고 품질. 빠르게: large-v3-turbo
    "device": "cuda",                 # cuda | cpu
    "compute_type": "float16",        # float16(GPU) | int8_float16 | int8
    "language": "ja",                 # 원음 언어(일본어 고정 — 번역도 JP 전제)
    "vad_filter": True,               # 무음/비발화 구간 제거(환각 억제) — 필수
    "beam_size": 5,
    # --- 번역 ---
    "translator": "nllb",             # nllb(빠름) | llm(품질·phase2, TM few-shot)
    "translator_llm": "huihui_ai/qwen2.5-abliterate:14b",  # llm 모드 번역 모델(무검열, 야간 12GB)
    "llm_fewshot_k": 6,               # 청크당 주입할 번역메모리 예시 수
    "llm_chunk_size": 12,             # 한 번에 번역할 세그먼트 수(문맥·속도 균형)
    # --- 출력 ---
    "out_suffix": "",                 # ""→<stem>.srt, "ko"→<stem>.ko.srt (기존 159개 관례=평범한 .srt)
    "backup_existing": True,          # 출력 위치에 기존 파일이 있으면 <stem>.orig.srt 로 1회 백업
    "skip_if_exists": True,           # generate: 기존 자막 있으면 건너뜀(사람 팬자막 보호)
    # --- 번역메모리(TM, phase 2) ---
    "tm_min_overlap": 0.2,            # KO 큐가 JP 발화로 이 비율 이상 덮여야 정렬 쌍 후보
    "tm_min_sim": 0.50,               # JP↔KO 교차언어 코사인(bge-m3) 이 미만이면 오정렬로 탈락
    # --- 싱크 수정(resync, phase 3) ---
    "resync_floor": 0.35,             # KO↔JP 의미 매칭 최소 코사인(미만이면 그 큐는 미매칭→보간)
    "resync_min_match": 0.30,         # 매칭률 이 미만이면 보간이 자막을 몰아 오히려 나빠짐 → 원본 복원
}


def subtitle_config() -> dict[str, Any]:
    """병합된 자막 설정 dict."""
    try:
        raw = load_config().get("subtitle") or {}
    except FileNotFoundError:
        raw = {}
    merged = dict(_DEFAULTS)
    merged.update(raw)
    return merged
