## 지침 파일 구성 (Copilot · Claude 공용)

이 저장소는 **GitHub Copilot 과 Claude Code 를 함께** 사용한다. AI 보조 지침은 계층화되어 있다.

- **이 파일** (`.github/copilot-instructions.md`): 저장소 전역 기본 지침 — 항상 적용.
- **`.github/instructions/*.instructions.md`**: 경로별 세부 지침. 각 파일의 `applyTo` 글롭에 매칭되는 파일을 편집할 때 자동 적용 (python / frontend / indexer / rag / scripts).
- **`.github/prompts/*.prompt.md`**: 반복 작업용 프롬프트. Copilot Chat 에서 `/이름` 으로 호출 (재인덱싱 · 서비스 재시작 · RAG 도구 추가 · API 엔드포인트 추가 · 문서 동기화 점검).
- **`.github/chatmodes/*.chatmode.md`**: flayAI 전용 채팅 모드.
- **`CLAUDE.md`** (루트): Claude Code 진입점 — 위 Copilot 문서들을 그대로 참조하도록 연결.

상세 동작 설명서는 [`docs/`](../docs/README.md), 검토로 드러난 미해결 작업은 [`docs/TODO.md`](../docs/TODO.md) 에 정리되어 있다.

## 기본 규칙 (우선순위 순)

우선순위가 충돌하는 경우(예: 문서 업데이트가 필요하면서 AI/ML 설명도 필요한 경우) 낮은 번호 순위를 먼저 적용한다. 즉, 1순위(언어) → 2순위(문서) → 3순위(설명 수준) 순으로 처리한다.

### 1순위: 응답 언어

- 모든 답변은 한국어로 작성한다.
- 소스 코드 주석(`.py`, `.ts`, `.tsx`, `.js`, `.jsx` 등)은 한국어로 작성한다.
- 단, `.bat`, `.cmd`, `.ps1` 파일은 비ASCII 문자 금지 — 주석도 영어로 작성한다.
  (Windows CP949 파싱 오류 방지; 자세한 이유는 핵심 함정 참조)

### 2순위: 문서 작성

- 코드 변경이 관련 문서에 영향을 미치는 경우에만 문서를 갱신한다.
- 문서 위치 규칙:
  - 변경된 코드 파일과 동일한 디렉토리에 `README.md` 가 있으면 그 파일에 작성한다.
  - 없으면 저장소 루트의 `docs/` 디렉토리에서 관련 파일을 찾아 있으면 그 파일에 작성한다. 관련 파일이 없으면 문서 작성을 생략한다(새 파일을 만들지 않는다).
- 문서 형식은 마크다운(Markdown) 으로 작성한다.

### 3순위: 설명 수준

본 프로젝트는 JS/TS/Java 등 일반 SW 개발에는 능숙하지만 AI/ML 분야는
입문 단계인 개발자의 개인 사용 및 학습용 프로젝트이다. 따라서 답변과 문서 작성 시
다음 기준을 따른다.

- AI/ML 관련 개념(임베딩, 벡터 DB, 토크나이저, RAG, 파인튜닝, 손실함수,
  모델 아키텍처 등) 이 처음 등장하면 한 단락 이내로 용어 정의를 덧붙인다.
- AI 관련 코드 변경에는 "무엇을 / 왜 / 어떤 입출력" 을 간단히 주석 또는
  설명으로 남긴다.
- 일반 프로그래밍 개념(언어 문법, 흔한 라이브러리 사용법, 디자인 패턴,
  빌드/배포 도구 등) 은 부연 설명 없이 코드/명령 중심으로 간결하게 답한다.

### 코스 수정 후에는 다음을 수행한다.

프로세스 재시작이 필요한지 알려주고, 재시작 해야 하는 bin/*.bat 파일과 명령어를 제시한다.

### Git 워크플로

개인 프로젝트이므로 별도 피처 브랜치·PR 절차를 두지 않는다.

- 작업은 `main` 브랜치에서 직접 하고, 변경이 마무리되면 곧바로 `main` 에 커밋한다 (피처 브랜치/PR 생성 금지).
- 커밋 메시지는 Conventional Commits 형식(`feat:`/`fix:`/`docs:`/`chore:` …)을 쓰되, **제목·본문은 한국어로 작성**한다(접두어와 코드 식별자는 영문 그대로).
- **`git push` 는 하지 않는다 — 원격 push 와 서버 배포(`pull`)는 사용자가 직접 수행한다.** 에이전트는 로컬 `main` 커밋까지만.

### 화면 확인 (프론트엔드)

프론트엔드 변경의 실제 동작 확인이 필요하면, 에이전트가 브라우저 도구(Claude-in-Chrome MCP 등)로 `https://ai.kamoru.jk:3000` 을 직접 띄워 확인해도 된다(자체 서명 인증서 경고는 무시). dev 서버는 hot-reload 이므로 저장 후 새로고침으로 반영된다.
- 전제: 일반 Chrome 창이 확장으로 연결돼 있어야 한다(시크릿/특수 창은 탭 그룹 미지원으로 실패할 수 있음).
- 브라우저 확인이 불가능할 때만 코드 컴파일/lint/HTTP 200 검증으로 대체하고, 시각 확인이 안 됐음을 사용자에게 알린다.

## 프로젝트 컨텍스트

로컬 비디오 컬렉션(`K:\Crazy\*`)을 자연어로 검색하는 **완전 로컬** 개인용 프로젝트.  
상세 문서: [docs/overview.md](../docs/overview.md) · [docs/architecture.md](../docs/architecture.md) · [docs/AI_PLAN.md](../docs/AI_PLAN.md)

### 컴포넌트 및 포트

| 컴포넌트 | 기술 | 포트 |
|----------|------|------|
| 백엔드 | FastAPI + uvicorn (`apps/api/`) | 8000 |
| 프론트 | Next.js 16 + React 19 + Tailwind 4 (`apps/web/`) | 3000 |
| 벡터 DB | Qdrant (Docker) | 6333 |
| LLM | Ollama `huihui_ai/qwen2.5-abliterate:7b` | 11434 |
| 관계 DB | SQLite `data/sqlite/flay.db` + FTS5 | — |

### 빌드 & 테스트 명령어

```powershell
# Python 테스트 (항상 .venv 사용, uv 는 PATH에 없을 수 있음)
.\.venv\Scripts\python.exe -m pytest -q

# 린트
.\.venv\Scripts\python.exe -m ruff check .

# 프론트엔드
cd apps\web ; npm run build ; npm run lint
```

### 프로세스 기동 (bin/*.bat)

```cmd
bin\all.bat start          # (개발) qdrant → ollama → api → web 순차 기동
bin\prod.bat               # (운영) HTTPS 일괄 기동 (next build → next start, uvicorn no-reload)
bin\api.bat restart        # API만 재시작
bin\reindex.bat quick      # 메타만 빠른 재인덱싱 (AI 없음)
bin\reindex.bat sync       # 텍스트 AI 포함 동기화
bin\reindex.bat full       # 야간 풀 인덱싱 (이미지/얼굴/OCR)
```

자세한 bat 사용법: [bin/README.md](../bin/README.md)

#### 개발 모드 — 에이전트 인앱 구동 (로그 가시성)

에이전트(Claude Code)가 개발용 api/web 을 직접 띄울 때는 별도 PowerShell 창
(`bin\api.bat`/`bin\web.bat` 의 `start cmd /k`) 대신 **클로드 앱 내부 백그라운드
프로세스**로 실행한다. 그래야 stdout 로그가 에이전트에게 실시간 스트리밍되어 즉시
진단할 수 있다. 사용자가 "서버 띄워줘 / 재시작해줘" 류로 요청하면 이 방식을 쓴다.

- API: `.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host ai.kamoru.jk --port 8000 --ssl-keyfile .cert/kamoru.jk.key --ssl-certfile .cert/kamoru.jk.pem`
- Web: `apps/web` 에서 `npm run dev`
- 사전 의존성 qdrant(6333)·ollama(11434)는 먼저 떠 있어야 한다 — 없으면 `bin\qdrant.bat`/`ollama` 로 기동 후 진행.
- **API 재시작은 수동**: FastAPI 자동 reload 없음 → 코드 변경 시 인앱 백그라운드 프로세스를 종료(8000 포트 PID `taskkill /F`) 후 다시 띄운다(별도 창 안 뜸). **`uvicorn --reload` 는 쓰지 말 것** — torch 등 무거운 import 로 reload 가 멈추고, WatchFiles 가 편집을 놓치며, multiprocessing 워커 고아 소켓으로 포트 정리가 꼬인다(검증됨, 부적합). 대신 **여러 백엔드 변경을 모아 재시작 1회로** 최소화한다.
- **참고(정상 동작)**: 인앱 백그라운드 API 를 `taskkill /F` 로 종료하면 그 백그라운드 작업이 'exit code 1 실패'로 표시된다 — 시작 실패가 아니라 강제 종료의 흔적이다. 재시작을 줄이면 이 알림도 준다.
- 포트 정리 시: `Get-NetTCPConnection -LocalPort 8000` 의 OwningProcess 가 죽은 PID 로 보이면 자식(워커)이 소켓을 상속한 것 — `Win32_Process` 로 자식 python(PPID=그 PID)을 찾아 `taskkill /F` 한다.
- **한계**: 이 프로세스들은 에이전트 세션의 자식이라 클로드 앱이 종료/업데이트되면 함께 죽는다. 앱과 독립적으로 유지하려면 `bin\*.bat`(별도 창) 또는 운영용 `bin\prod.bat` 를 쓴다.
- **운영(`bin\prod.bat`)은 변경 없음** — 단일 터미널 백그라운드 + `logs\*.log` 그대로 유지.

### 핵심 함정 (에이전트 주의)

- **Python 실행**: Python **3.11** (`.python-version`, `pyproject.toml requires-python>=3.11`). `.\.venv\Scripts\python.exe` 사용 (`python` 이나 `uv run` 이 PATH에 없을 수 있음)
- **호스팅/TLS**: API·웹은 로컬 도메인 `ai.kamoru.jk`(hosts 파일 매핑) + 자체 서명 인증서(`.cert/kamoru.jk.{key,pem}`)로 **HTTPS** 서빙. `config.yaml.server.host`, CORS 화이트리스트, `main.py` 호스트 검증 모두 `127.0.0.1`/`localhost`/`::1`/`ai.kamoru.jk` 만 허용 — **공용 인터넷 노출 금지**. (`.cert/` 는 `.gitignore`)
- **OCR 의존성**: 런타임은 `rapidocr-onnxruntime`(`packages/indexer/ocr.py`) 사용 — `pyproject.toml`/`uv.lock` 에 선언됨. (구 `paddleocr`/`paddlepaddle-gpu` 는 제거됨)
- **GPU 빌드는 uv config 로 고정 (NVIDIA GPU + CUDA 12.4 전제)**: `pyproject.toml [tool.uv]` 에서 torch/torchvision 은 PyTorch cu124 인덱스(`[[tool.uv.index]]` + `[tool.uv.sources]`)로, onnxruntime 은 CPU판 제외(`override-dependencies` 의 불가능 마커)로 잡아 둠. 그래서 `uv lock`/`uv sync` 가 GPU 빌드(`torch 2.6.0+cu124`, `torchvision 0.21.0+cu124`, `onnxruntime-gpu`)를 유지한다 → **`uv sync` 는 이제 안전**. 단 **GPU + CUDA 12.4 단일 개인 PC 전제**라, CPU/다른 CUDA 환경에 배포하면 깨질 수 있음(의도된 가정). onnxruntime CPU/GPU 는 같은 모듈명이라 공존 불가 — 둘 다 깔리면 CPU 가 GPU 를 덮어써 InsightFace 가 CPU 로 떨어지니 항상 `onnxruntime-gpu` 만 유지.
- **Qdrant v1.18+**: `collection.search()` 삭제됨 → `client.query_points(collection_name, query=vec, limit=N, with_payload=True)` 사용, 반환값은 `result.points`
- **FTS5 쿼리**: 토큰을 `"phrase"` 로 감싸고 `OR` 로 결합 (예: `"alice" OR "앨리스"`). 그냥 키워드 쓰면 CJK/짧은 토큰에서 `syntax error near "?"` 발생
- **번역 모델**: `facebook/nllb-200-distilled-600M`, `src_lang=jpn_Jpan`, `forced_bos_token_id` 로 `kor_Hang` 지정
- **Qdrant 포인트 ID**: opus 의 SHA1 앞 8 바이트(uint63) — 4개 컬렉션 공통. cross-reference 용
- **스튜디오 alias**: DB 에서 `"S1"` 같은 공식명이 아닌 `"sone"`, `"s1no1style"` 등으로 저장될 수 있음 → alias 없는 검색 필터는 0건 반환
- **CORS**: `config.yaml.server.cors_origins` 화이트리스트만 허용 (ai.kamoru.jk / localhost, http·https). 공용 인터넷 노출 금지

### Python 린트 규칙 (ruff)

새 Python 파일 작성 시 준수:
- `from typing import Iterable` 금지 → `from collections.abc import Iterable` 사용 (UP035)
- `from typing import AsyncGenerator` 금지 → `from collections.abc import AsyncGenerator` 사용 (UP035)
- 사용하지 않는 import 추가 금지 (F401)
- `.encode("utf-8")` 인자는 불필요 — `.encode()` 로만 작성 (UP012)
- 타입 어노테이션에 문자열 리터럴(`"SomeType"`) 사용 금지 — `from __future__ import annotations` 가 있으면 따옴표 불필요 (UP037)
- `useEffect` 내 제어 흐름에서 로컬 변수 할당 후 미사용 금지 (F841)
- 잘못된 타입 어노테이션 예: async generator 함수의 반환 타입은 `"anyio.abc.ByteStream"` 이 아닌 `AsyncGenerator[bytes, None]`

### TypeScript/Next.js 린트 규칙 (ESLint)

새 TSX 파일 작성 시 준수:
- 내부 페이지 링크(`href="/..."`)에 `<a>` 태그 금지 → `import Link from "next/link"` 후 `<Link>` 사용 (`@next/next/no-html-link-for-pages`)
- `useEffect` 내 동기 `setState` 호출은 `// eslint-disable-next-line react-hooks/set-state-in-effect` 로 억제 (데이터 로딩 reset 패턴 등 정상적인 경우에 한함)

### 코딩 스타일 (.editorconfig)

루트의 `.editorconfig` 가 편집기 동작을 통일한다. 새 파일 작성 시 아래 규칙을 코드에도 반영한다:

| 파일 유형 | indent | EOL | 비고 |
|-----------|--------|-----|------|
| `*.py` | 4 space | LF | ruff/black 기준 |
| `*.ts, *.tsx, *.js, *.jsx` | 2 space | LF | Prettier 기준 |
| `*.json, *.yaml, *.toml, *.css` | 2 space | LF | — |
| `*.bat, *.cmd` | — | **CRLF** | Windows 배치 파일 호환 |

- 모든 파일: UTF-8, 파일 끝 개행 필수, 줄 끝 공백 제거
- `*.md` 는 줄 끝 공백 보존 (마크다운 줄바꿈 `  ` 유지)

### 인덱서 파이프라인

CLI 진입점: `python -m packages.indexer.cli <cmd>`  
전체 흐름: `load → scan → history → fts → translate → embed`  
이미지: `embed-clip` / 얼굴: `extract-faces → cluster-faces` / OCR: `ocr-posters`  
각 단계는 **증분(incremental)** — 이미 처리된 행은 자동 skip. 강제 재처리는 `--rebuild`.
