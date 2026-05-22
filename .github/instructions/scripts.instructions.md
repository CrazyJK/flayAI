---
applyTo: "bin/**/*.bat,bin/**/*.cmd,scripts/**/*.ps1,scripts/**/*.bat"
description: "Windows 배치(.bat/.cmd) · PowerShell(.ps1) 스크립트 규칙"
---

# 스크립트 지침 (bin/ · scripts/)

Windows 전용. 프로세스 제어와 인덱싱/백업 자동화.

## 절대 규칙 — .bat / .cmd 인코딩

- **`.bat`·`.cmd` 파일에는 비ASCII 문자 금지** (주석 포함 영어로 작성). Windows CP949 콘솔에서 한글 주석이 파싱 오류를 일으킨다.
- 줄 끝은 **CRLF** (`.editorconfig` 의 `[*.{bat,cmd}]`). UTF-8 출력이 필요하면 상단에 `chcp 65001 >nul` (기존 `prod.bat` 참고).
- `.ps1` 은 LF, 비ASCII 허용(한국어 주석 OK).

## bin/ 프로세스 제어

| 파일 | 대상 | 사용 |
|------|------|------|
| `api.bat` / `web.bat` / `qdrant.bat` / `ollama.bat` | 개별 프로세스 | `<start\|stop\|restart>` |
| `all.bat` | 4개 일괄 (qdrant→ollama→api→web, 종료 역순) | `<start\|stop\|restart\|status>` |
| `prod.bat` | 운영 HTTPS 일괄 (next build→start, uvicorn no-reload) | `[--skip-build]` |
| `reindex.bat` | 인덱싱 묶음 | `<quick\|sync\|full\|clean> [apply]` |

- `start`: `start "<제목>" cmd /k ...` 로 새 콘솔창. `stop`: 포트 LISTEN PID → `taskkill /F /PID` (web 은 `/T` 자식 포함). qdrant 만 `docker compose stop/restart`.
- 새 .bat 도 어디서 실행하든 프로젝트 루트 기준으로 동작하게(`%~dp0..`) 작성.

## reindex 모드

- `quick`: load→scan→history→fts→sync-payload (AI 없음)
- `sync`: quick + translate + embed → sync-payload
- `full`: sync + embed-clip + extract-faces + cluster-faces + ocr-posters → sync-payload
- `clean`: cleanup dry-run (인자 `apply` 시 실제 삭제)

## scripts/ (PowerShell)

- `bootstrap.ps1`(첫 셋업) · `backup.ps1`(SQLite VACUUM + Qdrant snapshot) · `nightly_index.ps1`(야간 인덱싱) · `overnight.ps1` · 진단 스크립트(`diag_*`, `_check_*`).
- Python 호출은 항상 `.\.venv\Scripts\python.exe` (PATH 의 `python`/`uv run` 금지).
- PowerShell 에서 `python -c "(name)..."` 는 `(name)` 을 cmdlet 으로 파싱 → single-quote 또는 `.py` 파일로.

## 코스 수정 후

코드를 바꾸면 어떤 프로세스를 재시작해야 하는지 사용자에게 알려준다 (예: API 변경 → `bin\api.bat restart`, 프론트 빌드 변경 → `bin\prod.bat`).
