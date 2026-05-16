# bin/ — 프로세스 제어 배치 파일

flayAI 프로세스별 .bat 1개 + 전체 일괄 제어 .bat 1개.
모든 .bat 은 어디서 실행해도 프로젝트 루트 기준으로 동작.

## 구성

| 파일       | 대상                       | 포트   | 진입점                                         |
|------------|----------------------------|--------|------------------------------------------------|
| api.bat    | FastAPI / uvicorn          | 8000   | `apps.api.main:app` (Python, .venv)            |
| web.bat    | Next.js dev                | 3000   | `apps/web` (`npm run dev`)                     |
| qdrant.bat | Qdrant 벡터 DB (Docker)    | 6333   | `docker compose up -d qdrant` (flayai-qdrant)  |
| ollama.bat | 로컬 LLM 서버              | 11434  | `ollama serve`                                 |
| all.bat    | 위 4개 일괄 제어 + status  | -      | qdrant → ollama → api → web (종료는 역순)      |
| reindex.bat| 인덱싱 파이프라인 (CLI 묶음)| -      | `packages.indexer.cli` 의 load/scan/.../ocr-posters |

## 사용법

```cmd
bin\api.bat      <start|stop|restart>
bin\web.bat      <start|stop|restart>
bin\qdrant.bat   <start|stop|restart>
bin\ollama.bat   <start|stop|restart>
bin\all.bat      <start|stop|restart|status>
bin\reindex.bat  <quick|sync|full|clean> [apply]
```

예시:
```cmd
bin\api.bat restart        :: API 만 재시작
bin\all.bat start          :: 전체 의존성 순서로 기동
bin\all.bat status         :: 4개 포트 + qdrant 컨테이너 상태
bin\reindex.bat quick      :: K:\Crazy\* 변경 후 메타만 빠르게 반영
bin\reindex.bat sync       :: 일상 동기화 (텍스트 AI 포함)
bin\reindex.bat full       :: 야간 풀 인덱싱 (이미지/얼굴/OCR 포함)
bin\reindex.bat clean      :: 고아 dry-run (개수 확인)
bin\reindex.bat clean apply:: 고아 실제 삭제
```

### reindex 모드

| 모드  | 단계                                                                            | 용도                |
|-------|---------------------------------------------------------------------------------|---------------------|
| quick | load → scan → history → fts → **sync-payload**                                  | 메타만, AI 없음     |
| sync  | quick + translate + embed → **sync-payload**                                    | 일상 텍스트 동기화  |
| full  | sync + embed-clip + extract-faces + cluster-faces + ocr-posters → **sync-payload** | 야간/주말 풀 인덱싱 |
| clean | cleanup (`apply` 인자 없으면 dry-run, 있으면 실제 삭제)                         | 고아 row/포인트 정리|

각 단계는 incremental 이라 이미 처리한 건 자동 skip.

- **sync-payload**: SQLite 의 `kind`(instance/archive) / `playable` 가 바뀌면
  벡터 재계산 없이 Qdrant 4 컬렉션 payload 만 갱신 (변경분만).
- **clean**: ① 파일이 사라진 포스터, ② `video.json` 원본에서 사라진 videos,
  ③ Qdrant 만 단독으로 남은 opus 를 탐지. 기본은 dry-run 으로 개수만 보고,
  `bin\reindex.bat clean apply` 로 실제 삭제 (SQLite + Qdrant 모두).

## 동작 규칙

- **start**: `start "<제목>" cmd /k ...` 로 새 콘솔창 (로그 즉시 확인).
- **stop**: 포트 LISTEN PID → `taskkill /F /PID`. `web` 은 자식 트리 포함(`/T`).
  `qdrant` 만 `docker compose stop` (데이터 보존).
- **restart**: stop → 3초 대기 → start. `qdrant` 는 `docker compose restart`.
- **all start/stop**: 의존성 순서로 직렬 호출.

## 주의

- **Docker Desktop** 실행 중이어야 qdrant 동작.
- **Node/npm** PATH 필요 (web).
- **Ollama** 트레이 앱이 자동 재기동하는 경우 트레이 아이콘에서 Quit 필요.
- 각 프로세스 로그는 자체 기록 (`logs/`).
