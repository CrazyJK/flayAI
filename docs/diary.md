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
        ┌─ 회상 의도 감지(코드 정규식 _looks_like_recall)
        │      회상이면 ▶ store.recall_sessions ─ 그때 일기 원문 + 한 줄 답
        │      아니면   ▶ 맞장구/공감 스트리밍
        ▼
 데이터 저장소(영상과 공유, 테이블·컬렉션은 분리):
   SQLite: diary_sessions / diary_messages / diary_messages_fts(trigram)
   Qdrant: diary_messages 컬렉션(bge-m3 1024d) — user 발화만 임베딩
```

**회상 의도 감지는 코드(정규식)로 한다.** diary_llm(EXAONE 3.5)은 Ollama tool-calling 을
지원하지 않아(`tools` 인자에 400) tool-call 라우팅이 불가능하다. `_looks_like_recall` 이
검색/조회 명령·기억/시점 질문·명시적 회상어("보여줘/찾아줘/기억나?/언제였지?/회상")를 잡고,
`_recall_search_query` 가 명령어를 떼어 주제만 검색어로 만든다.

회상 검색은 영상 retriever 와 같은 **RRF(K=60)** 패턴: Qdrant 의미검색 + FTS5(BM25)
\+ 짧은 한글 키워드용 LIKE 부분매칭 결합. Qdrant 가 없으면 FTS+LIKE 단독으로 graceful degrade.

- **LIKE 부분매칭은 단일 글자(똥·꿈·비)나 질의 전체가 짧은 2글자(온천)만** 대상.
  긴 질의의 2글자 토큰(회사·행사·여행)은 노이즈라 제외.
- **관련도 컷오프**(`diary.recall_min_semantic`, 기본 0.5): 실제 키워드 매칭이 없고 의미
  유사도도 임계 미만이면 무관으로 보고 버린다. 의미검색은 무관해도 최근접을 늘 돌려주므로,
  이 컷이 없으면 top_k 까지 무관한 일기로 채워진다. 매칭이 없으면 0건 → "못 찾겠어" 응답.
- **표시는 시간순**: 선택은 관련도 상위 top_k 로 하되, 일기이므로 카드는 날짜 오름차순
  (오래된→최근)으로 보여준다(`recall_sessions`).

**색인 정책(회상 정확도):**
- 레거시 일기는 **제목을 검색용 content 에 포함**해 임베딩/FTS(제목은 고신호인데 본문엔
  없을 수 있음 — 예: 본문에 "크리스마스"가 없어도 제목 "크리스마스 소원 이벤트"로 회상).
- **회상 질문 메시지는 색인하지 않는다**(`add_message(index=False)`). 질문은 기억이 아니라
  물음이라, 색인하면 과거 질문이 새 질문과 매칭돼 회상을 오염시킨다.
- 재임포트/정리: `import_legacy --reset` 로 전량 삭제 후 다시 적재(`store.reset_diary`).

## 이미지 첨부 + 비전 분석

대화에 사진을 첨부할 수 있고, 비전 모델이 그 사진을 분석해 반응한다.

- 일기 챗 모델(EXAONE)은 텍스트 전용이라, **이미지가 붙은 턴은 비전 모델**
  (`config.models.vision` = gemma-4-abliterated, 무검열 멀티모달)로 라우팅한다.
- 흐름(`packages/diary/vision.describe_images` + 라우터 `_prepare_images`):
  1. 첨부 이미지를 `data/diary_assets/`로 추출(raw_html 의 `<img>`).
  2. 비전 모델이 한국어로 1~2문장 **사실 묘사**(caption) 생성.
  3. caption 을 검색용 `content` 에 `[사진: …]`로 합류 → **나중에 사진 내용으로도 회상** 가능.
  4. 일기 텍스트 모델이 caption 을 컨텍스트로 받아 사진에 **공감하는 답**을 한다.
- 전송: 프론트가 base64 data URL 을 `POST /api/diary/chat` 의 `images[]`(최대 8장,
  장당 10MB)로 실어 보낸다. 비전 호출은 블로킹이라 `asyncio.to_thread` 로 처리.
- 사진은 사용자 버블·회상 카드에 그대로 보인다(레거시 일기 사진과 동일 경로로 서빙).

## 회상 시 사진 보고 답하기

회상한 일기에 **첨부 사진이 있으면, 비전 모델이 그 사진을 보고 묘사**해 LLM 컨텍스트에
넣는다. 그래서 답이 `[사진]` 마커가 아니라 "체크무늬 원피스를 입고 있었네" 처럼 **사진을
직접 본 것처럼** 나온다(`chat._recall_image_context`).

- 회상된 세션의 `raw_html` 에서 이미지 파일명을 뽑아(`asset_names_from_html`),
  `config.models.vision` 으로 한국어 묘사 생성.
- **캡션 캐시**(`diary_image_captions` 테이블, 파일명=내용 해시 키): 같은 사진은 한 번만
  묘사하고 재사용 → 첫 회상만 느리고(비전 호출) 이후는 즉시. 한 요청의 신규 생성은 4장으로
  제한(`max_new`)해 첫 회상 지연을 억제.
- DB 접근은 메인(async) 스레드, 블로킹인 비전 호출만 `asyncio.to_thread`(SQLite 스레드 공유 불가).

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
| POST | `/api/diary/chat` | (SSE) 일상 대화 + 회상 + 이미지. `{query, session_id?, images?[]}` |
| GET | `/api/diary/sessions` | 세션 목록(히스토리) |
| GET | `/api/diary/sessions/{id}` | 세션 transcript |
| GET | `/static/diary-assets/{name}` | 임포트된 일기 이미지 서빙 |

SSE 이벤트: `session`(session_id) → (`recall` 그때 일기 원문) → `token`* → `done`.

## 설정 (config.yaml)

- `models.diary_llm`: `huihui_ai/exaone3.5-abliterated:7.8b` (영상 채팅 `llm` 과 분리)
- `data.diary_dir` / `data.diary_assets`
- `diary.idle_hours` / `diary.context_messages` / `diary.recall_top_k`

모델은 사용자가 직접 받는다: `ollama pull huihui_ai/exaone3.5-abliterated:7.8b`.
