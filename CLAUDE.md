# CLAUDE.md

Claude Code 진입점. 이 저장소는 **GitHub Copilot 과 Claude Code 를 함께** 사용하며, AI 보조 지침의 단일 진실 소스는 `.github/` 의 Copilot 문서다. 중복을 피하기 위해 Claude Code 도 아래 문서를 그대로 따른다.

## 먼저 읽을 것 (우선순위 순)

1. **[.github/copilot-instructions.md](.github/copilot-instructions.md)** — 저장소 전역 기본 지침. 응답 언어(한국어), 문서 작성 규칙, 빌드/테스트 명령, 핵심 함정, ruff/ESLint/editorconfig 규칙. **항상 적용.**
2. **[.github/instructions/](.github/instructions/)** — 경로별 세부 지침. 작업 중인 파일에 해당하는 것을 연다:
   - [python.instructions.md](.github/instructions/python.instructions.md) — 모든 `*.py`
   - [indexer.instructions.md](.github/instructions/indexer.instructions.md) — `packages/indexer/**`
   - [rag.instructions.md](.github/instructions/rag.instructions.md) — `packages/rag/**`
   - [frontend.instructions.md](.github/instructions/frontend.instructions.md) — `apps/web/**`
   - [scripts.instructions.md](.github/instructions/scripts.instructions.md) — `bin/**`, `scripts/**`
3. **[.github/prompts/](.github/prompts/)** — 반복 작업 절차(스킬): 재인덱싱 · 서비스 재시작 · RAG 도구 추가 · API 엔드포인트 추가 · 문서 동기화 점검. (Copilot 에선 `/이름` 으로 호출; Claude Code 에선 해당 파일을 열어 절차를 따른다.)
4. **[docs/](docs/README.md)** — 구현 기준 동작 설명서. 미해결 작업은 **[docs/TODO.md](docs/TODO.md)**.

> `.github/chatmodes/flayai.chatmode.md` 는 Copilot 채팅 모드 정의다. 동일한 컨텍스트를 Claude Code 도 공유한다.

## 프로젝트 한 줄 요약

로컬 비디오 컬렉션(`K:\Crazy\*`)의 메타데이터·포스터를 로컬 LLM 챗봇으로 자연어 검색하는 **완전 로컬** 개인 프로젝트. 사용자는 JS/TS/Java 에 능숙하나 AI/ML 은 입문 단계 → AI 개념은 첫 등장 시 한 단락 정의를 덧붙인다.

## 절대 잊지 말 것 (상세는 위 문서)

- **Python 실행**: `.\.venv\Scripts\python.exe` (Python 3.11). `python`/`uv run` 은 PATH 부재 또는 torch DLL 잠금 위험.
- **실제 스택값은 코드/설정에서 확인**: LLM `huihui_ai/qwen2.5-abliterate:7b`(`config.yaml`), Qdrant 4컬렉션, SQLite+FTS5(trigram), 호스트 `ai.kamoru.jk`+HTTPS(`.cert/`). 문서마다 7b/14b·3.11/3.12 표기가 엇갈리니 추정 말고 SoT 확인 ([docs/TODO.md](docs/TODO.md)).
- **재시작 필요**: FastAPI 는 자동 reload 없음 → 코드 변경 후 `bin\api.bat restart` 안내.
- **이 PC 환경**: Ollama/Docker 가 미설치일 수 있음. 구동·설치·인덱싱을 임의 실행하지 말고 명령을 제시하고 선행 조건을 안내한다.
- **문서 갱신 규칙**: 코드 변경이 문서에 영향을 주면 같은 디렉토리 README → 없으면 `docs/` 관련 파일 갱신. 새 문서는 함부로 만들지 않는다.
- **공용 인터넷 노출 금지** (로컬/LAN + 자체 TLS 전제).

## 자주 쓰는 명령

```powershell
.\.venv\Scripts\python.exe -m pytest -q            # 테스트
.\.venv\Scripts\python.exe -m ruff check .         # 린트
cd apps\web ; npm run build ; npm run lint         # 프론트
```

```cmd
bin\all.bat start | status | stop                  :: 개발 일괄 제어
bin\prod.bat                                        :: 운영 HTTPS 일괄 기동
bin\api.bat restart                                 :: API 재시작
bin\reindex.bat <quick|sync|full|clean>             :: 재인덱싱
```
