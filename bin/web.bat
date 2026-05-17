@echo off
REM ============================================================
REM  flayAI - Web 프론트엔드 (Next.js dev)
REM    포트     : 127.0.0.1:3000
REM    위치     : apps/web
REM    의존성   : API(8000)
REM    사전요건 : apps/web 에서 `npm install` 1회 완료
REM
REM  사용법: web.bat <start|stop|restart>
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
