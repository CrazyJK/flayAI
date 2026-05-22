# TODO — 문서·구현 동기화 및 후속 작업

> 2026-05-22 작성, 같은 날 1차 처리. README/`docs/`/`.github` 지침과 실제 코드·설정을 정적 검토(코드 실행·설치 없이)하여 도출한 불일치와 후속 작업 목록.
> 우선순위 표기: 🔴 기능/구성 영향 · 🟡 문서 정확도 · ⚪ 정리/참고.

검토에 쓸 점검 절차는 [`.github/prompts/docs-sync-check.prompt.md`](../.github/prompts/docs-sync-check.prompt.md) 로 재사용 가능.

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

> ⚠️ **venv 실설치(`uv sync`)는 미수행**: `.venv` 에는 아직 구 패키지가 남아 있다. 실제 정리는 환경에서 `uv sync` 실행(실행 중 Python/torch 프로세스 종료 후 — DLL 잠금 주의).

---

## 남은 작업

### ⚪ A5. scikit-learn 미사용 의심 (확인 필요)

- `packages/**`·`apps/**` 어디서도 `sklearn` import 없음. 얼굴 클러스터링은 numpy+torch 로 직접 구현([`cluster_faces.py`](../packages/indexer/cluster_faces.py)).
- A3 범위(LlamaIndex/FAISS/HDBSCAN)에 명시되지 않아 이번엔 제거하지 않음. 정말 미사용이면 `pyproject.toml` 에서 함께 제거 후 `uv lock` 가능.

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
