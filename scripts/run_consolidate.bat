@echo off
setlocal enabledelayedexpansion

:: Load .env if it exists
if exist ".env" (
    for /f "tokens=1,* delims==" %%a in (.env) do (
        set "%%a=%%b"
    )
)

:: Default to native if RUN_MODE not set
if "!RUN_MODE!"=="" set RUN_MODE=native

echo ========================================
echo  Haqita — Consolidation Pipeline
echo ========================================
echo  Run mode: !RUN_MODE!
echo.

echo  [1] Run consolidation
echo  [2] Dry-run (no database update)
echo  [3] Run with custom input directory
echo  [0] Back
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto RUN
if "%choice%"=="2" goto DRYRUN
if "%choice%"=="3" goto RUN_CUSTOM
if "%choice%"=="0" exit /b 0

echo Invalid choice.
pause
goto :EOF

:RUN
cls
echo ========================================
echo  Running Consolidation
echo ========================================
echo.
if "!RUN_MODE!"=="docker" (
    docker compose -f docker\docker-compose.yml run --build consolidate
) else (
    python scripts/consolidate.py
)
echo.
pause
exit /b 0

:DRYRUN
cls
echo ========================================
echo  Consolidation Dry-run
echo ========================================
echo.
python scripts/consolidate.py --dry-run
echo.
pause
exit /b 0

:RUN_CUSTOM
cls
echo ========================================
echo  Consolidation — Custom Input Directory
echo ========================================
echo.
set /p dir="Input directory: "
if "%dir%"=="" set dir=output
python scripts/consolidate.py --input-dir "%dir%"
echo.
pause
exit /b 0
