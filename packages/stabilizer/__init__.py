"""영상 안정화 서브시스템.

흔들린 영상을 배경/인물 기준으로 안정화한다. 잡 모델은 인덱서와 동일하게
서브프로세스로 실행(단계 사이 자원 해제) + status.json 으로 추적.
설계: docs/video-stabilization-plan.md
"""
