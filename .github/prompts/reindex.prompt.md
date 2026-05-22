---
mode: agent
description: "원본 데이터(K:\\Crazy\\*) 변경 후 인덱스를 재구축한다"
---

# 재인덱싱

원본 `K:\Crazy\*` (video.json / 포스터 등) 가 바뀌었을 때 SQLite + Qdrant 인덱스를 갱신한다.

## 모드 선택

상황을 확인하고 적절한 모드를 제안한다 (각 단계는 증분이라 이미 처리된 건 자동 skip).

| 모드 | 명령 | 단계 | 용도 |
|------|------|------|------|
| quick | `bin\reindex.bat quick` | load→scan→history→fts→sync-payload | 메타만, AI 없음, 빠름 |
| sync | `bin\reindex.bat sync` | quick + translate + embed | 일상 텍스트 동기화 |
| full | `bin\reindex.bat full` | sync + embed-clip + extract-faces + cluster-faces + ocr-posters | 야간/주말 풀 인덱싱 (이미지/얼굴/OCR, 수 시간) |
| clean | `bin\reindex.bat clean` | 고아 dry-run (`clean apply` 로 실제 삭제) | 사라진 포스터/영상/Qdrant 고아 정리 |

단계별 직접 실행이 필요하면: `.\.venv\Scripts\python.exe -m packages.indexer.cli <load|scan|...>` (`-n N` 처음 N건, `--rebuild`/`--force` 강제, `-v` 상세).

## 절차

1. 무엇이 바뀌었는지 묻거나 추정 → 모드 추천.
2. 사전 조건 확인: Qdrant(Docker) · (AI 단계면) Ollama 기동 여부. `bin\all.bat status`.
3. 명령 제시 (이 환경에서 직접 실행하지 말고, 사용자가 실행하도록 명령을 보여준다 — 본 PC 에는 Docker/Ollama 미설치일 수 있음).
4. 진행 확인: `Get-Content data\state.json | ConvertFrom-Json`, `/admin` 대시보드, `logs\<job>.log`.

## 주의

- full 의 ocr-posters 는 CPU 라 20K 포스터에 수 시간 → 야간 권장.
- GPU 12GB: 인덱싱 중 LLM/CLIP/InsightFace 동시 로드 금지 (스크립트가 unload 조정).
- 메타(kind/playable)만 바뀌면 벡터 재계산 없이 `sync-payload` 로 충분.
