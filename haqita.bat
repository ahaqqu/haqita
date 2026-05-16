@echo off
title Haqita - Grocery Price Tool
setlocal enabledelayedexpansion

:MENU
cls
echo ========================================
echo        Haqita - Grocery Price Tool
echo ========================================
echo.
echo  [1] Run full pipeline (Scrape → OCR → Consolidate)
echo  [2] Stage 1: Scrape
echo  [3] Stage 2: OCR
echo  [4] Stage 3: Consolidation
echo  [5] Tests
echo  [0] Exit
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto FULL_PIPELINE
if "%choice%"=="2" goto STAGE_SCRAPE
if "%choice%"=="3" goto STAGE_OCR
if "%choice%"=="4" goto STAGE_CONSOLIDATION
if "%choice%"=="5" goto STAGE_TESTS
if "%choice%"=="0" goto END

echo Invalid choice. Press any key to try again...
pause >nul
goto MENU

:: ============================================================
:: Full Pipeline
:: ============================================================

:FULL_PIPELINE
cls
echo ========================================
echo  Running Full Pipeline
echo ========================================
echo.
echo  Stage 1: Scrape all stores
echo  Stage 2: OCR all scraped images
echo  Stage 3: Consolidate (update database)
echo.
echo  Press any key to start, or Ctrl+C to cancel...
pause >nul
echo.

echo ========================================
echo  Stage 1: Scrape
echo ========================================
echo.
echo --- Lotte Mart ---
python scripts/scrapers/lotte.py
echo.
echo --- Superindo ---
python scripts/scrapers/superindo.py
echo.

echo ========================================
echo  Stage 2: OCR
echo ========================================
echo.
echo --- Lotte ---
python scripts/ocr/run_ocr.py --store lotte
echo.
echo --- Superindo ---
python scripts/ocr/run_ocr.py --store superindo
echo.

echo ========================================
echo  Stage 3: Consolidation
echo ========================================
echo.
python scripts/consolidate.py
echo.

echo ========================================
echo  Pipeline complete.
echo ========================================
echo.
pause
goto MENU

:: ============================================================
:: Stage 1: Scrape
:: ============================================================

:STAGE_SCRAPE
cls
echo ========================================
echo  Stage 1: Scrape
echo ========================================
echo.
echo  [1] Scrape all stores
echo  [2] Scrape Lotte Mart only
echo  [3] Scrape Superindo only
echo  [4] Dry-run (report new images only)
echo  [0] Back
echo.

set /p scrape_choice="Your choice: "

if "%scrape_choice%"=="1" goto SCRAPE_ALL
if "%scrape_choice%"=="2" goto SCRAPE_LOTTE
if "%scrape_choice%"=="3" goto SCRAPE_SUPERINDO
if "%scrape_choice%"=="4" goto SCRAPE_DRYRUN
if "%scrape_choice%"=="0" goto MENU

echo Invalid choice. Press any key to try again...
pause >nul
goto STAGE_SCRAPE

:SCRAPE_LOTTE
cls
echo ========================================
echo  Scrape Lotte Mart
echo ========================================
echo.
python scripts/scrapers/lotte.py
echo.
pause
goto STAGE_SCRAPE

:SCRAPE_SUPERINDO
cls
echo ========================================
echo  Scrape Superindo
echo ========================================
echo.
python scripts/scrapers/superindo.py
echo.
pause
goto STAGE_SCRAPE

:SCRAPE_ALL
cls
echo ========================================
echo  Scrape All Stores
echo ========================================
echo.
echo --- Lotte Mart ---
python scripts/scrapers/lotte.py
echo.
echo --- Superindo ---
python scripts/scrapers/superindo.py
echo.
pause
goto STAGE_SCRAPE

:SCRAPE_DRYRUN
cls
echo ========================================
echo  Scrape Dry-run
echo ========================================
echo.
echo --- Lotte Mart ---
python scripts/scrapers/lotte.py --dry-run
echo.
echo --- Superindo ---
python scripts/scrapers/superindo.py --dry-run
echo.
pause
goto STAGE_SCRAPE

:: ============================================================
:: Stage 2: OCR
:: ============================================================

:STAGE_OCR
cls
echo ========================================
echo  Stage 2: OCR
echo ========================================
echo.
echo  [1] OCR all images (both stores)
echo  [2] OCR Lotte images
echo  [3] OCR Superindo images
echo  [4] OCR specific image
echo  [5] Dry-run (report products without saving)
echo  [0] Back
echo.

set /p ocr_choice="Your choice: "

if "%ocr_choice%"=="1" goto OCR_BOTH
if "%ocr_choice%"=="2" goto OCR_LOTTE
if "%ocr_choice%"=="3" goto OCR_SUPERINDO
if "%ocr_choice%"=="4" goto OCR_SPECIFIC
if "%ocr_choice%"=="5" goto OCR_DRYRUN
if "%ocr_choice%"=="0" goto MENU

echo Invalid choice. Press any key to try again...
pause >nul
goto STAGE_OCR

:OCR_LOTTE
cls
echo ========================================
echo  OCR — Lotte
echo ========================================
echo.
python scripts/ocr/run_ocr.py --store lotte
echo.
pause
goto STAGE_OCR

:OCR_SUPERINDO
cls
echo ========================================
echo  OCR — Superindo
echo ========================================
echo.
python scripts/ocr/run_ocr.py --store superindo
echo.
pause
goto STAGE_OCR

:OCR_BOTH
cls
echo ========================================
echo  OCR — Both Stores
echo ========================================
echo.
echo --- Lotte ---
python scripts/ocr/run_ocr.py --store lotte
echo.
echo --- Superindo ---
python scripts/ocr/run_ocr.py --store superindo
echo.
pause
goto STAGE_OCR

:OCR_SPECIFIC
cls
echo ========================================
echo  OCR — Specific Image
echo ========================================
echo.
echo  Lotte images:
dir /b /s database\scrape\lotte\*.jpg database\scrape\lotte\*.jpeg database\scrape\lotte\*.png database\scrape\lotte\*.webp 2>nul
echo.
echo  Superindo images:
dir /b /s database\scrape\superindo\*.jpg database\scrape\superindo\*.jpeg database\scrape\superindo\*.png database\scrape\superindo\*.webp 2>nul
echo.
echo  Lotte OCR results:
dir /b database\ocr\lotte\*.json 2>nul
echo.
echo  Superindo OCR results:
dir /b database\ocr\superindo\*.json 2>nul
echo.
set /p img="Enter filename: "
if "%img%"=="" goto STAGE_OCR
set /p store="Store (lotte/superindo): "
if "!store!"=="" set store=lotte
echo.
python scripts/ocr/run_ocr.py --store !store! --image "!img!"
echo.
pause
goto STAGE_OCR

:OCR_DRYRUN
cls
echo ========================================
echo  OCR Dry-run
echo ========================================
echo.
echo  [1] Lotte
echo  [2] Superindo
echo  [3] Both
echo  [0] Back
echo.

set /p dry_choice="Your choice: "

if "%dry_choice%"=="1" goto OCR_LOTTE_DRY
if "%dry_choice%"=="2" goto OCR_SUPERINDO_DRY
if "%dry_choice%"=="3" goto OCR_BOTH_DRY
if "%dry_choice%"=="0" goto STAGE_OCR

echo Invalid choice. Press any key to try again...
pause >nul
goto OCR_DRYRUN

:OCR_LOTTE_DRY
cls
echo ========================================
echo  OCR Dry-run — Lotte
echo ========================================
echo.
python scripts/ocr/run_ocr.py --store lotte --dry-run
echo.
pause
goto STAGE_OCR

:OCR_SUPERINDO_DRY
cls
echo ========================================
echo  OCR Dry-run — Superindo
echo ========================================
echo.
python scripts/ocr/run_ocr.py --store superindo --dry-run
echo.
pause
goto STAGE_OCR

:OCR_BOTH_DRY
cls
echo ========================================
echo  OCR Dry-run — Both Stores
echo ========================================
echo.
echo --- Lotte ---
python scripts/ocr/run_ocr.py --store lotte --dry-run
echo.
echo --- Superindo ---
python scripts/ocr/run_ocr.py --store superindo --dry-run
echo.
pause
goto STAGE_OCR

:: ============================================================
:: Stage 3: Consolidation
:: ============================================================

:STAGE_CONSOLIDATION
cls
echo ========================================
echo  Stage 3: Consolidation
echo ========================================
echo.
echo  [1] Run consolidation
echo  [2] Dry-run (no database update)
echo  [0] Back
echo.

set /p cons_choice="Your choice: "

if "%cons_choice%"=="1" goto CONSOLIDATE_RUN
if "%cons_choice%"=="2" goto CONSOLIDATE_DRYRUN
if "%cons_choice%"=="0" goto MENU

echo Invalid choice. Press any key to try again...
pause >nul
goto STAGE_CONSOLIDATION

:CONSOLIDATE_RUN
cls
echo ========================================
echo  Consolidation
echo ========================================
echo.
echo  [1] Run natively
echo  [2] Run in Docker
echo  [0] Back
echo.

set /p run_choice="Your choice: "

if "%run_choice%"=="1" goto CONSOLIDATE_NATIVE
if "%run_choice%"=="2" goto CONSOLIDATE_DOCKER
if "%run_choice%"=="0" goto STAGE_CONSOLIDATION

echo Invalid choice. Press any key to try again...
pause >nul
goto CONSOLIDATE_RUN

:CONSOLIDATE_NATIVE
cls
echo ========================================
echo  Running Consolidation (native)
echo ========================================
echo.
python scripts/consolidate.py
echo.
pause
goto STAGE_CONSOLIDATION

:CONSOLIDATE_DOCKER
cls
echo ========================================
echo  Running Consolidation (Docker)
echo ========================================
echo.
docker compose up --build
echo.
pause
goto STAGE_CONSOLIDATION

:CONSOLIDATE_DRYRUN
cls
echo ========================================
echo  Consolidation Dry-run
echo ========================================
echo.
python scripts/consolidate.py --dry-run
echo.
pause
goto STAGE_CONSOLIDATION

:: ============================================================
:: Tests
:: ============================================================

:STAGE_TESTS
cls
echo ========================================
echo  Tests
echo ========================================
echo.
echo  [1] Integration tests (OCR)
echo  [2] Matching pipeline tests
echo  [0] Back
echo.

set /p test_choice="Your choice: "

if "%test_choice%"=="1" goto TEST_INTEGRATION
if "%test_choice%"=="2" goto TEST_MATCHING
if "%test_choice%"=="0" goto MENU

echo Invalid choice. Press any key to try again...
pause >nul
goto STAGE_TESTS

:TEST_INTEGRATION
cls
echo ========================================
echo  Integration Tests (OCR)
echo ========================================
echo.
call "tests\integration\run_integration_tests.bat"
echo.
pause
goto STAGE_TESTS

:TEST_MATCHING
cls
echo ========================================
echo  Matching Pipeline Tests
echo ========================================
echo.
python -m pytest tests/matching/ -v
echo.
pause
goto STAGE_TESTS

:: ============================================================
:: Exit
:: ============================================================

:END
cls
echo Goodbye!
timeout /t 2 /nobreak >nul
