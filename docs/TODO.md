# TODO — 문서·구현 동기화 및 후속 작업

> 2026-05-22 기준. README/`docs/`/`.github` 지침과 실제 코드·설정을 정적 검토(코드 실행·설치 없이)하여 도출한 불일치와 후속 작업 목록.
> 우선순위 표기: 🔴 기능/구성 영향 · 🟡 문서 정확도 · ⚪ 정리/참고.

검토에 쓸 점검 절차는 [`.github/prompts/docs-sync-check.prompt.md`](../.github/prompts/docs-sync-check.prompt.md) 로 재사용 가능.

---

## A. 코드 / 설정 불일치 (수정 권장)

### 🔴 A1. OCR 의존성 미선언 + 미사용 PaddleOCR 잔존

- 런타임은 `rapidocr_onnxruntime` 사용 ([`packages/indexer/ocr.py`](../packages/indexer/ocr.py)) — 그러나 [`pyproject.toml`](../pyproject.toml)/`uv.lock` 에 **미선언**.
- 반대로 미사용 `paddleocr` · `paddlepaddle-gpu` 가 의존성에 남아있음.
- [`config.yaml`](../config.yaml) `models.ocr_lang` 주석("PaddleOCR 언어")도 stale.
- **조치**: `rapidocr-onnxruntime` 를 `pyproject.toml` 에 추가, paddle 계열 제거 검토, ocr_lang 주석 수정(또는 키 제거).

### 🔴 A2. `pyproject.toml` 스크립트 진입점 깨짐

- `[project.scripts]` 의 `flay-api = "apps.api.main:start"` — 그러나 [`apps/api/main.py`](../apps/api/main.py) 에는 `start` 가 없고 `main()` 만 있음.
- **조치**: `flay-api = "apps.api.main:main"` 으로 수정. (`flay-index = "packages.indexer.cli:app"` 는 정상)

### 🟡 A3. 미사용 의존성 — LlamaIndex / FAISS / HDBSCAN

런타임 코드에서 import 되지 않음(`packages/**` + `apps/api/main.py` 확인):

- `llama-index-core`, `llama-index-llms-ollama`, `llama-index-embeddings-huggingface`, `llama-index-vector-stores-qdrant` — RAG 라우터는 `httpx` 로 Ollama tool calling 을 직접 구현 ([`packages/rag/router.py`](../packages/rag/router.py)). LlamaIndex 미사용.
- `faiss-cpu` — 이미지/얼굴은 Qdrant `posters_clip`/`faces` 컬렉션 사용. FAISS 미사용. [`config.yaml`](../config.yaml) 의 `data.faiss_poster`/`faiss_faces` 경로도 사용처 없음.
- `hdbscan` — [`packages/indexer/cluster_faces.py`](../packages/indexer/cluster_faces.py) 는 mutual-kNN + Union-Find 커스텀 구현. HDBSCAN 미사용.
- **조치**: 향후 계획(LlamaIndex 도입 등)이 없다면 의존성 정리. 설치 용량/시간 절감.

### ⚪ A4. "HDBSCAN" 레거시 명칭 정리

- 실제 클러스터링은 mutual-kNN + Union-Find(GPU). 그러나 `config.yaml` 파라미터명 `hdbscan_min_cluster_size`/`hdbscan_min_samples`, [`cli.py`](../packages/indexer/cli.py) docstring·[`docs/admin.md`](admin.md) 의 "HDBSCAN" 표현이 남아있음.
- **조치**: 명칭 통일 또는 "HDBSCAN 대체 구현" 주석 보강 ([`indexing-pipeline.md`](indexing-pipeline.md) 는 이미 정확히 설명).

---

## B. 문서 문구 불일치 (기존 docs/*.md — 본 작업에서 미수정)

> Q2 결정에 따라 기존 docs 본문은 건드리지 않고 목록만 정리. 반영 시 아래대로.

### 🟡 B1. LLM 모델 7b ↔ 14b

실제 [`config.yaml`](../config.yaml) `models.llm = huihui_ai/qwen2.5-abliterate:7b` (코드 주석도 7B 가정). 다음이 14b/"14B" 표기:

- [`architecture.md`](architecture.md) — "메인 모델 :14b"
- [`overview.md`](overview.md) — "Qwen2.5 14B"
- [`README.md`](README.md) (docs) — "Qwen2.5 14B"
- [`dev-guide.md`](dev-guide.md) — `ollama pull ...:14b`

> 정상: 루트 [`README.md`](../README.md), [`copilot-instructions.md`](../.github/copilot-instructions.md), [`admin.md`](admin.md).

### 🟡 B2. Python 3.12 ↔ 3.11

실제 [`.python-version`](../.python-version) = `3.11`, [`pyproject.toml`](../pyproject.toml) `requires-python = ">=3.11"`. 다음이 "Python 3.12" 표기: 루트 [`README.md`](../README.md), [`overview.md`](overview.md), [`README.md`](README.md)(docs), [`dev-guide.md`](dev-guide.md).

### 🟡 B3. "localhost 전용" ↔ `ai.kamoru.jk` + HTTPS

실제: 호스트 `ai.kamoru.jk`(hosts 매핑) + 자체 서명 TLS(`.cert/kamoru.jk.{key,pem}`)로 **HTTPS** 서빙 ([`config.yaml`](../config.yaml) `server`, [`apps/api/main.py`](../apps/api/main.py), [`apps/web/server.js`](../apps/web/server.js), [`bin/prod.bat`](../bin/prod.bat)). 호스트 화이트리스트는 `127.0.0.1`/`localhost`/`::1`/`ai.kamoru.jk`.

- [`overview.md`](overview.md)·[`architecture.md`](architecture.md)·[`api-reference.md`](api-reference.md)·[`dev-guide.md`](dev-guide.md) 의 "127.0.0.1 only" 단정은 부분적 — HTTPS/도메인/`prod.bat`/`server.js`/`.cert` 설명 보강 필요. (admin.md 만 ai.kamoru.jk 반영)

### 🟡 B4. 깨진 `AI_PLAN.md` 링크

실제 위치 [`docs/AI_PLAN.md`](AI_PLAN.md). 다음 링크가 루트를 가리켜 깨짐:

- 루트 [`README.md`](../README.md): `AI_PLAN.md` (2곳, line 30·79)
- [`README.md`](README.md)(docs): `../AI_PLAN.md` (line 14)
- **조치**: `docs/AI_PLAN.md` 로 수정. (copilot-instructions.md 는 정상)

### ⚪ B5. stale 절대 경로 (dev-guide.md)

[`dev-guide.md`](dev-guide.md) 의 `cd C:\kamoru\Workspace\git\flayAI` 및 schtasks 경로 → 실제 `C:\Handyground\Workspace\git\flayAI`.

### ⚪ B6. docs 인덱스/상태 누락

- [`README.md`](README.md)(docs) 문서 목록 표에 [`admin.md`](admin.md) 누락.
- [`indexing-pipeline.md`](indexing-pipeline.md) 의 ocr-posters "← 현재 진행 중" 표기 ↔ [`AI_PLAN.md`](AI_PLAN.md) "남은 작업"의 `ocr_posters` ✅ 완성 표기가 불일치 → 상태 갱신.
- [`cli.py`](../packages/indexer/cli.py) 모듈 docstring 이 일부 커맨드(translate/embed/embed-clip/extract-faces/cluster-faces/ocr-posters/sync-payload/cleanup) 누락.

---

## C. 계획(AI_PLAN) 대비 의도적 변경 — 오류 아님 (참고)

[`AI_PLAN.md`](AI_PLAN.md) 는 "계획" 문서로, 구현 과정에서 의도적으로 바뀐 항목들. 상단에 "구현 기준은 docs/" 안내가 이미 있으므로 그대로 두되 인지할 것:

| 항목 | 계획 | 구현 |
|------|------|------|
| 이미지/얼굴 저장 | FAISS | Qdrant `posters_clip`/`faces` 컬렉션 |
| OCR | PaddleOCR | RapidOCR(onnxruntime) — DLL 충돌 회피 |
| 번역 | `opus-mt-ja-ko` | `facebook/nllb-200-distilled-600M` |
| LLM | 14b | 7b (VRAM/속도) |
| 오케스트레이션 | LlamaIndex | httpx 직접 + Ollama tool calling |
| 얼굴 클러스터링 | HDBSCAN | mutual-kNN + Union-Find (GPU) |

---

## D. 미구현 / 남은 마일스톤 (AI_PLAN §남은 작업)

### M5 — 개인 문서 RAG

- [ ] `packages/indexer/personal_docs.py` 미구현 (OneDrive docx/pdf/xlsx 파서 매트릭스, Phase 5).
- [ ] [`config.yaml`](../config.yaml) `data.personal_docs_roots` = `C:\Users\namjk\OneDrive` — 현재 사용자 환경과 경로/사용자명 확인 필요.
- [ ] OneDrive 인덱싱 + 영상 검색과의 라우터 격리 검증.

### M6 — 운영 안정화

- [ ] `python eval/run_eval.py` 30케이스 정답률 ≥ 85% 검증 ([`eval/golden.yaml`](../eval/golden.yaml) 30건 작성됨).
- [ ] [`scripts/backup.ps1`](../scripts/backup.ps1) 복원 E2E 테스트.
- [ ] [`scripts/nightly_index.ps1`](../scripts/nightly_index.ps1) Windows Task Scheduler 등록.
- [ ] 7일 연속 야간 무인 인덱싱 성공 확인.

---

## 참고

- 이 PC 에는 Ollama/Docker 미설치 상태일 수 있음 — 위 항목 검증·수정 시 구동/설치가 필요한 작업(eval, 백업 복원, 인덱싱)은 환경 구성 후 진행.
- 본 검토는 정적 분석만 수행했으며 실제 실행/테스트는 하지 않음.
