# 영상 안정화 API — flayAI 통합 구현 계획

> 흔들린 짧은 세로 영상을 **배경(카메라 흔들림) 기준 전역 안정화**하되, 인물이 프레임 밖으로
> 나가거나 잘리지 않게 함께 고려하는 서버 API. 핵심 트릭은 **배경 모션 추정 시 인물 영역을
> 마스킹해 제외**해 움직이는 인물이 배경 모션 추정을 오염시키지 않게 하는 것.
>
> 이 문서는 **계획**이다(미구현). 원본 명세는 사용자가 제공한 「영상 안정화 API — 프로젝트 명세」.
> flayAI 의 기존 컨벤션(`.github/copilot-instructions.md`, [CLAUDE.md](../CLAUDE.md))에 맞춰
> "우리 프로젝트에서" 어떻게 짓는지를 구체화한다. 실제 구현 전 §13(미결정) 합의 필요.

---

## 0. 한눈에 — 무엇을, 어디에

| 항목 | 결정 | 근거 |
|---|---|---|
| 통합 방식 | **flayAI 레포 안에 새 서브시스템** (`packages/stabilizer` + `apps/api/routers/stabilize.py`) | 같은 12GB GPU·torch/CUDA·FFmpeg·FastAPI 스택을 공유 → VRAM 조율을 한 곳에서. 별도 서비스면 시청·인덱싱과 3중 경합 |
| 잡 처리 | **인하우스 서브프로세스 잡** (인덱서 패턴 재사용), **Celery/RQ 도입 안 함** | 명세는 Celery/RQ 권고하나, 이 프로젝트는 Redis/브로커 등 외부 인프라를 의도적으로 안 씀. 단계-서브프로세스가 곧 VRAM 격리 |
| 모션 추정 | **RAFT (torchvision 내장)**, 저해상도 추정 + 고해상도 워프. 경량 폴백 = ORB 특징점 | `torchvision==0.21.0` 에 `raft_large` 내장 → 신규 딥 의존성 0 |
| 세그멘테이션 | PoC = **YOLO11-seg(person)** + 내장 트래커, 품질 업그레이드 = SAM2 | 12GB 공유 GPU 에서 SAM2 비디오 예측기는 무겁다. 가벼운 길로 먼저 검증 (§13에서 확정) |
| 평활화 | PoC = **가우시안**, 옵션 = L1-optimal | 단순·충분. 크롭이 병목으로 드러나면 고품질로 (§10) |
| 동시 작업 | **1개** (전역 락) | 12GB 를 시청·기존 ML 스택과 나눠 씀 |

```
업로드 mp4
  │  POST /api/stabilize/jobs        (apps/api/routers/stabilize.py, localhost+TLS)
  ▼
data/stabilize/{job_id}/  ── 서브프로세스 잡(packages.stabilizer.cli) 단계별 실행, 단계 사이 VRAM 해제
  in.mp4 → frames/ → masks/ → transforms.json → smoothed.json → out.mp4
  ▲                                                            │
  └── GET /api/stabilize/jobs/{id} (폴링) ── status.json ──────┘  → GET .../result (out.mp4 다운로드)
```

---

## 1. flayAI 와의 관계 — 왜 같은 레포인가

원본 명세는 독립 서비스(FastAPI + Celery + Redis)를 그린다. 하지만 이 PC의 현실:

- **GPU 1장(RTX 4070 Ti 12GB)을 모니터 4개·영상 시청·flayAI ML 스택(bge-m3·CLIP·InsightFace·Ollama)과 공유**
  ([project_dev_gpu_env] 메모리). 안정화의 SAM2/RAFT 까지 더하면 VRAM 경합이 품질·안정성을 좌우한다.
- flayAI 는 이미 **단계마다 서브프로세스를 띄워 VRAM 을 해제**하는 인덱서 패턴과,
  GPU 단계 진입 시 Ollama 모델을 언로드하는 `ollama_vram` 훅을 갖고 있다.

→ 안정화를 같은 레포·같은 잡 모델 안에 두면 **이 VRAM 조율 메커니즘을 그대로 재사용**하고,
"인덱싱 중엔 안정화 금지" 같은 상호배제도 한 곳에서 건다. 별도 서비스로 떼면 조율 불가능한 3중 경합이 된다.

**재사용**: FastAPI 앱·라우터 패턴, typer CLI, 서브프로세스 잡 추적(`admin.py`), `ollama_vram.unload_all_models()`,
localhost-only + 자체 TLS, `packages/settings`(config 로더), SQLite(WAL)·`data/` 레이아웃, `docs/` 컨벤션.

**격리(섞지 않을 것)**: 안정화는 **K:\Crazy 컬렉션과 무관**한 임시 업로드 영상을 다룬다.
인덱서/RAG/Qdrant 컬렉션·`flay.db` 메타에 손대지 않는다. 잡 산출물은 `data/stabilize/` 에 격리하고 보존기간 후 정리한다.

---

## 2. 핵심 제약 — GPU 예산 (가장 중요)

> AI 개념 한 줄: **VRAM**(Video RAM)은 GPU 전용 메모리다. 모델 가중치 + 처리 중 텐서가 여기 올라간다.
> 12GB 를 넘기면 OOM(메모리 부족)으로 죽거나 느린 시스템 RAM 으로 밀려난다.

| 소비처 | 대략 VRAM | 비고 |
|---|---|---|
| 모니터 4개 데스크톱 | ~0.5–1.5GB | 상시 |
| 영상 시청(디코딩·브라우저) | ~0.5–2GB | 사용자 행동에 따라 변동 |
| flayAI 인덱싱 GPU 단계 | 수 GB | embed/clip/faces/ocr/caption — **안정화와 동시 금지** |
| Ollama 채팅 LLM(qwen 7B) | ~5–6GB | 유휴 5분 후 자동 해제. GPU 단계 진입 시 `unload_all_models()` 로 비움 |
| **RAFT(raft_large)** | **추정 ~2–4GB** | **저해상도(긴 변 512–720)에서 추정** → VRAM·속도 동시 절감. 워프는 본해상도 |
| **세그멘테이션(YOLO11-seg)** | **추정 ~1–2GB** | SAM2 비디오 예측기 선택 시 ~4–6GB+ (메모리 뱅크가 클립 길이에 따라 증가) |

**설계 결론**
1. **단계-서브프로세스**로 한 모델씩 올렸다 내린다(세그 끝 → 프로세스 종료로 VRAM 해제 → RAFT 시작).
   인덱서가 단계 사이 VRAM 을 비우는 것과 동일.
2. **동시 안정화 잡 = 1** (전역 락). 인덱싱 파이프라인과도 **상호배제**.
3. **모션 추정은 다운스케일 해상도**에서. 변환행렬은 저주파라 저해상도로 충분하고 RAFT VRAM/시간을 크게 절감.
4. GPU 단계 진입 시 기존 `ollama_vram.unload_all_models()` 호출(인덱서와 동일 훅).
5. 잡 실행 중 **영상 시청은 비권장**(경합)임을 관리 UI/문서에 명시. 실측 후 캡(§9 길이/해상도) 확정.

> 표의 VRAM 수치는 **추정**이다. M1 에서 본 PC·본 해상도로 `nvidia-smi` 실측해 §9 캡과 동시성 정책을 확정한다.

---

## 3. 아키텍처 — 디렉토리·모듈

기존 `packages/indexer`(단계형 파이프라인)를 그대로 본떠 새 패키지를 만든다.

```
packages/stabilizer/
  __init__.py
  cli.py            # typer — 각 단계가 서브커맨드 (decode/segment/flow/smooth/warp/encode), 'run' = 전체
  config.py         # config.yaml 의 stabilize 블록 파싱(기본값 포함)
  job.py            # 잡 디렉토리 레이아웃 + status.json 읽기/원자적 쓰기 + 상태 머신
  decode.py         # FFmpeg: in.mp4 → frames/%06d.png (+ fps/회전/해상도 probe)
  segment.py        # 인물 마스크 + 트래킹 → masks/%06d.png, track.json(프레임별 인물 bbox)
  flow.py           # RAFT(다운스케일) + 인물 마스크 제외 → 프레임별 변환행렬 → transforms.json
  smooth.py         # 궤적 누적 + 평활화(가우시안 | L1) → smoothed.json (보정 변환)
  warp.py           # 역변환 워프 + 인물 트랙 반영 최소 크롭 박스 → warped/ (or 인코더 직결)
  encode.py         # FFmpeg(NVENC): 워프 결과 → out.mp4 (+ 메트릭 기록)
  metrics.py        # 크롭 비율·안정화 정도(잔여 모션) 산출
  gpu.py            # VRAM 가드 / 다운스케일 정책 / ollama_vram.unload 연동

apps/api/routers/stabilize.py   # POST /jobs, GET /jobs, GET /jobs/{id}, GET /jobs/{id}/result, DELETE /jobs/{id}

data/stabilize/{job_id}/        # gitignore — 업로드·중간산출·결과·status.json (보존기간 후 정리)
tests/test_stabilizer_*.py      # 합성 흔들림 클립 픽스처로 단위/통합 테스트
docs/video-stabilization-plan.md (이 문서)  →  구현 후 docs/video-stabilization.md(동작 설명서)로 승격
```

CLI 진입점은 `pyproject.toml [project.scripts]` 에 `flay-stab = "packages.stabilizer.cli:app"` 추가
(기존 `flay-index` 와 동일 패턴).

---

## 4. 처리 파이프라인 — 인덱서식 단계 매핑

명세 §3(A 경로)의 6단계를 **인덱서처럼 "단계 = 서브프로세스 + 디스크 산출물 + 멱등/재개"** 로 구현한다.
중단/강제종료해도 디스크 산출물이 남아 재실행 시 이어진다(완료 프레임 skip). 단계 사이 프로세스가 죽어 VRAM 해제.

| # | 단계(CLI) | 입력 → 산출 | GPU | 핵심 |
|---|---|---|---|---|
| 1 | `decode` | in.mp4 → `frames/`, meta(fps·회전·WxH) | × | FFmpeg. 회전 메타 정규화. (옵션) 추정용 다운스케일 사본 |
| 2 | `segment` | frames → `masks/`, `track.json` | ○ | 인물 마스크 + ID 일관 트래킹. bbox 궤적도 저장(5번 크롭용) |
| 3 | `flow` | frames(저해상도)+masks → `transforms.json` | ○ | **RAFT 로 dense flow → 인물 마스크 픽셀 제외 → RANSAC 으로 프레임간 전역 affine/homography 적합** |
| 4 | `smooth` | transforms → `smoothed.json` | × | 카메라 궤적 누적 → 오프라인 평활화(미래 프레임 활용) → 프레임별 보정 변환 |
| 5 | `warp` | frames + smoothed + track → `warped/` (or 직결) | △ | 역변환 워프 + **인물 bbox 트랙을 포함하는 최소 크롭 박스** 결정(세로 9:16 손실 최소화) |
| 6 | `encode` | warped → `out.mp4` + metrics | × | FFmpeg **NVENC**(h264/hevc), 원본 fps·오디오 보존 |

**3번이 "인물+배경 동시"의 핵심**: 인물을 마스킹해 **순수 배경 모션만** 추출 → 움직이는 인물이 카메라 궤적을 오염시키지 않음.

> 단계를 따로 둘지 한 프로세스로 묶을지는 트레이드오프다. **분리**: VRAM 격리·재개성↑, 디스크 I/O(프레임 PNG)↑.
> **권고**: 분리 유지(인덱서 일관성 + 12GB 제약). 단 `frames/`·`warped/` 는 잡 종료 시 삭제하고 `out.mp4`만 남겨 디스크 절약(§9).

---

## 5. 기술 스택 — 명세 대비 선택과 의도적 이탈

| 역할 | 명세 권고 | 본 계획 채택 | 비고 |
|---|---|---|---|
| 디코딩/인코딩 | FFmpeg | **FFmpeg + NVENC** | 4070 Ti(Ada)는 h264/hevc NVENC 지원 → 인코딩 GPU 오프로드. ffmpeg 바이너리 PATH 필요 |
| 모션 추정 | RAFT / ORB | **RAFT = `torchvision.models.optical_flow.raft_large`** (내장), 폴백 ORB(OpenCV) | torchvision 0.21 내장이라 **신규 딥 의존성 0**. 저해상도 추정 |
| 세그+트래킹 | SAM2 / YOLO11-seg | **PoC: YOLO11-seg(ultralytics) + 내장 트래커**, 업그레이드: SAM2 | 12GB·속도 우선. §13에서 확정. 추상화(`segment.py` 백엔드 교체 가능)로 둠 |
| 워프·행렬 | OpenCV | **OpenCV**(`estimateAffinePartial2D`/`findHomography`/`warpAffine`/`warpPerspective`) | 신규 의존성 opencv-python |
| API | FastAPI | **FastAPI**(기존 앱에 라우터 추가) | 신규 앱 아님 |
| 비동기 | Celery/RQ | **인하우스 서브프로세스 잡**(인덱서 패턴) | ★ 이탈. 외부 브로커 미도입 — 아래 |

**왜 Celery/RQ 를 안 쓰나(중요 이탈)**: 이 프로젝트는 단일 개인 PC·로컬 전용이며 Redis 등 외부 브로커를
의도적으로 안 둔다. 관리자 인덱서가 이미 **서브프로세스로 CLI 단계를 띄우고 `_running_jobs` 로 추적**한다.
안정화도 같은 패턴이면: ① 동시성 1·상호배제를 한 코드에서 통제, ② 서브프로세스 종료 = VRAM 해제(공짜),
③ 새 인프라 0. 워커 수를 늘려야 할 만큼 트래픽이 생기면 그때 재검토(§13).

**신규 의존성**(추가 필요): `ultralytics`(YOLO11-seg, 트래커 포함) **또는** SAM2, `opencv-python`,
`ffmpeg`(시스템 바이너리 — `imageio-ffmpeg`로 번들 대안). RAFT·torch·numpy 는 이미 있음.
> ⚠️ **uv lock 주의**: torch/torchvision 은 cu124 인덱스로 고정(`[tool.uv.sources]`)돼 있다([feedback_uv_sync_torch]).
> `ultralytics` 가 torch 를 끌어당겨 CPU 빌드로 덮지 않게, 추가 후 `uv sync` 결과의 torch 빌드(+cu124)를 반드시 검증.

---

## 6. API 설계

기존 라우터(`admin.py`, `image.py`)와 동일하게 **localhost-only + 자체 TLS** 전제. prefix `/api/stabilize`.

| 메서드 | 경로 | 동작 |
|---|---|---|
| POST | `/api/stabilize/jobs` | multipart 업로드(mp4) + 파라미터 → 잡 생성, `{job_id, status:"queued"}` 반환. 다른 잡/인덱싱 실행 중이면 409 |
| GET | `/api/stabilize/jobs` | 잡 목록(상태·단계·진행률) |
| GET | `/api/stabilize/jobs/{id}` | 단일 잡 상태(폴링용) — status.json 반영 + metrics |
| GET | `/api/stabilize/jobs/{id}/result` | 완료 시 `out.mp4` 다운로드(`FileResponse`) |
| POST | `/api/stabilize/jobs/{id}/cancel` | 현재 단계 서브프로세스 terminate(인덱서 pause 와 동일 기법) |
| DELETE | `/api/stabilize/jobs/{id}` | 잡 디렉토리 삭제 |

**상태 머신**: `queued → running(stage=decode|segment|flow|smooth|warp|encode) → done | failed | canceled`.
잡은 영상당 수 초~수 분 → **동기 HTTP 금지, 폴링**. 진행률 = (완료 단계 + 현재 단계 프레임 진행)/총.

**잡 추적 모델**: 인덱서는 `_running_jobs`(메모리, 재시작 시 소실). 안정화 잡은 더 길고 **다운로드 산출물**이 있어
**잡당 `status.json`(워커가 원자적 갱신) = 단일 진실 소스**로 두고, API 는 그걸 읽는다(재시작 후에도 폴링·결과 복구).
선택적으로 `data/stabilize/index.json` 또는 작은 `stabilize.db` 로 목록 가속(메모리 캐시 + status.json 동기화).

---

## 7. config.yaml 추가 블록(안)

```yaml
stabilize:
  work_dir: "data/stabilize"        # 잡 작업 루트 (.gitignore)
  max_input_seconds: 60             # 입력 길이 상한 (명세 미결정 → 실측 후 확정)
  max_input_pixels: 2073600         # 1920x1080 상한 (초과 시 거부 or 다운스케일)
  estimate_long_side: 640           # 모션 추정 다운스케일(긴 변 px) — VRAM/속도 핵심 노브
  segment_backend: "yolo11"         # yolo11 | sam2
  segment_model: "yolo11x-seg.pt"   # 또는 경량 yolo11n-seg.pt
  flow_backend: "raft"              # raft | orb
  smoothing: "gaussian"             # gaussian | l1
  smoothing_sigma: 30               # 가우시안 창(프레임) — 클수록 부드럽지만 지연/크롭↑
  crop_mode: "person_aware"         # 인물 트랙 포함 최소 크롭
  max_crop_ratio: 0.15              # 변당 최대 허용 크롭 비율(세로 보호) — 초과 시 평활화 강도 자동 완화
  encoder: "h264_nvenc"             # NVENC. 폴백 libx264
  retain_hours: 24                  # 잡 산출물 보존 후 자동 정리
  concurrency: 1                    # 동시 잡 수(12GB 공유 → 1)
```

`upload_max_bytes`(현재 10MB)는 영상엔 너무 작다 → 안정화 업로드는 **별도 상한**(예: 200–500MB)을 두고
`max_input_seconds`/`max_input_pixels` 로 실질 제어. config.yaml `server.upload_*` 와 분리.

---

## 8. 평활화 알고리즘 (명세 미결정 #1)

> AI 개념 한 줄: **카메라 궤적**은 프레임별 변환을 누적한 "카메라가 그동안 어떻게 움직였나"의 곡선이다.
> 안정화 = 이 곡선을 **부드럽게 다시 그린 뒤**(원하는 궤적), 원본→평활 궤적 차이를 각 프레임에 역으로 적용.

- **가우시안(PoC 기본)**: 누적 궤적(dx,dy,da…)을 가우시안 커널로 저역통과. 단순·빠름·오프라인이라 미래 프레임 활용 가능.
  `sigma` 하나로 강도 조절. 약점: 급격한 의도된 패닝도 깎임.
- **L1-optimal(업그레이드)**: 궤적을 정적/등속/등가속 구간(C0/C1/C2)의 조합으로 LP 최적화(YouTube 스태빌라이저 방식).
  결과가 "삼각대+슬라이더" 같고 크롭도 제약으로 넣을 수 있어 **세로 크롭 최소화에 유리**. 약점: 구현·튜닝 비용.

**권고**: M3 에서 **가우시안으로 동작 확보 → 동일 인터페이스(`smooth.py`)로 L1 추가**해 같은 클립으로 크롭 비율·잔여 모션 A/B.
크롭이 병목이면 L1 채택, 아니면 가우시안 유지.

---

## 9. 워프 + 최소 크롭 (세로 9:16 핵심 품질)

- 워프로 가장자리에 빈 영역(검은 띠)이 생긴다. 그걸 잘라내되 **세로 영상은 크게 자르면 인물이 답답** → "얼마나 안 자르고 안정화하느냐"가 핵심 지표.
- **person-aware 크롭**: `segment` 가 남긴 **인물 bbox 트랙(track.json)** 의 합집합을 반드시 포함하는,
  모든 프레임에서 유효 픽셀만 담는 **공통 최대 내접 사각형**을 9:16 비율로 구한다.
- **피드백 루프**: 요구 크롭이 `max_crop_ratio` 초과면 → `smooth` 강도(sigma/L1 제약)를 **자동 완화**해 재계산
  (덜 부드럽지만 덜 자름). 트레이드오프를 코드가 자동 절충.
- 길이/해상도 상한(§7)은 **M1 VRAM·시간 실측 후 확정**(명세 미결정 #3). 잠정: ≤60s, ≤1080p, 추정 640px.

---

## 10. 품질 평가 지표 (명세 §6 마지막 항목)

`metrics.py` 가 `out.mp4` 와 함께 기록(잡 status 에 노출):

- **크롭 비율**: 결과/원본 화각 비(낮을수록 손실↑). 가장 중요한 세로 품질 지표.
- **안정화 정도(잔여 모션)**: 안정화 후 프레임간 잔여 변환 크기 평균/표준편차(작을수록 안정).
- **인물 유지율**: 인물 bbox 가 크롭 안에 온전히 남은 프레임 비율.
- (옵션) 처리 시간·peak VRAM — 캡·동시성 정책 튜닝용.

가우시안 vs L1, YOLO11 vs SAM2 비교를 이 지표로 객관화한다.

---

## 11. 보안·운영

- **localhost-only + 자체 TLS**: 기존 라우터와 동일 가드(`_localhost_only`). 인터넷 노출 금지([CLAUDE.md]).
- **업로드 검증**: 확장자/시그니처/길이/해상도 화이트리스트, 경로 탈출 방지(job_id 는 서버 생성 UUID).
- **상호배제**: 인덱싱 파이프라인 실행 중 안정화 거부(역도) — `admin._running_jobs` 와 교차 확인.
- **자원 정리**: `retain_hours` 경과 잡 자동 삭제(인덱서 `cleanup.py` 스타일). `frames/`·`warped/` 는 완료 즉시 삭제.
- **API 재시작 수동**(기존 규칙): 라우터/패키지 변경 후 8000 포트 프로세스 재기동. `--reload` 금지([CLAUDE.md]).
- **gitignore**: `data/stabilize/` 추가. 노골적 샘플 영상·문구는 커밋 금지(점잖은 기본값만 — Git 워크플로 규칙).

---

## 12. 테스트 전략

- **합성 흔들림 픽스처**: 정지 이미지/짧은 클립에 **알려진 흔들림 변환을 코드로 주입** → 안정화 후 잔여 모션이 임계 이하인지(역검증).
- **단위**: `smooth`(궤적→평활 수학), 크롭 박스 계산(인물 bbox 포함·9:16 비율), `flow` 의 마스크 제외 로직(인물 픽셀이 RANSAC 에서 빠지는지).
- **통합**: 5–10프레임 초소형 클립으로 decode→…→encode 전체를 CPU/소 VRAM 에서 통과(CI 가벼움 유지). GPU 무거운 경로는 `@pytest.mark.gpu` 로 옵트인.
- 명령: `.\.venv\Scripts\python.exe -m pytest -k stabilizer -q` ([CLAUDE.md] 테스트 규칙).

---

## 13. 미결정 — 구현 전 사용자 확정 필요

명세의 "미결정" + 통합으로 새로 생긴 결정들:

1. **세그멘테이션 백엔드**: YOLO11-seg(가벼움·빠름, **권고 시작점**) vs SAM2(품질·마스크 정밀, 무겁고 12GB 빠듯). 추상화는 양쪽 두되 PoC 기본은?
2. **평활화**: 가우시안 시작 → 필요 시 L1 추가(권고). 처음부터 L1 갈지?
3. **길이/해상도 상한 + 동시성**: 잠정 ≤60s/≤1080p/추정640px/동시1 — M1 실측 후 확정.
4. **출력 규격**: 코덱(h264 vs hevc), fps/오디오 보존 범위, 컨테이너(mp4 고정?).
5. **프론트 UI**: API만(curl/외부 호출) vs `apps/web` 에 간단 업로드·미리보기 페이지 추가 여부.
6. **B 경로(무크롭 생성형, RStab 등)**: 본 계획은 A 경로 PoC 한정. 크롭이 병목으로 확인된 뒤 별도 계획으로.

---

## 14. 마일스톤 (제안)

명세 §6 체크리스트를 flayAI 통합 관점으로 재배열. 각 M 종료 시 한국어 Conventional Commit(피처 브랜치 없이 main 직접 — [feedback_git_workflow]).

| M | 목표 | 산출 | 검증 |
|---|---|---|---|
| **M0** | 스캐폴딩 | `packages/stabilizer` 골격, `stabilize.py` 라우터(잡 생성/폴링/결과), `data/stabilize` 레이아웃, config 블록, gitignore | 더미 잡이 queued→done 흐르고 폴링됨(영상 무가공 패스스루) |
| **M1** | FFmpeg I/O + VRAM 실측 | `decode`/`encode`(NVENC), 다운스케일 정책, **본 PC VRAM·시간 측정 → §9 캡 확정** | mp4 in→out 라운드트립, 실측표 |
| **M2** | 세그 + 마스킹 모션 | `segment`(YOLO11-seg+트래커), `flow`(RAFT+마스크 제외+RANSAC) → transforms.json | 인물 픽셀이 모션 추정에서 빠짐(단위) |
| **M3** | 평활화 + 워프/크롭 | `smooth`(가우시안), `warp`(person-aware 최소 크롭), 피드백 루프 | 합성 흔들림 클립 잔여 모션↓, 크롭 비율 기록 |
| **M4** | 잡 견고화 | 단계 재개·취소·상호배제(인덱싱 교차), `retain_hours` 정리, status.json 원자적 갱신 | 강제종료 후 재실행 이어감, 동시 잡 거부 |
| **M5** | 품질·비교 | `metrics`, L1 평활화 옵션, 가우시안 vs L1 / YOLO vs SAM2 A/B | 지표로 백엔드 확정 |
| **M6**(옵션) | 프론트 | `apps/web` 업로드·진행률·전후 미리보기 | 브라우저에서 업로드→다운로드 |

---

## 15. 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| 12GB VRAM 초과(세그+RAFT+시청 동시) | OOM·죽음 | 단계-서브프로세스 격리, 저해상도 추정, 동시1, 시청 비권장 명시, M1 실측 |
| `ultralytics`/SAM2 가 torch CPU 빌드로 덮음 | InsightFace 등 GPU 깨짐 | 추가 후 `uv sync` torch +cu124 검증([feedback_uv_sync_torch]) |
| 프레임 PNG 디스크 폭증 | 디스크 고갈 | 완료 즉시 frames/warped 삭제, retain_hours 정리, 길이 캡 |
| 세로 크롭 과다 | 품질 병목 | person-aware 크롭 + 피드백 루프, 필요 시 L1, 최후 B 경로 |
| FFmpeg/NVENC PATH·드라이버 이슈(Windows) | 인코딩 실패 | libx264 폴백, imageio-ffmpeg 번들 옵션, M1 에서 환경 확인 |
| 동기 HTTP 로 처리 시 타임아웃 | UX 실패 | 처음부터 폴링 잡 모델(동기 금지) |

---

## 16. 문서·디렉토리 영향

- 신규: 이 문서. 구현 시작 후 `docs/video-stabilization.md`(동작 설명서)로 분리, `docs/README.md` 표·`docs/TODO.md` 갱신.
- 변경: `pyproject.toml`(deps + `flay-stab` 스크립트), `config.yaml`(stabilize 블록), `.gitignore`(data/stabilize), `apps/api/main.py`(라우터 include).
- 인덱서/RAG/Qdrant/`flay.db` 메타는 **불변**(격리 원칙 §1).

---

### 부록 — 명세 §6 체크리스트 ↔ 본 계획 매핑

| 명세 다음 작업 | 본 계획 |
|---|---|
| 프로젝트 스캐폴딩(FastAPI+워커+FFmpeg I/O) | M0 + M1 (워커=인하우스 서브프로세스 잡) |
| SAM2 마스킹 → RAFT 연동 골격 | M2 (PoC 는 YOLO11-seg, SAM2 는 백엔드 옵션) |
| 궤적 평활화(가우시안 vs L1) | M3(가우시안) + M5(L1 비교) §8 |
| 워프 + 최소 크롭(인물 반영) | M3 §9 |
| 비동기 잡 큐 + 폴링 API | M0/M4 §6 (Celery 대신 인하우스) |
| 품질 평가 지표 | M5 §10 |
