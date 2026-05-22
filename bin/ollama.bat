@echo off
REM ============================================================
REM  flayAI - Ollama local LLM server
REM    Port      : 127.0.0.1:11434
REM    Model     : huihui_ai/qwen2.5-abliterate:7b (config.yaml)
REM    Note      : Windows installer runs as a tray service.
REM                If the tray restarts it after stop, Quit from the tray.
REM
REM  Usage: ollama.bat <start|stop|restart>
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
