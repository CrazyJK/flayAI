# Indexing Pipeline — 원본 데이터 → 검색 가능한 인덱스

> 모든 단계는 `python -m packages.indexer.cli <command>` 로 실행합니다.
> 야간 자동 실행은 [`scripts/nightly_index.ps1`](../scripts/nightly_index.ps1).

## 전체 흐름

```
                K:\Crazy\Info\video.json          K:\Crazy\Storage\**.jpg
                K:\Crazy\Info\history.csv         K:\Crazy\Archive\**.jpg
                         │                                   │
                  flay-index load                    flay-index scan
                         ▼                                   ▼
                ┌─────────────────────────────────────────────────┐
                │  SQLite: videos, actresses, posters, ...        │
                └─────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬────────────────┬────────────────┐
        ▼                ▼                ▼                ▼                ▼
   translate         embed (text)    embed-clip      extract-faces      ocr-posters
   (JP→KO, NLLB)     BGE-M3 → Q      CLIP → Q        InsightFace → Q    RapidOCR → Q
        │                │                │                │                │
        └─→ title_ko     └─→ videos       └─→ posters_clip│                └─→ poster_ocr
            desc_ko          (1024d)          (768d)      ▼                    (1024d)
                                                    cluster-faces
                                                    (NN + Union-Find, GPU)
                                                          │
                                                          ▼
                                                    face_clusters
                                                    (자동 라벨링)
```

각 단계는 **증분(incremental)** 이 기본. 이미 처리된 행은 건너뜀.
`--rebuild` / `--force` 로 강제 재처리 가능.

## 단계별 상세

### 1. `load` — JSON 로드 (M1)

- 입력: `K:\Crazy\Info\video.json`, `K:\Crazy\Info\history.csv`
- 출력 테이블: `videos`, `actresses`, `actress_aliases`, `video_actresses`, `studios`, `tags`, `video_tags`, `likes`, `history`
- 핵심 로직: **배우 별칭 병합**.
  `Alice`, `Alice S.`, `앨리스` 같은 표기를 하나의 `canonical_name` 으로 합치고 별칭 테이블에 풀어둘
  (`packages/indexer/actress_merge.py`).

### 2. `scan` — 포스터 스캔 (M1)

- 입력: `K:\Crazy\Storage`, `K:\Crazy\Archive`, ...
- 출력: `posters(opus, path, video_path, kind)` 행
- `kind` 판정:
  - `K:\Crazy\Archive\...` 하위 → `archive` (메타만 보존, 영상 파일 없음)
  - 그 외 + 같은 폴더에 영상 파일이 있으면 → `instance` (지금 볼 수 있음)
- 파일명 `[Studio][OPUS][제목][배우][날짜].jpg` 패턴을 `poster_parser.py` 가 파싱.

### 3. `history` — 시청 기록 (M1)

- `history.csv` → `history` 테이블. last_play 갱신.

### 4. `fts` — FTS5 인덱스 (M1)

- 가상 테이블 `videos_fts` (title_jp + title_ko + desc_ko + studio + actresses + tags).
- 사용처: 키워드 매칭 (BM25). 의미 검색만으론 약한 정확한 이름 매칭에 강함.

### 5. `translate` — JP → KO 번역 (M2)

- 모델: `facebook/nllb-200-distilled-600M` (`jpn_Jpan` → `kor_Hang`)
- 길이 비율 필터 (0.30 ~ 3.00) 벗어나면 LLM 폴백.
- 결과: `videos.title_ko`, `videos.desc_ko`. 결과 사본은 `translations` 테이블에 캐싱.

### 6. `embed` — 영상 텍스트 임베딩 (M2)

- 모델: BGE-M3 (Sentence Transformers, 1024d, multilingual)
- 입력 문서: 영상 1개당 "title_jp + title_ko + desc_ko + studio + 배우목록 + 태그" 합본 텍스트.
- 출력: Qdrant `videos` 컬렉션. payload 에 opus, kind, year, studio, canonical_actresses 등 메타 포함 (필터링용).

### 7. `embed-clip` — 포스터 이미지 임베딩 (M4a)

- 모델: OpenCLIP `ViT-L-14` (`laion2b_s32b_b82k`, 768d)
- 입력: `posters.path` 의 모든 이미지.
- 출력: Qdrant `posters_clip`. 텍스트 ↔ 이미지 cross-modal 검색 가능 (CLIP 의 핵심).
- 성능: 20,334장 / 685초 / GPU.

### 8. `extract-faces` — 얼굴 추출 (M4b)

- 모델: InsightFace `buffalo_l` (RetinaFace + ArcFace, 512d)
- 입력: 포스터 이미지.
- 출력:
  - SQLite `poster_faces(id, opus, bbox, embedding_blob, cluster_id)`
  - Qdrant `faces` 컬렉션 — 개별 얼굴 단위.
- 성능: 20,305 포스터 → 208,215 얼굴 / 79분.

### 9. `cluster-faces` — 얼굴 클러스터링 (M4b)

이 프로젝트에서 가장 까다로운 단계.

- 목표: 비슷한 얼굴 임베딩을 그룹으로 묶고, 그 그룹에 배우 이름을 자동 부여.
- 알고리즘 (HDBSCAN 대체, `packages/indexer/cluster_faces.py`):
  1. 모든 얼굴 임베딩(208K) 을 fp16 텐서로 GPU 에 올림.
  2. 블록 단위(4096) 로 `X @ X.T` 코사인 유사도 계산.
  3. 각 행에서 top-K(16) 이웃 추출.
  4. **상호 kNN (mutual-kNN)** 필터: i 가 j 의 top-K 에 있고 **동시에** j 가 i 의 top-K 에 있을 때만 엣지로 인정. 거대 sink 클러스터 방지.
  5. 유사도 ≥ 0.6 인 엣지를 Union-Find 로 합치기.
  6. 컴포넌트 크기 ≥ `min_cluster_size` 만 클러스터로 유지.
- 라벨링: 클러스터 내 얼굴들의 opus 중 "단일 배우 영상" 다수결 → 신뢰도 ≥ 임계값이면 자동 부여.
- 결과 (현재): 2834 클러스터, 1834개 자동 라벨 (64.7%), 77초.

### 10. `ocr-posters` — 포스터 OCR (M5a) **← 현재 진행 중**

- 모델: RapidOCR (PP-OCR ONNX, CPU). PaddleOCR 의존성 지옥 회피 차원에서 채택.
- 출력:
  - SQLite `posters.ocr_text` (실패는 빈 문자열로 저장 → 재시도 방지)
  - Qdrant `poster_ocr` (BGE-M3 임베딩)
- 성능: 약 0.7 it/s (CPU) → 20K 포스터 약 8시간. 야간/백그라운드용.

## 진행 추적

모든 잡은 `data/state.json` 의 `stage` 항목에 진행률을 기록 (`packages/indexer/state.py`):

```json
{
  "ocr_posters": { "total": 20324, "processed": 250, "ts": "..." }
}
```

로그는 `logs/<job>.log` 에 50건마다 한 줄.

## CLI 명령 요약

```powershell
# 전체 순차 (load → scan → history → fts)
python -m packages.indexer.cli all

# 단계별
python -m packages.indexer.cli load
python -m packages.indexer.cli scan
python -m packages.indexer.cli translate
python -m packages.indexer.cli embed
python -m packages.indexer.cli embed-clip
python -m packages.indexer.cli extract-faces
python -m packages.indexer.cli cluster-faces
python -m packages.indexer.cli ocr-posters

# 옵션 공통
#   -n / --limit N    처음 N건만
#   --rebuild         이미 처리한 것도 다시
#   -v                상세 로그
```
