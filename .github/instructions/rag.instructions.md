---
applyTo: "packages/rag/**/*.py"
description: "RAG 검색 + LLM tool calling 라우팅 규칙"
---

# RAG 지침

`packages/rag/` = 검색기 + 랭커 + LLM 라우터. 채팅 한 줄이 답이 되기까지의 핵심.

## 구성

| 파일 | 책임 |
|------|------|
| `router.py` | Ollama tool calling 흐름. `SYSTEM_PROMPT`, 1차(tool 결정)→도구 실행→2차(스트리밍 응답) |
| `tools.py` | LLM 이 호출하는 도구 5종 + `TOOL_SCHEMA`(JSON Schema) + `TOOL_DISPATCH` |
| `retriever.py` | 하이브리드 검색: Qdrant semantic + SQLite FTS5 → RRF 결합 |
| `ranker.py` | 가중치 재정렬 (`config.yaml.ranking`) |

## 도구 5종 (read-only)

`search_videos` · `similar_to` · `get_video` · `get_actress` · `stats`.
모든 도구는 **read-only** (DB read + Qdrant search 만). write 는 별도 명시적 라우트.
새 도구 추가 시: `tools.py` 에 함수 + `TOOL_SCHEMA` 항목 + `TOOL_DISPATCH` 등록 3곳을 모두 갱신하고, `SYSTEM_PROMPT` 의 라우팅 규칙에 호출 조건을 명문화한다.

## LLM (Ollama)

- 모델은 `config.yaml.models.llm` = `huihui_ai/qwen2.5-abliterate:**7b**` (코드/주석은 7B 가정). 모델명을 하드코딩하지 말고 `_llm_model()` 사용.
- **7B 의 언어 관성**이 강해 한국어 응답이 중국어/일본어로 흘러가는 경향이 있다. `router.py` 에는 이를 막는 방어 로직이 다수 있음 — 함부로 제거하지 말 것:
  - `SYSTEM_PROMPT` 의 "오직 한국어" 절대 규칙
  - 도구 결과 직후 한국어 강제 user 지시 재주입
  - 1차 응답 content 비우기 (잡담 언어 전이 차단)
  - `options`: `temperature=0.2`, `repeat_penalty=1.25` (쉼표/줄바꿈 루프 방지)
- `_compact_tool_result()` 로 핵심 필드만 LLM 에 전달 (score_breakdown 등 잡음 제거 → 환각 감소).

## 라우팅 방어 (router.py)

- tool 미호출 시 `search_videos(query=user_query)` 강제 폴백 (빈손 응답 금지).
- 질문에 품번 패턴(`[A-Za-z]{2,7}-?\d{2,5}`)이 없으면 `get_video`/`similar_to` 호출을 `search_videos` 로 교체.
- `_extract_meta()` 로 "2023년 7월" 등 연/월을 코드 레벨에서 추출해 args 에 주입.
- SSE 응답이 hang 되지 않도록 스트리밍 generator 는 `finally` 에서 `await gen.aclose()`.

## 검색 / 랭킹

- 하이브리드: `semantic_search`(Qdrant `videos`, BGE-M3) + `fts_search`(SQLite FTS5 trigram) → `rrf_merge`(RRF_K=60).
- FTS 쿼리는 `_fts_query()` 가 토큰을 `"phrase"` 로 감싸 `OR` 결합 (CJK 안전).
- 가중치(`ranker.rank`): semantic 0.70 / fts 0.15 / usage 0.10 / recency 0.05 (half-life 180d). 값은 `config.yaml.ranking` 에서만 조정.
- query 가 비고 필터만 있으면 `_meta_only_search` (SQL 직접 정렬) 폴백.

## SSE 이벤트 계약 (프론트와 공유)

`tool_call {name,args}` → `tool_result {name,result}` → `token {text}` × N → `done {message,...}` / `error {message}`. 이벤트 타입 이름/구조를 바꾸면 `apps/web` 의 채팅 파서도 함께 수정해야 한다.
