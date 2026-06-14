"""배경 안정화 엔진 (v1) — ffmpeg vidstab.

검증(docs/video-stabilization-plan.md §실측)에서 dense+robust+시간평활 방식이 군중·저텍스처
영상에서도 무크롭 캔버스 ~x1.12 로 안정화됨을 확인 → v1 배경 엔진으로 vidstab 채택.
2패스: vidstabdetect(흔들림 검출) → vidstabtransform(보정). 무크롭=optzoom=0:crop=black.
강도(strength)는 smoothing(프레임)으로 매핑. 후속 RAFT+마스킹 엔진은 별도 모듈로 추가.

주의: vidstab 필터의 result/input 경로는 Windows 절대경로의 콜론(C:)이 필터 파싱을 깨므로
REPO_ROOT 기준 상대(posix) 경로로 주고 cwd=REPO_ROOT 로 ffmpeg 를 실행한다(검증됨).
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from packages.settings import REPO_ROOT

log = logging.getLogger(__name__)


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return p.returncode, (p.stderr or "")[-600:]


def _rel(p: Path) -> str:
    """REPO_ROOT 기준 상대 posix 경로(필터 인자용)."""
    return p.resolve().relative_to(REPO_ROOT).as_posix()


def _probe(ffprobe: str, path: Path) -> dict[str, Any]:
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,nb_frames,codec_name",
           "-show_entries", "format=duration", "-of", "json", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    j = json.loads(out.stdout or "{}")
    st = (j.get("streams") or [{}])[0]
    num, _, den = (st.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0
    return {
        "width": int(st.get("width", 0)), "height": int(st.get("height", 0)),
        "fps": round(fps, 3), "codec": st.get("codec_name"),
        "duration": round(float((j.get("format") or {}).get("duration", 0) or 0), 2),
    }


def _smoothing(cfg: dict, strength: str) -> int:
    presets = cfg.get("smoothing_presets", {})
    return int(presets.get(strength, presets.get("smooth", 40)))


def _auto_background_strength(ff: str, work_mp4: Path, W: int, H: int) -> tuple[str, float]:
    """카메라 이동량을 빠르게 측정해 강도 자동 선택.

    work.mp4 를 8fps·256px·gray 로 파이프 디코딩 → 프레임간 전역 이동(ORB+RANSAC) 누적 →
    누적 가로 이동 범위 / 폭 = drift. 정지형이면 lock, 크게 이동하면 dejitter.
    (드리프트는 저주파라 8fps 로 충분. 전경 군중이 다소 부풀릴 수 있어 임계는 보수적.)
    """
    import cv2
    import numpy as np

    wo = 256
    ho = 2 * round(H * wo / W / 2) if W else 256
    proc = subprocess.Popen(
        [ff, "-hide_banner", "-v", "error", "-i", str(work_mp4),
         "-vf", f"fps=8,scale={wo}:{ho},format=gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, cwd=str(REPO_ROOT))
    orb = cv2.ORB_create(800)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    fsz = wo * ho
    pk = pd = None
    cx = 0.0
    xs = [0.0]
    while True:
        buf = proc.stdout.read(fsz)
        if not buf or len(buf) < fsz:
            break
        g = np.frombuffer(buf, np.uint8).reshape(ho, wo)
        kp, des = orb.detectAndCompute(g, None)
        if pd is not None and des is not None and len(kp) > 6 and len(pk) > 6:
            mm = bf.knnMatch(pd, des, k=2)
            good = [a for a, b in mm if a.distance < 0.75 * b.distance]
            if len(good) >= 10:
                s = np.float32([pk[a.queryIdx].pt for a in good])
                t = np.float32([kp[a.trainIdx].pt for a in good])
                M, _ = cv2.estimateAffinePartial2D(s, t, method=cv2.RANSAC)
                if M is not None:
                    cx += float(M[0, 2])
        xs.append(cx)
        pk, pd = kp, des
    proc.stdout.close()
    proc.wait()
    arr = np.array(xs)
    drift = float((arr.max() - arr.min()) / wo) if len(arr) > 2 else 0.0
    chosen = "lock" if drift < 0.5 else "smooth" if drift < 2.5 else "dejitter"
    return chosen, round(drift, 2)


def _metrics(out_mp4: Path, smoothing: int) -> dict[str, Any]:
    """결과 검은여백을 실측해 무크롭 캔버스 확장 비율 산출(품질 지표). 실패해도 잡은 진행."""
    m: dict[str, Any] = {"smoothing": smoothing}
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(str(out_mp4))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        sample = set(int(i) for i in np.linspace(0, max(n - 1, 0), min(max(n, 1), 80)))
        margins = []
        i = 0
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            if i in sample:
                g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
                cols = np.where(g.max(0) > 12)[0]
                rows = np.where(g.max(1) > 12)[0]
                if len(cols) and len(rows):
                    margins.append((cols[0], W - 1 - cols[-1], rows[0], H - 1 - rows[-1]))
            i += 1
        cap.release()
        if margins and W and H:
            lm = np.array(margins).max(0)
            m["canvas_expand_w"] = round((W + int(lm[0]) + int(lm[1])) / W, 3)
            m["canvas_expand_h"] = round((H + int(lm[2]) + int(lm[3])) / H, 3)
            m["output_wh"] = [W, H]
    except Exception as e:  # noqa: BLE001 — 지표 산출 실패가 잡을 막지 않게
        m["metrics_error"] = str(e)[:120]
    return m


def run_background(jdir: Path, strength: str, options: dict, cfg: dict,
                   set_status: Callable[..., Any]) -> None:
    """배경 안정화 잡 본체. set_status(**kw) 로 진행상황을 status.json 에 반영."""
    ff, fp = cfg["ffmpeg"], cfg["ffprobe"]
    inp = jdir / "in.mp4"
    work = jdir / "work"
    work.mkdir(parents=True, exist_ok=True)
    if not inp.exists():
        raise FileNotFoundError("입력 in.mp4 없음")

    meta = _probe(fp, inp)
    set_status(input=meta, stage="decode", progress=5)
    max_s = cfg.get("max_input_seconds") or 0
    if max_s and meta["duration"] > max_s:
        raise ValueError(f"입력이 너무 김: {meta['duration']}s > {max_s}s")

    # 1) 작업본 생성(필요시 다운스케일, 오디오 보존)
    mh = cfg.get("max_height") or 0
    work_mp4 = work / "work.mp4"
    cmd = [ff, "-hide_banner", "-v", "error", "-y", "-i", str(inp)]
    if mh and meta["height"] > mh:
        cmd += ["-vf", f"scale=-2:{mh}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", str(work_mp4)]
    rc, err = _run(cmd)
    if rc != 0:
        raise RuntimeError(f"디코딩/스케일 실패: {err}")

    # 강도 자동 선택(auto): 카메라 이동량을 측정해 lock/smooth/dejitter 결정
    eff_strength = strength
    auto_info = None
    if strength == "auto":
        wmeta = _probe(fp, work_mp4)
        eff_strength, drift = _auto_background_strength(ff, work_mp4, wmeta["width"], wmeta["height"])
        auto_info = {"drift": drift, "chosen": eff_strength}
        set_status(note=f"자동: 카메라 이동 {drift}×폭 → '{eff_strength}'")

    # 2) 흔들림 검출
    set_status(stage="detect", progress=30)
    trf = work / "transforms.trf"
    rc, err = _run([ff, "-hide_banner", "-v", "error", "-y", "-i", str(work_mp4),
                    "-vf", f"vidstabdetect=shakiness=6:accuracy=15:result={_rel(trf)}",
                    "-f", "null", "-"])
    if rc != 0:
        raise RuntimeError(f"vidstabdetect 실패: {err}")

    # 3) 보정 + 인코딩. edge=crop 이면 optzoom=1(여백 제거 위해 줌인=잘라내기), 아니면 무크롭(검은 여백)
    set_status(stage="transform", progress=55)
    smoothing = _smoothing(cfg, eff_strength)
    edge = (options or {}).get("edge") or cfg.get("edge", "blur")
    out = jdir / "out.mp4"
    zoom = "optzoom=1" if edge == "crop" else "optzoom=0:crop=black"
    vf = (f"vidstabtransform=input={_rel(trf)}:smoothing={smoothing}"
          f":{zoom}:maxshift=-1:maxangle=-1")

    def _encode(encoder: str) -> tuple[int, str]:
        c = [ff, "-hide_banner", "-v", "error", "-y", "-i", str(work_mp4), "-vf", vf, "-c:v", encoder]
        c += (["-preset", "p4", "-cq", "20"] if "nvenc" in encoder else ["-preset", "veryfast", "-crf", "20"])
        c += ["-c:a", "copy", str(out)]
        return _run(c)

    enc = cfg.get("encoder", "h264_nvenc")
    rc, err = _encode(enc)
    if rc != 0 and "nvenc" in enc:
        log.warning("NVENC 인코딩 실패 -> libx264 폴백: %s", err)
        set_status(note="nvenc 실패 -> libx264 폴백")
        rc, err = _encode("libx264")
    if rc != 0:
        raise RuntimeError(f"vidstabtransform 실패: {err}")

    metrics = _metrics(out, smoothing)
    metrics["edge"] = edge
    if auto_info:
        metrics["auto"] = auto_info
    set_status(status="done", stage="encode", progress=100,
               outputs=[{"variant": "background", "file": "out.mp4", "metrics": metrics}])
