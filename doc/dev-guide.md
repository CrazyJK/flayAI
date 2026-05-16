# Dev Guide — 로컬에서 띄우고 만지기

## 사전 요구사항

- Windows 10/11, NVIDIA GPU (12GB 권장)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Qdrant 컨테이너)
- [Ollama for Windows](https://ollama.com/download/windows)
- Python 3.12 + [uv](https://docs.astral.sh/uv/) — `pip install uv`
- Node.js 20+ + npm (Next.js 16)
- 데이터: `K:\Crazy\` 가 마운트되어 있고 `K:\Crazy\Info\video.json` 등이 있어야 함

## 첫 셋업 (한 번만)

```powershell
# 1) Python 환경
cd C:\kamoru\Workspace\git\flayAI
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"     # pyproject.toml 의 의존성 일괄 설치

# 2) Qdrant 띄우기
docker compose up -d qdrant
curl http://127.0.0.1:6333/healthz     # 200 확인

# 3) LLM 받기
ollama pull huihui_ai/qwen2.5-abliterate:14b

# 4) 웹 의존성
cd apps\web
npm install
cd ..\..
```

자동화: `scripts/bootstrap.ps1` 가 위 단계들을 한 번에 한다.

## 데이터 인덱싱 (최초 1회 또는 데이터 갱신 시)

```powershell
# 메타 로드 (load → scan → history → fts)
python -m packages.indexer.cli all -v

# 번역 + 임베딩 (M2)
python -m packages.indexer.cli translate
python -m packages.indexer.cli embed

# 이미지 임베딩 (M4a, GPU)
python -m packages.indexer.cli embed-clip

# 얼굴 (M4b, GPU, 약 80분)
python -m packages.indexer.cli extract-faces
python -m packages.indexer.cli cluster-faces

# 포스터 OCR (M5a, CPU, 약 8시간 — 야간 권장)
python -m packages.indexer.cli ocr-posters
```

각 명령은 **증분**이 기본 — 이미 처리된 행은 자동으로 건너뜀.
강제 재처리는 `--rebuild` 또는 `--force`.

## 일상 실행

두 개의 터미널 또는 [`scripts/overnight.ps1`](../scripts/overnight.ps1) 같은 헬퍼 사용.

```powershell
# 터미널 1 — Qdrant 가 이미 떠 있다고 가정
# FastAPI (포어그라운드, 콘솔 로그 보기)
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

# 백그라운드로 띄우려면:
Start-Process -FilePath .\.venv\Scripts\python.exe `
  -ArgumentList "-m","uvicorn","apps.api.main:app","--host","127.0.0.1","--port","8000" `
  -RedirectStandardOutput "logs\api.out.log" `
  -RedirectStandardError  "logs\api.err.log" `
  -WindowStyle Hidden -PassThru
```

```powershell
# 터미널 2 — Next.js
cd apps\web
npm run dev          # http://127.0.0.1:3000
```

## 자주 쓰는 명령 모음

```powershell
# 헬스 체크
Invoke-RestMethod http://127.0.0.1:8000/healthz

# 채팅 (간단 폼)
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/chat -Method Post `
  -ContentType application/json -Body '{"query":"Alice 출연작"}'

# 포스터 OCR 검색
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/search/poster-ocr -Method Post `
  -ContentType application/json -Body '{"query":"S Model","limit":5}'

# 인덱서 상태
Get-Content data\state.json | ConvertFrom-Json

# Qdrant 컬렉션 카운트
Invoke-RestMethod http://127.0.0.1:6333/collections | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:6333/collections/videos/count
```

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 평가 (M6)

```powershell
python eval/run_eval.py            # 30 케이스 전체
python eval/run_eval.py --tag ocr  # 카테고리 필터
python eval/run_eval.py --tag actress -v
```

수락 기준: 정답률 ≥ 85%. 결과는 `eval/results/{ts}.json` 으로 자동 저장 (gitignored).

## 백업 & 복구

```powershell
# 백업 (SQLite + Qdrant snapshot)
.\scripts\backup.ps1                   # 기본 K:\Backup\flayAI\{ts}
.\scripts\backup.ps1 -DstRoot D:\Backup
```

자동 회전: 최근 7일 + 매주 일요일 분 보관.

복구: 백업 폴더의 `flay.db` 를 `data/sqlite/` 로 복사, Qdrant snapshot 파일을
`/collections/<name>/snapshots/upload` 로 POST. ([Qdrant 문서](https://qdrant.tech/documentation/concepts/snapshots/))

## 야간 자동 인덱싱

[`scripts/nightly_index.ps1`](../scripts/nightly_index.ps1) — translate → embed → (주1) 이미지/얼굴/ocr → backup.

Windows Task Scheduler 등록 예:

```powershell
schtasks /Create /SC DAILY /ST 03:00 /TN flayAI-Nightly `
  /TR "powershell.exe -ExecutionPolicy Bypass -File C:\kamoru\Workspace\git\flayAI\scripts\nightly_index.ps1"
```

## 디버그 / 진단 스크립트

`scripts/` 하위:

| 스크립트 | 용도 |
|----------|------|
| `_smoke_bge.py` | BGE-M3 임베딩 동작 smoke |
| `diag_cosine.py` | 임의 두 영상 코사인 유사도 출력 |
| `diag_metadata.py` | SQLite 통계 (FK 위반·널 비율) |
| `m2_chat_scenarios.py` | M2 수락 시나리오 7건 자동 |
| `m4_clip_recall.py` | M4 CLIP self-search recall |

## 자주 만나는 함정

| 증상 | 원인 / 해결 |
|------|-------------|
| `OSError WinError 127` (DLL load) | torch / paddle / albumentations 가 같은 native lib 을 충돌 임포트. `paddleocr` 대신 `rapidocr-onnxruntime` 사용 중인 이유. |
| `uv run` 으로 인덱서 돌리면 멈춤 | torch DLL 잠금 충돌. `.\.venv\Scripts\python.exe -m packages.indexer.cli ...` 직접 사용. |
| PowerShell `python -c "(name)..."` 파스 에러 | `(name)` 을 cmdlet 으로 해석. heredoc 으로 `.py` 파일 작성해 실행하거나 single-quote. |
| 한글 OCR 결과 콘솔 mojibake | PowerShell 콘솔 코드페이지. Qdrant 에 저장된 값은 utf-8 정상. `$env:PYTHONIOENCODING='utf-8'` 시도. |
| FastAPI 가 새 라우터를 못 본다 | 코드 변경 후 프로세스 재시작 필요. `--reload` 옵션은 lazy load 모델과 궁합이 나빠 사용 안 함. |
| Qdrant 컬렉션이 비어 있다 | 해당 인덱서 잡이 안 돌았거나, `data/state.json` 의 cursor 가 막혀 있을 수 있음. `--rebuild` 로 강제. |
| GPU OOM | LLM·CLIP·InsightFace 동시 로드 금지. 인덱서 잡 사이에 Ollama unload (nightly 가 자동 처리). |

## 파일 한 장 컨닝페이퍼

- 설정: [`config.yaml`](../config.yaml) — 경로, 모델, 가중치
- 스키마: [`packages/indexer/db.py`](../packages/indexer/db.py)
- API 엔트리: [`apps/api/main.py`](../apps/api/main.py)
- RAG 라우터: [`packages/rag/router.py`](../packages/rag/router.py)
- 도구: [`packages/rag/tools.py`](../packages/rag/tools.py)
- 검색기: [`packages/rag/retriever.py`](../packages/rag/retriever.py)
- CLI: [`packages/indexer/cli.py`](../packages/indexer/cli.py)
