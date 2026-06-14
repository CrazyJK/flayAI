"""인물 안정화 엔진 (v1) — 클릭으로 지정한 주인공을 화면에 고정.

흐름:
 1) work.mp4 생성(다운스케일, h264, 오디오 보존)
 2) YOLO11-seg 로 프레임별 사람 검출 → **클릭 시드 그리디 추적**으로 주인공 트랙(bbox) 구성
    (밀집 군중에서 ByteTrack ID 가 끊겨 12% 만 유지되는 문제를, 클릭 1점으로 시드한 뒤
     프레임마다 직전 박스와 IoU/중심거리가 가장 가까운 검출로 잇는 그리디 추적으로 회피)
 3) 피사체 궤적 → 강도별 평활(target=gauss(traj,sigma)) → 프레임별 평행이동 shift=target-traj
 4) **무크롭**: 모든 프레임을 확장 캔버스에 shift 만큼 옮겨 배치(검은 여백) → ffmpeg(NVENC) 인코딩

주인공 지정: options['subject'] = {"t": 초, "x": 0~1, "y": 0~1}. 없으면 '가장 중앙의 큰 사람' 자동.
추적 백엔드는 후속에 SAM2(클릭→메모리 전파)로 교체 가능 — 이 모듈의 _build_track 만 바꾸면 됨.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from packages.settings import REPO_ROOT

log = logging.getLogger(__name__)


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return p.returncode, (p.stderr or "")[-600:]


def _probe(ffprobe: str, path: Path) -> dict[str, Any]:
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
           "-show_entries", "format=duration", "-of", "json", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    j = json.loads(out.stdout or "{}")
    st = (j.get("streams") or [{}])[0]
    num, _, den = (st.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0
    return {
        "width": int(st.get("width", 0)), "height": int(st.get("height", 0)),
        "fps": round(fps, 3), "rate": st.get("r_frame_rate") or "30",
        "duration": round(float((j.get("format") or {}).get("duration", 0) or 0), 2),
    }


def _gauss(x: np.ndarray, sigma: float) -> np.ndarray:
    r = max(int(3 * sigma), 1)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(x, r, mode="edge"), k, mode="valid")


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _detect(work_mp4: Path, cfg: dict) -> tuple[list[np.ndarray], int, int]:
    """프레임별 사람 bbox 리스트 + (W, H). YOLO11-seg(boxes) 사용."""
    from ultralytics import YOLO

    model = YOLO(str(REPO_ROOT / cfg.get("segment_model", "yolo11x-seg.pt")))
    W = H = 0
    per_frame: list[np.ndarray] = []
    for r in model.predict(source=str(work_mp4), classes=[0],
                           imgsz=int(cfg.get("segment_imgsz", 640)),
                           stream=True, verbose=False, device=0):
        if not H:
            H, W = r.orig_shape
        boxes = (r.boxes.xyxy.cpu().numpy() if r.boxes is not None and len(r.boxes) else
                 np.zeros((0, 4), np.float32))
        per_frame.append(boxes)
    return per_frame, W, H


def _build_track(dets: list[np.ndarray], W: int, H: int, fps: float,
                 subject: dict | None) -> np.ndarray:
    """클릭 시드 그리디 추적 → 프레임별 주인공 중심 (N,2). 검출 없는 프레임은 직전 유지."""
    n = len(dets)
    cx_img, cy_img = W / 2.0, H / 2.0

    def centrality(b):
        bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        d = np.hypot(bx - cx_img, by - cy_img) / np.hypot(cx_img, cy_img)
        area = (b[2] - b[0]) * (b[3] - b[1]) / (W * H)
        return area * max(1 - d, 0) ** 2

    # 시드 프레임/박스
    if subject and "t" in subject:
        f0 = int(np.clip(round(float(subject["t"]) * fps), 0, n - 1))
        px, py = float(subject.get("x", 0.5)) * W, float(subject.get("y", 0.5)) * H
    else:
        # 가장 '중앙+큰 사람'이 잘 잡히는 프레임을 시드로
        scores = [max((centrality(b) for b in d), default=0) for d in dets]
        f0 = int(np.argmax(scores)) if scores else 0
        px = py = None

    def seed_box(f):
        d = dets[f]
        if not len(d):
            return None
        if px is not None:  # 클릭 좌표를 포함하는 박스 우선, 없으면 가장 가까운 중심
            inside = [b for b in d if b[0] <= px <= b[2] and b[1] <= py <= b[3]]
            if inside:
                return max(inside, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
            return min(d, key=lambda b: np.hypot((b[0] + b[2]) / 2 - px, (b[1] + b[3]) / 2 - py))
        return max(d, key=centrality)

    # 시드 프레임에 검출이 없으면 가까운 프레임으로 이동
    start = f0
    while start < n and seed_box(start) is None:
        start += 1
    if start >= n:
        raise RuntimeError("영상에서 사람을 찾지 못했습니다(인물 모드 불가).")

    track: list[np.ndarray | None] = [None] * n
    track[start] = seed_box(start)

    # 앞으로
    for f in range(start + 1, n):
        prev = track[f - 1]
        cand = dets[f]
        if len(cand):
            best = max(cand, key=lambda b: _iou(prev, b))
            if _iou(prev, best) < 0.05:  # 겹침이 거의 없으면 중심거리로
                pc = ((prev[0] + prev[2]) / 2, (prev[1] + prev[3]) / 2)
                best = min(cand, key=lambda b: np.hypot((b[0] + b[2]) / 2 - pc[0],
                                                        (b[1] + b[3]) / 2 - pc[1]))
                # 너무 멀면(점프) 유지
                bc = ((best[0] + best[2]) / 2, (best[1] + best[3]) / 2)
                if np.hypot(bc[0] - pc[0], bc[1] - pc[1]) > 0.25 * W:
                    best = prev
            track[f] = best
        else:
            track[f] = prev
    # 뒤로
    for f in range(start - 1, -1, -1):
        nxt = track[f + 1]
        cand = dets[f]
        if len(cand):
            best = max(cand, key=lambda b: _iou(nxt, b))
            if _iou(nxt, best) < 0.05:
                nc = ((nxt[0] + nxt[2]) / 2, (nxt[1] + nxt[3]) / 2)
                best = min(cand, key=lambda b: np.hypot((b[0] + b[2]) / 2 - nc[0],
                                                        (b[1] + b[3]) / 2 - nc[1]))
                bc = ((best[0] + best[2]) / 2, (best[1] + best[3]) / 2)
                if np.hypot(bc[0] - nc[0], bc[1] - nc[1]) > 0.25 * W:
                    best = nxt
            track[f] = best
        else:
            track[f] = nxt

    cen = np.array([[(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] for b in track], np.float32)
    return cen


def run_person(jdir: Path, strength: str, options: dict, cfg: dict,
               set_status: Callable[..., Any]) -> None:
    ff, fp = cfg["ffmpeg"], cfg["ffprobe"]
    inp = jdir / "in.mp4"
    work = jdir / "work"
    work.mkdir(parents=True, exist_ok=True)
    if not inp.exists():
        raise FileNotFoundError("입력 in.mp4 없음")

    meta = _probe(fp, inp)
    set_status(input={"width": meta["width"], "height": meta["height"], "fps": meta["fps"],
                      "duration": meta["duration"], "codec": "?"}, stage="decode", progress=5)
    max_s = cfg.get("max_input_seconds") or 0
    if max_s and meta["duration"] > max_s:
        raise ValueError(f"입력이 너무 김: {meta['duration']}s > {max_s}s")

    # 1) work.mp4 (다운스케일 + 오디오)
    mh = cfg.get("max_height") or 0
    work_mp4 = work / "work.mp4"
    cmd = [ff, "-hide_banner", "-v", "error", "-y", "-i", str(inp)]
    if mh and meta["height"] > mh:
        cmd += ["-vf", f"scale=-2:{mh}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", str(work_mp4)]
    rc, err = _run(cmd)
    if rc != 0:
        raise RuntimeError(f"디코딩/스케일 실패: {err}")
    wmeta = _probe(fp, work_mp4)
    W, H, rate, fps = wmeta["width"], wmeta["height"], wmeta["rate"], wmeta["fps"]

    # 2) 검출 + 주인공 추적
    set_status(stage="detect", progress=25)
    try:
        dets, dW, dH = _detect(work_mp4, cfg)
    except ImportError:
        raise RuntimeError("ultralytics 미설치 — 인물 모드를 쓰려면 설치가 필요합니다.")
    if dW and (dW != W or dH != H):
        W, H = dW, dH
    subject = options.get("subject")
    if isinstance(subject, str):
        try:
            subject = json.loads(subject)
        except json.JSONDecodeError:
            subject = None
    cen = _build_track(dets, W, H, fps, subject)

    # 3) 평활 → 평행이동 shift = target - 실제
    set_status(stage="transform", progress=55)
    presets = cfg.get("smoothing_presets", {})
    sigma = float(presets.get("smooth", 40) if strength == "auto" else presets.get(strength, 40))
    tx = _gauss(cen[:, 0], sigma) - cen[:, 0]
    ty = _gauss(cen[:, 1], sigma) - cen[:, 1]
    minx, maxx = int(np.floor(tx.min())), int(np.ceil(tx.max()))
    miny, maxy = int(np.floor(ty.min())), int(np.ceil(ty.max()))
    Wout = (W + (maxx - minx) + 1) & ~1  # 짝수
    Hout = (H + (maxy - miny) + 1) & ~1
    offx = np.round(tx - minx).astype(int)
    offy = np.round(ty - miny).astype(int)

    # 4) 무크롭 워프 → 인코딩 (스트리밍, 프레임 디스크 저장 없음)
    set_status(stage="warp", progress=70)
    import cv2

    out = jdir / "out.mp4"
    encoder = cfg.get("encoder", "h264_nvenc")

    def _encode(enc_name):
        enc_cmd = [ff, "-hide_banner", "-v", "error", "-y",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{Wout}x{Hout}", "-r", rate, "-i", "-",
                   "-i", str(work_mp4), "-map", "0:v", "-map", "1:a?",
                   "-c:v", enc_name]
        enc_cmd += (["-preset", "p4", "-cq", "20"] if "nvenc" in enc_name
                    else ["-preset", "veryfast", "-crf", "20"])
        enc_cmd += ["-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", str(out)]
        proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, cwd=str(REPO_ROOT))
        cap = cv2.VideoCapture(str(work_mp4))
        n = len(offx)
        f = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                k = min(f, n - 1)
                canvas = np.zeros((Hout, Wout, 3), np.uint8)
                oy, ox = offy[k], offx[k]
                canvas[oy:oy + H, ox:ox + W] = frame
                proc.stdin.write(canvas.tobytes())
                f += 1
        finally:
            cap.release()
            if proc.stdin:
                proc.stdin.close()
            proc.wait()
        return proc.returncode, f

    rc, nframes = _encode(encoder)
    if rc != 0 and "nvenc" in encoder:
        log.warning("NVENC 실패 → libx264 폴백")
        set_status(note="nvenc 실패 → libx264 폴백")
        rc, nframes = _encode("libx264")
    if rc != 0:
        raise RuntimeError("인물 모드 인코딩 실패")

    metrics = {
        "smoothing": int(sigma),
        "canvas_expand_w": round(Wout / W, 3),
        "canvas_expand_h": round(Hout / H, 3),
        "output_wh": [Wout, Hout],
        "subject_seeded": bool(subject),
        "frames": nframes,
    }
    set_status(status="done", stage="encode", progress=100,
               outputs=[{"variant": "person", "file": "out.mp4", "metrics": metrics}])
