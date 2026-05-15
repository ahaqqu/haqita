@echo off
title Haqita - Grocery Price Tool
setlocal enabledelayedexpansion

:MENU
cls
echo ========================================
echo        Haqita - Grocery Price Tool
echo ========================================
echo.
echo  [1] Scrape Lotte Mart promos
echo  [2] Scrape Superindo promos
echo  [3] Dry-run Lotte
echo  [4] Dry-run Superindo
echo  [5] Integration tests  (OCR + asserts)
echo  [6] Consolidate prices  (Docker)
echo  [7] Matching pipeline tests
echo  [0] Exit
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto RUN_LOTTE
if "%choice%"=="2" goto RUN_SUPERINDO
if "%choice%"=="3" goto RUN_LOTTE_DRY
if "%choice%"=="4" goto RUN_SUPERINDO_DRY
if "%choice%"=="5" goto RUN_INTEGRATION
if "%choice%"=="6" goto RUN_CONSOLIDATE
if "%choice%"=="7" goto RUN_MATCHING
if "%choice%"=="0" goto END

echo Invalid choice. Press any key to try again...
pause >nul
goto MENU

:RUN_LOTTE
cls
echo ========================================
echo  Scraping Lotte Mart Promos
echo ========================================
echo.
python scripts/scrapers/lotte.py
echo.
pause
goto MENU

:RUN_SUPERINDO
cls
echo ========================================
echo  Scraping Superindo Promos
echo ========================================
echo.
python scripts/scrapers/superindo.py
echo.
pause
goto MENU

:RUN_LOTTE_DRY
cls
echo ========================================
echo  Dry-run Lotte Mart (no OCR)
echo ========================================
echo.
python scripts/scrapers/lotte.py --dry-run
echo.
pause
goto MENU

:RUN_SUPERINDO_DRY
cls
echo ========================================
echo  Dry-run Superindo (no OCR)
echo ========================================
echo.
python scripts/scrapers/superindo.py --dry-run
echo.
pause
goto MENU

:RUN_INTEGRATION
cls
echo ========================================
echo  Integration Tests
echo ========================================
echo.
echo  Runs OCR on real brochure images and
echo  compares output against expected asserts.
echo.
call "tests\integration\run_integration_tests.bat"
echo.
pause
goto MENU

:RUN_CONSOLIDATE
cls
echo ========================================
echo  Consolidation Pipeline
echo ========================================
echo.
echo  Running in Docker...
echo.
docker compose up --build
echo.
pause
goto MENU

:RUN_MATCHING
cls
echo ========================================
echo  Matching Pipeline Tests
echo ========================================
echo.
python -m pytest tests/matching/ -v
echo.
pause
goto MENU

:END
cls
echo Goodbye!
timeout /t 2 /nobreak >nul
