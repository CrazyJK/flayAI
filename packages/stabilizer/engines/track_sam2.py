"""SAM2 클릭→메모리 전파 주인공 추적 (인물 모드 고품질 트래커).

YOLO 그리디 추적은 밀집 군중 가림에서 정체성이 옆 사람으로 넘어가 튐이 남는다.
SAM2 는 한 번의 클릭(점 프롬프트)을 영상 메모리로 전파해 가림 너머까지 같은 사람을
따라가고, 박스가 아닌 마스크 중심이라 떨림도 적다. tiny + CPU 오프로드로 VRAM ~0.7GB.

출력은 그리디(_build_track)와 동일: (cen[N,2] work 좌표 앵커 궤적, (relx,rely)).
person.py 가 이 모듈을 디스패치하고, 미설치/실패 시 그리디로 폴백한다.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from packages.settings import REPO_ROOT

log = logging.getLogger(__name__)


def sam2_available(cfg: dict) -> bool:
    try:
        import sam2  # noqa: F401
    except ImportError:
        return False
    ckpt = REPO_ROOT / cfg.get("sam2_checkpoint", "data/stabilize/_models/sam2.1_hiera_tiny.pt")
    return ckpt.exists()


def _clean(raw: np.ndarray, W: int) -> np.ndarray:
    """미검출(NaN) 선형 보간 + 이상치(점프) median 대체 — 그리디와 동일 후처리."""
    n = len(raw)
    idx = np.arange(n)
    for j in (0, 1):
        ok = ~np.isnan(raw[:, j])
        if ok.sum() >= 2:
            raw[:, j] = np.interp(idx, idx[ok], raw[ok, j])
        elif ok.sum() == 1:
            raw[:, j] = raw[ok, j][0]

    def medf(a, k=7):
        r = k // 2
        return np.array([np.median(a[max(0, i - r):i + r + 1]) for i in range(len(a))])

    med = np.stack([medf(raw[:, 0]), medf(raw[:, 1])], 1)
    bad = np.hypot(raw[:, 0] - med[:, 0], raw[:, 1] - med[:, 1]) > 0.06 * W
    raw[bad] = med[bad]
    return raw.astype(np.float32)


def build_track_sam2(work_mp4: Path, W: int, H: int, fps: float, subject: dict,
                     cfg: dict, set_status: Callable[..., Any]) -> tuple[np.ndarray, tuple]:
    import cv2
    import torch
    from sam2.build_sam import build_sam2_video_predictor

    ff = cfg["ffmpeg"]
    fdir = work_mp4.parent / "sam2_frames"
    if fdir.exists():
        shutil.rmtree(fdir, ignore_errors=True)
    fdir.mkdir(parents=True, exist_ok=True)
    fh = int(cfg.get("sam2_frame_height", 720))
    fh -= fh % 2

    # SAM2 는 정수 이름의 jpg 디렉토리를 입력으로 받는다 (00000.jpg ...)
    subprocess.run(
        [ff, "-hide_banner", "-v", "error", "-y", "-i", str(work_mp4),
         "-vf", f"scale=-2:{fh}", "-start_number", "0", str(fdir / "%05d.jpg")],
        cwd=str(REPO_ROOT), check=False)
    frames = sorted(fdir.glob("*.jpg"))
    n = len(frames)
    if n == 0:
        raise RuntimeError("SAM2 프레임 추출 실패")
    fr0 = cv2.imread(str(frames[0]))
    fH, fW = fr0.shape[:2]

    seed = int(np.clip(round(float(subject["t"]) * fps), 0, n - 1))
    cx_n, cy_n = float(subject.get("x", 0.5)), float(subject.get("y", 0.5))
    px, py = cx_n * fW, cy_n * fH

    predictor = build_sam2_video_predictor(
        cfg.get("sam2_config", "configs/sam2.1/sam2.1_hiera_t.yaml"),
        str(REPO_ROOT / cfg.get("sam2_checkpoint", "data/stabilize/_models/sam2.1_hiera_tiny.pt")),
        device="cuda")

    # 위치 기준: x=마스크 중심(좌우 안정), y=마스크 상단(머리 — 하반신이 군중에 가려도 안정).
    # 중심 y 는 다리가 가렸다 보였다 하면 출렁이므로 머리 기준이 이 footage 류에 강건.
    cxs: list[float] = [np.nan] * n   # 중심 x (정규화)
    tops: list[float] = [np.nan] * n  # 마스크 상단 y (정규화)
    ws: list[float] = [np.nan] * n
    hs: list[float] = [np.nan] * n
    set_status(stage="track", progress=30)
    try:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            state = predictor.init_state(video_path=str(fdir),
                                         offload_video_to_cpu=True, offload_state_to_cpu=True)
            predictor.add_new_points_or_box(
                state, frame_idx=seed, obj_id=1,
                points=np.array([[px, py]], dtype=np.float32),
                labels=np.array([1], dtype=np.int32))
            for reverse in (False, True):
                for fidx, _oids, mlog in predictor.propagate_in_video(
                        state, start_frame_idx=seed, reverse=reverse):
                    m = mlog[0, 0] > 0.0
                    if bool(m.any()):
                        ys, xs = torch.where(m)
                        mh, mw = m.shape
                        cxs[fidx] = xs.float().mean().item() / mw
                        tops[fidx] = ys.min().item() / mh
                        ws[fidx] = (xs.max() - xs.min()).item() / mw
                        hs[fidx] = (ys.max() - ys.min()).item() / mh
    finally:
        shutil.rmtree(fdir, ignore_errors=True)

    def _interp(a):
        a = np.asarray(a, float)
        idx = np.arange(len(a))
        ok = ~np.isnan(a)
        if ok.sum() >= 2:
            return np.interp(idx, idx[ok], a[ok])
        return np.full(len(a), a[ok][0] if ok.any() else 0.0)

    def _g(a, s):
        r = max(int(3 * s), 1)
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
        k /= k.sum()
        return np.convolve(np.pad(a, r, mode="edge"), k, mode="valid")

    cx_a, top_a = _interp(cxs), _interp(tops)
    w_a, h_a = _g(_interp(ws), 15), _g(_interp(hs), 15)
    # 앵커 오프셋: 클릭이 (중심x, 상단y) 로부터 박스 몇 배 떨어졌나. 미지정이면 머리 약간 아래.
    sw = w_a[seed] if w_a[seed] > 1e-6 else 1.0
    sh = h_a[seed] if h_a[seed] > 1e-6 else 1.0
    fx = float(np.clip((cx_n - cx_a[seed]) / sw, -0.6, 0.6))
    fy = float(np.clip((cy_n - top_a[seed]) / sh, 0.0, 1.0))
    raw = np.array([[(cx_a[i] + fx * w_a[i]) * W, (top_a[i] + fy * h_a[i]) * H] for i in range(n)],
                   float)
    cen = _clean(raw, W)
    # 마스크 픽셀 경계 떨림(노이즈) 제거 — 피사체 실제 이동은 저주파라 σ5(≈0.08s)면 안전.
    cen[:, 0], cen[:, 1] = _g(cen[:, 0], 5), _g(cen[:, 1], 5)
    return cen, (round(fx, 3), round(fy, 3))
