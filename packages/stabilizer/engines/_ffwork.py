"""work.mp4 생성 공용 — 하드웨어 디코딩(NVDEC)·다운스케일·저fps 보간 + 저fps 경고."""

from __future__ import annotations

import subprocess
from pathlib import Path

from packages.settings import REPO_ROOT


def build_work(ff: str, inp: Path, work_mp4: Path, meta: dict, cfg: dict, options: dict | None) -> None:
    """입력 → work.mp4(h264, 오디오 보존). NVDEC 시도 후 실패 시 소프트웨어 폴백.

    - decode_hwaccel: cuda(기본, NVDEC) | none
    - max_height 초과면 다운스케일
    - options.interpolate + 입력 fps < interpolate_fps 면 minterpolate 로 보간(저fps gif 부드럽게)
    - 이미 있으면 재사용('둘 다' 모드에서 앞 엔진이 만든 work 를 뒷 엔진이 재사용 → 디코딩 1회)
    """
    if work_mp4.exists() and work_mp4.stat().st_size > 0:
        return
    max_height = cfg.get("max_height") or 0
    hwaccel = cfg.get("decode_hwaccel", "cuda")
    target_fps = int(cfg.get("interpolate_fps", 30) or 0)
    vf: list[str] = []
    if (options or {}).get("interpolate") and target_fps and (meta.get("fps") or 0) < target_fps:
        vf.append(f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir")
    if max_height and meta.get("height", 0) > max_height:
        vf.append(f"scale=-2:{max_height}")
    vfs = ",".join(vf)

    def _cmd(hw: str | None) -> list[str]:
        c = [ff, "-hide_banner", "-v", "error", "-y"]
        if hw and hw != "none":
            c += ["-hwaccel", hw]
        c += ["-i", str(inp)]
        if vfs:
            c += ["-vf", vfs]
        c += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", str(work_mp4)]
        return c

    def _run(c: list[str]) -> tuple[int, str]:
        p = subprocess.run(c, capture_output=True, text=True, cwd=str(REPO_ROOT))
        return p.returncode, (p.stderr or "")[-500:]

    rc, err = _run(_cmd(hwaccel))
    if rc != 0 and hwaccel and hwaccel != "none":
        rc, err = _run(_cmd("none"))  # HW 디코딩 실패 → 소프트웨어 폴백(gif 등)
    if rc != 0:
        raise RuntimeError(f"디코딩/스케일 실패: {err}")


def lowfps_note(meta: dict) -> str | None:
    """저fps/소수프레임 입력이면 품질 제한 안내 문자열. 아니면 None."""
    fps = meta.get("fps") or 0
    frames = fps * (meta.get("duration") or 0)
    if (fps and fps < 15) or (frames and frames < 30):
        return (f"저fps/소수프레임 입력(~{fps:.0f}fps·~{frames:.0f}프레임) — "
                f"안정화 품질이 제한됩니다(소스 한계).")
    return None
