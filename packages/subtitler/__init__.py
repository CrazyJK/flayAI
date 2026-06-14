"""자막 서브시스템 — instance 영상의 일본어 음성을 한국어 자막(.srt)으로.

흐름(상세: docs/subtitle-plan.md):
  외부에서 opus 로 신청 → subtitle_jobs 큐 적재 → 야간 드레인(cli drain)이 순차 처리.
  영상 1개당: Whisper(JP, VAD) 전사 → 번역(JP→KO) → <stem>.srt 사이드카 기록.

Whisper 전사 패스 하나가 (A)자막 생성 · (B)기존 자막 싱크수정 · (C)번역메모리 구축을
모두 떠받친다. phase 1 은 (A) 생성만 구현.
"""
