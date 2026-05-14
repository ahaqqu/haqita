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
echo  [3] Dry-run Lotte  (no OCR, just check for new images)
echo  [4] Dry-run Superindo
echo  [5] Consolidate ^& build index.html
echo  [6] Full pipeline  (Lotte + Superindo + Consolidate)
echo  [7] Open index.html in browser
echo  [8] Health check
echo  [0] Exit
echo.
set /p choice="Your choice: "

if "%choice%"=="1" goto RUN_LOTTE
if "%choice%"=="2" goto RUN_SUPERINDO
if "%choice%"=="3" goto RUN_LOTTE_DRY
if "%choice%"=="4" goto RUN_SUPERINDO_DRY
if "%choice%"=="5" goto RUN_CONSOLIDATE
if "%choice%"=="6" goto FULL_PIPELINE
if "%choice%"=="7" goto OPEN_HTML
if "%choice%"=="8" goto HEALTH_CHECK
if "%choice%"=="0" goto END

echo Invalid choice. Press any key to try again...
pause >nul
goto MENU

:RUN_LOTTE
cls
echo ========================================
echo  Scraping Lotte Mart
echo ========================================
echo.
python scripts/scrapers/lotte_qwen.py
echo.
pause
goto MENU

:RUN_SUPERINDO
cls
echo ========================================
echo  Scraping Superindo
echo ========================================
echo.
python scripts/scrapers/superindo_qwen.py
echo.
pause
goto MENU

:RUN_LOTTE_DRY
cls
echo ========================================
echo  Dry-run Lotte (no OCR)
echo ========================================
echo.
python scripts/scrapers/lotte_qwen.py --dry-run
echo.
pause
goto MENU

:RUN_SUPERINDO_DRY
cls
echo ========================================
echo  Dry-run Superindo (no OCR)
echo ========================================
echo.
python scripts/scrapers/superindo_qwen.py --dry-run
echo.
pause
goto MENU

:RUN_CONSOLIDATE
cls
echo ========================================
echo  Consolidating Promo Data
echo ========================================
echo.
python scripts/consolidate.py
echo.
pause
goto MENU

:FULL_PIPELINE
cls
echo ========================================
echo  Full Pipeline
echo ========================================
echo.
echo [1/4] Health check...
python scripts/health_check.py
if %errorlevel% neq 0 (
  echo Health check failed. Aborting pipeline.
  pause
  goto MENU
)
echo [2/4] Scraping Lotte...
python scripts/scrapers/lotte_qwen.py
echo [3/4] Scraping Superindo...
python scripts/scrapers/superindo_qwen.py
echo [4/4] Consolidating...
python scripts/consolidate.py
echo.
echo Pipeline complete. Opening browser...
start /B python -m http.server 8000 --directory .
timeout /t 1 /nobreak >nul
start http://localhost:8000/index.html
echo.
pause
goto MENU

:OPEN_HTML
cls
echo ========================================
echo  Opening index.html
echo ========================================
echo.
echo Starting local server...
start /B python -m http.server 8000 --directory .
timeout /t 1 /nobreak >nul
start http://localhost:8000/index.html
echo Browser should open. If not, visit http://localhost:8000/index.html
echo.
pause
goto MENU

:HEALTH_CHECK
cls
echo ========================================
echo  Health Check
echo ========================================
echo.
python scripts/health_check.py
echo.
pause
goto MENU

:END
cls
echo Goodbye!
timeout /t 2 /nobreak >nul
