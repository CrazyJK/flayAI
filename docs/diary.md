# 일기형 대화 (Diary)

flayAI 의 로컬 인프라를 재활용한 **일상 대화이자 영구 일기** 기능. 영상 검색(`/`)과
한 앱에 공존하되, 데이터·라우터·페이지는 완전히 분리되어 있다.

## 무엇인가

- **수동적 경청자**: 챗봇이 먼저 말 걸지 않는다. 내 말에 공감·맞장구·동의만 한다.
  훈계·거부가 없도록 **무검열(abliterated) 한국어 모델**(EXAONE 3.5)을 쓴다.
- **영구 저장**: 모든 대화를 영구 보관. 메시지를 **세션(한 자리 대화)** 단위로 묶는다.
- **회상**: "저번에 똥 싼 게 언제였지?" 처럼 과거를 물으면, 그때 **세션 대화 원문 전체**
  (레거시 일기는 사진 포함)를 카드로 보여주고 한 줄로 답한다.

## 아키텍처

```
apps/web /diary  ──SSE──▶  POST /api/diary/chat
                                  │  packages/diary/chat.route_diary_chat
                                  ▼
        ┌─ 1차 LLM(diary_llm, recall_memory tool) ─ 회상 의도 판정
        │      회상이면 ▶ store.recall_sessions ─ 그때 일기 원문 + 한 줄 답
        │      아니면   ▶ 맞장구/공감 스트리밍
        ▼
 데이터 저장소(영상과 공유, 테이블·컬렉션은 분리):
   SQLite: diary_sessions / diary_messages / diary_messages_fts(trigram)
   Qdrant: diary_messages 컬렉션(bge-m3 1024d) — user 발화만 임베딩
```

회상 검색은 영상 retriever 와 같은 **RRF(K=60)** 패턴: Qdrant 의미검색 + FTS5(BM25)
\+ 짧은 한글 키워드용 LIKE 부분매칭(똥·꿈·비 등 1~2글자) 결합. Qdrant 가 없으면 FTS+LIKE
단독으로 graceful degrade.

## 데이터 모델

- `diary_sessions(id, started_at, ended_at, title, weather, summary, source_key)`
  - `source_key`: 레거시 일기 임포트 멱등 키(=날짜). 라이브 챗 세션은 NULL.
- `diary_messages(id, session_id, role, content, raw_html, created_at, source)`
  - `content`: 검색·임베딩용 평문. `raw_html`: 표시용 원본(레거시 일기·이미지 포함).
  - `source`: `'chat'` | `'diary_import'`.
- `diary_messages_fts`: trigram FTS5(한글 부분매칭).
- Qdrant `diary_messages`: point id = `diary_messages.id`, payload `{message_id, session_id,
  role, created_at_epoch, content}`. **user 발화만** 임베딩(회상 대상은 내가 한 말).

## 세션 수명

`get_or_create_session` 은 마지막 메시지가 `config.diary.idle_hours`(기본 6h) 이내면 최근
세션을 이어가고, 넘으면 새 세션을 연다. 프론트는 첫 응답의 `session` 이벤트로 받은
`session_id` 를 이후 요청에 실어 같은 세션을 이어쓴다. 헤더의 `+ 새 대화` 로 초기화.

## 레거시 일기 임포트 (일회성)

기존 일기 앱이 남긴 `K:/Crazy/Diary/*.diary`(JSON) 를 과거 기억으로 적재한다.

```powershell
.\.venv\Scripts\python.exe -m packages.diary.import_legacy
.\.venv\Scripts\python.exe -m packages.diary.import_legacy --no-embed   # 임베딩 생략(FTS+LIKE만)
```

- **정본만**: 정확히 `YYYY-MM-DD.diary` 형식만 임포트. `.diary.N`(자동저장 버전)은 스킵.
  무접미사 `.diary` 가 최신 편집본이라 가장 길고 정확하다.
- 한 파일 = 세션 1개 + user 메시지 1개. `meta.created/lastModified/title/weather` 를 세션에,
  HTML 평문을 `content`, 이미지 추출된 원본을 `raw_html` 에 저장.
- **base64 인라인 이미지**는 `data/diary_assets/<sha1>.<ext>` 로 추출(중복 제거)하고 src 를
  `/static/diary-assets/<name>` 로 치환 → DB 는 가볍게, 웹은 `<img>` 로 렌더.
- **멱등**: `source_key`(=날짜) 가 이미 있으면 스킵 → 재실행 안전.

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/diary/chat` | (SSE) 일상 대화 + 회상. `{query, session_id?}` |
| GET | `/api/diary/sessions` | 세션 목록(히스토리) |
| GET | `/api/diary/sessions/{id}` | 세션 transcript |
| GET | `/static/diary-assets/{name}` | 임포트된 일기 이미지 서빙 |

SSE 이벤트: `session`(session_id) → (`recall` 그때 일기 원문) → `token`* → `done`.

## 설정 (config.yaml)

- `models.diary_llm`: `huihui_ai/exaone3.5-abliterated:7.8b` (영상 채팅 `llm` 과 분리)
- `data.diary_dir` / `data.diary_assets`
- `diary.idle_hours` / `diary.context_messages` / `diary.recall_top_k`

모델은 사용자가 직접 받는다: `ollama pull huihui_ai/exaone3.5-abliterated:7.8b`.
