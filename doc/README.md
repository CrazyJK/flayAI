# flayAI 문서

웹/JS 개발자를 위한 flayAI 가이드. 이 폴더의 문서들은 다음 순서로 읽으면 좋습니다.

| # | 파일 | 내용 |
|---|------|------|
| 1 | [overview.md](overview.md) | 무엇을 만드는가, 왜 만드는가, 큰 그림 |
| 2 | [architecture.md](architecture.md) | 컴포넌트 구조와 저장소 (SQLite / Qdrant / Ollama) |
| 3 | [indexing-pipeline.md](indexing-pipeline.md) | 데이터 → 검색 가능한 인덱스로 만드는 단계 (M1~M5) |
| 4 | [chat-and-rag.md](chat-and-rag.md) | "회사 배경 영상" 한 줄이 답으로 돌아오기까지 |
| 5 | [api-reference.md](api-reference.md) | REST 엔드포인트 목록 |
| 6 | [dev-guide.md](dev-guide.md) | 로컬 실행, 자주 쓰는 명령 |

상위 문서로 [`AI_PLAN.md`](../AI_PLAN.md) 가 있습니다. 거기는 전체 설계 명세이고,
이 폴더는 **이미 구현된 것을 기준으로 한 동작 설명서**입니다.

## 한 줄 요약

> 내 PC에 있는 비디오 컬렉션 메타데이터(JSON·CSV)와 포스터 이미지를 LLM 챗봇으로 자연어 검색하기.
> 로컬 전용. 외부 노출 없음.

## 기술 스택 (한눈에)

- **백엔드**: Python 3.12 + FastAPI (포트 8000)
- **프론트**: Next.js 16 + React 19 + Tailwind 4 (포트 3000)
- **벡터 DB**: Qdrant (Docker, 포트 6333) — 4 컬렉션
- **관계 DB**: SQLite (`data/sqlite/flay.db`) — 메타데이터 + FTS5
- **LLM**: Ollama 로 띄운 Qwen2.5 14B (abliterated) — 한국어 + 도구 호출
- **임베딩**: BGE-M3 (1024d, 텍스트), OpenCLIP ViT-L/14 (768d, 이미지)
- **얼굴**: InsightFace buffalo_l (512d)
- **OCR**: RapidOCR (ONNX Runtime)

## 흐름 한 장 요약

```
사용자가 채팅
   ↓
Next.js (SSE)
   ↓
FastAPI /api/chat
   ↓
RAG 라우터 → Ollama LLM 에 "tool 써서 답해" 라고 요청
   ↓
LLM 이 search_videos(actress="aoi", year=2023) 같은 도구 호출
   ↓
SQLite + Qdrant 하이브리드 검색 (FTS5 + 벡터)
   ↓
결과를 LLM 에 다시 넣어 자연어 답변 생성 (스트리밍)
   ↓
SSE 로 토큰 단위 전송
```

자세한 건 [chat-and-rag.md](chat-and-rag.md).
