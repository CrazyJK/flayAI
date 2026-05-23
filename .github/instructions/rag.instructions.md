---
applyTo: "packages/rag/**/*.py"
description: "RAG 검색 + LLM tool calling 라우팅 규칙"
---

# RAG 지침

`packages/rag/` = 검색기 + 랭커 + LLM 라우터. 채팅 한 줄이 답이 되기까지의 핵심.

## 구성

| 파일 | 책임 |
|------|------|
| `router.py` | Ollama tool calling 흐름. `SYSTEM_PROMPT`, 1차(tool 결정)→코드 필터 보강→도구 실행→코드 요약(2차 LLM 없음) |
| `tools.py` | LLM 이 호출하는 도구 5종 + `TOOL_SCHEMA`(JSON Schema) + `TOOL_DISPATCH` |
| `retriever.py` | 하이브리드 검색: Qdrant semantic + SQLite FTS5 → RRF 결합 |
| `ranker.py` | 가중치 재정렬 (`config.yaml.ranking`) |

## 도구 5종 (read-only)

`search_videos` · `similar_to` · `get_video` · `get_actress` · `stats`.
모든 도구는 **read-only** (DB read + Qdrant search 만). write 는 별도 명시적 라우트.
새 도구 추가 시: `tools.py` 에 함수 + `TOOL_SCHEMA` 항목 + `TOOL_DISPATCH` 등록 3곳을 모두 갱신하고, `SYSTEM_PROMPT` 의 라우팅 규칙에 호출 조건을 명문화한다.

## LLM (Ollama)

- 모델은 `config.yaml.models.llm` = `huihui_ai/qwen2.5-abliterate:**7b**` (코드/주석은 7B 가정). 모델명을 하드코딩하지 말고 `_llm_model()` 사용. (12GB VRAM 에선 7B 가 100% GPU 로 들어가 적합 — 14B/멀티모달은 오프로드·thinking 으로 부적합. 검증 결과는 `docs/TODO.md` 참고.)
- **LLM 은 1차 "도구 라우팅"에만 쓴다.** 도구 결과를 자연어로 설명하는 2차 호출은 **하지 않는다** — 사용자 목적은 opus 결과(카드)이고, 코드(`_summarize_results`)가 "건수+적용 필터" 한 줄을 만든다.
- 그래서 과거의 한국어→중국어 드리프트 방어 로직(한자 컷 `_collect_korean_answer`, 3회 재시도, 도구 결과 후 한국어 강제 재주입, `_compact_tool_result`)은 **모두 제거됨**. 2차 LLM 답변을 다시 도입하지 않는 한 되살리지 말 것.
- `options`: `temperature=0.2`, `repeat_penalty=1.25` (1차 tool_call 안정용).

## 라우팅 방어 (router.py)

- tool 미호출 시 `search_videos(query=user_query)` 강제 폴백 (빈손 응답 금지).
- 질문에 품번 패턴(`[A-Za-z]{2,7}-?\d{2,5}`)이 없으면 `get_video`/`similar_to` 호출을 `search_videos` 로 교체.
- `_extract_meta()` 로 질문에서 year/month/min_rank/rank/min_likes/kind/playable 를 정규식으로 추출해 `search_videos` args 에 주입(LLM 누락·미호출 방어). 평점은 "N 이상"→`min_rank`(≥), "랭크 N"·"별점 N"(수식어 없이)→`rank`(정확히 N), "좋아요/하트/찜 N"→`min_likes`(≥, `videos.like_count`). studio/actress 는 query 로 semantic+FTS 매칭.
- `_extract_tag()` 로 DB `tags.name`(2자+, 10분 캐시 `_known_tags`)이 질문에 그대로 포함되면 최장 매칭 태그를 `tag` 로 주입(테마 질의 정확도↑). 한국어 어미·조사 변형은 부분문자열로 못 잡음('웃고 있는'≠태그 '웃는') → 그땐 의미검색 의존.
- 결과 요약은 `_summarize_results()` 가 코드로 "건수+필터" 한 줄을 만들어 `token` 이벤트로 한 번 push.

## 검색 / 랭킹

- 하이브리드: `semantic_search`(Qdrant `videos`, BGE-M3) + `fts_search`(SQLite FTS5 trigram) → `rrf_merge`(RRF_K=60).
- FTS 쿼리는 `_fts_query()` 가 토큰을 `"phrase"` 로 감싸 `OR` 결합 (CJK 안전).
- 가중치(`ranker.rank`): semantic 0.70 / fts 0.15 / usage 0.10 / recency 0.05 (half-life 180d). 값은 `config.yaml.ranking` 에서만 조정.
- query 가 비고 필터만 있으면 `_meta_only_search` (SQL 직접 정렬) 폴백.

## SSE 이벤트 계약 (프론트와 공유)

`tool_call {name,args}` → `tool_result {name,result}` → `token {text}` × N → `done {message,...}` / `error {message}`. 이벤트 타입 이름/구조를 바꾸면 `apps/web` 의 채팅 파서도 함께 수정해야 한다.
