# Overview — 무엇을 만드는가

## 문제

- 내 PC 의 `K:\Crazy\Info\video.json` 에 비디오 컬렉션 메타가 영상 단위로 들어 있다.
- 제목/설명은 **일본어**가 많고, 배우는 **별칭/한자/영문** 여러 표기가 섞여 있다.
- 그 위에 포스터 이미지 2만 장이 `K:\Crazy\Storage`, `K:\Crazy\Archive` 등에 흩어져 있다.
- 폴더/파일명으로 찾는 데 한계가 명백. **자연어로 검색하고 싶다.**

## 목표

> "회사 배경의 일상 영상", "지금 볼 수 있는 ~", "Alice 출연작",
> "이 사진의 배우 출연작" 같은 질의를 한국어로 던지고 답을 받는다.

내 PC 안에서 **외부 노출 없이**.

## 왜 LLM + RAG 인가

웹 개발자에게 익숙한 용어로 풀면:

- **LLM (Large Language Model)** = "한국어를 잘하는 응답 생성기".
  여기서는 `Qwen2.5 14B` 를 [Ollama](https://ollama.com) 로 띄워서 씁니다.
  하지만 LLM 은 내 데이터를 모릅니다.
- **RAG (Retrieval-Augmented Generation)** = "검색해서 그 결과를 LLM 에게 보여주고 답하게 한다".
  즉, "LLM 단독" 이 아니라 "DB 검색 + LLM 종합".
- **Tool calling** = LLM 이 답하기 전에 `search_videos(actress="alice")` 같은
  **함수를 호출하라**고 우리가 시킬 수 있는 기능. 정확한 데이터를 가져오는 핵심 메커니즘.

JS 비유:

```ts
// 사이트의 일반적인 RAG 흐름을 의사코드로 쓰면
const tools = { search_videos, similar_to, get_video, ... };
const llmResp = await ollama.chat({
  model: "qwen2.5",
  messages: [...history, { role: "user", content: query }],
  tools: schemaOf(tools),  // OpenAI tool calling 과 동일
});
for (const call of llmResp.tool_calls) {
  const result = await tools[call.name](call.args);
  history.push({ role: "tool", content: JSON.stringify(result) });
}
// 결과까지 본 LLM 이 다시 한 번 응답 → 사용자에게 SSE 스트리밍
```

이게 이 프로젝트의 본질이고, 나머지는 다 **검색을 잘 하기 위한 인프라**입니다.

## 시나리오 (구현 완료)

| 질의 예 | 처리 |
|---------|------|
| `Alice Smith 출연작 5개` | `search_videos(actress=...)` → SQLite 메타 only |
| `회사 사무실 배경 영상` | `search_videos(query=...)` → BGE-M3 임베딩 + Qdrant top-k → FTS5 BM25 와 RRF 결합 |
| `2023년 7월 발매작` | 메타 필터 only |
| `S1 평점 4 이상` | studio + rank 필터 |
| `지금 볼 수 있는 회사 영상` | `kind=instance` + 의미 검색 |
| `이 사진의 배우는?` | OpenCLIP 또는 InsightFace 임베딩 → `posters_clip` / `faces` Qdrant |
| `S Model` (포스터 OCR) | RapidOCR 로 추출한 텍스트를 BGE-M3 임베딩 후 검색 |

## 시나리오 (계획)

- 개인 문서 RAG (OneDrive 의 docx/pdf/xlsx) — Phase 5 (M5b)
- 야간 자동 인덱싱 + 백업 — M6 (스크립트는 작성됨, 등록은 사용자 작업)

## 동작 환경

- Windows 11
- 12GB GPU (RTX 4070 Ti) — InsightFace · CLIP · LLM 추론용
- 외부 네트워크는 모델/패키지 다운로드 시에만 사용. 운영 트래픽은 100% 로컬 (127.0.0.1).
