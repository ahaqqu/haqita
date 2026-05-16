@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Haqita — Consolidation Pipeline
echo ========================================
echo.

echo  [1] Run consolidation (Docker)
echo  [2] Run consolidation (native Python)
echo  [3] Run with custom input directory
echo  [0] Back
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto RUN_DOCKER
if "%choice%"=="2" goto RUN_NATIVE
if "%choice%"=="3" goto RUN_CUSTOM
if "%choice%"=="0" exit /b 0

echo Invalid choice.
pause
goto :EOF

:RUN_DOCKER
cls
echo ========================================
echo  Running Consolidation in Docker
echo ========================================
echo.
docker compose -f docker\docker-compose.yml run --build consolidate
echo.
pause
exit /b 0

:RUN_NATIVE
cls
echo ========================================
echo  Running Consolidation Natively
echo ========================================
echo.
python scripts/consolidate.py
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
