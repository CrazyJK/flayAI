# 영상 안정화 API — flayAI 통합 초기 계획

> 흔들린 짧은 세로 영상을 입력받아 흔들림을 제거한 안정화 영상을 돌려주는 서버 기능.
> 단순 손떨림 보정이 아니라 **무엇을 기준으로 고정할지(배경 / 인물 / 둘 다)** 를 골라 안정화한다.
> 배경 기준일 때의 핵심 트릭은 **모션 추정 시 인물 영역을 마스킹해 제외**해, 움직이는 인물이
> 카메라 모션 추정을 오염시키지 않게 하는 것.
>
> 이 문서는 **확정된 계획**이며, 일부는 **구현 완료**(아래 §구현 현황)다. flayAI 컨벤션
> ([CLAUDE.md](../CLAUDE.md), `.github/copilot-instructions.md`)에 맞춰 구현한다.
> 워프로 생기는 빈 영역은 **자르지 않는다** — 결과가 원본보다 커져도 괜찮다(검은 여백 허용).
> 잘라내기/재프레이밍은 **별도 후속 기능**으로 분리한다(§10).

---

## 구현 현황 (2026-06-14 기준)

샘플(장원영 입장 직캠, 4K·60fps·AV1·34s)로 검증하며 배경·인물 모드 전 기능 구현·동작 확인.
**상태: 배경/인물 안정화 + 클릭 지정(SAM2) + 자동 강도 + 여백 처리(블러/크롭) + 전체 UI 동작.**

### 확정 설계 (사용자 합의)
- 옵션 = **[기준: 배경 | 인물] × [강도: dejitter ~ smooth ~ lock | auto] × [여백: 채움(blur) | 잘라내기(crop)]**.
- **인물 주인공 지정 = 한 프레임 클릭** → SAM2 메모리 전파(가림 강건). 클릭 지점(얼굴/몸통)이 고정 앵커.
- **배경 엔진 = ffmpeg vidstab**(robust). RAFT+마스킹은 후속. **잡 처리 = 인하우스 서브프로세스**(외부 브로커 없음).

### 실측 요약 (RTX 4070 Ti)
| 항목 | 값 |
|---|---|
| AV1 4K 디코딩+다운스케일 | 93 fps (sw) |
| YOLO11x-seg(540px) / RAFT(360~720) | 45fps·0.5GB / 0.25~2.9GB (4K 직접 RAFT는 OOM) |
| **SAM2 tiny**(클릭 추적, CPU오프로드) | **VRAM ~0.7GB · 24fps** |
| 배경 vidstab 무크롭 캔버스 | 첫15초 정지형 lock ×1.20 / 전체 트래블 soft ×1.12 |
| SAM2 효과 | **정체성 점프 greedy 12 → SAM2 0**(군중 가림 튐 제거) |
| 밴드패스 보정 | 인물 배경 미세 튐 **34~47%↓** |
| **한계** | ① 카메라 전진(시차)이 크면 2D 한계(완전 락은 B경로 3D) ② **저fps gif**(예: 10프레임·5fps)는 데이터 부족으로 안정화 절반까지만(보간·디노이즈로도 개선 안 됨 — 소스 한계) |

### 구현됨 ✅
**잡/인프라** (`packages/stabilizer`, `apps/api/routers/stabilize.py`, `apps/api/main.py`)
- 잡 모델(`job.py`, status.json 원자적 기록·재시작 복구), 서브프로세스 워커(`cli.py`), 파이프라인 디스패치
- API: POST/GET `jobs`, `result`(GET+HEAD·Range), `cancel`, `DELETE` · localhost-only + 동시 1잡 + 인덱싱 상호배제 · CORS(GET/POST/DELETE)
- **보존기간 정리**: `cleanup_old_jobs()`(retain_hours 경과 잡 삭제, 새 잡 시 + CLI `cleanup`)
- config `stabilize:` 블록 · 단위 테스트(`tests/test_stabilizer.py`)

**배경 엔진** (`engines/vidstab.py`)
- vidstab 2패스(detect→transform), 강도 프리셋(dejitter/smooth/lock)→smoothing
- **auto 강도**: work.mp4 ORB 카메라 이동량(drift) 측정 → lock/smooth/dejitter (seg15→lock, 전체→dejitter 검증)
- 여백: 채움(`optzoom=0` 검은 여백) / **잘라내기**(`optzoom=1` 줌인) · NVENC+libx264 폴백 · 캔버스 확장 지표

**인물 엔진** (`engines/person.py`, `engines/track_sam2.py`)
- **SAM2 추적**(`track_sam2.py`): 클릭 점 프롬프트 → 전후 양방향 메모리 전파. tiny+CPU오프로드. x=마스크 중심·y=마스크 상단(머리, 가림 강건) + σ5 평활. 체크포인트 없거나 실패 시 **그리디(YOLO11-seg) 폴백**
- **클릭 앵커**: 클릭 지점의 상대 위치를 고정점으로(얼굴/몸통 구분)
- **추적 후처리**: 미검출 선형보간 + 이상치 median 대체 + **밴드패스 보정**(σ_denoise=4 → 배경 미세 튐 제거)
- 피사체 락(평행이동 target=gauss−gauss), **auto 강도**(주인공 화면 이동량 excursion)
- 여백: 채움(**blur** 흐린 확대) / black / **잘라내기**(공통영역 교집합, 너무 작으면 blur 폴백) · 스트리밍 워프(프레임 디스크 미저장)

**프론트** (`apps/web/src/app/stabilize/page.tsx`)
- 업로드(드래그&드롭·큰 화면, **mp4/mov/avi/mkv/webm + gif/이미지**) · 파일 변경 · **새 영상** 시작
- 기준(배경/인물) · 강도(auto 기본) · 여백 처리(채움/잘라내기) 선택
- **인물 클릭 지정 UI**(큰 영상에서 얼굴/몸통 클릭, 마커) · gif/이미지는 `<img>` 렌더
- 진행: **단계별 원형 불빛**(대기/진행/완료/실패 색, 좌측 사이드, 처리 중 미리보기 유지)
- 결과: 전/후 비교(영상 꽉 차게 fit·비율 유지) + **동시 재생**(음소거 토글) + 다운로드 + 다시 설정
- 모니터 방향 반응형 3단(옵션|메인|최근작업) · 최근작업 친절한 라벨·상대시간·전체 삭제

**의존성**: `ultralytics`·`sam2` pyproject 선언(`uv lock` 필요 — [project_stabilizer_pip_deps] 메모리). SAM2 체크포인트
`data/stabilize/_models/sam2.1_hiera_tiny.pt`(별도 다운로드, gitignore). 가중치 `yolo*.pt`·`data/stabilize/` gitignore.

### 남은 할 일 ⬜

**기능**
- [x] **인물 스케일 고정 토글** — 주인공 크기까지 일정(앵커 기준 줌, 출력 작업크기 고정). 거리 변화 클수록 배경 줌 손실↑
- [ ] **여백 temporal 모자이크**(배경 모드) — 검은/블러 여백을 이웃 프레임으로 메움. 인물 모드는 캔버스가
  주인공 기준이라 이웃 배경 비정렬 → 부적합(blur 유지). 배경 모드 + 명시적 transform 필요(B1과 결합)
- [ ] **RAFT+마스킹 배경 엔진**(B1) — vidstab로 충분하나, 참조프레임 정합 '진짜 락'·temporal 채움·파이프 통일 필요 시
- [ ] **얼굴/포즈 기반 정밀 앵커**(우선순위 낮음) — 현재는 SAM2 마스크 상단(머리)+클릭 오프셋으로 얼굴을
  *근사* 고정. InsightFace(이미 보유, 추가 의존성 0)로 눈·코 랜드마크에 *정밀* 고정 가능(얼굴 클로즈업·눈높이
  맞춤용). 매 프레임 주인공 마스크 안 얼굴 선택 + 평활, **얼굴 없는 프레임(뒤돌기 등)은 마스크 앵커로 폴백**.
  일반 안정화엔 머리 앵커로 충분 → 얼굴 중심 영상이 실제로 필요할 때 추가
- [x] **"둘 다" 모드** — 한 업로드로 배경·인물 두 결과(엔진이 out_name+dict 반환, 파이프라인 누적,
  work.mp4 공유). 결과 화면 variant 탭, `result?variant=` 서빙
- [ ] **B경로**(RStab 등 3D 풀FOV) — 시차 큰 트래블의 완전 무크롭 락(연구용, GPU 큼)

**품질/UX**
- [x] **저fps/소수프레임 입력 경고** — status note(`_ffwork.lowfps_note`). 프론트 "참고:"에 표시
- [x] **gif 보간 옵션**(minterpolate) — 옵션 `interpolate`, UI 토글. 끊김 완화용(흔들림은 미개선)
- [x] **진행률 세분화** — SAM2 추적(30→52%)·인물 워프(70→98%) 루프 진행 갱신
- [ ] UI 추가 다듬기(검출 박스 탭 선택 등)

**운영**
- [x] **`uv lock`** — ultralytics·sam2 락 동기화(torch cu124 유지). 설치는 사용자 `uv sync`
- [x] **NVDEC AV1 하드웨어 디코딩**(`-hwaccel cuda`) — 4K AV1 디코딩 2배+(`_ffwork`, SW 폴백)
- [ ] 구현 안정화 후 `docs/video-stabilization.md`(동작 설명서)로 분리, `docs/README.md`·`docs/TODO.md` 반영

### ⚠️ 대형/연구 항목 — 착수 전 반드시 재확인 (사용자 지시)

> **이 세 항목을 "구현하라"는 요청을 받으면, 곧바로 시작하지 말고 아래 경고를 다시 보여주고
> "그래도 진행할지" 한 번 더 물어볼 것.** (큰 시간/리스크 → 묻고 합의 후 착수.)

1. **RAFT+마스킹 배경 엔진** — *연구 아님, 큰 엔지니어링.* RAFT(torchvision)·YOLO 보유라 신규 의존성 0,
   VRAM ~1GB. 하지만 person.py 만한 **새 엔진 한 벌**(decode→플로우→마스킹→강건 전역적합→평활→워프→인코딩),
   1~2세션. **vidstab로 이미 충분(×1.12)** → 진짜 락·temporal 채움·파이프 통일이 *실제로 필요할 때만*.
2. **여백 temporal 모자이크**(배경 전용) — *naive는 가능, 깨끗한 버전은 연구성.* **1번(명시적 transform) 선행 필요.**
   이웃 프레임 정합으로 여백 채움 → 이음새·노출차·**움직이는 사람 고스팅**(비디오 모자이킹 영역). 중대형.
3. **B경로(3D 뷰합성, RStab 등)** — **진짜 별도 프로젝트.** 깊이+카메라자세+다중프레임융합+신경렌더링.
   외부 **학술 레포**(특정 CUDA/torch·커스텀 op·Linux 전용 경향) → 환경 셋업만 수일, **12GB 초과 위험**,
   연구 품질(반사·동적·저텍스처 취약). *시차 큰 전진 샷의 완전 무크롭 락*이 꼭 필요할 때만 착수.

---

## 0. 한눈에 — 무엇을, 어디에

| 항목 | 결정 | 근거 |
|---|---|---|
| 통합 방식 | **flayAI 레포 안 새 서브시스템** (`packages/stabilizer` + `apps/api/routers/stabilize.py` + `apps/web` 화면) | 같은 12GB GPU·torch/CUDA·FFmpeg·FastAPI 스택 공유 → VRAM 조율을 한 곳에서 |
| 안정화 기준 | **배경 / 인물 / 둘 다** 사용자 선택(잡 파라미터 + UI 라디오) | §4 |
| 크롭 | **하지 않음. 캔버스 확장(검은 여백 허용).** 잘라내기는 별도 후속 기능 | 사용자 결정 — "원본보다 커져도 OK" |
| 잡 처리 | **인하우스 서브프로세스 잡**(인덱서 패턴 재사용). 외부 브로커(Celery/Redis) 미도입 | 단계-서브프로세스가 곧 VRAM 격리. 새 인프라 0 |
| 모션 추정(배경) | **RAFT (torchvision 내장)**, 저해상도 추정. 경량 폴백 ORB | `torchvision==0.21.0` 에 `raft_large` 내장 → 신규 딥 의존성 0 |
| 모션 추정(인물) | 세그멘테이션 **트랙(인물 bbox 궤적)** 으로 피사체 모션 산출 | 별도 RAFT 불필요(가벼움) |
| 세그+트래킹 | PoC = **YOLO11-seg(person) + 내장 트래커**, 업그레이드 = SAM2 | 12GB·속도 우선. `segment.py` 백엔드 교체 가능 |
| 평활화 | **가우시안**(기본) → 동일 인터페이스로 L1-optimal 옵션 추가 | §9 |
| 프론트 | **만든다** — 업로드+옵션 화면 / 진행 화면 / 결과 보기(전후 비교) | §11 |
| 동시 작업 | **1개**(전역 락) + 인덱싱과 상호배제 | 12GB 공유 |

```
업로드 mp4 + 옵션(기준=배경|인물|둘다, 평활화 강도, …)
  │  POST /api/stabilize/jobs        (localhost + 자체 TLS)
  ▼
data/stabilize/{job_id}/  ── 서브프로세스 잡(packages.stabilizer.cli) 단계별 실행, 단계 사이 VRAM 해제
  in.mp4 → frames/ → masks/+track.json → transforms.json → smoothed.json → out.mp4 (+ 검은 여백)
  ▲                                                                           │
  └── GET /api/stabilize/jobs/{id} (폴링) ── status.json ──────────────────────┘
                                                       │
  apps/web /stabilize 화면 ── 업로드·옵션·진행·결과(전후 비교) ──────────────────┘  → 결과 재생/다운로드
```

---

## 1. 왜 flayAI 레포 안인가

이 PC의 현실: **GPU 1장(RTX 4070 Ti 12GB)을 모니터 4개·영상 시청·flayAI ML 스택(bge-m3·CLIP·InsightFace·Ollama)과 공유**한다.
안정화의 세그멘테이션/RAFT 까지 더하면 VRAM 경합이 안정성·품질을 좌우한다.

flayAI 는 이미 **단계마다 서브프로세스를 띄워 VRAM 을 해제**하는 인덱서 패턴과, GPU 단계 진입 시 Ollama
모델을 언로드하는 `ollama_vram` 훅을 갖고 있다. 안정화를 같은 레포·같은 잡 모델에 두면 **이 조율을 그대로
재사용**하고 "인덱싱 중엔 안정화 금지" 같은 상호배제도 한 곳에서 건다. 별도 서비스로 떼면 조율 불가능한 3중 경합이 된다.

**재사용**: FastAPI 앱·라우터, typer CLI, 서브프로세스 잡 추적(`admin.py`), `ollama_vram.unload_all_models()`,
localhost-only + 자체 TLS, `packages/settings`(config 로더), SQLite(WAL)·`data/` 레이아웃, Next.js 웹·`docs/` 컨벤션.

**격리**: 안정화는 **K:\Crazy 컬렉션과 무관**한 임시 업로드 영상을 다룬다. 인덱서/RAG/Qdrant 컬렉션·`flay.db`
메타에 손대지 않는다. 산출물은 `data/stabilize/` 에 격리하고 보존기간 후 정리한다.

---

## 2. 핵심 제약 — GPU 예산 (가장 중요)

> AI 개념 한 줄: **VRAM**(Video RAM)은 GPU 전용 메모리다. 모델 가중치 + 처리 중 텐서가 여기 올라간다.
> 12GB 를 넘기면 OOM(메모리 부족)으로 죽거나 느린 시스템 RAM 으로 밀려난다.

| 소비처 | 대략 VRAM | 비고 |
|---|---|---|
| 모니터 4개 데스크톱 | ~0.5–1.5GB | 상시 |
| 영상 시청(디코딩·브라우저) | ~0.5–2GB | 사용자 행동에 따라 변동 |
| flayAI 인덱싱 GPU 단계 | 수 GB | **안정화와 동시 금지**(상호배제) |
| Ollama 채팅 LLM(qwen 7B) | ~5–6GB | 유휴 5분 후 해제. GPU 단계 진입 시 `unload_all_models()` 로 비움 |
| **RAFT(raft_large)** | **추정 ~2–4GB** | **배경 모드 한정.** 저해상도(긴 변 512–720)에서 추정 → VRAM·속도 절감 |
| **세그멘테이션(YOLO11-seg)** | **추정 ~1–2GB** | SAM2 선택 시 ~4–6GB+ (메모리 뱅크가 클립 길이에 비례 증가) |

**설계 결론**
1. **단계-서브프로세스**로 한 모델씩 올렸다 내린다(세그 끝 → 종료로 VRAM 해제 → RAFT 시작). 인덱서와 동일.
2. **동시 안정화 잡 = 1**(전역 락). 인덱싱 파이프라인과 **상호배제**.
3. **배경 모드 모션 추정은 다운스케일 해상도**에서. 변환행렬은 저주파라 저해상도로 충분 → RAFT VRAM/시간 절감.
4. GPU 단계 진입 시 `ollama_vram.unload_all_models()`(인덱서와 동일 훅).
5. 잡 실행 중 **영상 시청 비권장**(경합)임을 UI/문서에 명시.
6. **인물 모드는 GPU 가벼움**(세그멘테이션만, RAFT 불필요) → 비용 우위.

> 표의 VRAM 수치는 **추정**이다. M1 에서 본 PC·본 해상도로 `nvidia-smi` 실측해 §8 캡과 동시성 정책을 확정한다.

---

## 3. 아키텍처 — 디렉토리·모듈

기존 `packages/indexer`(단계형 파이프라인)를 본떠 새 패키지를 만든다.

```
packages/stabilizer/
  __init__.py
  cli.py            # typer — 각 단계가 서브커맨드 (decode/segment/flow/smooth/warp/encode), 'run' = 전체
  config.py         # config.yaml 의 stabilize 블록 파싱(기본값 포함)
  job.py            # 잡 디렉토리 레이아웃 + status.json 원자적 읽기/쓰기 + 상태 머신
  decode.py         # FFmpeg: in.mp4 → frames/%06d.png (+ fps·회전·해상도 probe)
  segment.py        # 인물 마스크 + ID 일관 트래킹 → masks/%06d.png, track.json(프레임별 인물 bbox)
  flow.py           # 기준별 프레임간 변환 산출 → transforms.json
                    #   배경: RAFT(다운스케일) dense flow → 인물 마스크 픽셀 제외 → RANSAC 전역 affine/homography
                    #   인물: track.json 의 bbox 궤적(중심 이동 + 크기 변화)으로 피사체 변환
  smooth.py         # 궤적 누적 + 평활화(가우시안 | L1) → smoothed.json (프레임별 보정 변환)
  warp.py           # 역변환 워프 → warped/ (or 인코더 직결). 무크롭: 전체 화각 포함하도록 캔버스 확장(검은 여백)
  encode.py         # FFmpeg(NVENC): 워프 결과 → out.mp4 (+ 메트릭 기록)
  metrics.py        # 안정화 정도(잔여 모션)·캔버스 확장 비율·처리시간/peak VRAM
  gpu.py            # VRAM 가드 / 다운스케일 정책 / ollama_vram.unload 연동

apps/api/routers/stabilize.py     # POST /jobs, GET /jobs, GET /jobs/{id}, GET /jobs/{id}/result, POST .../cancel, DELETE /jobs/{id}
apps/web/src/app/stabilize/        # 업로드+옵션 / 진행 / 결과(전후 비교) 화면 (§11)

data/stabilize/{job_id}/          # gitignore — 업로드·중간산출·결과·status.json (보존기간 후 정리)
tests/test_stabilizer_*.py        # 합성 흔들림 클립 픽스처로 단위/통합 테스트
docs/video-stabilization-plan.md (이 문서)  →  구현 후 docs/video-stabilization.md(동작 설명서)로 승격
```

CLI 진입점은 `pyproject.toml [project.scripts]` 에 `flay-stab = "packages.stabilizer.cli:app"` 추가(기존 `flay-index` 와 동일 패턴).

---

## 4. 안정화 기준 — 배경 / 인물 / 둘 다

> 원리상 한 영상에서 인물과 배경을 **동시에 완전 고정**하는 건 불가능하다(인물이 배경 대비 움직이면 둘을 같이 멈출 수 없음).
> 그래서 "무엇을 멈출지"를 사용자가 고른다.

| 모드 | 무엇을 고정 | 모션 추정 방법 | GPU | 결과 느낌 |
|---|---|---|---|---|
| **배경**(기본·권고) | 카메라 흔들림 제거 → 배경이 고정 | RAFT dense flow + **인물 마스크 제외** + RANSAC 전역 변환 | 무거움(RAFT) | 삼각대로 찍은 듯. 인물은 자연스럽게 배경 위에서 움직임 |
| **인물** | 피사체(인물)가 화면에 고정/안정 | 인물 **track(bbox 중심 이동 + 크기 변화)** 로 피사체 변환 산출 후 상쇄 | 가벼움(세그만) | 인물이 멈춰 보이고 배경이 흐름. "얼굴 고정" 류 |
| **둘 다** | 두 결과를 **모두 산출**(비교용) | 위 둘을 한 잡에서 각각 | 배경+인물 합 | 같은 입력의 배경고정본·인물고정본 2개 출력 |

- "둘 다"는 단일 프레임에서 양쪽을 동시 고정한다는 뜻이 **아니라**, 한 번 업로드로 **두 버전을 만들어 비교**하게 하는 것.
  세그멘테이션은 한 번만 돌리고(공유), 이후 배경/인물 경로를 각각 평활화·워프·인코딩한다.
- 향후 "둘 다" 를 단일 혼합본(배경 안정화 + 피사체 느린 재중심)으로 확장하는 건 별도 검토(§14).

---

## 5. 처리 파이프라인 — 인덱서식 단계 매핑

각 단계를 **"단계 = 서브프로세스 + 디스크 산출물 + 멱등/재개"** 로 구현한다. 중단/강제종료해도 디스크 산출물이
남아 재실행 시 이어진다(완료 프레임 skip). 단계 사이 프로세스가 죽어 VRAM 해제.

| # | 단계(CLI) | 입력 → 산출 | GPU | 핵심 |
|---|---|---|---|---|
| 1 | `decode` | in.mp4 → `frames/`, meta(fps·회전·WxH) | × | FFmpeg. 회전 메타 정규화. (옵션) 추정용 다운스케일 사본 |
| 2 | `segment` | frames → `masks/`, `track.json` | ○ | 인물 마스크 + ID 일관 트래킹. bbox 궤적도 저장(배경=제외용, 인물=모션원) |
| 3 | `flow` | frames(저해상도)+masks/track → `transforms.json` | 배경 ○ / 인물 × | 기준별 프레임간 변환 산출(§4) |
| 4 | `smooth` | transforms → `smoothed.json` | × | 카메라/피사체 궤적 누적 → 오프라인 평활화(미래 프레임 활용) → 프레임별 보정 변환 |
| 5 | `warp` | frames + smoothed → `warped/` (or 직결) | △ | 역변환 워프, **무크롭** — 전체 화각이 들어가도록 캔버스 확장(§10) |
| 6 | `encode` | warped → `out.mp4` + metrics | × | FFmpeg **NVENC**(h264/hevc), 원본 fps·오디오 보존 |

"둘 다" 모드는 1~2 를 공유하고 3~6 을 배경/인물 각각 실행해 `out_background.mp4`·`out_person.mp4` 를 만든다.

> 단계 분리 트레이드오프 — **분리**: VRAM 격리·재개성↑, 디스크 I/O(프레임 PNG)↑. **권고**: 분리 유지.
> 단 `frames/`·`warped/` 는 잡 완료 시 삭제하고 `out*.mp4` 만 남겨 디스크 절약(§8 정리).

---

## 6. 기술 스택

| 역할 | 채택 | 비고 |
|---|---|---|
| 디코딩/인코딩 | **FFmpeg + NVENC** | 4070 Ti(Ada)는 h264/hevc NVENC 지원 → 인코딩 GPU 오프로드. 폴백 libx264. ffmpeg 바이너리 PATH 필요(또는 `imageio-ffmpeg` 번들) |
| 모션 추정(배경) | **RAFT = `torchvision.models.optical_flow.raft_large`**(내장), 폴백 ORB(OpenCV) | torchvision 0.21 내장 → 신규 딥 의존성 0. 저해상도 추정 |
| 모션 추정(인물) | 세그 **track** 기반(중심 이동/크기) | RAFT 불필요. 회전까지 필요하면 마스크 내부 flow 로 확장(후속) |
| 세그+트래킹 | **YOLO11-seg(ultralytics) + 내장 트래커**(PoC), SAM2(업그레이드) | `segment.py` 백엔드 추상화로 교체 가능 |
| 워프·행렬 | **OpenCV**(`estimateAffinePartial2D`/`findHomography`/`warpAffine`/`warpPerspective`) | 신규 의존성 opencv-python |
| API | **FastAPI**(기존 앱에 라우터 추가) | 신규 앱 아님 |
| 프론트 | **Next.js 16 + React 19 + Tailwind 4**(기존 web) | 신규 화면 추가 |
| 비동기 | **인하우스 서브프로세스 잡**(인덱서 패턴) | 외부 브로커 미도입 — 아래 |

**잡 처리에 Celery/RQ 를 안 쓰는 이유**: 단일 개인 PC·로컬 전용이며 Redis 등 외부 브로커를 의도적으로 안 둔다.
관리자 인덱서가 이미 **서브프로세스로 CLI 단계를 띄우고 추적**한다. 안정화도 같은 패턴이면 ① 동시성 1·상호배제를
한 코드에서 통제, ② 서브프로세스 종료 = VRAM 해제(공짜), ③ 새 인프라 0. 트래픽이 워커 다중화를 요구할 만큼 커지면 재검토.

**신규 의존성**: `ultralytics`(YOLO11-seg, 트래커 포함) 또는 SAM2, `opencv-python`, `ffmpeg`(시스템 바이너리 / `imageio-ffmpeg` 대안).
RAFT·torch·numpy 는 이미 있음.
> ⚠️ **uv lock 주의**: torch/torchvision 은 cu124 인덱스로 고정돼 있다. `ultralytics` 가 torch 를 CPU 빌드로
> 덮지 않게, 추가 후 `uv sync` 결과의 torch 빌드(+cu124)를 반드시 검증한다(InsightFace 등 기존 GPU 경로 보호).

---

## 7. API 설계

기존 라우터와 동일하게 **localhost-only + 자체 TLS** 전제. prefix `/api/stabilize`.

| 메서드 | 경로 | 동작 |
|---|---|---|
| POST | `/api/stabilize/jobs` | multipart 업로드(mp4) + 옵션(mode·강도 등) → 잡 생성, `{job_id, status:"queued"}`. 다른 잡/인덱싱 중이면 409 |
| GET | `/api/stabilize/jobs` | 잡 목록(상태·단계·진행률) |
| GET | `/api/stabilize/jobs/{id}` | 단일 잡 상태(폴링) — status.json + metrics + 산출물 목록 |
| GET | `/api/stabilize/jobs/{id}/result?variant=background\|person` | 완료 시 결과 mp4 다운로드/재생(`FileResponse`, Range 지원). 단일 모드는 variant 생략 |
| POST | `/api/stabilize/jobs/{id}/cancel` | 현재 단계 서브프로세스 terminate(인덱서 pause 와 동일 기법) |
| DELETE | `/api/stabilize/jobs/{id}` | 잡 디렉토리 삭제 |

**POST 파라미터(안)**: `mode`(background|person|both), `smoothing_strength`(low|medium|high → sigma 프리셋),
(고급) `segment_backend`, `flow_backend`, `encoder`, `canvas`(expand|original).

**상태 머신**: `queued → running(stage=decode|segment|flow|smooth|warp|encode) → done | failed | canceled`.
영상당 수 초~수 분 → **동기 HTTP 금지, 폴링**. 진행률 = (완료 단계 + 현재 단계 프레임 진행)/총. "둘 다"는 변형별 진행 합산.

**잡 추적 모델**: 인덱서는 `_running_jobs`(메모리, 재시작 시 소실). 안정화 잡은 더 길고 **다운로드 산출물**이 있어
**잡당 `status.json`(워커가 원자적 갱신) = 단일 진실 소스**로 두고 API 가 그걸 읽는다(재시작 후에도 폴링·결과 복구).
선택적으로 `data/stabilize/index.json` 으로 목록 가속.

---

## 8. config.yaml 추가 블록(안)

```yaml
stabilize:
  work_dir: "data/stabilize"        # 잡 작업 루트 (.gitignore)
  mode: "background"                # 기본 안정화 기준: background | person | both
  max_input_seconds: 60             # 입력 길이 상한 (M1 실측 후 확정)
  max_input_pixels: 2073600         # 1920x1080 상한 (초과 시 거부 or 다운스케일)
  estimate_long_side: 640           # 배경 모드 모션 추정 다운스케일(긴 변 px) — VRAM/속도 핵심 노브
  segment_backend: "yolo11"         # yolo11 | sam2
  segment_model: "yolo11x-seg.pt"   # 또는 경량 yolo11n-seg.pt
  flow_backend: "raft"              # raft | orb  (배경 모드 모션 추정)
  smoothing: "gaussian"             # gaussian | l1
  smoothing_sigma: 30               # 가우시안 창(프레임). 강도 프리셋 low/medium/high 가 이 값으로 매핑
  canvas: "expand"                  # expand(전체 화각 보존, 캔버스 확장) | original(원본 크기 유지)
  encoder: "h264_nvenc"             # NVENC. 폴백 libx264
  retain_hours: 24                  # 잡 산출물 보존 후 자동 정리
  concurrency: 1                    # 동시 잡 수(12GB 공유 → 1)
```

`server.upload_max_bytes`(현재 10MB)는 영상엔 너무 작다 → 안정화 업로드는 **별도 상한**(예: 200–500MB)을 두고
`max_input_seconds`/`max_input_pixels` 로 실질 제어한다. 기존 이미지 업로드 설정과 분리.

---

## 9. 평활화 알고리즘

> AI 개념 한 줄: **궤적**은 프레임별 변환을 누적한 "그동안 어떻게 움직였나"의 곡선이다(배경 모드=카메라 궤적,
> 인물 모드=피사체 궤적). 안정화 = 이 곡선을 **부드럽게 다시 그린 뒤**, 원본↔평활 차이를 각 프레임에 역으로 적용.

- **가우시안(기본)**: 누적 궤적(dx,dy,da…)을 가우시안 커널로 저역통과. 단순·빠름·오프라인이라 미래 프레임 활용.
  강도 프리셋(약/중/강)이 `sigma` 로 매핑. 약점: 급격한 의도된 패닝도 깎임.
- **L1-optimal(옵션, 후속)**: 궤적을 정적/등속/등가속 구간(C0/C1/C2) 조합으로 LP 최적화(YouTube 스태빌라이저 방식).
  결과가 "삼각대+슬라이더" 같다. 약점: 구현·튜닝 비용.

**진행**: M3 에서 **가우시안으로 동작 확보** → 후속(M6)에서 동일 인터페이스(`smooth.py`)로 L1 추가, 같은 클립으로 잔여 모션 A/B.

---

## 10. 워프 — 무크롭, 캔버스 확장

- 워프하면 가장자리에 빈 영역(검은 띠)이 생긴다. **이를 자르지 않는다.** 결과가 원본보다 커져도 괜찮다.
- **캔버스 확장(`canvas: expand`)**: 각 프레임의 네 꼭짓점을 보정 변환으로 옮긴 위치의 **전체 합집합 사각형**을
  출력 캔버스로 잡는다. 모든 프레임의 모든 픽셀이 보존되고(손실 0), 데이터 없는 영역은 검은 여백. 출력 크기는
  전 프레임 공통(가장 큰 외접). 흔들림이 클수록 원본보다 눈에 띄게 커질 수 있다.
- `canvas: original` 옵션: 원본 크기를 유지(보정으로 밀려난 일부 내용은 화면 밖으로). 기본은 `expand`.
- **잘라내기/재프레이밍은 이 계획 범위 밖** — 안정화 후 검은 여백을 9:16 로 다시 자르거나 인물 기준으로 리프레임하는
  **별도 후속 기능**으로 분리한다. (안정화는 정보를 버리지 않고, 크롭은 그 위에서 선택적으로.)

이 결정의 효과: 인물이 잘려 나갈 일이 원천적으로 없어지고(무크롭), "얼마나 안 자르고 안정화하느냐"는 크롭 단계로 넘어간다.

---

## 11. 프론트엔드 UI (`apps/web`)

기존 Next.js 16 + React 19 + Tailwind 4 웹에 `/stabilize` 경로를 추가한다. localhost + 자체 TLS 전제.

**① 업로드 + 옵션 화면**
- 영상 업로드(드래그&드롭 / 파일 선택). 길이·해상도 상한 안내, 클라이언트 1차 검증.
- **안정화 기준**(라디오, 필수): `배경` / `인물` / `둘 다` — 각 항목에 한 줄 설명(§4 표의 "결과 느낌").
- **평활화 강도**: `약` / `중`(기본) / `강`.
- **고급 옵션**(접이식): 세그 백엔드(YOLO11/SAM2), 모션 추정(RAFT/ORB), 코덱(h264/hevc NVENC), 캔버스(확장/원본).
- 제출 → `POST /jobs` → `job_id` 받고 진행 화면으로.

**② 진행 화면**
- `GET /jobs/{id}` 폴링(작업 중 빠르게, 그 외 느리게 — 기존 admin 가시성 게이팅 패턴 재사용).
- 단계 진행바(decode→segment→flow→smooth→warp→encode)와 % 표시, **취소** 버튼.
- "둘 다" 모드면 배경/인물 두 변형 진행을 함께 표시.

**③ 결과 보기 화면**
- 안정화 영상 **재생**(`/result` Range 스트리밍) + **다운로드**.
- **전/후 비교**: 원본 vs 결과(나란히 또는 슬라이더). 캔버스가 커진 경우 그대로 보여줌(여백 포함).
- **지표 표시**(§12): 잔여 모션·캔버스 확장 비율·처리시간.
- "둘 다" 모드면 `배경 결과` / `인물 결과` 탭으로 각각.

**④ 최근 잡 목록**(선택): 상태·기준·생성시각, 결과 화면으로 이동.

내비게이션에 항목 추가. API 는 모두 localhost-only 가드를 그대로 통과(같은 호스트에서 서빙).

---

## 12. 품질 평가 지표

`metrics.py` 가 결과와 함께 기록(잡 status·결과 화면에 노출):

- **안정화 정도(잔여 모션)**: 안정화 후 프레임간 잔여 변환 크기 평균/표준편차(작을수록 안정) — 핵심 지표.
- **캔버스 확장 비율**: 출력/원본 면적비(클수록 흔들림이 컸다는 정보. 크롭 안 하므로 품질 감점 아님).
- **처리 시간 · peak VRAM**: 캡·동시성 정책 튜닝용.

가우시안 vs L1, YOLO11 vs SAM2, 배경 vs 인물 비교를 이 지표로 객관화한다.

---

## 13. 보안·운영

- **localhost-only + 자체 TLS**: 기존 라우터와 동일 가드(`_localhost_only`). 인터넷 노출 금지.
- **업로드 검증**: 확장자/시그니처/길이/해상도 화이트리스트, 경로 탈출 방지(job_id 는 서버 생성 UUID).
- **상호배제**: 인덱싱 파이프라인 실행 중 안정화 거부(역도) — `admin._running_jobs` 와 교차 확인.
- **자원 정리**: `retain_hours` 경과 잡 자동 삭제(인덱서 `cleanup.py` 스타일). `frames/`·`warped/` 는 완료 즉시 삭제.
  무크롭 출력은 원본보다 커질 수 있으니 디스크 여유·정리 주기를 보수적으로.
- **API 재시작 수동**(기존 규칙): 라우터/패키지 변경 후 8000 포트 프로세스 재기동. `--reload` 금지.
- **gitignore**: `data/stabilize/` 추가. 노골적 샘플 영상·문구는 커밋 금지(점잖은 기본값만).

---

## 14. 테스트 전략

- **합성 흔들림 픽스처**: 정지 이미지/짧은 클립에 **알려진 흔들림 변환을 코드로 주입** → 안정화 후 잔여 모션이 임계 이하인지(역검증).
- **단위**: `smooth`(궤적→평활 수학), `flow` 배경 경로의 마스크 제외(인물 픽셀이 RANSAC 에서 빠지는지), 인물 경로의 track→변환,
  캔버스 확장 외접 계산(전 프레임 픽셀 보존·여백 위치).
- **통합**: 5–10프레임 초소형 클립으로 decode→…→encode 전체를 CPU/소 VRAM 에서 통과(CI 가벼움). GPU 무거운 경로는 `@pytest.mark.gpu` 옵트인.
- 명령: `.\.venv\Scripts\python.exe -m pytest -k stabilizer -q`.

---

## 15. 미결정 — 구현 전 확정/실측

1. **세그멘테이션 백엔드**: YOLO11-seg(가벼움, **PoC 권고**) vs SAM2(마스크 정밀, 무거움). 추상화는 양쪽 두되 기본은?
2. **길이/해상도 상한 + 동시성**: 잠정 ≤60s/≤1080p/추정640px/동시1 — M1 실측 후 확정.
3. **출력 규격**: 코덱(h264 vs hevc), fps/오디오 보존 범위, 컨테이너(mp4 고정?).
4. **"둘 다" 향후 확장**: 단일 혼합본(배경 안정화 + 피사체 느린 재중심) 도입 여부 — 우선은 "두 결과 산출"만.
5. **고급 옵션 노출 범위**: UI 고급 패널에 어디까지 노출할지(세그/모션/코덱/캔버스).

---

## 16. 마일스톤 (제안)

각 M 종료 시 한국어 Conventional Commit(피처 브랜치 없이 main 직접, push 는 사용자).

| M | 목표 | 산출 | 검증 |
|---|---|---|---|
| **M0** | 스캐폴딩 | `packages/stabilizer` 골격, `stabilize.py` 라우터(생성/폴링/결과), `data/stabilize` 레이아웃, config 블록, gitignore | 더미 잡 queued→done, 폴링됨(무가공 패스스루) |
| **M1** | FFmpeg I/O + VRAM 실측 | `decode`/`encode`(NVENC), 다운스케일 정책, **본 PC VRAM·시간 실측 → §8 캡 확정** | mp4 in→out 라운드트립, 실측표 |
| **M2** | 세그 + 모션 | `segment`(YOLO11+트래커), `flow`(배경=RAFT+마스크 제외+RANSAC, 인물=track) → transforms.json | 인물 픽셀이 배경 추정에서 빠짐, 인물 track 변환 산출(단위) |
| **M3** | 평활화 + 무크롭 워프 | `smooth`(가우시안), `warp`(캔버스 확장, 검은 여백) | 합성 흔들림 클립 잔여 모션↓, 전 픽셀 보존 확인 |
| **M4** | 잡 견고화 | 단계 재개·취소·상호배제(인덱싱 교차), `retain_hours` 정리, status.json 원자 갱신, "둘 다" 2산출 | 강제종료 후 재실행 이어감, 동시 잡 거부 |
| **M5** | 프론트엔드 | `/stabilize` 업로드+옵션 / 진행 / 결과(전후 비교) 화면 | 브라우저에서 업로드→선택→다운로드, 둘 다 모드 두 결과 |
| **M6** | 품질·옵션 | `metrics`, L1 평활화 옵션, SAM2 백엔드, A/B 비교 | 지표로 백엔드·평활화 확정 |

---

## 17. 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| 12GB VRAM 초과(세그+RAFT+시청 동시) | OOM·죽음 | 단계-서브프로세스 격리, 저해상도 추정, 동시1, 시청 비권장, M1 실측 |
| `ultralytics`/SAM2 가 torch CPU 빌드로 덮음 | InsightFace 등 GPU 깨짐 | 추가 후 `uv sync` torch +cu124 검증 |
| 프레임 PNG + 확장 출력 디스크 폭증 | 디스크 고갈 | 완료 즉시 frames/warped 삭제, retain_hours 정리, 길이 캡, 보수적 정리 주기 |
| 무크롭 출력이 과도하게 커짐(심한 흔들림) | 재생·전송 부담 | `canvas: original` 옵션, 강도 조절, 후속 크롭 기능 |
| FFmpeg/NVENC PATH·드라이버 이슈(Windows) | 인코딩 실패 | libx264 폴백, imageio-ffmpeg 번들, M1 환경 확인 |
| 동기 HTTP 처리 시 타임아웃 | UX 실패 | 처음부터 폴링 잡 모델(동기 금지) |

---

## 18. 문서·디렉토리 영향

- 신규: 이 문서. 구현 시작 후 `docs/video-stabilization.md`(동작 설명서)로 분리, `docs/README.md` 표·`docs/TODO.md` 갱신.
- 변경: `pyproject.toml`(deps + `flay-stab`), `config.yaml`(stabilize 블록), `.gitignore`(data/stabilize),
  `apps/api/main.py`(라우터 include), `apps/web`(/stabilize 화면 + 내비).
- 인덱서/RAG/Qdrant/`flay.db` 메타는 **불변**(격리 원칙 §1).
