"""data/state.json atomic read/write (resumable indexing).

AI_PLAN.md §6.2.
- atomic write: tmp → os.replace
- 단계별 cursor 보관
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from packages.settings import load_config, repo_path

SCHEMA_VERSION = 1
DEFAULT_STATE: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "stages": {
        "load_jsons": {"done": False, "rows": 0},
        "scan_posters": {
            "done": False,
            "scanned": 0,
            "matched": 0,
            "unmatched": 0,
            "instance": 0,
            "archive": 0,
        },
        "history_csv": {"last_ts": 0},
        "translate": {"done": False, "completed": 0, "cursor_opus": None},
        "embed_text": {"done": False, "completed": 0},
        "ocr_posters": {"done": False, "completed": 0},
        "embed_clip": {"done": False, "completed": 0},
        "extract_faces": {"done": False, "completed": 0},
    },
}


def state_path() -> Path:
    cfg = load_config()
    return repo_path(cfg["data"]["state_path"])


def load_state() -> dict[str, Any]:
    p = state_path()
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_STATE))  # deep copy
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # forward-compat: 누락 단계는 default로 채움
    for stage, default_val in DEFAULT_STATE["stages"].items():
        data.setdefault("stages", {}).setdefault(stage, default_val)
    return data


def save_state(state: dict[str, Any]) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state.", suffix=".json.tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        # Windows에서 다른 프로세스가 대상 파일을 열고 있으면 PermissionError 발생 — 재시도
        for attempt in range(5):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1 * (attempt + 1))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_stage(stage: str, **fields: Any) -> dict[str, Any]:
    """단일 단계 필드 갱신 후 저장."""
    state = load_state()
    state["stages"].setdefault(stage, {}).update(fields)
    save_state(state)
    return state
