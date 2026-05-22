@echo off
REM ============================================================
REM  flayAI - Web frontend (Next.js dev)
REM    Port     : 127.0.0.1:3000
REM    Location : apps/web
REM    Depends  : API(8000)
REM    Prereq   : run `npm install` once in apps/web
REM
REM  Usage: web.bat <start|stop|restart>
REM ============================================================
setlocal
set "ACTION=%~1"
if /i "%ACTION%"=="start"   goto :start
if /i "%ACTION%"=="stop"    goto :stop
if /i "%ACTION%"=="restart" goto :restart
echo Usage: web.bat ^<start^|stop^|restart^>
exit /b 1

:start
pushd "%~dp0..\apps\web"
echo [web start] Next.js dev on https://ai.kamoru.jk:3000
start "flayAI-Web" cmd /k "npm run dev"
popd
goto :eof

:stop
echo [web stop] killing process tree on port 3000 ...
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo   - taskkill /F /T /PID %%P
    taskkill /F /T /PID %%P >nul 2>&1
    set "FOUND=1"
)
if not defined FOUND echo   (no process listening on 3000)
goto :eof

:restart
call "%~f0" stop
timeout /t 3 /nobreak >nul
call "%~f0" start
goto :eof
