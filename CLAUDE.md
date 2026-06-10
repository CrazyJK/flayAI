# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

이 저장소는 **GitHub Copilot 과 Claude Code 를 함께** 사용하며, AI 보조 지침의 단일 진실 소스(SoT)는 `.github/` 의 Copilot 문서다. Claude Code 도 아래 문서를 그대로 따른다(중복 작성 금지).

## 먼저 읽을 것 (우선순위 순)

1. **[.github/copilot-instructions.md](.github/copilot-instructions.md)** — 저장소 전역 기본 지침: 응답 언어(한국어), 문서 작성 규칙, 빌드/테스트 명령, 핵심 함정, **개발 모드(에이전트 인앱 구동)**, Git 워크플로. **항상 적용.**
2. **[.github/instructions/](.github/instructions/)** — 경로별 세부 지침. 작업 파일에 해당하는 것을 연다: `python` / `indexer`(`packages/indexer/**`) / `rag`(`packages/rag/**`) / `frontend`(`apps/web/**`) / `scripts`(`bin/**`,`scripts/**`).
3. **[.github/prompts/](.github/prompts/)** — 반복 작업 절차(재인덱싱·서비스 재시작·RAG 도구 추가·API 엔드포인트 추가·문서 동기화). Claude Code 에선 해당 파일을 열어 절차를 따른다.
4. **[docs/](docs/README.md)** — 구현 기준 동작 설명서. 미해결 작업은 **[docs/TODO.md](docs/TODO.md)**.

## 프로젝트 한 줄 요약

로컬 비디오 컬렉션(`K:\Crazy\*`)의 메타데이터·포스터를 로컬 LLM 챗봇으로 자연어 검색하는 **완전 로컬** 개인 프로젝트(인터넷 노출 금지, LAN + 자체 TLS). 사용자는 JS/TS/Java 에 능숙하나 AI/ML 은 입문 단계 → AI 개념은 첫 등장 시 한 단락 정의를 덧붙인다.

## 아키텍처 (빅 픽처)

원본 데이터 → **인덱서 파이프라인**이 검색 인덱스(데이터 저장소들)를 구축 → **RAG/API** 가 그 위에서 채팅·검색을 서빙 → **웹**이 표시. 두 서브시스템은 데이터 저장소를 통해서만 연결된다.

```
K:\Crazy\Info\*.json,*.csv  +  K:\Crazy\{Storage,Archive}\**.jpg
        │  packages/indexer  (CLI: python -m packages.indexer.cli <stage>)
        ▼
┌─────────────── 데이터 저장소 ───────────────┐
│ SQLite (data/*.db, WAL) + FTS5(trigram)      │  ← 메타·관계·전문검색
│ Qdrant 5 컬렉션:                              │  ← 벡터 검색
│   videos(1024d,bge-m3) posters_clip(768d,CLIP)│
│   faces(512d,InsightFace) poster_ocr(1024d)   │
│   poster_caption(1024d)                       │
│ Ollama: chat LLM + vision(캡션) 모델          │  ← 생성/캡션 (외부 프로세스)
└──────────────────────────────────────────────┘
        │  packages/rag (검색·라우팅)  →  apps/api (FastAPI)
        ▼  apps/web (Next.js, https://ai.kamoru.jk:3000)
```

- **인덱서 파이프라인** (`packages/indexer`): 12단계 순차 실행. 순서가 중요(`caption-posters` 가 `embed` 보다 먼저라야 캡션이 videos 임베딩 `[장면]` 블록에 합류). 관리자 일괄 버튼은 **각 단계를 별도 서브프로세스**(`cli <stage>`)로 띄운다(단계 사이 VRAM 해제). 단계 순서: `load → scan → history → fts → translate → caption-posters → embed → embed-clip → extract-faces → cluster-faces → ocr-posters → sync-payload`. 거의 모든 단계가 **증분·멱등**(완료분 skip)이고 SQLite 는 **WAL + 배치 단위 commit**(예: OCR 20건마다) → 중단/강제종료해도 데이터 손상 없이 재실행 시 이어진다. 임베딩 단계(`embed`/`embed-clip`)도 `embed_state(collection,opus,sig)` 시그니처로 증분 — 문서(videos) 또는 `path|mtime|타일구성`(posters_clip, 포스터당 전체+절반2+4분면 7타일 점)가 바뀐 것만 재임베딩(첫 실행은 기존 Qdrant 점 시드해 스킵, `--force` 로 전량). 가변 payload 는 `sync-payload` 가 따로 갱신. 상세: [docs/indexing-pipeline.md](docs/indexing-pipeline.md).
- **RAG 채팅** (`packages/rag`): **2차 LLM 답변 생성을 쓰지 않는다.** 흐름 = ① 1회 LLM tool-call(라우팅) → ② `router._extract_meta` 가 정규식으로 메타 필터를 코드 추출(year/month/kind/playable/min_rank/rank/min_likes/min_play/max_play/sort) + `_extract_tags` 가 DB 태그명을 (겹치지 않게) **복수** 사전 매칭(최장 우선, 최대 4개) → search_videos args 에 `tags` 로 주입(복수 태그는 모두 포함=AND) + `_extract_count_tags` 가 남녀 명수('여러 남자'·'여자 2명' 등)를 카운트 태그(`M:N`=앞 남자수·뒤 여자수, 값 1/2/n)로 환산해 `tag_any`(같은 차원 후보를 OR)로 주입. 태그 필터는 `Filters.tag_groups`(그룹내 OR·그룹간 AND)로 적용(LLM 누락 방어) → ③ `retriever.hybrid_search` = Qdrant bge-m3 의미검색 + SQLite FTS5(BM25) → **RRF 결합**(RRF_K=60) → ④ `ranker.rank` 가중치 정렬 → ⑤ 코드가 "건수+필터" 한 줄 요약. 결과는 SSE 로 스트리밍. 상세: [docs/chat-and-rag.md](docs/chat-and-rag.md).
- **관리자/모니터링** (`apps/api/routers/admin.py` + `apps/web/src/app/admin/page.tsx`): 폴링 분리 — `/monitor`(시스템 지표만, 1초) · `/services`(Qdrant·Ollama·인덱서·작업, 5초/작업중 2초) · `/dashboard`(전체, 초기·수동). 프론트는 가시성 게이팅(`document.hidden` 시 폴링 생략). 파이프라인 **일시정지/재개**(`/jobs/{job}/pause|resume`) 지원 — 현재 단계 서브프로세스를 terminate 하고 재개 시 멈춘 단계부터(증분이라 안전). 상세: [docs/admin.md](docs/admin.md).

> 실제 모델/컬렉션 값은 추정하지 말고 **`config.yaml` 과 코드에서 확인**한다(문서마다 표기가 엇갈릴 수 있음 — [docs/TODO.md](docs/TODO.md)).

## 자주 쓰는 명령

```powershell
.\.venv\Scripts\python.exe -m pytest -q                      # 전체 테스트
.\.venv\Scripts\python.exe -m pytest tests/test_rag_ranker.py -q   # 단일 파일
.\.venv\Scripts\python.exe -m pytest -k ranker -q            # 이름 필터로 단일 테스트
.\.venv\Scripts\python.exe -m ruff check .                   # 파이썬 린트
.\.venv\Scripts\python.exe -m packages.indexer.cli <stage>   # 인덱서 단계 직접 실행 (load/scan/embed/...)
cd apps\web ; npm run build ; npm run lint                   # 프론트 빌드·린트
```

```cmd
bin\prod.bat                                        :: 운영 HTTPS 일괄 기동(독립 유지)
bin\all.bat start | status | stop                   :: 개발 일괄 제어(별도 창)
bin\api.bat restart                                 :: API 재시작(별도 콘솔 창 방식)
bin\reindex.bat <quick|sync|full|clean>             :: 재인덱싱
```

**개발 모드(에이전트가 직접 띄울 때)** — 별도 창(`bin\*.bat` 의 `start cmd /k`) 대신 **클로드 앱 내부 백그라운드 프로세스**로 실행해 로그를 실시간으로 본다(상세는 copilot-instructions §개발 모드):

```
.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host ai.kamoru.jk --port 8000 --ssl-keyfile .cert/kamoru.jk.key --ssl-certfile .cert/kamoru.jk.pem
cd apps/web && npm run dev   # https://ai.kamoru.jk:3000
```

## 절대 잊지 말 것

- **Python 실행**: `.\.venv\Scripts\python.exe` (Python 3.11). `python`/`uv run` 은 PATH 부재·torch DLL 잠금 위험.
- **API 재시작은 수동**: FastAPI 자동 reload 없음 → 코드 변경 시 인앱 백그라운드 프로세스를 종료(8000 포트 PID `taskkill /F`) 후 다시 띄운다. **`uvicorn --reload` 는 쓰지 말 것** — torch 무거운 import 로 reload 가 멈추고 WatchFiles 가 편집을 놓치며 워커 고아 소켓으로 포트 정리가 꼬인다(검증됨). 대신 백엔드 변경을 모아 재시작 1회로 최소화. (인앱 프로세스를 `taskkill /F` 하면 그 백그라운드 작업이 'exit 1 실패'로 뜨는데, 시작 실패가 아니라 강제종료 흔적이다.) 인앱 프로세스는 클로드 앱 종료/업데이트 시 함께 죽는다 → 독립 유지는 `bin\prod.bat`.
- **Git**: `main` 에서 직접 작업, **작업 완료 시 묻지 말고 자동으로 커밋**(Conventional Commits, 제목·본문 한국어). 피처 브랜치·PR 금지. **`git push`·배포는 사용자가 직접** — 에이전트는 로컬 커밋까지만.
- **노골적·사적 콘텐츠 git 분리**: 비속어·성적·개인 수위가 담긴 프롬프트/문구/치환 규칙은 코드·문서·커밋 메시지에 직접 박지 말고 **gitignore 된 오버라이드 파일**로 분리(커밋 코드엔 점잖은 기본값만). 예: `diary_prompts.yaml`(ignore) ↔ `diary_prompts.example.yaml`(커밋 틀). 상세는 copilot-instructions §Git 워크플로.
- **`.bat`/`.cmd`/`.ps1` 은 비ASCII 금지**(주석 포함, Windows CP949 파싱 오류 방지). 소스 코드 주석은 한국어.
- **문서 갱신**: 코드 변경이 문서에 영향을 주면 같은 디렉토리 README → 없으면 `docs/` 관련 파일 갱신. 새 문서는 함부로 만들지 않는다.
- **PowerShell 도구는 Windows PowerShell 5.1** — `??`(null 병합), 삼항 연산자 미지원. `if/else` 로 작성.
- **인터넷 노출 금지**(로컬/LAN + 자체 TLS 전제).
