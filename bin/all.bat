@echo off
REM ============================================================
REM  flayAI - 전체 프로세스 일괄 제어
REM    구성     : qdrant(6333) + ollama(11434) + api(8000) + web(3000)
REM    start    : qdrant -> ollama -> api -> web (의존성 순)
REM    stop     : web -> api -> ollama -> qdrant (역순)
REM    restart  : stop -> 3s -> start
REM    status   : 4개 포트 LISTEN 상태 + qdrant 컨테이너 상태
REM
REM  사용법: all.bat <start|stop|restart|status>
REM ============================================================
setlocal enabledelayedexpansion
set "ACTION=%~1"
set "BIN=%~dp0"

if /i "%ACTION%"=="start"   goto :start
if /i "%ACTION%"=="stop"    goto :stop
if /i "%ACTION%"=="restart" goto :restart
if /i "%ACTION%"=="status"  goto :status
echo Usage: all.bat ^<start^|stop^|restart^|status^>
exit /b 1

:start
call "%BIN%qdrant.bat" start
timeout /t 3 /nobreak >nul
call "%BIN%ollama.bat" start
timeout /t 2 /nobreak >nul
call "%BIN%api.bat" start
timeout /t 3 /nobreak >nul
call "%BIN%web.bat" start
echo.
echo [all start] done. open https://ai.kamoru.jk:3000
goto :eof

:stop
call "%BIN%web.bat" stop
call "%BIN%api.bat" stop
call "%BIN%ollama.bat" stop
call "%BIN%qdrant.bat" stop
echo.
echo [all stop] done.
goto :eof

:restart
call "%~f0" stop
timeout /t 3 /nobreak >nul
call "%~f0" start
goto :eof

:status
echo === flayAI status ===
call :check  8000 api
call :check  3000 web
call :check  6333 qdrant
call :check 11434 ollama
echo.
echo --- docker (flayai-qdrant) ---
docker ps --filter "name=flayai-qdrant" --format "  {{.Names}}  {{.Status}}"
goto :eof

:check
set "PORT=%~1"
set "NAME=%~2"
set "PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set "PID=%%P"
if defined PID (
    echo   [UP  ]  %NAME%   port %PORT%   pid !PID!
) else (
    echo   [DOWN]  %NAME%   port %PORT%
)
exit /b 0
