# API Reference

베이스 URL: `http://127.0.0.1:8000`. 모든 엔드포인트는 localhost 전용.

## 채팅

### `POST /api/chat`

SSE 스트리밍. RAG + LLM 응답. UI 의 메인 흐름.

요청:

```json
{
  "query": "Alice 출연작",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

응답: `text/event-stream`. `data:` 줄 마다 JSON 1건.

이벤트 타입:

- `tool_call`  — `{type, name, args}`
- `tool_result` — `{type, name, result: {items: [hit, ...]}}`
- `token`       — `{type, text}`
- `done`        — `{type, message}`
- `error`       — `{type, message}`

`hit` 구조 (자주 등장):

```ts
{
  opus: string,
  title: string|null,        // ko 우선, 없으면 jp
  title_jp: string|null,
  title_ko: string|null,
  studio: string|null,
  release_date: string|null, // "YYYY-MM-DD"
  year: number|null,
  month: number|null,
  kind: "instance" | "archive",
  rank: number,
  play: number,
  like_count: number,
  actresses: string[],       // canonical 이름들
  poster_path: string|null,
  video_path: string|null,
  playable: boolean,
  score?: number,
  // 컨텍스트별 추가 필드 (예: ocr_text)
}
```

## 메타 검색

### `POST /api/search/videos`

채팅을 거치지 않고 직접 도구 호출.

```json
{
  "query": "회사 일상",
  "actress": "alice",
  "studio": "StudioA",
  "year": 2023, "month": 7,
  "kind": "instance",
  "playable": true,
  "min_rank": 4,
  "tag": "office",
  "limit": 10
}
```

응답: `{ "items": [hit, ...] }`

### `GET /api/videos/{opus}`

영상 단일 조회.

### `GET /api/actresses/{name}`

배우 메타 + 대표작.

### `GET /api/similar/{opus}?exclude_watched=true&limit=10`

의미적으로 비슷한 영상.

## 번역

### `POST /api/translate`

```json
{ "text": "...", "target": "ko", "sentencewise": true }
```

응답: `{ "text": "..." }`

## 이미지 검색 (CLIP)

### `POST /api/image/search/text`

텍스트 → 포스터 이미지 의미 검색 (CLIP cross-modal).

```json
{ "query": "office uniform", "limit": 10, "kind": "instance" }
```

### `POST /api/image/search`

이미지 업로드 → 비슷한 포스터.

```
multipart/form-data:
  image: <file>
  limit: 10
  kind:  instance | archive   (옵션)
```

## 얼굴 검색

### `POST /api/face/search`

이미지에서 얼굴 검출 → 클러스터 매칭 → 출연작.

```
multipart/form-data:
  image: <file>
  limit: 5
```

응답:

```json
{
  "faces": [
    { "bbox": [...], "matches": [ { "cluster_id": 12, "label": "alice", "votes": 152, "confidence": 1.0 }, ... ] }
  ],
  "items": [hit, ...]
}
```

## 얼굴 라벨링 (관리)

### `GET /api/face/clusters?min_size=5&labeled=auto|manual|none&page=...`

얼굴 클러스터 목록. 라벨링 UI 가 사용.

### `GET /api/face/clusters/{cluster_id}/samples?limit=12`

클러스터 대표 얼굴 샘플 (썸네일).

### `POST /api/face/clusters/{cluster_id}/label`

```json
{ "label": "alice" }
```

사람이 직접 라벨 부여. (`null` 로 보내면 제거)

## 포스터 OCR 검색

### `POST /api/search/poster-ocr`

```json
{ "query": "S Model", "limit": 10, "kind": "instance" }
```

응답: `{ "items": [hit + ocr_text, ...] }`

## 관리

### `GET /api/admin/stats`

요청자 IP 가 127.0.0.1/localhost/::1 이 아니면 403.

```json
{ "videos": 20818, "actresses": ..., "posters": ..., ... }
```

### `GET /healthz` — `{ "status": "ok" }`

### `GET /static/posters/{opus}` — 포스터 파일 직접 서빙

## 인증 / 보안 메모

- CORS: `config.yaml` 의 `server.cors_origins` 화이트리스트만 (기본 localhost:3000).
- 인증 없음. **로컬 전용 운영 전제.** 외부로 절대 노출 금지.
- `/api/admin/*` 는 추가로 client IP 검증.
- LLM 도구는 read-only. write 는 별도 라우트 (`/api/face/clusters/.../label` 처럼 명시적).

## 클라이언트 코드 예시

```ts
// 채팅 스트리밍
async function* chat(query: string) {
  const r = await fetch("http://127.0.0.1:8000/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  const dec = new TextDecoder();
  const reader = r.body!.getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop()!;
    for (const line of lines) {
      if (line.startsWith("data:")) yield JSON.parse(line.slice(5));
    }
  }
}

// 메타 검색
const { items } = await fetch("http://127.0.0.1:8000/api/search/videos", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ actress: "alice", year: 2023, limit: 5 }),
}).then(r => r.json());
```
