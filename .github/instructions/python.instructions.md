---
applyTo: "**/*.py"
description: "flayAI Python 공통 규칙 (FastAPI 백엔드 + 인덱서 + RAG)"
---

# Python 지침

Python **3.11** 기준. ruff/black, line-length 100. 모든 주석은 한국어.

## 실행 / 환경

- 항상 `.\.venv\Scripts\python.exe` 로 실행. `python` / `uv run` 은 PATH에 없거나 torch DLL 잠금을 일으킬 수 있다.
- 모듈 실행 형태: `.\.venv\Scripts\python.exe -m packages.indexer.cli <cmd>`, `... -m pytest -q`, `... -m ruff check .`
- 설정은 단일 진입점 `packages/settings.py` 의 `load_config()` (lru_cache) 로만 읽는다. 경로는 `repo_path()` 로 절대화. `config.yaml` 키를 코드에 하드코딩하지 말 것.

## ruff 규칙 (select = E,F,W,I,UP / ignore = E501)

새 파일/수정 시 준수:

- `from typing import Iterable | AsyncGenerator` 금지 → `from collections.abc import ...` (UP035).
- 사용하지 않는 import 금지 (F401).
- `.encode("utf-8")` 인자 불필요 → `.encode()` (UP012).
- 파일 상단에 `from __future__ import annotations` 가 있으면 타입 어노테이션에 문자열 리터럴(`"SomeType"`) 사용 금지 (UP037). 거의 모든 모듈이 이 import 를 둔다 — 새 모듈도 동일하게.
- async generator 반환 타입은 `AsyncGenerator[bytes, None]` 처럼 정확히. 잘못된 `"anyio.abc.ByteStream"` 류 금지.
- import 정렬(I): first-party 는 `apps`, `packages`.

## 타입 / 스타일

- 함수 시그니처에 타입 어노테이션 권장. `dict | None`, `int | None` 등 `X | None` 표기 (py3.10+ 문법).
- DB 접근은 `packages/indexer/db.py` 의 `connect()` 사용 (Row factory + WAL + busy_timeout 적용됨). 직접 `sqlite3.connect` 하지 말 것.
- 연결은 `try/finally` 로 항상 close (기존 코드 패턴 참고).

## AI/ML 코드 작성 시 (3순위 지침)

- 임베딩/벡터/토크나이저/RAG 등 개념이 처음 나오면 한 단락 이내 용어 정의를 주석으로.
- AI 관련 변경에는 "무엇을 / 왜 / 어떤 입출력" 을 docstring 또는 주석에 남긴다 (기존 모듈 docstring 양식 참고).

## 핵심 함정

- **Qdrant v1.18+**: `collection.search()` 삭제됨 → `client.query_points(collection_name, query=vec, limit=N, with_payload=True)`, 결과는 `resp.points`.
- **FTS5 (trigram)**: 쿼리 토큰을 `"phrase"` 로 감싸고 `OR` 결합 (`packages/rag/retriever.py._fts_query` 참고). 생 키워드는 CJK/짧은 토큰에서 `syntax error near "?"`.
- **Qdrant 포인트 ID**: opus 의 SHA1 앞 8바이트(uint63) — 4개 컬렉션 공통(`embed_text.opus_to_id`). 같은 영상은 어느 컬렉션에서나 같은 ID.
- 코드 변경 후 FastAPI 는 새 라우터/모듈을 자동 반영하지 않음(`--reload` 미사용) → `bin\api.bat restart` 필요.
