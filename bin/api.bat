@echo off
REM ============================================================
REM  flayAI - API 서버 (FastAPI / uvicorn)
REM    포트     : 127.0.0.1:8000
REM    진입점   : apps.api.main:app
REM    의존성   : Qdrant(6333), Ollama(11434)
REM    로그     : 새 콘솔창 stdout + logs/flayai.log
REM
REM  사용법: api.bat <start|stop|restart>
REM ============================================================
setlocal
set "ACTION=%~1"
if /i "%ACTION%"=="start"   goto :start
if /i "%ACTION%"=="stop"    goto :stop
if /i "%ACTION%"=="restart" goto :restart
echo Usage: api.bat ^<start^|stop^|restart^>
exit /b 1

:start
pushd "%~dp0.."
echo [api start] FastAPI on http://127.0.0.1:8000
start "flayAI-API" cmd /k ".venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000"
popd
goto :eof

:stop
echo [api stop] killing process on port 8000 ...
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo   - taskkill /F /PID %%P
    taskkill /F /PID %%P >nul 2>&1
    set "FOUND=1"
)
if not defined FOUND echo   (no process listening on 8000)
goto :eof

:restart
call "%~f0" stop
timeout /t 3 /nobreak >nul
call "%~f0" start
goto :eof
