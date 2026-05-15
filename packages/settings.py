"""config.yaml 로더 (전체 프로젝트 공용)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# repo root = packages/.. 의 부모
REPO_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """config.yaml 을 dict로 반환. 파일이 없으면 FileNotFoundError."""
    cfg_path = Path(path) if path else REPO_ROOT / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def repo_path(relative: str) -> Path:
    """repo 루트 기준 절대 경로."""
    return (REPO_ROOT / relative).resolve()
