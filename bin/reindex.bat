@echo off
REM ============================================================
REM  flayAI - apply source changes (reindex)
REM    Call when JSON/posters/videos under K:\Crazy\* change.
REM    Each stage is incremental (already-processed rows auto-skip).
REM
REM  Usage: reindex.bat <quick|sync|full|clean> [apply]
REM
REM  quick : metadata only (light/fast, no AI)
REM          load   : K:\Crazy\Info\*.json -> SQLite videos
REM          scan   : poster scan + kind reclassify (instance/archive)
REM          history: history.csv -> SQLite usage_log
REM          fts    : rebuild videos_fts
REM          sync-payload : push kind/playable changes to Qdrant 4 collections
REM
REM  sync  : quick + text AI (daily sync)
REM          translate    : JP/EN title/desc -> KO
REM          embed        : bge-m3 -> Qdrant videos (1024d)
REM          sync-payload : same as above
REM
REM  full  : sync + all visual/face/OCR AI (nightly/weekend)
REM          embed-clip    : OpenCLIP -> Qdrant posters_clip (768d)
REM          extract-faces : InsightFace -> Qdrant faces (512d)
REM          cluster-faces : mutual-kNN + Union-Find + actress auto-mapping
REM          ocr-posters   : RapidOCR -> Qdrant poster_ocr (1024d)
REM          sync-payload  : once more at the end
REM
REM  clean : orphan cleanup (poster file gone / video gone from JSON / Qdrant-only opus)
REM            reindex.bat clean           -> dry-run (counts only)
REM            reindex.bat clean apply     -> actual delete
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

if /i "%MODE%"=="quick" goto :finalize

echo.
echo --- translate (JP/EN -^> KO)
%CLI% translate
if errorlevel 1 goto :fail

echo.
echo --- embed (bge-m3 -^> Qdrant videos)
%CLI% embed
if errorlevel 1 goto :fail

if /i "%MODE%"=="sync" goto :finalize

echo.
echo --- embed-clip (OpenCLIP -^> Qdrant posters_clip)
%CLI% embed-clip
if errorlevel 1 goto :fail

echo.
echo --- extract-faces (InsightFace -^> Qdrant faces)
%CLI% extract-faces
if errorlevel 1 goto :fail

echo.
echo --- cluster-faces (mutual-kNN + Union-Find)
%CLI% cluster-faces
if errorlevel 1 goto :fail

echo.
echo --- ocr-posters (RapidOCR -^> Qdrant poster_ocr)
%CLI% ocr-posters
if errorlevel 1 goto :fail

:finalize
echo.
echo --- fts (videos_fts rebuild - reflects latest title_ko/desc_ko)
%CLI% fts
if errorlevel 1 goto :fail

echo.
echo --- sync-payload (kind/playable Qdrant sync)
%CLI% sync-payload
if errorlevel 1 goto :fail
goto :done

:clean
echo.
if /i "%ARG2%"=="apply" (
    echo --- cleanup --apply ^(actual delete^)
    %CLI% cleanup --apply
) else (
    echo --- cleanup ^(dry-run; actual delete: reindex.bat clean apply^)
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
echo   clean  : orphan dry-run.  actual delete: reindex.bat clean apply
exit /b 1
