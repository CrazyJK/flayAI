@echo off
REM ============================================================
REM  flayAI - Qdrant vector DB (Docker)
REM    Container  : flayai-qdrant (docker-compose.yml)
REM    Port       : 127.0.0.1:6333 (REST), 6334 (gRPC)
REM    Volume     : ./data/qdrant
REM    Collections: videos / posters_clip / faces / poster_ocr
REM    Prereq     : Docker Desktop running
REM
REM  Usage: qdrant.bat <start|stop|restart>
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
