## 기본 규칙 (우선순위 순)

### 1순위: 응답 언어

- 모든 답변과 코드 주석은 한국어로 작성한다.

### 2순위: 문서 작성

- 코드 변경이 관련 문서에 영향을 미치는 경우에만 문서를 갱신한다.
- 문서 위치 규칙:
  - 변경된 코드 파일과 동일한 디렉토리에 `README.md` 가 있으면 그 파일에 작성한다.
  - 없으면 저장소 루트의 `doc/` 디렉토리에서 관련 파일을 찾고 있을때만 그 파일에 작성한다.
- 문서 형식은 마크다운(Markdown) 으로 작성한다.

### 3순위: 설명 수준

본 프로젝트는 JS/TS/Java 등 일반 SW 개발에는 능숙하지만 AI/ML 분야는
입문 단계인 개발자의 개인 사용 및 학습용 프로젝트이다. 따라서 답변과 문서 작성 시
다음 기준을 따른다.

- AI/ML 관련 개념(임베딩, 벡터 DB, 토크나이저, RAG, 파인튜닝, 손실함수,
  모델 아키텍처 등) 이 처음 등장하면 한 단락 이내로 용어 정의를 덧붙인다.
- AI 관련 코드 변경에는 "무엇을 / 왜 / 어떤 입출력" 을 간단히 주석 또는
  설명으로 남긴다.
- 일반 프로그래밍 개념(언어 문법, 흔한 라이브러리 사용법, 디자인 패턴,
  빌드/배포 도구 등) 은 부연 설명 없이 코드/명령 중심으로 간결하게 답한다.

### 코스 수정 후에는 다음을 수행한다.

프로세스 재시작이 필요한지 알려주고, 재시작 해야 하는 bin/*.bat 파일과 명령어를 제시한다.

---

## 프로젝트 컨텍스트

로컬 비디오 컬렉션(`K:\Crazy\*`)을 자연어로 검색하는 **완전 로컬** 개인용 프로젝트.  
상세 문서: [doc/overview.md](doc/overview.md) · [doc/architecture.md](doc/architecture.md) · [AI_PLAN.md](AI_PLAN.md)

### 컴포넌트 및 포트

| 컴포넌트 | 기술 | 포트 |
|----------|------|------|
| 백엔드 | FastAPI + uvicorn (`apps/api/`) | 8000 |
| 프론트 | Next.js 16 + React 19 + Tailwind 4 (`apps/web/`) | 3000 |
| 벡터 DB | Qdrant (Docker) | 6333 |
| LLM | Ollama `huihui_ai/qwen2.5-abliterate:7b` | 11434 |
| 관계 DB | SQLite `data/sqlite/flay.db` + FTS5 | — |

### 빌드 & 테스트 명령어

```powershell
# Python 테스트 (항상 .venv 사용, uv 는 PATH에 없을 수 있음)
.\.venv\Scripts\python.exe -m pytest -q

# 린트
.\.venv\Scripts\python.exe -m ruff check .

# 프론트엔드
cd apps\web ; npm run build ; npm run lint
```

### 프로세스 기동 (bin/*.bat)

```cmd
bin\all.bat start          # qdrant → ollama → api → web 순차 기동
bin\api.bat restart        # API만 재시작
bin\reindex.bat quick      # 메타만 빠른 재인덱싱 (AI 없음)
bin\reindex.bat sync       # 텍스트 AI 포함 동기화
bin\reindex.bat full       # 야간 풀 인덱싱 (이미지/얼굴/OCR)
```

자세한 bat 사용법: [bin/README.md](bin/README.md)

### 핵심 함정 (에이전트 주의)

- **Python 실행**: `.\.venv\Scripts\python.exe` 사용 (`python` 이나 `uv run` 이 PATH에 없을 수 있음)
- **Qdrant v1.18+**: `collection.search()` 삭제됨 → `client.query_points(collection_name, query=vec, limit=N, with_payload=True)` 사용, 반환값은 `result.points`
- **FTS5 쿼리**: 토큰을 `"phrase"` 로 감싸고 `OR` 로 결합 (예: `"alice" OR "앨리스"`). 그냥 키워드 쓰면 CJK/짧은 토큰에서 `syntax error near "?"` 발생
- **번역 모델**: `facebook/nllb-200-distilled-600M`, `src_lang=jpn_Jpan`, `forced_bos_token_id` 로 `kor_Hang` 지정
- **Qdrant 포인트 ID**: opus 의 SHA1 앞 8 바이트(uint63) — 4개 컬렉션 공통. cross-reference 용
- **스튜디오 alias**: DB 에서 `"S1"` 같은 공식명이 아닌 `"sone"`, `"s1no1style"` 등으로 저장될 수 있음 → alias 없는 검색 필터는 0건 반환
- **CORS**: API 는 localhost 전용, 외부 네트워크 노출 금지

### Python 린트 규칙 (ruff)

새 Python 파일 작성 시 준수:
- `from typing import Iterable` 금지 → `from collections.abc import Iterable` 사용 (UP035)
- `from typing import AsyncGenerator` 금지 → `from collections.abc import AsyncGenerator` 사용 (UP035)
- 사용하지 않는 import 추가 금지 (F401)
- `.encode("utf-8")` 인자는 불필요 — `.encode()` 로만 작성 (UP012)
- 타입 어노테이션에 문자열 리터럴(`"SomeType"`) 사용 금지 — `from __future__ import annotations` 가 있으면 따옴표 불필요 (UP037)
- `useEffect` 내 제어 흐름에서 로컬 변수 할당 후 미사용 금지 (F841)
- 잘못된 타입 어노테이션 예: async generator 함수의 반환 타입은 `"anyio.abc.ByteStream"` 이 아닌 `AsyncGenerator[bytes, None]`

### TypeScript/Next.js 린트 규칙 (ESLint)

새 TSX 파일 작성 시 준수:
- 내부 페이지 링크(`href="/..."`)에 `<a>` 태그 금지 → `import Link from "next/link"` 후 `<Link>` 사용 (`@next/next/no-html-link-for-pages`)
- `useEffect` 내 동기 `setState` 호출은 `// eslint-disable-next-line react-hooks/set-state-in-effect` 로 억제 (데이터 로딩 reset 패턴 등 정상적인 경우에 한함)

### 인덱서 파이프라인

CLI 진입점: `python -m packages.indexer.cli <cmd>`  
전체 흐름: `load → scan → history → fts → translate → embed`  
이미지: `embed-clip` / 얼굴: `extract-faces → cluster-faces` / OCR: `ocr-posters`  
각 단계는 **증분(incremental)** — 이미 처리된 행은 자동 skip. 강제 재처리는 `--rebuild`.