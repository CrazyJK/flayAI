@echo off
REM ============================================================
REM  flayAI - 소스 변경 반영 (재인덱싱)
REM    원본 K:\Crazy\* 의 JSON/포스터/영상이 바뀌면 호출.
REM    각 단계는 incremental (이미 처리한 건 자동 skip).
REM
REM  사용법: reindex.bat <quick|sync|full|clean> [apply]
REM
REM  quick : 메타데이터만 (가볍고 빠름, AI 없음)
REM          load   : K:\Crazy\Info\*.json -> SQLite videos
REM          scan   : 포스터 스캔 + kind 재분류 (instance/archive)
REM          history: history.csv -> SQLite usage_log
REM          fts    : videos_fts 재구축
REM          sync-payload : kind/playable 변경분 Qdrant 4 컬렉션 반영
REM
REM  sync  : quick + 텍스트 AI (일상 동기화)
REM          translate    : JP/EN 제목/설명 -> KO
REM          embed        : bge-m3 -> Qdrant videos (1024d)
REM          sync-payload : 위와 동일
REM
REM  full  : sync + 모든 시각/얼굴/OCR AI (야간/주말)
REM          embed-clip    : OpenCLIP -> Qdrant posters_clip (768d)
REM          extract-faces : InsightFace -> Qdrant faces (512d)
REM          cluster-faces : HDBSCAN + 배우 자동 매핑
REM          ocr-posters   : RapidOCR -> Qdrant poster_ocr (1024d)
REM          sync-payload  : 마지막에 한 번 더
REM
REM  clean : 고아 정리 (파일 사라진 포스터 / JSON 사라진 영상 / Qdrant 단독 opus)
REM            reindex.bat clean           -> dry-run (개수만)
REM            reindex.bat clean apply     -> 실제 삭제
REM ============================================================
setlocal
set "MODE=%~1"
set "ARG2=%~2"
if /i "%MODE%"=="quick" goto :ok
if /i "%MODE%"=="sync"  goto :ok
if /i "%MODE%"=="full"  goto :ok
if /i "%MODE%"=="clean" goto :ok
goto :usage
:ok

pushd "%~dp0.."
set "PY=.venv\Scripts\python.exe"
set "CLI=%PY% -m packages.indexer.cli"
set "T0=%TIME%"

echo === reindex %MODE% : start %T0% ===

if /i "%MODE%"=="clean" goto :clean

echo.
echo --- load (JSON -^> SQLite)
%CLI% load
if errorlevel 1 goto :fail

echo.
echo --- scan (posters + classify)
%CLI% scan
if errorlevel 1 goto :fail

echo.
echo --- history (history.csv)
%CLI% history
if errorlevel 1 goto :fail

echo.
echo --- fts (videos_fts rebuild)
%CLI% fts
if errorlevel 1 goto :fail

if /i "%MODE%"=="quick" goto :sync_payload

echo.
echo --- translate (JP/EN -^> KO)
%CLI% translate
if errorlevel 1 goto :fail

echo.
echo --- embed (bge-m3 -^> Qdrant videos)
%CLI% embed
if errorlevel 1 goto :fail

if /i "%MODE%"=="sync" goto :sync_payload

echo.
echo --- embed-clip (OpenCLIP -^> Qdrant posters_clip)
%CLI% embed-clip
if errorlevel 1 goto :fail

echo.
echo --- extract-faces (InsightFace -^> Qdrant faces)
%CLI% extract-faces
if errorlevel 1 goto :fail

echo.
echo --- cluster-faces (HDBSCAN)
%CLI% cluster-faces
if errorlevel 1 goto :fail

echo.
echo --- ocr-posters (RapidOCR -^> Qdrant poster_ocr)
%CLI% ocr-posters
if errorlevel 1 goto :fail

:sync_payload
echo.
echo --- sync-payload (kind/playable Qdrant 동기화)
%CLI% sync-payload
if errorlevel 1 goto :fail
goto :done

:clean
echo.
if /i "%ARG2%"=="apply" (
    echo --- cleanup --apply ^(실제 삭제^)
    %CLI% cleanup --apply
) else (
    echo --- cleanup ^(dry-run, 실제 삭제: reindex.bat clean apply^)
    %CLI% cleanup
)
if errorlevel 1 goto :fail
goto :done

:done
echo.
echo === reindex %MODE% : done (start %T0%, end %TIME%) ===
popd
exit /b 0

:fail
echo.
echo *** FAILED at step (errorlevel %ERRORLEVEL%)
popd
exit /b 1

:usage
echo Usage: reindex.bat ^<quick^|sync^|full^|clean^> [apply]
echo.
echo   quick  : load + scan + history + fts                       + sync-payload
echo   sync   : quick + translate + embed                         + sync-payload
echo   full   : sync + embed-clip + extract-faces + cluster-faces + ocr-posters + sync-payload
echo   clean  : 고아 dry-run.  실제 삭제: reindex.bat clean apply
exit /b 1
