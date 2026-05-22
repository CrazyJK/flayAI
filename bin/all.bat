@echo off
REM ============================================================
REM  flayAI - control all processes at once
REM    Components: qdrant(6333) + ollama(11434) + api(8000) + web(3000)
REM    start    : qdrant -> ollama -> api -> web (dependency order)
REM    stop     : web -> api -> ollama -> qdrant (reverse)
REM    restart  : stop -> 3s -> start
REM    status   : 4 port LISTEN states + qdrant container status
REM
REM  Usage: all.bat <start|stop|restart|status>
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
call :start_one  6333 qdrant "%BIN%qdrant.bat"
call :start_one 11434 ollama "%BIN%ollama.bat"
call :start_one  8000 api    "%BIN%api.bat"
call :start_one  3000 web    "%BIN%web.bat"
echo.
echo [all start] done. open https://ai.kamoru.jk:3000
goto :eof

:start_one
REM  %1=port  %2=name  %3=service bat path
REM  skip if the port is already LISTENING; otherwise start and wait
set "PORT=%~1"
set "NAME=%~2"
set "SVC=%~3"
set "PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set "PID=%%P"
if defined PID (
    echo   [skip ] %NAME% already listening on port %PORT% ^(pid !PID!^)
) else (
    echo   [start] %NAME% ...
    call "%SVC%" start
    timeout /t 3 /nobreak >nul
)
exit /b 0

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
