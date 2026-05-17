@echo off
chcp 65001 >nul
REM ============================================================
REM  flayAI - Production Mode Startup
REM    Starts all processes in one terminal (no new windows).
REM    Processes run in background; logs written to logs\*.log.
REM
REM    vs. all.bat (dev):
REM      api : uvicorn without --reload
REM      web : npm run build -> next start  (no hot-reload)
REM
REM  Usage: prod.bat [--skip-build]
REM    --skip-build  skip Next.js build (reuse existing .next)
REM ============================================================
setlocal enabledelayedexpansion

set "ROOT=%~dp0.."
set "SKIP_BUILD=0"
if /i "%~1"=="--skip-build" set "SKIP_BUILD=1"

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

REM ---- 1. Qdrant (Docker detached, already background) ------
echo [1/5] Qdrant (Docker)...
pushd "%ROOT%"
docker compose up -d qdrant
if errorlevel 1 ( echo   ERROR: docker compose failed & exit /b 1 )
popd
timeout /t 3 /nobreak >nul

REM ---- 2. Ollama --------------------------------------------
echo [2/5] Ollama... ^(logs\ollama.log^)
where ollama >nul 2>&1
if errorlevel 1 ( echo   ERROR: ollama not found in PATH & exit /b 1 )
start /b cmd /c "ollama serve > %ROOT%\logs\ollama.log 2>&1"
timeout /t 2 /nobreak >nul

REM ---- 3. Next.js build (skippable) ------------------------
if "%SKIP_BUILD%"=="0" (
    echo [3/5] Next.js build... ^(logs\web-build.log^)
    pushd "%ROOT%\apps\web"
    npm run build > "%ROOT%\logs\web-build.log" 2>&1
    if errorlevel 1 (
        echo   ERROR: build failed. see logs\web-build.log
        popd
        exit /b 1
    )
    popd
    echo        build OK
) else (
    echo [3/5] Next.js build skipped ^(--skip-build^)
)

REM ---- 4. API (FastAPI, no --reload) ------------------------
echo [4/5] API ^(FastAPI^)... ^(logs\api.log^)
start /b cmd /c "cd /d %ROOT% && .venv\Scripts\python.exe -m uvicorn apps.api.main:app --host ai.kamoru.jk --port 8000 --ssl-keyfile .cert/kamoru.jk.key --ssl-certfile .cert/kamoru.jk.pem > logs\api.log 2>&1"
timeout /t 3 /nobreak >nul

REM ---- 5. Web (Next.js production server) ------------------
echo [5/5] Web ^(next start^)... ^(logs\web.log^)
start /b cmd /c "cd /d %ROOT%\apps\web && node server.js > %ROOT%\logs\web.log 2>&1"

echo.
echo ====================================================
echo  flayAI production ready.
echo    API  : https://ai.kamoru.jk:8000
echo    Web  : https://ai.kamoru.jk:3000
echo    Logs : %ROOT%\logs\
echo ====================================================
echo  Processes are running in background.
echo  To stop all : bin\all.bat stop
echo  To tail log : powershell Get-Content logs\api.log -Wait
