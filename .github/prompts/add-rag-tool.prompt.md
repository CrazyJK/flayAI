---
mode: agent
description: "LLM 이 호출할 수 있는 새 RAG 도구를 추가한다"
---

# RAG 도구 추가

`packages/rag/tools.py` 의 도구 5종(`search_videos`, `similar_to`, `get_video`, `get_actress`, `stats`)에 새 read-only 도구를 추가하는 절차.

## 체크리스트

1. **함수 작성** (`packages/rag/tools.py`)
   - read-only (DB read + Qdrant search 만, 외부 effect 없음).
   - JSON-serializable 인자/반환. 결과 영상은 `_video_to_hit(conn, opus, scored=...)` 로 표준 `hit` dict 생성.
   - 배우 인자는 `_resolve_actress_alias`, 태그는 `_resolve_tag_id` 로 정규화.
   - 연결은 `connect()` + `try/finally` close.

2. **스키마 등록** — `TOOL_SCHEMA` 리스트에 항목 추가 (`type: function`, `function.name/description/parameters`). description 은 LLM 이 **언제 부를지** 명확히.

3. **디스패치 등록** — `TOOL_DISPATCH` dict 에 `"name": fn` 추가.

4. **라우팅 규칙** — `packages/rag/router.py` 의 `SYSTEM_PROMPT` 에 호출 조건을 한 줄 명문화. 품번 의존 도구라면 router 의 품번 방어 로직(`get_video`/`similar_to` 교체)에 포함할지 검토.

5. **결과 슬림화** — LLM 컨텍스트에 큰 payload 가 들어가면 7B 가 환각한다. 필요하면 `_compact_tool_result()` 에 새 도구의 핵심 필드 추출을 추가.

6. **검증** — `eval/golden.yaml` 에 케이스 추가, `python eval/run_eval.py` (수락 ≥ 85%). 단위 테스트는 `tests/test_rag_*`.

7. **재시작** — `bin\api.bat restart`.

## 주의

- write 가 필요하면 도구가 아니라 별도 명시적 라우트(예: 라벨링)로. LLM 도구는 read-only 원칙.
- 모델명/URL 하드코딩 금지 — `_llm_model()`, `load_config()`.
