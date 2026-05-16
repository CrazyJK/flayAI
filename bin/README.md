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

## 사용법

```cmd
bin\api.bat     <start|stop|restart>
bin\web.bat     <start|stop|restart>
bin\qdrant.bat  <start|stop|restart>
bin\ollama.bat  <start|stop|restart>
bin\all.bat     <start|stop|restart|status>
```

예시:
```cmd
bin\api.bat restart        :: API 만 재시작
bin\all.bat start          :: 전체 의존성 순서로 기동
bin\all.bat status         :: 4개 포트 + qdrant 컨테이너 상태
```

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
