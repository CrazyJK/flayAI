# 관리자 모니터링 페이지

flayAI 시스템 상태를 한눈에 확인하고 인덱서 배치 작업을 시작할 수 있는 관리자 페이지.

## 접근 방법

- URL: `https://ai.kamoru.jk:3000/admin`
- 모든 페이지 우측 상단 네비게이션 **관리자** 링크

## 화면 구성

4개 섹션이 1열(세로)로 배치됩니다. 데이터는 **수동 새로고침**으로만 갱신됩니다 (자동 폴링 없음 — 서버 부하 절약).

---

### 1. Qdrant 벡터 DB

Qdrant 컬렉션별 현황을 카드 형태로 표시합니다.

| 필드        | 설명                                               |
| ----------- | -------------------------------------------------- |
| 컬렉션 이름 | `videos` / `posters_clip` / `faces` / `poster_ocr` |
| 설명        | 컬렉션 용도 (임베딩 모델 포함)                     |
| 포인트 수   | 저장된 벡터 포인트 수                              |
| 차원        | 벡터 차원 수 (조회 가능한 경우)                    |
| 상태        | Qdrant 내부 상태 (`green` / `yellow` 등)           |

> **오류 처리**: `vectors_count` 등 qdrant-client 버전 간 속성 불일치는 `getattr` 로 안전하게 처리합니다.

---

### 2. Ollama LLM

설치된 모델 목록과 현재 VRAM 로드 상태를 함께 표시합니다.

| 필드          | 설명                                      |
| ------------- | ----------------------------------------- |
| 모델 이름     | Ollama 레지스트리 이름                    |
| 파라미터 크기 | 7B / 14B 등                               |
| 양자화        | Q4_K_M 등 양자화 수준                     |
| 패밀리        | llama / qwen 등 기반 아키텍처             |
| 모델 크기     | 디스크 파일 크기                          |
| VRAM 로드 중  | 현재 메모리에 로드 여부 (초록 인디케이터) |
| VRAM 사용량   | 로드 중일 때만 표시                       |
| 만료 시각     | idle 후 자동 언로드 시각                  |

> **원리**: `/api/tags` (설치 목록) + `/api/ps` (실행 목록) 를 합쳐 모델별로 로드 상태를 표시합니다.

---

### 3. SQLite DB

테이블별 1줄 설명과 레코드 수를 표시합니다.

| 필드        | 설명                   |
| ----------- | ---------------------- |
| 테이블 이름 | SQLite 내 테이블명     |
| 설명        | 테이블 용도 한 줄 요약 |
| 레코드 수   | `COUNT(*)` 결과        |

헤더에 전체 테이블 수와 최근 24시간 쿼리 로그 건수도 표시합니다.

---

### 4. 인덱서

#### 집계 수치

영상 / 포스터 / 배우 / 얼굴 클러스터 / 라벨 완료 수를 뱃지로 표시합니다.

#### 파이프라인 진행률 + 시작 버튼 (통합)

각 단계가 하나의 카드로 묶여 있습니다:

- 단계 이름 + 1줄 설명
- 완료/전체 카운트 + 진행률 바 + 대기 수
- 해당 단계를 실행하는 **시작 버튼** (옆에 위치)
- 완료/실패 시 로그 확인 토글(▼/▲)

| 단계          | CLI 커맨드      | 대상           |
| ------------- | --------------- | -------------- |
| 번역          | `translate`     | 영상 수 기준   |
| 텍스트 임베딩 | `embed`         | 영상 수 기준   |
| 이미지 임베딩 | `embed-clip`    | 포스터 수 기준 |
| 포스터 OCR    | `ocr-posters`   | 포스터 수 기준 |
| 얼굴 추출     | `extract-faces` | 포스터 수 기준 |

#### 기타 작업

파이프라인 외 단독 작업 목록 (버튼 + 1줄 설명):

| 작업            | CLI             | 설명                                         |
| --------------- | --------------- | -------------------------------------------- |
| JSON 로드       | `load`          | K:/Crazy/Info/\*.json → SQLite 증분 ETL      |
| 포스터 스캔     | `scan`          | 포스터 디렉토리 탐색 + instance/archive 분류 |
| 히스토리 CSV    | `history`       | 재생 히스토리 CSV → SQLite                   |
| FTS 재구축      | `fts`           | videos_fts5 전문 검색 인덱스 재생성          |
| 얼굴 클러스터링 | `cluster-faces` | HDBSCAN으로 얼굴 벡터 배우 단위 그룹화       |
| 페이로드 동기화 | `sync-payload`  | Qdrant payload를 SQLite 최신 데이터로 갱신   |

---

## API 엔드포인트 (FastAPI)

모든 엔드포인트는 localhost-only (127.0.0.1 / localhost / ai.kamoru.jk):

| 메서드 | 경로                    | 설명                                                |
| ------ | ----------------------- | --------------------------------------------------- |
| `GET`  | `/api/admin/dashboard`  | 전체 시스템 현황 (Qdrant·SQLite·Ollama·인덱서)      |
| `GET`  | `/api/admin/jobs`       | 실행 중·완료 작업 목록                              |
| `POST` | `/api/admin/jobs/{job}` | 인덱서 CLI 작업 시작 (`packages.indexer.cli {job}`) |

### 허용된 job 값

`load` `scan` `history` `fts` `all` `translate` `embed` `embed-clip` `extract-faces` `cluster-faces` `ocr-posters` `sync-payload`

### dashboard 응답 구조

```json
{
  "qdrant": {
    "available": true,
    "collections": [
      {
        "name": "videos",
        "points_count": 20818,
        "vectors_count": 20818,
        "dim": 1024,
        "status": "green"
      }
    ]
  },
  "sqlite": {
    "available": true,
    "tables": [{ "name": "videos", "count": 20818 }],
    "recent_queries_24h": 42
  },
  "ollama": {
    "available": true,
    "models": [
      {
        "name": "huihui_ai/qwen2.5-abliterate:7b",
        "size": 4700000000,
        "parameter_size": "7B",
        "quantization": "Q4_K_M",
        "family": "qwen2",
        "loaded": true,
        "size_vram": 5100000000,
        "expires_at": "2026-05-17T15:30:00Z"
      }
    ],
    "running_count": 1
  },
  "indexer": {
    "available": true,
    "totals": {
      "videos": 20818,
      "posters": 20334,
      "actresses": 3434,
      "face_clusters": 2834,
      "labeled_clusters": 1839
    },
    "completed": {
      "translate": 2206,
      "embed_text": 2048,
      "embed_clip": 20334,
      "ocr_posters": 0,
      "extract_faces": 20305
    },
    "pending": {
      "translate": 18612,
      "embed_text": 18770,
      "embed_clip": 0,
      "ocr_posters": 20334,
      "extract_faces": 29
    }
  },
  "jobs": {
    "embed": {
      "status": "done",
      "returncode": 0,
      "started_at": 1747450000,
      "finished_at": 1747453600
    }
  }
}
```

---

## 구현 파일

| 파일                                                                  | 역할                                   |
| --------------------------------------------------------------------- | -------------------------------------- |
| [apps/api/routers/admin.py](../apps/api/routers/admin.py)             | FastAPI 라우터 — 데이터 수집·작업 실행 |
| [apps/web/src/app/admin/page.tsx](../apps/web/src/app/admin/page.tsx) | Next.js 관리자 페이지                  |

---

## 재시작

변경 사항 반영:

```bat
bin\api.bat restart
```
