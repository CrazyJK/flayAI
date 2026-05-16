# Chat & RAG — 사용자의 한 줄이 답으로 돌아오기까지

## 0. 사전 지식 (이미 안다면 스킵)

### LLM 의 채팅 API 모양

OpenAI 든 Ollama 든 모양은 같다:

```http
POST /api/chat
{
  "model": "qwen2.5",
  "messages": [
    { "role": "system",  "content": "당신은 비서다 ..." },
    { "role": "user",    "content": "Aoi 출연작 알려줘" }
  ],
  "tools": [ /* JSON Schema */ ]
}
```

`tools` 를 주면 LLM 이 답 대신 `tool_calls: [{name, arguments}]` 를 돌려줄 수 있다.
서버가 그 함수를 실행해서 결과를 `role: tool` 메시지로 추가하고 **한번 더** 호출하면 LLM 이 최종 답을 만든다.

JS 에서 GPT 함수 호출 써본 적 있다면 동일.

### RAG 의 핵심 아이디어

LLM 은 내 DB 를 모른다 → **검색해서 결과를 컨텍스트로 넣어준다** → 답.

이때 검색을 "키워드(BM25)" 만으로 하면 "회사 배경" 같은 자연어 의도를 못 잡는다.
그래서 **임베딩 벡터의 코사인 유사도** 로 의미 검색을 한다.
둘 다 약점이 있어서 **하이브리드** (BM25 + 벡터 → RRF 로 합산) 가 표준 패턴.

flayAI 는 이 모든 걸 한다.

---

## 1. 전체 흐름 (한 장)

```
User: "회사 배경의 일상 영상"
   │
   ▼ POST /api/chat (SSE)
┌──────────────────────────────────────────────────┐
│ apps/api/main.py @app.post("/api/chat")          │
│ → route_chat(messages)  (packages/rag/router.py) │
└──────────────────────────────────────────────────┘
   │
   ▼ 1차 LLM 호출 (Ollama, stream=false, tools=[...])
   │   payload: system + user
   │
LLM 응답:  { "tool_calls": [
              { "name": "search_videos",
                "arguments": { "query": "회사 배경 일상" } } ] }
   │
   ▼ 도구 실행 (packages/rag/tools.py)
   ┌──────────────────────────────────────────┐
   │ search_videos(query, actress?, year?, ...) │
   │  → retriever.hybrid_search()              │
   │     ├ Qdrant videos (BGE-M3 임베딩 검색)   │
   │     └ SQLite videos_fts (BM25)            │
   │     → RRF 결합 + ranker.rank() 가중치      │
   │  → [hit, hit, hit, ...]                   │
   └──────────────────────────────────────────┘
   │
   ▼ SSE 로 클라이언트에 tool_call / tool_result 이벤트 즉시 push
   │
   ▼ 2차 LLM 호출 (stream=true)
   │   messages 에 도구 결과 JSON 을 role=tool 로 추가
   │
LLM: "회사 배경 일상 영상 5건 추천드립니다 ..." (토큰 단위 스트리밍)
   │
   ▼ SSE event=token 마다 push
   │
User 화면: 카드 + 자연어 응답
```

## 2. SSE 이벤트 종류

`/api/chat` 는 다음 4종을 흘려보낸다:

| event type | 페이로드 | 의미 |
|------------|----------|------|
| `tool_call` | `{name, args}` | LLM 이 도구를 호출했다 (UI 에서 "검색 중..." 표시) |
| `tool_result` | `{name, result: {items: [...]}}` | 도구 실행 결과 (UI 가 결과 카드를 즉시 그릴 수 있음) |
| `token` | `{text: "..."}` | LLM 응답 토큰 (자연어 응답 스트리밍) |
| `done` / `error` | 종료 신호 | |

JS 클라이언트 코드 형태:

```ts
const r = await fetch("/api/chat", { method: "POST", body: JSON.stringify({ query }) });
const reader = r.body!.getReader();
const decoder = new TextDecoder();
for (;;) {
  const { value, done } = await reader.read();
  if (done) break;
  for (const line of decoder.decode(value).split("\n")) {
    if (!line.startsWith("data:")) continue;
    const ev = JSON.parse(line.slice(5));
    switch (ev.type) {
      case "tool_result": renderCards(ev.result.items); break;
      case "token":       appendText(ev.text); break;
    }
  }
}
```

## 3. LLM 에게 주는 도구 5종

`packages/rag/tools.py` 정의. JSON Schema 는 `TOOL_SCHEMA` 변수.

| 도구 | 시그니처 (요약) | 언제 호출되도록 시켰는가 |
|------|----------------|------------------------|
| `search_videos` | `query?, actress?, studio?, year?, month?, kind?, tag?, min_rank?, playable?, limit=10` | 자연어 검색의 기본. 거의 대부분이 여기. |
| `similar_to` | `opus, exclude_watched=true, limit=10` | 품번이 명시되어 있을 때 유사 영상 |
| `get_video` | `opus` | 품번 단일 조회 |
| `get_actress` | `name` | 배우 메타 + 대표작 |
| `stats` | `actress?, tag?, group_by?` | 통계/집계 |

라우팅 규칙은 `SYSTEM_PROMPT` 에 명문화 (`packages/rag/router.py`).
**LLM 이 잘못된 도구를 안 부르게 하는 게 정확도의 핵심**이라, 이 system prompt 가 곧 평가 정답률을 결정.

## 4. 하이브리드 검색 (`packages/rag/retriever.py`)

`search_videos` 가 `query` 를 받으면:

```
                ┌─────────────────────────────┐
                │ Filters: actress, year, ... │  ← LLM 이 채워 보냄
                └─────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
   Qdrant videos                              SQLite FTS5
   (BGE-M3 임베딩)                              (BM25)
   payload 필터로 actress/year 등 적용         WHERE actress=? AND year=?
        ▼                                           ▼
   [(opus, sem_score)] × N                    [(opus, bm_score)] × N
        │                                           │
        └──────────────── RRF ─────────────────────┘
                          │
                          ▼
              ranker.rank(): 가중치
                semantic 0.70
                fts      0.15
                usage    0.10   (play / like_count)
                recency  0.05   (last_play, half_life=180d)
                          │
                          ▼
                  [hit] × limit
```

RRF (Reciprocal Rank Fusion) = `Σ 1 / (k + rank_i)`. 점수 스케일이 다른 두 검색기를 자연스럽게 합치는 표준 트릭.

**모든 자연어 검색이 안 되면** (filter 만 있고 query 없음): SQLite 메타 only 폴백 (`_meta_only_search`).
예: "2023년 7월 발매작" → query 없이 year=2023, month=7 만으로 정렬.

## 5. 이미지/얼굴 검색 흐름

채팅(`/api/chat`) 이 아니라 **별도 엔드포인트**.

### 이미지 한 장 → 비슷한 포스터 (`/api/image/search`)
1. 업로드된 이미지를 OpenCLIP ViT-L/14 로 768d 임베딩.
2. Qdrant `posters_clip` top-K.
3. opus 로 SQLite 메타 join → hit.

### 이미지 한 장 → 배우 매칭 (`/api/face/search`)
1. InsightFace 로 얼굴들 검출.
2. 각 얼굴 512d → Qdrant `faces` top-K.
3. 결과들의 `cluster_id` 다수결 → 클러스터의 라벨(canonical_name) = 배우.
4. `search_videos(actress=...)` 처럼 출연작 반환.

### 포스터 OCR 텍스트 검색 (`/api/search/poster-ocr`)
1. 사용자 쿼리를 BGE-M3 임베딩.
2. Qdrant `poster_ocr` top-K.
3. opus 로 SQLite 메타 join + payload 의 ocr_text 포함하여 응답.

## 6. 모델 메모리 관리

GPU 12GB 한정이라 모두 동시 로드 불가. 정책:

- **LLM**: Ollama 가 keep-alive 후 자동 unload (`scripts/nightly_index.ps1` 에서 명시적 unload 가능).
- **BGE-M3, CLIP, InsightFace**: 첫 요청 시 lazy load, 이후 process 종료까지 유지.
- 야간 인덱싱 단계 사이에는 큰 모델을 unload 하도록 nightly 스크립트가 순서 조정.

## 7. 평가 (M6)

`eval/golden.yaml` 30 케이스를 `eval/run_eval.py` 가 채팅 API 로 자동 검증.
M6 수락 기준: 정답률 ≥ 85%. 현재 actress 서브셋 6/7 통과 (85.7%).

```powershell
python eval/run_eval.py            # 전체
python eval/run_eval.py --tag ocr  # 카테고리 필터
python eval/run_eval.py --id actress-alias-001
```
