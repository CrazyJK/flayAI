@echo off
REM ============================================================
REM  flayAI - Qdrant 벡터 DB (Docker)
REM    컨테이너 : flayai-qdrant (docker-compose.yml)
REM    포트     : 127.0.0.1:6333 (REST), 6334 (gRPC)
REM    볼륨     : ./data/qdrant
REM    컬렉션   : videos / posters_clip / faces / poster_ocr
REM    사전요건 : Docker Desktop 실행 중
REM
REM  사용법: qdrant.bat <start|stop|restart>
REM ============================================================
setlocal
set "ACTION=%~1"
pushd "%~dp0.."
if /i "%ACTION%"=="start" (
    echo [qdrant start] docker compose up -d qdrant
    docker compose up -d qdrant
) else if /i "%ACTION%"=="stop" (
    echo [qdrant stop] docker compose stop qdrant
    docker compose stop qdrant
) else if /i "%ACTION%"=="restart" (
    echo [qdrant restart] docker compose restart qdrant
    docker compose restart qdrant
) else (
    echo Usage: qdrant.bat ^<start^|stop^|restart^>
    popd
    exit /b 1
)
popd
