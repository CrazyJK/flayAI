@echo off
REM ============================================================
REM  flayAI - Ollama 로컬 LLM 서버
REM    포트     : 127.0.0.1:11434
REM    모델     : huihui_ai/qwen2.5-abliterate:7b (config.yaml)
REM    비고     : Windows 설치판은 트레이 서비스로 상주.
REM               stop 후 트레이가 재기동하면 트레이에서 Quit 필요.
REM
REM  사용법: ollama.bat <start|stop|restart>
REM ============================================================
setlocal
set "ACTION=%~1"
if /i "%ACTION%"=="start"   goto :start
if /i "%ACTION%"=="stop"    goto :stop
if /i "%ACTION%"=="restart" goto :restart
echo Usage: ollama.bat ^<start^|stop^|restart^>
exit /b 1

:start
echo [ollama start] ollama serve
where ollama >nul 2>&1
if errorlevel 1 (
    echo   ERROR: ollama not found in PATH. install from https://ollama.com
    exit /b 1
)
start "flayAI-Ollama" cmd /k "ollama serve"
goto :eof

:stop
echo [ollama stop] killing process on port 11434 ...
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":11434 " ^| findstr "LISTENING"') do (
    echo   - taskkill /F /PID %%P
    taskkill /F /PID %%P >nul 2>&1
    set "FOUND=1"
)
if not defined FOUND echo   (no process listening on 11434)
goto :eof

:restart
call "%~f0" stop
timeout /t 3 /nobreak >nul
call "%~f0" start
goto :eof
