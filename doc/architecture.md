# Architecture — 구성 요소

## 컴포넌트 다이어그램

```
 ┌──────────────────────┐
 │  Next.js 16 (web)    │  포트 3000
 │  - 채팅 / 이미지 / 얼굴 / 라벨링 페이지
 │  - SSE 로 /api/chat 구독
 └──────────┬───────────┘
            │ HTTP (CORS: localhost 만)
 ┌──────────▼───────────┐
 │  FastAPI (api)       │  포트 8000
 │  - apps/api/main.py  │
 │  - routers/image.py  │  CLIP, 얼굴 검색, 라벨링
 │  - routers/ocr.py    │  포스터 OCR 검색
 └────┬─────┬─────┬─────┘
      │     │     │
      │     │     └─► Ollama  127.0.0.1:11434  (LLM)
      │     │
      │     └─► Qdrant  127.0.0.1:6333  (벡터 DB)
      │
      └─► SQLite  data/sqlite/flay.db  (메타 + FTS5)

 ┌──────────────────────┐
 │  Indexer (CLI)       │  배치 작업 (인덱싱·임베딩·번역·클러스터링)
 │  packages/indexer/   │  python -m packages.indexer.cli <cmd>
 └──────────────────────┘
```

웹 개발자 관점에서 비교:

| 역할 | 웹 스택에서 비유 |
|------|------------------|
| FastAPI | Express / Hono 같은 HTTP 서버 |
| Next.js | (그대로) |
| Qdrant | Elasticsearch / Pinecone 의 벡터 검색 전담 |
| SQLite | Postgres/MySQL 대신 단일 파일 RDB. **FTS5** 가 살아있음 (BM25 키워드 검색) |
| Ollama | OpenAI API 의 로컬 버전. `/api/chat` 호환 |
| Indexer | "마이그레이션 + 시드" 보다는 "ETL 잡" 에 가깝다. 데이터를 검색 가능하게 정규화/임베딩 |

## 저장소 4종

### 1. SQLite — `data/sqlite/flay.db`

진실의 원천(source of truth). 모든 메타데이터.

주요 테이블 (`packages/indexer/db.py` 참조):

| 테이블 | 책임 |
|--------|------|
| `videos` | opus(PK), title_jp, title_ko, desc_ko, studio, release_date, kind(instance/archive), play, rank, like_count, last_play |
| `actresses` | canonical_name(PK) — 정규화된 배우 이름 |
| `actress_aliases` | alias_norm → canonical_name 매핑. "앨리스" / "Alice" / "Alice S." 가 같은 사람을 가리키게 |
| `video_actresses` | M:N 조인 |
| `studios`, `tags`, `video_tags`, `likes`, `history` | 기타 메타 |
| `posters` | opus 별 포스터 경로. ocr_text 컬럼은 M5 에서 채워짐 |
| `poster_faces` | 포스터에서 추출한 얼굴 박스 + cluster_id |
| `face_clusters` | cluster_id → 자동 라벨된 배우 |
| `videos_fts` | FTS5 가상 테이블. 한국어/일본어 키워드 BM25 검색 |

### 2. Qdrant — 4 컬렉션

벡터 검색. Qdrant 는 Docker 컨테이너로 띄움 (`docker-compose.yml`).

| 컬렉션 | 차원 | 내용 | 임베딩 모델 |
|--------|------|------|-------------|
| `videos` | 1024 | 영상별 "제목 + 설명 + 배우 + 태그" 합본 텍스트 | BGE-M3 |
| `posters_clip` | 768 | 포스터 이미지 자체 | OpenCLIP ViT-L/14 |
| `faces` | 512 | 포스터에서 추출된 개별 얼굴 | InsightFace buffalo_l |
| `poster_ocr` | 1024 | 포스터에서 OCR 한 텍스트 | BGE-M3 |

모든 포인트의 **ID 는 opus 의 SHA1 첫 8 바이트(uint63)** — 모든 컬렉션에서 같은 영상이면 같은 ID.
얼굴/포스터/OCR 를 opus 단위로 cross-reference 하기 위한 트릭.

### 3. Ollama — 모델 서버

`http://127.0.0.1:11434`. OpenAI 와 비슷한 `/api/chat` 호환 엔드포인트.

- **메인 모델**: `huihui_ai/qwen2.5-abliterate:14b` — 한국어/도구 호출 지원 양호
- 14B 모델이 GPU 7~9GB 사용. 추론 중에만 로드.

### 4. 모델 캐시 — `~/.cache/huggingface`

BGE-M3 / OpenCLIP / InsightFace / RapidOCR 모델 파일. 첫 실행 시 자동 다운로드.

## 디렉토리 레이아웃 (실제)

```
flayAI/
├── apps/
│   ├── api/                     ← FastAPI
│   │   ├── main.py              ← 채팅·검색·관리 엔드포인트
│   │   └── routers/
│   │       ├── image.py         ← CLIP·얼굴 검색·라벨링
│   │       └── ocr.py           ← 포스터 OCR 검색
│   └── web/                     ← Next.js (별도 README)
├── packages/
│   ├── indexer/                 ← ETL & 임베딩 CLI
│   │   ├── cli.py               ← typer 진입점
│   │   ├── load_jsons.py        ← K:\ 의 JSON → SQLite
│   │   ├── poster_scanner.py    ← 포스터 파일 스캔 → posters 테이블
│   │   ├── translate.py         ← JP → KO 번역 (NLLB-200)
│   │   ├── embed_text.py        ← BGE-M3 → Qdrant videos
│   │   ├── embed_clip.py        ← CLIP → posters_clip
│   │   ├── faces.py             ← InsightFace → poster_faces + faces
│   │   ├── cluster_faces.py     ← 얼굴 NN+UnionFind 클러스터링 (GPU)
│   │   ├── ocr.py               ← RapidOCR → posters.ocr_text + poster_ocr
│   │   ├── actress_merge.py     ← 별칭 정규화
│   │   └── db.py                ← SQLite 스키마
│   ├── rag/                     ← 검색 + LLM 라우팅
│   │   ├── router.py            ← Ollama tool calling 흐름
│   │   ├── tools.py             ← LLM 이 호출하는 5종 도구
│   │   ├── retriever.py         ← 하이브리드 검색 (FTS + 벡터)
│   │   └── ranker.py            ← RRF + 가중치 재정렬
│   └── settings.py              ← config.yaml 로더
├── config.yaml                  ← 단일 설정 (경로·모델·가중치)
├── docker-compose.yml           ← Qdrant 컨테이너
├── scripts/                     ← bootstrap·backup·nightly·진단
├── eval/                        ← golden.yaml + run_eval.py
├── tests/                       ← pytest
└── doc/                         ← 이 폴더
```

## 데이터가 사는 곳

| 데이터 | 위치 | 백업 대상? |
|--------|------|------------|
| 원본 영상 JSON, 포스터 | `K:\Crazy\*` | (원본이므로 별도) |
| SQLite | `data/sqlite/flay.db` | ✓ `scripts/backup.ps1` |
| Qdrant | `data/qdrant/` (도커 볼륨) | ✓ snapshot API |
| 모델 캐시 | `~/.cache/huggingface` | ✗ 재다운로드 가능 |
| 인덱싱 진행 cursor | `data/state.json` | ✓ |
| 로그 | `logs/*.log` | ✗ |
