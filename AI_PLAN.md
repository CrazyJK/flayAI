# flayAI — 개인 LLM + RAG 구축 계획

내 PC에 LLM과 RAG를 구성해서 (1) 영상 컬렉션 검색·관리와 (2) 개인 문서 검색을 자연어로 수행한다.
챗봇 + 기존 웹앱(REST 호출)에서 같은 백엔드를 공유한다.

---

## 1. 환경 & 요구사항

### 1.1 PC 사양
- CPU: i7-13700K (3.40 GHz)
- RAM: 32GB (평소 12~15GB 사용)
- GPU: RTX 4070 Ti 12GB (평소 1~3GB)
- DISK: NVMe 2TB

### 1.2 사용 시나리오

**영상 관리**
- 배우 이름으로 출연작 검색
- 키워드/자연어로 제목·설명·태그 검색 ("회사 일상" 같은 자연어 포함)
- 사진 → 배우 매칭 → 출연작
- 연도/월 필터
- 포스터 OCR 검색
- JP/EN → KO 번역
- 사용 신호(play/rank/likes) 기반 추천 ("안 본 거", "좋아한 것 비슷한 거")
- **instance/archive 구분** 검색 (지금 볼 수 있는 것 vs 메타만 보존)

**개인 문서 관리** (Phase 5)
- OneDrive 폴더 전체. 일상 기록·재무 등.

### 1.3 선호 / 제약
- TS/JS 익숙. 그 외 자유 추천.
- **localhost 전용** 운영 (외부 노출 금지).
- 야간 장시간 인덱싱 OK.

---

## 2. 데이터 자료

### 2.1 영상 메타 (`K:\Crazy\Info\video.json`)
영상 단위 단일 JSON. `opus`(품번)가 PK.
```json
{
  "opus": "BLK-628",
  "play": 1,
  "rank": 4,
  "lastPlay": 1689515599000,
  "lastAccess": 1756209604125,
  "lastModified": 1756209604132,
  "comment": "",
  "title": "引っ越しの挨拶に行ったお隣は…",
  "desc": "引っ越しも終わって…",
  "tags": [
    { "id": 17, "name": "옆집여자", "group": null, "description": "이웃, 옆집", "lastModified": 0 }
  ],
  "likes": [ 1689517988754 ]
}
```
> title/desc는 대부분 일본어. tags 배열은 **id만 신뢰**, name/desc는 마스터(`tag.json`) 기준.

### 2.2 배우 (`K:\Crazy\Info\actress.json`)
```json
{
  "favorite": true,
  "name": "Aoi",
  "localName": "葵",
  "otherNames": ["Ono Yuko"],
  "birth": "1994年12月03日",
  "body": "92H - 58 - 88",
  "height": 160,
  "debut": 2014,
  "comment": "Ono Yuko 로 바뀜.",
  "lastModified": 1774533869840,
  "coverSize": 0
}
```
> ⚠ **`otherNames`** 는 개명 전/후 이름. **같은 인물**로 병합 필요. 충돌(birth/body/height 등) 시 **`lastModified`가 큰 쪽** 신뢰.

### 2.3 제작사 (`K:\Crazy\Info\studio.json`)
```json
{ "name": "Switch", "company": "", "homepage": null, "lastModified": 0 }
```

### 2.4 태그 (`K:\Crazy\Info\tag.json`, `tagGroup.json`)
```json
// tag
{ "id": 72, "name": "ASMR", "group": "screen", "description": "속삭, 음어, 보이스", "lastModified": 1732940214000 }
// tagGroup
{ "id": "situation", "name": "상황", "desc": "NTR", "lastModified": -1 }
```

### 2.5 히스토리 (`K:\Crazy\Info\history.csv`)
```csv
2026-05-14 23:27:13, SSIS-560, PLAY, [S1][SSIS-560][제목][Kawakita Saika][2022.10.25]
2026-05-14 23:31:30, SSIS-560, UPDATE, {"opus":"SSIS-560","play":8,...}
```

### 2.6 포스터 파일 (~20,000장)
- 확장자: jpg / png / webp
- 분산된 폴더에 저장 (`config.yaml`의 `poster_roots` 에 등록된 하위만 스캔)
- 파일명 패턴: `[studio][opus][title][actressList][release].ext`
- 샘플: `K:\Crazy\Storage\kira\[kira][BLK-628][이사 인사를 하러…][Kinoshita Himari, Mori Hinako][2023.07.18].jpg`
- **`actressList` (4번째 `[]`) 가 video↔actress 연결의 유일한 source of truth.** 비어 있으면 unknown, 콤마 구분으로 다수 가능.

### 2.7 ⭐ Instance vs Archive
포스터의 의미가 위치/동반 파일에 따라 다르다:

| 종류 | 조건 | 의미 |
|------|------|------|
| **instance** | 포스터와 **같은 stem(확장자 제외 동일)** 의 영상 파일(mp4/mkv/avi/wmv/mov/m4v 등)이 같은 폴더에 존재 | 재생 가능한 보유 영상 |
| **archive** | `K:\Crazy\Archive\` 하위에 위치 (영상 파일은 제거됨) | 메타·포스터만 보존, 재생 불가 |

→ 검색 응답에 `kind` (instance / archive) 표기, 필터 `kind=instance`/`archive`/둘 다 제공.

### 2.8 개인 문서 (Phase 5)
OneDrive 폴더 전체. 다양한 형식: txt, md, pdf, docx, xlsx, 이미지 등.

---

## 3. 아키텍처

```
┌──────────────────┐     HTTP/SSE      ┌──────────────────┐
│ 기존 웹앱 / 챗봇 │ ────────────────▶│ FastAPI          │
│ (Next.js 챗 UI)  │                   │ Gateway          │
└──────────────────┘                   └─────────┬────────┘
                                                 │
                                       ┌─────────▼─────────┐
                                       │ LlamaIndex Router │
                                       │ (LLM Tool Calling)│
                                       └─────────┬─────────┘
                  ┌──────────────┬───────────────┼──────────────┬──────────────┐
                  ▼              ▼               ▼              ▼              ▼
           ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
           │ Ollama   │   │ Qdrant   │   │ SQLite   │   │ FAISS    │   │ FAISS    │
           │ LLM      │   │ (text +  │   │ (meta +  │   │ posters  │   │ faces    │
           │          │   │  OCR)    │   │  FTS5)   │   │ (CLIP)   │   │ (Insight)│
           └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                  ▲              ▲              ▲              ▲              ▲
                  └──────────────┴── 인덱싱 파이프라인 ─┴──────────────┴──────────────┘
                                 (translate / OCR / embed / face)
```

**원칙**
- **로컬 우선**: 전 구성요소 PC 내부, 127.0.0.1 바인딩.
- **모듈 분리**: LLM / 임베딩 / 벡터 / 메타 / 이미지 독립.
- **하이브리드 검색**: SQL(정형) + Vector(의미) + CLIP(이미지) → LLM 종합.
- **모듈식 인덱서**: 각 단계 resumable, `state.json` 체크포인트.

---

## 4. 모델 & 기술 스택 (Final)

### 4.1 모델 (RTX 4070 Ti 12GB)

| 용도 | 모델 | VRAM | 비고 |
|------|------|------|------|
| LLM | `huihui_ai/qwen2.5-abliterate:14b` (Q4_K_M) | ~9GB | 한국어 우수, 거부 회로 제거됨 |
| LLM 대안 | `dolphin-2.9.4-llama3.1-8b` Q5 | ~6GB | 빠른 응답이 필요할 때 |
| 텍스트 임베딩 | `BAAI/bge-m3` | ~2GB | 한/일/영, dense + sparse |
| 이미지 임베딩 | `OpenCLIP ViT-L/14` (laion2b_s32b_b82k) | ~2GB | 인덱싱 시에만 GPU 점유 |
| 얼굴 검출/임베딩 | `InsightFace (buffalo_l)` | ~1GB | 포스터 → 얼굴 클러스터링 |
| OCR | `PaddleOCR` (한/영/일 동시) | ~1.5GB | 실패 시 `manga-ocr` 폴백 |
| 번역 JP→KO | `Helsinki-NLP/opus-mt-ja-ko` | CPU OK | 품질 미달 시 LLM 폴백 |

> NSFW: instruct 베이스 모델은 거부 빈도 높음 → `abliterated`(refusal direction을 weight에서 제거) 채택. M0에서 NSFW 짧은 프롬프트 1~2개로 실제 검증.

### 4.2 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| LLM 서버 | **Ollama** | 설치 간단, OpenAI 호환 API |
| 오케스트레이션 | **LlamaIndex** (Python) | RAG / tool calling / 멀티모달 |
| API | **FastAPI** (Python) | LlamaIndex 동일 런타임, OpenAPI 자동생성 |
| 챗봇 UI | **Next.js + TypeScript** | 익숙한 스택 |
| 벡터 DB | **Qdrant** (Docker) | 메타 필터 강력, 로컬 운영 쉬움 |
| 메타 DB | **SQLite** + FTS5(trigram) | 24MB 규모엔 충분, 한/일 부분매칭 |
| 이미지 검색 | **FAISS** (IndexFlatIP) | 20K 인메모리 충분 |
| 패키지 | **uv** (Python), **pnpm** (Node) | 빠른 dependency 관리 |
| 컨테이너 | **Docker Compose** | Qdrant 일괄 관리 |

> Python을 백엔드로: 임베딩/OCR/CLIP/InsightFace 생태계가 Python 중심. UI는 익숙한 TS.

---

## 5. 데이터 모델

### 5.1 SQLite 스키마 (`data/sqlite/flay.db`)

`opus`(품번)가 모든 테이블의 join key.

```sql
-- 영상
CREATE TABLE videos (
  opus           TEXT PRIMARY KEY,
  title_jp       TEXT,
  title_ko       TEXT,           -- JP→KO 사전 번역
  desc_jp        TEXT,
  desc_ko        TEXT,
  studio         TEXT,           -- 파일명 1번째 [] 또는 video.json
  release_date   TEXT,           -- 'YYYY-MM-DD'
  release_year   INTEGER,
  release_month  INTEGER,
  comment        TEXT,
  play           INTEGER DEFAULT 0,
  rank           INTEGER DEFAULT 0,
  last_play      INTEGER,
  last_access    INTEGER,
  last_modified  INTEGER,
  like_count     INTEGER DEFAULT 0,
  has_poster     INTEGER DEFAULT 0,
  kind           TEXT             -- 'instance' | 'archive' | NULL
);
CREATE INDEX idx_videos_year_month ON videos(release_year, release_month);
CREATE INDEX idx_videos_rank       ON videos(rank DESC, last_play DESC);
CREATE INDEX idx_videos_kind       ON videos(kind);

-- FTS5 (한국어/일본어 부분매칭, RRF 융합용)
CREATE VIRTUAL TABLE videos_fts USING fts5(
  opus UNINDEXED, title_jp, title_ko, desc_jp, desc_ko, comment,
  tokenize = 'trigram'
);

-- 배우 (canonical 단위; otherNames는 별도 alias 테이블로)
CREATE TABLE actresses (
  canonical_name TEXT PRIMARY KEY,   -- 표준 이름 (병합 후)
  display_name   TEXT,                -- UI 표시 (가장 최근 lastModified의 name)
  local_name     TEXT,                -- 한자/한글 표기
  favorite       INTEGER DEFAULT 0,
  birth          TEXT,
  body           TEXT,
  height         INTEGER,
  debut          INTEGER,
  comment        TEXT,
  last_modified  INTEGER,             -- 병합에 사용된 최신값
  cluster_id     INTEGER              -- InsightFace 매핑
);

-- 배우 별칭 (otherNames, localName, name 모두 포함 → canonical_name 으로)
CREATE TABLE actress_aliases (
  alias_norm     TEXT PRIMARY KEY,    -- normalize_actress(alias)
  alias_raw      TEXT,
  canonical_name TEXT NOT NULL REFERENCES actresses(canonical_name)
);
CREATE INDEX idx_alias_canonical ON actress_aliases(canonical_name);

-- 영상-배우 N:M (파일명 actressList 기반, alias 거쳐 canonical로 저장)
CREATE TABLE video_actresses (
  opus            TEXT,
  canonical_name  TEXT,
  PRIMARY KEY (opus, canonical_name)
);

-- 제작사
CREATE TABLE studios (
  name      TEXT PRIMARY KEY,
  company   TEXT,
  homepage  TEXT
);

-- 태그 / 그룹
CREATE TABLE tag_groups (
  id    TEXT PRIMARY KEY,
  name  TEXT,
  desc  TEXT
);
CREATE TABLE tags (
  id          INTEGER PRIMARY KEY,
  name        TEXT,
  group_id    TEXT,
  description TEXT
);
CREATE TABLE video_tags (
  opus    TEXT,
  tag_id  INTEGER,
  PRIMARY KEY (opus, tag_id)
);

-- 좋아요 시계열 (video.likes)
CREATE TABLE likes (
  opus  TEXT,
  ts    INTEGER,
  PRIMARY KEY (opus, ts)
);

-- 히스토리 (history.csv)
CREATE TABLE history (
  ts       INTEGER,
  opus     TEXT,
  action   TEXT,             -- PLAY / UPDATE / ...
  payload  TEXT,
  PRIMARY KEY (ts, opus, action)
);

-- 포스터 + instance/archive 판정
CREATE TABLE posters (
  opus       TEXT PRIMARY KEY,
  path       TEXT NOT NULL,
  ext        TEXT,
  size       INTEGER,
  mtime      INTEGER,
  ocr_text   TEXT,
  kind       TEXT,             -- 'instance' | 'archive'
  video_path TEXT              -- instance인 경우 동반 영상 파일 경로
);

-- 얼굴 클러스터 → 배우 매핑
CREATE TABLE face_clusters (
  cluster_id     INTEGER PRIMARY KEY,
  canonical_name TEXT,
  sample_count   INTEGER,
  confidence     REAL
);
CREATE TABLE poster_faces (
  poster_opus  TEXT,
  face_idx     INTEGER,
  cluster_id   INTEGER,
  bbox         TEXT,
  PRIMARY KEY (poster_opus, face_idx)
);

-- 번역 캐시
CREATE TABLE translations (
  hash      TEXT PRIMARY KEY,   -- sha1(text + model)
  src_lang  TEXT,
  tgt_lang  TEXT,
  src_text  TEXT,
  tgt_text  TEXT
);

-- 운영 로그
CREATE TABLE query_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER,
  endpoint    TEXT,
  query       TEXT,
  tool_calls  TEXT,
  latency_ms  INTEGER,
  result_n    INTEGER,
  user_rating INTEGER
);
```

### 5.2 Qdrant 컬렉션
| 컬렉션 | 벡터 | payload 핵심 필터 |
|--------|------|-------------------|
| `videos` | bge-m3 (1024d) | opus, year, month, canonical_actresses[], tag_ids[], studio, rank, play, like_count, last_play, kind |
| `poster_ocr` | bge-m3 | opus, kind |
| `personal_docs` | bge-m3 | path, mtime, mime |

### 5.3 FAISS
| 인덱스 | 차원 | 내용 |
|--------|------|------|
| `posters.index` (IndexFlatIP) | 768 (CLIP ViT-L) | id ↔ opus 맵 |
| `actor_faces.index` | 512 (InsightFace) | id ↔ (poster_opus, face_idx) |

### 5.4 배우 병합 로직 (otherNames)

```python
def build_actress_master(records: list[dict]) -> tuple[list[Actress], list[Alias]]:
    # 1. Union-Find: name + otherNames + localName 으로 그룹핑
    uf = UnionFind()
    for r in records:
        keys = [r["name"]] + r.get("otherNames", []) + ([r["localName"]] if r.get("localName") else [])
        keys = [normalize_actress(k) for k in keys if k]
        for k in keys[1:]:
            uf.union(keys[0], k)

    # 2. 각 그룹에 대해 canonical 결정 + 충돌 필드는 lastModified 큰 쪽 우선
    groups = uf.groups()
    out_actresses, out_aliases = [], []
    for group_keys in groups:
        members = [r for r in records if normalize_actress(r["name"]) in group_keys]
        latest = max(members, key=lambda r: r.get("lastModified", 0))
        canonical = normalize_actress(latest["name"])

        merged = Actress(
            canonical_name=canonical,
            display_name=latest["name"],
            local_name=latest.get("localName"),
            favorite=any(m.get("favorite") for m in members),
            birth=latest.get("birth"),
            body=latest.get("body"),
            height=latest.get("height"),
            debut=latest.get("debut") or min((m.get("debut") for m in members if m.get("debut")), default=None),
            comment=latest.get("comment"),
            last_modified=latest.get("lastModified", 0),
        )
        out_actresses.append(merged)
        for k in group_keys:
            out_aliases.append(Alias(alias_norm=k, alias_raw=k, canonical_name=canonical))
    return out_actresses, out_aliases

def normalize_actress(name: str) -> str:
    import unicodedata, re
    n = unicodedata.normalize("NFKC", name).strip().lower()
    return re.sub(r"\s+", " ", n)
```

병합 검증: actress.json 입력 N건 → canonical M건 (M ≤ N), `actress_aliases` 의 모든 alias는 정확히 1개 canonical에 매핑.

### 5.5 파일명 파서

```python
import re
PATTERN = re.compile(
    r'^\[(?P<studio>[^\]]+)\]'
    r'\[(?P<opus>[^\]]+)\]'
    r'\[(?P<title>.+)\]'                 # greedy
    r'\[(?P<actresses>[^\]]*)\]'
    r'\[(?P<release>\d{4}\.\d{2}\.\d{2})\]'
    r'\.(?P<ext>jpg|png|webp)$',
    re.IGNORECASE
)
# actresses: ',' split → trim → normalize → alias 테이블 lookup → canonical_name
# release:  '2023.07.18' → '2023-07-18'
# 매칭 실패 → unmatched_posters.log
```

### 5.6 Instance / Archive 판정

```python
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".webm"}
ARCHIVE_ROOT = Path("K:/Crazy/Archive").resolve()

def classify_poster(poster_path: Path) -> tuple[str, Path | None]:
    if ARCHIVE_ROOT in poster_path.resolve().parents:
        return "archive", None
    stem = poster_path.stem  # 확장자 제외 동일 이름
    for ext in VIDEO_EXTS:
        cand = poster_path.with_suffix(ext)
        if cand.exists():
            return "instance", cand
    return "instance", None  # 영상은 없지만 archive도 아님 → instance(미보유)로 분류, kind=instance
```

> 정책: archive 폴더 외부에서 영상 파일이 없어도 `kind="instance"`(보유 의도)로 두고, `video_path=NULL`로 표시. 검색 시 `playable=true` 옵션이면 `video_path IS NOT NULL` 추가.

---

## 6. 인덱싱 파이프라인

### 6.1 단계 (resumable)

```
[1] load_jsons      studio.json, actress.json (병합), tag*.json, video.json
                    → studios, actresses, actress_aliases, tag_groups, tags,
                      videos, video_tags, likes
[2] scan_posters    config.poster_roots 재귀 + 파일명 파싱
                    → posters (kind 판정 포함), video_actresses (canonical),
                      videos.has_poster=1, videos.kind 동기화
[3] history_csv     마지막 ts 이후만 append
[4] translate       JP→KO (opus-mt-ja-ko, translations 캐시)
                    → videos.title_ko, desc_ko, FTS 재구축
[5] embed_text      bge-m3 → Qdrant `videos`
                    문서 = "[제목 JP] {title_jp}\n[제목 KO] {title_ko}\n
                            [설명] {desc_ko}\n출연: {canonical_actresses}\n
                            태그: {tag_names + descriptions}\n
                            제작: {studio}\n발매: {YYYY-MM}\n
                            코멘트: {comment}\n종류: {kind}"
[6] ocr_posters     PaddleOCR → posters.ocr_text + Qdrant `poster_ocr`
[7] embed_clip      OpenCLIP ViT-L → FAISS posters.index
[8] extract_faces   InsightFace 검출/임베딩 → poster_faces
                    HDBSCAN 클러스터링 → face_clusters
                    자동 매핑: 클러스터 ↔ video_actresses 교차 → canonical_name
[9] personal_docs   (Phase 5) OneDrive 다중 파서 → Qdrant `personal_docs`
```

### 6.2 체크포인트 (`data/state.json`)
```json
{
  "schema_version": 1,
  "stages": {
    "load_jsons":    { "done": true,  "rows": 12345 },
    "scan_posters":  { "done": true,  "scanned": 19877, "matched": 19560, "unmatched": 317,
                       "instance": 18002, "archive": 1558 },
    "translate":     { "done": false, "cursor_opus": "SSIS-512", "completed": 8300 },
    "embed_text":    { "done": false, "completed": 0 },
    "ocr_posters":   { "done": false, "completed": 0 },
    "embed_clip":    { "done": false, "completed": 0 },
    "extract_faces": { "done": false, "completed": 0 },
    "history_csv":   { "last_ts": 1715712000000 }
  }
}
```
- 1000건마다 atomic write (tmp → rename)
- SIGINT 시 cursor 저장 후 종료

### 6.3 처리 시간 추정 (4070 Ti)

| 단계 | 처리량 | 20K건 예상 |
|------|--------|-----------|
| JSON ETL + actress 병합 | - | < 1분 |
| 포스터 스캔 + instance/archive 판정 | ~30K files/min | ~1분 |
| JP→KO 번역 (opus-mt) | ~50 docs/sec (CPU) | ~7분 |
| bge-m3 임베딩 | ~200 docs/sec (GPU) | ~2분 |
| PaddleOCR | ~3 imgs/sec (GPU) | **~2시간** |
| OpenCLIP ViT-L | ~30 imgs/sec (GPU) | ~12분 |
| InsightFace + HDBSCAN | ~10 imgs/sec | ~40분 |

**최초 풀 인덱싱**: 약 3시간 → 야간 1회.
**증분 (신규 100건)**: 5분 미만.

### 6.4 VRAM 동시성 관리
- 인덱싱 모드: `ollama stop ...` 으로 LLM unload → CLIP/OCR 안전
- 단계 직렬화: `embed_text → ocr → embed_clip → faces`
- 서빙 모드: LLM + bge-m3 만 상주, CLIP/InsightFace는 lazy + idle 60s 후 해제
- `/api/index/refresh`: LLM unload → 인덱싱 → reload

---

## 7. 검색 / 질의

### 7.1 라우팅 매핑

| 사용자 질문 | 처리 |
|-------------|------|
| "Aoi 출연작" | actress_aliases lookup → canonical → SQL JOIN |
| "葵 출연작" / "Ono Yuko 출연작" | 같은 canonical로 수렴 → 동일 결과 |
| "회사 일상 영상" | bge-m3 Qdrant top-30 + FTS5 top-30 → RRF → 랭킹 보정 → top-10 |
| "지금 볼 수 있는 \~" | 위 + payload `kind=instance AND video_path IS NOT NULL` 필터 |
| "옛날에 갖고 있던 \~" | payload `kind=archive` 필터 |
| 사진 업로드 → 영상 | InsightFace → FAISS faces → cluster_id → canonical_name → SQL |
| "어두운 분위기 포스터" | OpenCLIP 텍스트 임베딩 → FAISS posters |
| "포스터에 '学園'" | Qdrant `poster_ocr` 또는 SQLite `posters.ocr_text LIKE` |
| "2023년 7월" | `WHERE release_year=2023 AND release_month=7 ORDER BY rank DESC` |
| "좋아한 것 비슷한 것" | likes 최근 N개 → 각 Qdrant 유사도 합산 → 미시청 필터 |
| "안 본 추천" | `WHERE play=0 AND rank>=3` + 즐겨찾기 평균 임베딩 유사도 |

라우팅: **LLM tool calling** 1차, 실패 시 LlamaIndex `RouterQueryEngine` 백업.

### 7.2 랭킹 공식

```
final_score = 0.70 * semantic_sim                  # bge-m3 cosine
            + 0.15 * fts_score (BM25 normalized)
            + 0.10 * usage_boost                   # log(1+play) + 0.5*rank/5 + 0.3*log(1+like_count)
            + 0.05 * recency_boost                 # exp(-Δdays/180), last_play 기준
```
가중치는 `config.yaml` 에서 조정, 평가셋(§10.3)으로 튜닝.

### 7.3 LLM Tool Schema (LlamaIndex `FunctionTool`)

```python
search_videos(
    query: str,
    year: int | None = None,
    month: int | None = None,
    actress: str | None = None,         # alias 자동 정규화
    tag: str | None = None,
    kind: Literal["instance","archive","any"] = "any",
    playable: bool | None = None,        # video_path 존재 여부
    watched: bool | None = None,
    min_rank: int | None = None,
    limit: int = 10,
) -> list[VideoHit]

search_by_actress_face(image_b64: str, top_k: int = 5) -> list[ActressMatch]
search_by_poster_text(query: str, top_k: int = 20) -> list[PosterHit]    # CLIP
search_poster_ocr(query: str, top_k: int = 10) -> list[VideoHit]
similar_to(opus: str, exclude_watched: bool = True) -> list[VideoHit]
translate(text: str, target: Literal["ko","en","ja"] = "ko") -> str
stats(actress: str | None, tag: str | None, year: int | None) -> dict
```

모든 tool은 **read-only**. write는 별도 admin 라우트.

### 7.4 사전 번역 정책
- `opus-mt-ja-ko` 1차, 캐시 (sha1+model)
- 번역 길이가 원문의 30% 미만 또는 300% 초과 → LLM 폴백
- title은 통째로, desc는 문장 단위 분할 → 번역 → 결합

---

## 8. API & UI

### 8.1 REST 엔드포인트

```
POST /api/chat                  # 자유 질의 (라우터 + SSE 스트리밍)
POST /api/search/videos         # { query, filters }
POST /api/search/by-face        # multipart 이미지
POST /api/search/by-poster      # CLIP text/image → 포스터
POST /api/ocr                   # 단일 이미지 OCR
POST /api/translate             # { text, target }
GET  /api/videos/:opus
GET  /api/actresses/:canonical  # alias 정보 포함
GET  /static/posters/:opus      # 포스터 파일 서빙
POST /api/index/refresh         # 증분 재색인 (admin)
GET  /api/admin/stats           # 24h 사용 통계
GET  /api/face/clusters         # 미라벨 클러스터 목록
POST /api/face/label            # cluster_id → canonical_name 라벨링
```
OpenAPI 스펙은 `/docs` 자동 생성, 외부 웹앱이 그대로 호출.

### 8.2 챗봇 UI (Next.js, Phase 3)
- 채팅 페이지 (SSE 스트리밍, abort 가능)
- 검색 결과 카드: 포스터 썸네일 + 메타 + `kind` 뱃지(instance/archive) + 액션(좋아요, 비슷한 거)
- 얼굴 라벨링 페이지: 미매핑 클러스터 9-grid + 배우 후보 드롭다운
- 모바일 LAN 접근 차단 (127.0.0.1 only)

### 8.3 기존 웹앱 통합
- flayAI는 별도 REST 서비스. 기존 웹앱이 HTTP로 호출.
- CORS 화이트리스트: `http://127.0.0.1:3000` + 기존 웹앱 origin (config에 명시)
- SDK는 후순위 (필요 시 OpenAPI에서 자동 생성)

---

## 9. 보안 / 운영

### 9.1 보안 체크리스트
- [ ] FastAPI bind: `127.0.0.1` only. `0.0.0.0` 시 startup abort
- [ ] Qdrant Docker port: `127.0.0.1:6333:6333`
- [ ] Ollama: `OLLAMA_HOST=127.0.0.1:11434`
- [ ] CORS 화이트리스트 명시
- [ ] `/api/admin/*` localhost 헤더 검증
- [ ] LLM tool은 read-only, write는 admin 라우트
- [ ] 업로드 이미지: 10MB 제한, 확장자 화이트리스트
- [ ] K: 드라이브 미마운트 시 fail-fast
- [ ] 개인 문서 RAG는 별도 Qdrant 컬렉션 + 라우트 격리

### 9.2 백업 (`scripts/backup.ps1`)
```powershell
$ts  = Get-Date -Format "yyyyMMdd-HHmmss"
$dst = "K:\Backup\flayAI\$ts"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
sqlite3 data/sqlite/flay.db "VACUUM INTO '$dst/flay.db'"
curl -X POST http://127.0.0.1:6333/collections/videos/snapshots
curl -X POST http://127.0.0.1:6333/collections/poster_ocr/snapshots
curl -X POST http://127.0.0.1:6333/collections/personal_docs/snapshots
Copy-Item data/qdrant/snapshots/* "$dst/qdrant/" -Recurse
Copy-Item data/faiss/*.index "$dst/faiss/"
Copy-Item data/state.json,config.yaml "$dst/"
```
보존: 최근 7개 + 매주 1개 (rotation).

### 9.3 로깅 / 관측성
- `structlog` JSON → `logs/flayai.log` (rotate 100MB × 10)
- SQLite `query_log` 테이블에 질의/응답/지연/사용자 평가 기록
- `/api/admin/stats`: 24h 평균 latency, 인기 질의, 실패율

### 9.4 야간 인덱싱
- `scripts/nightly_index.ps1` → Windows Task Scheduler 등록
- 절차: LLM unload → translate → embed_text → (이미지 단계는 주 1회) → reload

---

## 10. 마일스톤 (M0 ~ M6)

각 마일스톤은 **산출물 + 수락 기준**. 미통과 시 다음 진행 금지.

### M0 — 환경 부트스트랩
**산출물**: `scripts/bootstrap.ps1`, `docker-compose.yml`, `pyproject.toml`, `config.yaml`
**수락**:
- `nvidia-smi` GPU 인식
- `docker compose up -d qdrant` → `curl http://127.0.0.1:6333/healthz` = 200
- `ollama pull huihui_ai/qwen2.5-abliterate:14b` 성공
- 검증 프롬프트 3종 (한국어 일반 / 일본어→한국어 번역 / 짧은 NSFW) 모두 응답, 거부 0
- bge-m3 인코딩 smoke test 성공

### M1 — 메타데이터 ETL
**산출물**:
- `packages/indexer/load_jsons.py` (배우 병합 포함)
- `packages/indexer/poster_parser.py`
- `packages/indexer/poster_scanner.py` (instance/archive 판정 포함)
- `packages/indexer/history.py`
- `tests/test_poster_parser.py`, `test_actress_merge.py`

**수락**:
- `flay-index load` → 모든 테이블 row count > 0, FK 위반 0
- 배우 병합 검증: `Aoi` ↔ `Ono Yuko` ↔ `葵` 가 동일 canonical로 묶임
- `flay-index scan` → 매칭율 ≥ 95%, instance/archive 카운트 출력
- `flay-index history` → last_ts == CSV 마지막 행 ts
- pytest 통과

### M2 — 번역 + 임베딩 + 검색 API (PoC)
**산출물**: `translate.py`, `embed_text.py`, `packages/rag/{retriever,ranker,router,tools}.py`, `apps/api/main.py` + routers
**수락**:
- 번역 100건 사람 검토 통과율 ≥ 80%
- 전체 임베딩 → Qdrant `videos` 점수 분포 정상 (top-1 cosine ≥ 0.5 비율 > 70%)
- `POST /api/chat` 다음 7개 시나리오 ≥ 6/7:
  1. "Kawakita Saika 출연작 5개"
  2. "Aoi 출연작" / "Ono Yuko 출연작" 동일 결과 확인
  3. "회사 배경의 일상 영상"
  4. "2023년 7월 발매작"
  5. "S1 제작사 평점 4 이상"
  6. "지금 볼 수 있는 회사 영상" (instance만)
  7. "최근 좋아요 누른 것 비슷한 거"
- p95 latency ≤ 3초 (스트리밍 첫 토큰)
- OpenAPI `/docs` 정상

### M3 — 챗봇 UI
**산출물**: `apps/web/` (Next.js + Tailwind), 채팅 + SSE + 결과 카드 (kind 뱃지 포함)
**수락**: M2 7개 시나리오를 UI에서 동작, abort 가능, LAN 차단 확인

### M4 — 이미지 검색 (CLIP + Face)
**산출물**: `embed_clip.py`, `faces.py`, `routers/face.py`, 얼굴 라벨링 페이지
**수락**:
- 포스터 임베딩 100%, FAISS top-1 self-search recall = 1.0
- 얼굴 클러스터 → 배우 자동 매핑 정확도 ≥ 80% (수동 50명 검증)
- 사진 1장 업로드 → 배우 top-5 응답 ≤ 2초

### M5 — OCR + 개인 문서 RAG
**산출물**:
- `ocr.py` (PaddleOCR 배치)
- `personal_docs.py` (OneDrive 파서 매트릭스)

| 확장자 | 파서 |
|--------|------|
| `.txt`, `.md` | 그대로 |
| `.pdf` | `pypdf` (텍스트) → 폴백 OCR (스캔본) |
| `.docx` | `python-docx` |
| `.xlsx` | `openpyxl` (시트별 텍스트화) |
| `.jpg/.png/.webp` | PaddleOCR |
| 그 외 | skip + 로그 |

**수락**:
- 20K 포스터 OCR 완료, 샘플 100건 정확도 ≥ 85%
- OneDrive 1만 건 인덱싱, 파서별 실패율 ≤ 5%
- "내 작년 12월 가계부" → 정답 문서 top-3
- 영상 검색에 개인 문서 미혼입 (라우터 격리 검증)

### M6 — 운영 안정화
**산출물**: `eval/golden.yaml`(30건) + `eval/run_eval.py`, `scripts/backup.ps1`, `scripts/nightly_index.ps1`, structlog + query_log, README
**수락**:
- 정답률 ≥ 85%
- 빈 폴더에 백업 복원 → 모든 검색 동작 (E2E 복구)
- 7일 연속 야간 인덱싱 무인 성공

---

## 11. 평가 / 리스크

### 11.1 평가셋 (`eval/golden.yaml`, 30건)

| 카테고리 | 건수 | 예 |
|----------|------|----|
| 배우 정확매칭 | 4 | "Ai Asakura 출연작 3개 이상" |
| 배우 별칭/개명 | 3 | "葵", "Ono Yuko" → 동일 결과 검증 |
| 키워드 한국어 | 4 | "회사 사무실 배경" |
| 키워드 일본어 | 2 | "学園もの" |
| 자연어 의미 | 4 | "비 오는 날 분위기" |
| 날짜 필터 | 3 | "2022년 10월" |
| 사용 신호 | 3 | "안 본 것 평점 높은 거" |
| instance/archive | 2 | "지금 볼 수 있는 ~", "옛날에 본 ~" |
| 포스터 OCR | 2 | 포스터 안 일본어 검색 |
| 얼굴 검색 | 3 | 알려진 배우 사진 → top-1 정답 |

케이스 형식:
```yaml
- id: actress-alias-001
  query: "Ono Yuko 출연작"
  expect:
    same_result_as: actress-alias-002   # "葵 출연작"
    min_results: 1
- id: kind-instance-001
  query: "지금 볼 수 있는 회사 영상"
  expect:
    all_must_have: { kind: instance, video_path_present: true }
```

### 11.2 리스크 레지스터

| 리스크 | 영향 | 대응 |
|--------|------|------|
| abliterated 한국어 품질 저하 | 응답 품질↓ | M0 검증, 미달 시 정상 Qwen + 메타 한정 라우팅 |
| FTS5 trigram 한글 부정확 | 키워드 recall↓ | bge-m3 sparse 폴백, RRF 가중치 조정 |
| OCR 일본어 정확도 낮음 | 포스터 검색 누락 | `manga-ocr` 폴백 |
| 얼굴 자동 매핑 오류 | 잘못된 결과 | 신뢰도 임계값 보수적, 수동 라벨링 UI |
| 배우 병합 오버머지 (동명이인) | 잘못된 그룹 | otherNames 명시된 경우만 union, 의심 케이스 검토 큐 |
| K: 드라이브 미마운트 | 부팅 실패 | settings에서 fail-fast |
| Qdrant 손상 | 검색 불가 | 일일 snapshot, FTS5만으로 degrade 모드 |
| OneDrive 동기화 잠김 | 파서 실패 | 재시도 + 24h 후 unmatched 검토 |
| 신규 영상 미번역 상태 | 한글 검색 미스 | nightly cursor 자동 번역 |
| LLM이 SQL injection성 호출 | 데이터 손상 | tool은 read-only, 파라미터 화이트리스트 |
| Instance 판정 시 동반 영상 누락 (다른 stem) | 잘못된 kind | 정책 확정: 현재는 stem 일치만. 추후 fuzzy 매칭 옵션 고려 |

---

## 12. 디렉토리 구조 (실제 생성 파일)

```
flayAI/
├── docker-compose.yml
├── config.yaml
├── pyproject.toml
├── .python-version                     # 3.11
├── README.md
├── apps/
│   ├── api/
│   │   ├── main.py                     # FastAPI entry, 127.0.0.1 강제
│   │   ├── deps.py                     # DI: db, qdrant, ollama
│   │   ├── settings.py                 # config.yaml 로더
│   │   ├── schemas.py                  # pydantic
│   │   └── routers/
│   │       ├── chat.py
│   │       ├── search.py
│   │       ├── face.py
│   │       ├── ocr.py
│   │       ├── translate.py
│   │       └── admin.py
│   └── web/                            # Next.js (M3에서 생성)
├── packages/
│   ├── indexer/
│   │   ├── cli.py                      # `flay-index <stage|all>`
│   │   ├── state.py                    # state.json atomic R/W
│   │   ├── load_jsons.py
│   │   ├── actress_merge.py            # otherNames 병합 로직
│   │   ├── poster_parser.py
│   │   ├── poster_scanner.py           # instance/archive 판정
│   │   ├── translate.py
│   │   ├── embed_text.py
│   │   ├── ocr.py
│   │   ├── embed_clip.py
│   │   ├── faces.py
│   │   ├── personal_docs.py            # Phase 5
│   │   └── history.py
│   └── rag/
│       ├── router.py                   # LLM tool routing
│       ├── tools.py                    # search_videos 등
│       ├── retriever.py                # Qdrant + FTS5 RRF
│       ├── ranker.py                   # 7.2 공식
│       └── prompts.py
├── data/
│   ├── sqlite/flay.db
│   ├── faiss/{posters,actor_faces}.index
│   ├── qdrant/                         # docker volume
│   └── state.json
├── eval/
│   ├── golden.yaml
│   └── run_eval.py
├── scripts/
│   ├── bootstrap.ps1
│   ├── backup.ps1
│   └── nightly_index.ps1
└── tests/
    ├── test_poster_parser.py
    ├── test_actress_merge.py
    ├── test_classify_kind.py
    ├── test_ranker.py
    └── test_router.py
```

---

## 13. config.yaml (예시)

```yaml
data:
  info_dir: "K:/Crazy/Info"
  poster_roots:
    - "K:/Crazy/Storage/kira"
    # 추가 폴더는 여기에
  archive_root: "K:/Crazy/Archive"
  poster_extensions: [jpg, png, webp]
  video_extensions:  [mp4, mkv, avi, wmv, mov, m4v, ts, webm]

models:
  llm:        "huihui_ai/qwen2.5-abliterate:14b"
  embedding:  "BAAI/bge-m3"
  clip:       "ViT-L-14/laion2b_s32b_b82k"
  ocr:        "paddleocr"
  translator: "Helsinki-NLP/opus-mt-ja-ko"
  face:       "buffalo_l"

ranking:
  semantic_weight: 0.70
  fts_weight:      0.15
  usage_weight:    0.10
  recency_weight:  0.05
  recency_half_life_days: 180

server:
  host:     "127.0.0.1"
  api_port: 8000
  web_port: 3000
  qdrant:   "http://127.0.0.1:6333"
  ollama:   "http://127.0.0.1:11434"
  cors_origins:
    - "http://127.0.0.1:3000"
    # 기존 웹앱 origin 추가
```

---

## 14. Day 1 즉시 실행

```powershell
cd c:\kamoru\Workspace\git\flayAI
git init
ni -ItemType Directory apps,packages,data,eval,scripts,tests -Force

# Python 환경
winget install --id=astral-sh.uv -e
uv init --python 3.11
uv add fastapi "uvicorn[standard]" llama-index-core llama-index-llms-ollama `
       llama-index-embeddings-huggingface llama-index-vector-stores-qdrant `
       qdrant-client sentence-transformers transformers torch `
       paddlepaddle-gpu paddleocr open_clip_torch insightface onnxruntime-gpu `
       hdbscan sqlite-utils structlog pydantic-settings pyyaml watchdog `
       python-docx openpyxl pypdf

# 인프라
docker compose up -d qdrant
ollama pull huihui_ai/qwen2.5-abliterate:14b

# 검증
ollama run huihui_ai/qwen2.5-abliterate:14b "한국어로 자기소개 한 줄"
curl http://127.0.0.1:6333/healthz
nvidia-smi

# config.yaml 채우기 (poster_roots 폴더 목록 확정)
notepad config.yaml
```

이 5단계가 통과하면 **M1 (메타데이터 ETL)** 코드 작성으로 진입한다.
