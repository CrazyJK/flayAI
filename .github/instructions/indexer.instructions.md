---
applyTo: "packages/indexer/**/*.py"
description: "인덱서 파이프라인 (ETL · 번역 · 임베딩 · 얼굴 · OCR) 규칙"
---

# 인덱서 지침

CLI 진입점: `python -m packages.indexer.cli <cmd>` (typer). 원본 `K:\Crazy\*` → SQLite + Qdrant 4 컬렉션.

## 파이프라인 단계

메타: `load → scan → history → fts` (= `all`).
AI: `translate → embed`(텍스트) · `embed-clip`(이미지) · `extract-faces → cluster-faces`(얼굴) · `ocr-posters`(OCR) · `sync-payload` · `cleanup`.

각 단계는 **증분(incremental)** 이 기본 — 이미 처리된 행은 자동 skip. 강제 재처리는 `--rebuild` / `--force`.
새 단계를 추가하면 `cli.py` 에 typer 커맨드를 등록하고, `apps/api/routers/admin.py` 의 `ALLOWED_JOBS` 와 관리자 페이지에도 반영할지 검토한다.

## 모델 (config.yaml `models`)

| 용도 | 모델 | 차원 / 비고 |
|------|------|-------------|
| 텍스트 임베딩 | BGE-M3 (`BAAI/bge-m3`) | 1024d, `videos`/`poster_ocr` |
| 이미지 임베딩 | OpenCLIP `ViT-L-14` (`laion2b_s32b_b82k`) | 768d, `posters_clip` |
| 얼굴 | InsightFace `buffalo_l` | 512d, `faces` |
| OCR | **RapidOCR** (`rapidocr_onnxruntime`) | CPU/ONNX. PaddleOCR DLL 지옥 회피 차원 |
| 번역 JP→KO | `facebook/nllb-200-distilled-600M` | `src_lang=jpn_Jpan`, `forced_bos_token_id`→`kor_Hang` |

> ⚠ `config.yaml.models.ocr_lang` 주석은 "PaddleOCR" 로 stale. 실제 OCR 은 RapidOCR. ([docs/TODO.md](../../docs/TODO.md))

## 규칙

- **임베딩 모델/Qdrant 클라이언트는 `embed_text.py` 의 `_embedder()` / `_qdrant()` 를 재사용**한다 (모듈 전역 lazy singleton). 모듈마다 새로 로드하면 VRAM 낭비.
- 포인트 ID 는 `embed_text.opus_to_id(opus)` (opus SHA1 앞 8바이트). 4개 컬렉션 공통이라 cross-reference 가능 — 직접 ID 를 만들지 말 것.
- 진행률은 `packages/indexer/state.py` 의 `update_stage(...)` 로 `data/state.json` 에 기록 (50건마다 등). 로그는 `logs/<job>.log`.
- 빈 OCR 결과도 `ocr_text=""` 로 저장해 재시도를 막는다 (`force` 로만 재실행).
- 새 Qdrant 컬렉션은 `ensure_collection` 패턴(존재 시 skip + payload index 생성)을 따른다.
- GPU 12GB 한정: LLM·CLIP·InsightFace 동시 로드 금지. 야간 스크립트가 단계 사이 unload 를 조정.

## 배우 별칭 / 파일명

- 배우는 `actress_merge.normalize_actress()` 로 정규화 후 `actress_aliases` → `canonical_name` 으로 수렴 (`Alice`/`Alice S.`/`앨리스` 동일 인물).
- 포스터 파일명 `[studio][opus][title][actressList][release].ext` 는 `poster_parser.py` 가 파싱. 4번째 `[]`(actressList) 가 video↔actress 연결의 source of truth.
- `kind` 판정: `K:\Crazy\Archive\` 하위 → `archive`, 그 외 → `instance`(영상 동반 시 `video_path` 채움).

## 얼굴 클러스터링 주의

`cluster_faces.py` 는 이름과 달리 **HDBSCAN 이 아니라** mutual-kNN + Union-Find(GPU) 커스텀 구현이다. config 의 `hdbscan_*` 파라미터명·`cli` docstring 의 "HDBSCAN" 표현은 레거시 명칭. ([docs/TODO.md](../../docs/TODO.md))
