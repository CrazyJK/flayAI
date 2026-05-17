# flayAI

> 내 PC 의 비디오 컬렉션 메타데이터(JSON·CSV)와 포스터 이미지를
> 로컬 LLM 챗봇으로 자연어 검색하는 개인용 프로젝트.
> **완전 로컬 (외부 네트워크 노출 없음)**.

## 기술 스택

| 영역      | 기술                                                  |
|-----------|-------------------------------------------------------|
| 백엔드    | Python 3.12 + FastAPI (`:8000`)                       |
| 프론트    | Next.js 16 + React 19 + Tailwind 4 (`:3000`)          |
| 벡터 DB   | Qdrant (Docker, `:6333`) — 4 컬렉션                    |
| 관계 DB   | SQLite (`data/sqlite/flay.db`) + FTS5                 |
| LLM       | Ollama + `huihui_ai/qwen2.5-abliterate:7b` (`:11434`) |
| 임베딩    | BGE-M3 (1024d, 텍스트), OpenCLIP ViT-L/14 (768d, 이미지) |
| 얼굴      | InsightFace buffalo_l (512d)                          |
| OCR       | RapidOCR (ONNX Runtime)                               |

## 디렉토리

```
apps/        FastAPI 백엔드 + Next.js 프론트
packages/    indexer / rag / settings 등 파이썬 패키지
bin/         프로세스 제어 & 재인덱싱 배치 파일
config.yaml  데이터 경로/모델/포트 설정
data/        SQLite + Qdrant 영속 데이터
docs/         상세 가이드 (overview / architecture / ...)
logs/        실행 로그
AI_PLAN.md   전체 설계 명세 (마일스톤 M1~M9)
```

## 빠른 시작

### 1. 사전 요구

- Windows + Docker Desktop
- Python 3.12 (`.venv` 가 `uv` 로 구성됨)
- Node.js (`apps/web` 의 `npm install` 용)
- [Ollama](https://ollama.com/) 설치 후 모델 pull:
  ```cmd
  ollama pull huihui_ai/qwen2.5-abliterate:7b
  ```

### 2. 프로세스 기동

```cmd
bin\all.bat start     :: qdrant → ollama → api → web 순차 기동
bin\all.bat status    :: 4개 포트 + qdrant 컨테이너 상태
bin\all.bat stop      :: 역순 종료
```

개별 제어가 필요하면 [`bin/README.md`](bin/README.md) 참고
(`api.bat / web.bat / qdrant.bat / ollama.bat <start|stop|restart>`).

### 3. 인덱싱

원본 데이터 (`K:\Crazy\*`) 가 바뀌면:

```cmd
bin\reindex.bat quick   :: 메타만 (AI 없음, 빠름)
bin\reindex.bat sync    :: 일상 동기화 (텍스트 AI 포함)
bin\reindex.bat full    :: 야간 풀 인덱싱 (이미지/얼굴/OCR 포함)
bin\reindex.bat clean   :: 고아 dry-run  (apply 인자로 실제 삭제)
```

각 단계는 incremental — 이미 처리한 건 자동 skip.

### 4. 사용

브라우저로 <http://127.0.0.1:3000> 접속. 채팅 입력창에 자연어로 질의.

## 더 읽기

- 동작 설명서 (구현 기준): [`docs/README.md`](docs/README.md)
  - [overview](docs/overview.md) · [architecture](docs/architecture.md)
  - [indexing-pipeline](docs/indexing-pipeline.md) · [chat-and-rag](docs/chat-and-rag.md)
  - [api-reference](docs/api-reference.md) · [dev-guide](docs/dev-guide.md)
- 전체 설계/마일스톤: [`AI_PLAN.md`](AI_PLAN.md)

## 라이선스

[LICENSE](LICENSE) 참고. 개인 학습용 프로젝트.
