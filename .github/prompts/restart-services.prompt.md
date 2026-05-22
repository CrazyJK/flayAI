---
mode: agent
description: "코드 변경 후 어떤 프로세스를 재시작해야 하는지 판단하고 명령을 제시한다"
---

# 서비스 재시작

코드를 수정한 뒤 변경 사항을 반영하기 위한 재시작 가이드. FastAPI 는 `--reload` 를 쓰지 않으므로(모델 lazy load 와 궁합 문제) 수동 재시작이 필요하다.

## 무엇을 재시작할지

방금 변경한 파일 경로를 보고 판단한다:

| 변경 영역 | 재시작 |
|-----------|--------|
| `apps/api/**`, `packages/rag/**`, `packages/indexer/**`, `packages/settings.py`, `config.yaml` | `bin\api.bat restart` |
| `apps/web/**` (개발 모드) | dev 서버는 핫리로드 — 보통 불필요. `next.config`/의존성 변경 시 `bin\web.bat restart` |
| `apps/web/**` (운영 빌드) | `bin\prod.bat` (재빌드) 또는 `--skip-build` 없이 |
| `docker-compose.yml` (Qdrant) | `bin\qdrant.bat restart` |
| 전체 | `bin\all.bat restart` |

## 절차

1. 변경 파일 목록 확인 (`git status` / 방금 편집한 경로).
2. 위 표로 최소 범위의 재시작 대상 결정.
3. 명령을 제시한다. 본 PC 에 Docker/Ollama 미설치일 수 있으므로 직접 실행하지 말고 명령을 보여주고, 필요한 선행 프로세스(Qdrant/Ollama) 기동 여부도 함께 안내.
4. 확인: `bin\all.bat status`, `Invoke-RestMethod https://ai.kamoru.jk:8000/healthz`.

> 참고: API 는 `ai.kamoru.jk` + HTTPS(`.cert/`) 로 뜬다. 헬스 체크 URL 도 `https://` 다.
