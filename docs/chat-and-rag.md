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
    { "role": "user",    "content": "Alice 출연작 알려줘" }
  ],
  "tools": [ /* JSON Schema */ ]
}
```

`tools` 를 주면 LLM 이 답 대신 `tool_calls: [{name, arguments}]` 를 돌려줄 수 있다.
서버가 그 함수를 실행해서 결과를 `role: tool` 메시지로 추가하고 **한번 더** 호출하면 LLM 이 최종 답을 만든다.

JS 에서 GPT 함수 호출 써본 적 있다면 동일.

> **flayAI 는 2차 호출(자연어 답변 생성)을 생략한다.** 사용자 목적은 검색 결과(opus 카드)이고
> 설명 문장은 불필요하기 때문. 대신 코드로 "건수 + 적용 필터" 한 줄만 만든다(§1). 이렇게 하면
> 7B 모델의 한국어→중국어 드리프트·재시도가 사라지고 응답이 빨라진다(워밍 후 1~2초).

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
   ▼ 코드 필터 보강 (_extract_meta + _extract_tags): year/month/kind/playable/min_rank/rank/min_likes/min_play/max_play/sort + DB 태그명 복수 추출(AND) → args 주입
   │   (LLM 이 tool_call 을 빠뜨려도 폴백 + 이 보강으로 결과가 정확)
   │
   ▼ SSE 로 클라이언트에 tool_call / tool_result 이벤트 즉시 push
   │
   ▼ 코드 요약 생성 (2차 LLM 호출 없음)
   │   _summarize_results(): "5건을 찾았어요 · 조건: 2023년 · 7월" 같은 한 줄
   │
   ▼ SSE event=token 으로 요약 한 줄 push → done
   │
User 화면: 카드(opus 결과) + 코드 요약 한 줄
```

## 2. SSE 이벤트 종류

`/api/chat` 는 다음 4종을 흘려보낸다:

| event type | 페이로드 | 의미 |
|------------|----------|------|
| `tool_call` | `{name, args}` | LLM 이 도구를 호출했다 (UI 에서 "검색 중..." 표시) |
| `tool_result` | `{name, result: {items: [...]}}` | 도구 실행 결과 (UI 가 결과 카드를 즉시 그릴 수 있음) |
| `token` | `{text: "..."}` | **코드 생성 요약 한 줄**(건수+적용 필터). LLM 자연어 생성이 아님 |
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
| `search_videos` | `query?, actress?, studio?, year?, month?, kind?, tag?, min_rank?, rank?, min_likes?, min_play?, max_play?, sort?, playable?, limit=10` | 자연어 검색의 기본. 거의 대부분이 여기. `min_rank`=평점≥N, `rank`=정확히 N, `min_likes`=좋아요≥N, `min_play`/`max_play`=재생횟수 N 이상/이하, `sort`=`recent`(최근 본 순)/`oldest`(오래 안 본 순). |
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
                │ Filters: actress, year, ... │  ← LLM tool_call + 코드(_extract_meta)
                └─────────────────────────────┘
   ※ year/month/kind/playable/min_rank/rank/min_likes/min_play/max_play/sort 는 _extract_meta 가
     질문에서 정규식으로 추출해 search_videos 인자에 주입한다(LLM 누락 방어). "평점 N 이상"→min_rank(≥),
     "랭크 N"·"별점 N"(수식어 없이)→rank(정확히 N), "좋아요/하트/찜 N"→min_likes(≥), "재생(횟수) N 이상/이하"·
     "N번 이상/이하 본"→min_play/max_play, "최근/마지막에 본"→sort=recent·"오래 안 본"→sort=oldest(last_play
     정렬). studio/actress 는 query 로 semantic+FTS 매칭.
   ※ _extract_tags: DB tags.name(2자+, 10분 캐시)이 질문에 그대로 들어 있으면 겹치지 않는 매칭을 최장 우선·
     최대 4개까지 tags 로 주입(복수 태그는 AND=모두 포함). 예: "온천 며느리"→tags=[온천,며느리].
     한국어 어미·조사 변형('웃고 있는' vs 태그 '웃는')은
     부분문자열로 못 잡으므로 그땐 의미검색에 의존.
   ※ _extract_count_tags: 남녀 명수 → 카운트 태그(M:N=앞 남자·뒤 여자, 값 1/2/n). '여러 남자'→남=n→
     tag_any=[n:1,n:n](OR 한 그룹), '여자 2명'→여=2→[1:2,2:2]. 태그 필터는 tag_groups(그룹내 OR·그룹간 AND):
     테마 태그=AND, 카운트=OR 한 그룹. 예: "온천에서 여러 남자" → 온천 AND (n:1 OR n:n).
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
