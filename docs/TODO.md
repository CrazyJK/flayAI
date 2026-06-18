# TODO — 문서·구현 동기화 및 후속 작업

> 2026-05-22 작성, 같은 날 1차 처리. README/`docs/`/`.github` 지침과 실제 코드·설정을 정적 검토(코드 실행·설치 없이)하여 도출한 불일치와 후속 작업 목록.
> 우선순위 표기: 🔴 기능/구성 영향 · 🟡 문서 정확도 · ⚪ 정리/참고.

검토에 쓸 점검 절차는 [`.github/prompts/docs-sync-check.prompt.md`](../.github/prompts/docs-sync-check.prompt.md) 로 재사용 가능.

---

## 🆕 영상 안정화(Stabilizer)

신규 서브시스템 [`docs/video-stabilization-plan.md`](video-stabilization-plan.md) — 흔들린 영상을 배경/인물 기준으로
안정화(클릭→SAM2 추적, 자동 강도, 여백 블러/크롭). **배경·인물 모드 + 전체 UI 동작.** 구현 현황과 **남은 할 일**(인물
스케일 고정·temporal 모자이크·RAFT 엔진·정밀 앵커·저fps 경고·진행률 세분화 등)은 그 문서의 "구현 현황" 절에 정리.

- ✅ `uv lock` 완료(ultralytics·sam2 동기화, torch cu124 유지). 설치 반영은 사용자 `uv sync`.
- 🟡 SAM2 체크포인트는 gitignore — 이 PC엔 있음. 다른 환경 체크아웃 시 재다운로드 필요(`data/stabilize/_models/sam2.1_hiera_tiny.pt`).

---

## 🆕 자막 생성(Subtitle)

신규 서브시스템 [`docs/subtitle-plan.md`](subtitle-plan.md) — instance 영상의 일본어 음성을 한국어
자막(`<stem>.srt`)으로. 외부에서 opus 신청 → 야간 드레인 배치. **phase 1(생성+큐+야간) 구현·테스트 통과.**

- 🔴 **의존성 설치**: `pyproject.toml` 에 `faster-whisper>=1.1` 추가됨 → `uv lock` 후 사용자 `uv sync`.
  CTranslate2 자체 CUDA12 libs 가 onnxruntime-gpu/torch 와 공존하는지 **`uv sync` 후 GPU 인식 검증**.
- 🔴 **모델·스케줄러**: large-v3 최초 1회 자동 다운로드(≈3GB). `scripts/nightly_subtitle.ps1` 작업
  스케줄러 등록(nightly_index 와 시간 분리 — GPU 동시 사용 방지).
- ⬜ **phase 2(번역메모리)**: 159개 팬자막으로 JP↔KO TM/용어집 → LLM few-shot 번역 + 평가셋.
- ⬜ **phase 3(싱크 수정)**: 기존 자막 드리프트를 Whisper 발화구간에 DTW 재정렬(타이밍만 교정).
- ✅ **자막 화면**: `/subtitle` 단독 페이지(신청 폼 + 큐/진행/이력). 관리자에서 분리,
  헤더 네비 '자막'. 카드 래퍼는 공용 `_components/SectionCard.tsx` 로 추출(관리자와 공유).

---

## 🆕 일기형 대화(Diary) — 수동 후속 작업

신규 기능 [`docs/diary.md`](diary.md) 구현 완료(코드·테스트·빌드 통과). 환경 의존 단계는 사용자 실행 필요:

- 🔴 **모델 받기**: `ollama pull huihui_ai/exaone3.5-abliterated:7.8b` (한국어 무검열, 7.8B Q4 ≈ 5GB VRAM — 영상 시청과 GPU 공유 유의).
- 🔴 **레거시 일기 일회성 임포트**: `.\.venv\Scripts\python.exe -m packages.diary.import_legacy` (Qdrant·Ollama 기동 상태에서). 정본 `.diary` 24개 적재, 멱등.
- ⚪ 후속 아이디어: 세션 제목/요약 LLM 지연 생성, assistant 발화 양방향 임베딩, `/diary` 히스토리 사이드 패널.

---

## ✅ 완료 (1차 처리)

문서(B 전체) + lock 무관 코드(A2/A4 + A1 주석)를 반영했다. 의존성 변경과 환경 필요 작업은 아래 "남은 작업" 으로 미뤘다.

- **A2** `pyproject.toml [project.scripts]` 진입점 `flay-api` `:start` → `:main` 수정.
- **A4** "HDBSCAN" 레거시 명칭 정리 — `config.yaml` 파라미터 주석, [`cli.py`](../packages/indexer/cli.py) docstring(모듈+`cluster-faces`), [`admin.md`](admin.md) 를 mutual-kNN + Union-Find 로 정정.
- **A1(주석)** `config.yaml` `models.ocr_lang` 주석을 "RapidOCR 사용, 이 값 미사용(레거시)" 으로 수정. (의존성 manifest 변경은 아래 잔여)
- **B1** LLM `:14b`/"14B" → `:7b` ([`architecture.md`](architecture.md), [`overview.md`](overview.md), [`README.md`](README.md)(docs), [`dev-guide.md`](dev-guide.md)).
- **B2** "Python 3.12" → 3.11 (루트 [`README.md`](../README.md), [`README.md`](README.md)(docs), [`dev-guide.md`](dev-guide.md)).
- **B3** "localhost 전용" → `ai.kamoru.jk` + 자체 TLS HTTPS 사실 반영 (overview/architecture/api-reference/dev-guide).
- **B4** 깨진 `AI_PLAN.md` 링크를 `docs/AI_PLAN.md` 위치로 수정 (루트 README, docs/README).
- **B5** [`dev-guide.md`](dev-guide.md) stale 절대 경로 `C:\kamoru\...` → `C:\Handyground\...`.
- **B6** [`README.md`](README.md)(docs)에 `admin.md`·`TODO.md` 추가, [`indexing-pipeline.md`](indexing-pipeline.md) ocr-posters "진행 중" 표기 제거, [`cli.py`](../packages/indexer/cli.py) 모듈 docstring 에 전체 커맨드 나열.

> 참고: [`AI_PLAN.md`](AI_PLAN.md) 는 "계획" 문서라 의도적으로 구현과 다르므로(아래 C) 수정하지 않았다.

---

## ✅ 완료 (2차 처리, 2026-05-22)

이 PC 에 `uv`/Ollama/Docker 가 설치되어, 1차에서 "uv 미설치" 로 보류했던 의존성 정리(A1 의존성 / A3)를 처리하고 `uv.lock` 을 재생성했다.

- **A1(의존성)** [`pyproject.toml`](../pyproject.toml): 런타임이 쓰는 `rapidocr-onnxruntime>=1.4` 추가, 미사용 `paddlepaddle-gpu`·`paddleocr` 제거.
- **A3** [`pyproject.toml`](../pyproject.toml): 미사용 `llama-index-*`(4종)·`faiss-cpu`·`hdbscan` 제거. [`config.yaml`](../config.yaml) `data.faiss_poster`/`faiss_faces` 경로 제거(코드 참조 없음 확인).
- **lock 재생성**: `uv lock` → 146 packages resolved. 위 패키지 + 고아 transitive(aiohttp·sqlalchemy·nltk·tiktoken 등) 제거, `rapidocr-onnxruntime 1.4.4`·`onnxruntime 1.26.0` 추가. `uv lock --check` 통과.

> ✅ **`uv sync` 안전화 완료 (GPU 빌드 lock 고정)**: 한때 `uv sync` 가 lock 의 CPU torch 로 GPU torch 를 덮어써 깨졌고 rapidocr 가 끌어온 CPU `onnxruntime` 이 `onnxruntime-gpu` 를 가려 InsightFace 가 CPU 로 떨어졌었다. 이제 [`pyproject.toml`](../pyproject.toml) `[tool.uv]` 에서 torch/torchvision 은 PyTorch cu124 인덱스로, onnxruntime 은 CPU판 제외(`override-dependencies`)로 고정 → `uv lock`/`uv sync` 가 GPU 빌드(`torch 2.6.0+cu124`·`torchvision 0.21.0+cu124`·`onnxruntime-gpu`)를 유지한다. **단 NVIDIA GPU + CUDA 12.4 단일 개인 PC 전제**(CPU/다른 CUDA 배포 시 깨질 수 있음 — 의도된 가정). 검증: `uv sync` 후 `torch.cuda.is_available()` / onnxruntime `CUDAExecutionProvider` 모두 True.

---

## ✅ 완료 (3차 처리, 2026-05-23) — 채팅 LLM 평가 + RAG 단순화 + 의존성 정리(A5)

Ollama 가 구동되어 채팅 LLM 후보를 실측 비교했다. 결론과 근거:

- **채팅 모델 = `qwen2.5-abliterate:7b` 확정.** 12GB VRAM + 앱이 GPU ~3.7GB 점유 → LLM 은 ~5GB 이하(≈7~8B Q4)라야 100% GPU 로 들어감.
  - 14b(9GB): 26% CPU 오프로드 + 콜드 로드 시 CUDA init 간헐 실패 → 부적합.
  - qwen3-vl:8b: thinking 을 끌 수 없어(`think:false`·`/no_think` 무시) 도구호출 ~37초 → 채팅·캡션 모두 부적합.
  - EXAONE 3.5 7.8B(한국어 네이티브): Ollama tools API 미지원(400) + tool 결과를 못 읽어 환각 → RAG 부적합.
- **RAG 단순화(refactor `3c914fc`):** 2차 LLM 답변 생성을 제거하고 코드 요약(`_summarize_results`)으로 대체. 사용자 목적은 opus 결과(카드)이고 묘사 문장은 불필요. 7B 의 중국어 드리프트 방어 로직 일체 제거. `_extract_meta` 가 min_rank/kind/playable 까지 코드 추출 → 응답 LLM 1회로 단축(워밍 후 1~2초).
- **포스터 캡션 기능 구현(`1d0f36b`):** VLM 이 포스터 → 한국어 장면설명/태그 → `posters.caption` → embed_text `[장면]` 블록으로 videos 임베딩에 합류(시각 검색 강화). 모델 = `gemma-4-abliterated:e4b` (gemma 계열은 `think:false` 가 먹혀 ~1초/장; qwen2.5-vl 은 비전 인코더가 느려 27~79초/장이라 탈락). 전체 배치 후 `embed` 재실행 필요. 상세 [`indexing-pipeline.md`](indexing-pipeline.md) §11.
- **개인문서 M5(향후):** `gemma4`(검열 거부 불요 영역 + 128K 멀티모달).
- **미사용 모델 정리:** `qwen2.5-vl-abliterated:7b`(캡션 느림) · `qwen3-vl-abliterated:8b`(thinking) · `qwen2.5-abliterate:14b`(채팅 7b 확정 + 설명문 제거로 불필요) 삭제. 캡션 경량 대안 `gemma-4-abliterated:e2b` 는 백업 유지.
- **A5 — scikit-learn 직접 의존성 제거:** 코드 어디서도 `sklearn` 직접 import 없음(얼굴 클러스터링은 numpy+torch 자작). 단 `insightface`·`sentence-transformers` 가 transitive 로 요구하므로 [`pyproject.toml`](../pyproject.toml) 의 **직접 선언만** 제거 → `uv lock` 재생성. 설치물 불변(scikit-learn 은 transitive 로 잔류), lock diff 는 flayai 의 requires-dist/dependencies 2줄만 정리, `uv lock --check` 통과(142 packages).

---

## 남은 작업

### D — 미구현 / 남은 마일스톤 (환경 필요)

실행·설치가 필요해 현재 PC(Ollama/Docker/uv 미설치)에서는 보류.

#### M5 — 개인 문서 RAG

- [ ] `packages/indexer/personal_docs.py` 미구현 (OneDrive docx/pdf/xlsx 파서, Phase 5).
- [ ] [`config.yaml`](../config.yaml) `data.personal_docs_roots` = `C:\Users\namjk\OneDrive` — 현재 사용자 환경과 경로/사용자명 확인 필요.
- [ ] OneDrive 인덱싱 + 영상 검색과의 라우터 격리 검증.

#### M6 — 운영 안정화

- [ ] `python eval/run_eval.py` 30케이스 정답률 ≥ 85% 검증 ([`eval/golden.yaml`](../eval/golden.yaml) 30건 작성됨).
- [ ] [`scripts/backup.ps1`](../scripts/backup.ps1) 복원 E2E 테스트.
- [ ] [`scripts/nightly_index.ps1`](../scripts/nightly_index.ps1) Windows Task Scheduler 등록.
- [ ] 7일 연속 야간 무인 인덱싱 성공 확인.

---

## C. 계획(AI_PLAN) 대비 의도적 변경 — 오류 아님 (참고)

[`AI_PLAN.md`](AI_PLAN.md) 는 "계획" 문서로, 구현 과정에서 의도적으로 바뀐 항목들. 상단에 "구현 기준은 docs/" 안내가 있으므로 그대로 둔다:

| 항목 | 계획 | 구현 |
|------|------|------|
| 이미지/얼굴 저장 | FAISS | Qdrant `posters_clip`/`faces` 컬렉션 |
| OCR | PaddleOCR | RapidOCR(onnxruntime) — DLL 충돌 회피 |
| 번역 | `opus-mt-ja-ko` | `facebook/nllb-200-distilled-600M` |
| LLM | 14b | 7b (VRAM/속도) |
| 오케스트레이션 | LlamaIndex | httpx 직접 + Ollama tool calling |
| 얼굴 클러스터링 | HDBSCAN | mutual-kNN + Union-Find (GPU) |

---

## 참고

- (갱신 2026-05-22) 이 PC 에 `uv`/Ollama/Docker 설치 확인됨 → 의존성 lock 재생성(A1/A3) 완료. D(M5/M6)는 실행·시간이 필요한 마일스톤이라 여전히 별도 진행.
- 1차 처리는 정적 편집만 수행. 2차 처리는 manifest 편집 + `uv lock` 재생성까지 수행했으나, venv 실설치(`uv sync`)·서비스 구동·인덱싱·테스트는 하지 않음.
