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

    # 클릭 앵커: 시드 박스 안에서 클릭한 상대 위치(예: 위 15%=얼굴)를 고정점으로.
    # 매 프레임 박스가 커지거나 움직여도 같은 상대 위치를 따라간다. 미지정이면 박스 중심(0.5,0.5).
    sb = track[start]
    if px is not None and sb is not None:
        relx = float(np.clip((px - sb[0]) / max(sb[2] - sb[0], 1.0), 0.0, 1.0))
        rely = float(np.clip((py - sb[1]) / max(sb[3] - sb[1], 1.0), 0.0, 1.0))
    else:
        relx = rely = 0.5

    def assoc(ref, cand):
        """직전 known 박스 ref 에 맞는 검출(없거나 너무 멀면 None=미검출 처리)."""
        if ref is None or not len(cand):
            return None
        best = max(cand, key=lambda b: _iou(ref, b))
        if _iou(ref, best) >= 0.05:
            return best
        rc = ((ref[0] + ref[2]) / 2, (ref[1] + ref[3]) / 2)
        c2 = min(cand, key=lambda b: np.hypot((b[0] + b[2]) / 2 - rc[0], (b[1] + b[3]) / 2 - rc[1]))
        cc = ((c2[0] + c2[2]) / 2, (c2[1] + c2[3]) / 2)
        return c2 if np.hypot(cc[0] - rc[0], cc[1] - rc[1]) <= 0.25 * W else None

    last = track[start]  # 앞으로 — 마지막 확신 박스 기준
    for f in range(start + 1, n):
        m = assoc(last, dets[f])
        track[f] = m
        if m is not None:
            last = m
    last = track[start]  # 뒤로
    for f in range(start - 1, -1, -1):
        m = assoc(last, dets[f])
        track[f] = m
        if m is not None:
            last = m

    # 프레임별 앵커 = 박스 안 (relx,rely) 상대 위치. 미검출/불확실 프레임은 NaN → 보간(스냅 방지)
    raw = np.array([[b[0] + relx * (b[2] - b[0]), b[1] + rely * (b[3] - b[1])]
                    if b is not None else [np.nan, np.nan] for b in track], float)
    idx = np.arange(n)
    for j in (0, 1):
        ok = ~np.isnan(raw[:, j])
        if ok.sum() >= 2:
            raw[:, j] = np.interp(idx, idx[ok], raw[ok, j])
        elif ok.sum() == 1:
            raw[:, j] = raw[ok, j][0]

    # 이상치(추적이 다른 사람으로 튄 프레임) 제거: 롤링 median 에서 크게 벗어나면 median 으로 대체
    def _medfilt(a, k=7):
        r = k // 2
        return np.array([np.median(a[max(0, i - r):i + r + 1]) for i in range(len(a))])

    med = np.stack([_medfilt(raw[:, 0]), _medfilt(raw[:, 1])], 1)
    bad = np.hypot(raw[:, 0] - med[:, 0], raw[:, 1] - med[:, 1]) > 0.06 * W
    raw[bad] = med[bad]
    return raw.astype(np.float32), (round(relx, 3), round(rely, 3))


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

    # 2) 주인공 추적 — 클릭이 있으면 SAM2(메모리 전파, 군중 가림 강건), 아니면/실패 시 YOLO 그리디
    set_status(stage="detect", progress=25)
    subject = options.get("subject")
    if isinstance(subject, str):
        try:
            subject = json.loads(subject)
        except json.JSONDecodeError:
            subject = None

    cen = anchor = None
    if cfg.get("person_tracker", "sam2") == "sam2" and subject and "t" in subject:
        try:
            from .track_sam2 import build_track_sam2, sam2_available
            if sam2_available(cfg):
                cen, anchor = build_track_sam2(work_mp4, W, H, fps, subject, cfg, set_status)
        except Exception as e:  # noqa: BLE001 — SAM2 실패 시 그리디로 폴백
            log.warning("SAM2 추적 실패 → 그리디 폴백: %s", e)
            set_status(note="SAM2 추적 실패 → 기본 추적으로 폴백")
            cen = None

    tracker_used = "sam2" if cen is not None else "greedy"
    if cen is None:  # 그리디(YOLO) 추적
        try:
            dets, dW, dH = _detect(work_mp4, cfg)
        except ImportError:
            raise RuntimeError("ultralytics 미설치 — 인물 모드를 쓰려면 설치가 필요합니다.")
        if dW and (dW != W or dH != H):
            W, H = dW, dH
        cen, anchor = _build_track(dets, W, H, fps, subject)

    # 3) 평활 → 평행이동 shift = target - 실제
    set_status(stage="transform", progress=55)
    presets = cfg.get("smoothing_presets", {})
    # 강도 자동 선택(auto): 주인공이 화면을 얼마나 가로지르나로 결정.
    # 거의 안 움직이면 lock(저렴하게 고정), 많이 가로지르면 dejitter(캔버스 폭증 방지).
    auto_info = None
    eff = strength
    if strength == "auto":
        exc = max(float((cen[:, 0].max() - cen[:, 0].min()) / W),
                  float((cen[:, 1].max() - cen[:, 1].min()) / H))
        eff = "lock" if exc < 0.3 else "smooth" if exc < 0.7 else "dejitter"
        auto_info = {"excursion": round(exc, 2), "chosen": eff}
        set_status(note=f"자동: 주인공 이동 {exc:.2f}×화면 → '{eff}'")
    sigma = float(presets.get(eff, 40))
    # shift = gauss(궤적,σ_강도) − gauss(궤적,σ_denoise) (밴드패스).
    # σ_denoise 보다 빠른 떨림은 보정 대상에서 제외 → 추적 노이즈가 배경 미세 튐으로 새지 않게.
    sden = min(float(cfg.get("track_denoise_sigma", 4)), sigma)
    refx, refy = _gauss(cen[:, 0], sden), _gauss(cen[:, 1], sden)
    tx = _gauss(cen[:, 0], sigma) - refx
    ty = _gauss(cen[:, 1], sigma) - refy
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
        "anchor": list(anchor),
        "tracker": tracker_used,
        "frames": nframes,
    }
    if auto_info:
        metrics["auto"] = auto_info
    set_status(status="done", stage="encode", progress=100,
               outputs=[{"variant": "person", "file": "out.mp4", "metrics": metrics}])
