"""일기형 대화(일상 챗 + 영구 일기) 서브시스템.

flayAI 의 로컬 인프라(Ollama abliterate LLM + Qdrant bge-m3 + SQLite FTS5)를 재활용해,
사용자의 일상 대화를 영구 저장하고 과거 대화를 회상(검색)하는 기능을 제공한다.

- schema:        SQLite 테이블(diary_sessions/diary_messages/FTS) + Qdrant 컬렉션
- store:         세션·메시지 CRUD + 회상(hybrid 검색)
- htmlutil:      레거시 일기 HTML 평문화 + base64 이미지 추출
- import_legacy: 기존 .diary 파일 일회성 임포트
- chat:          수동적 경청자 LLM 라우팅(맞장구·동의 + 회상)
"""
