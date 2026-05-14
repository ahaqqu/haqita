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
echo  [5] Run standalone OCR on images
echo  [6] Run integration tests  (requires Ollama)
echo  [0] Exit
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto RUN_LOTTE
if "%choice%"=="2" goto RUN_SUPERINDO
if "%choice%"=="3" goto RUN_LOTTE_DRY
if "%choice%"=="4" goto RUN_SUPERINDO_DRY
if "%choice%"=="5" goto RUN_OCR
if "%choice%"=="6" goto RUN_INTEGRATION
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
python scripts/scrapers/lotte_qwen.py
echo.
pause
goto MENU

:RUN_SUPERINDO
cls
echo ========================================
echo  Scraping Superindo Promos
echo ========================================
echo.
python scripts/scrapers/superindo_qwen.py
echo.
pause
goto MENU

:RUN_LOTTE_DRY
cls
echo ========================================
echo  Dry-run Lotte Mart (no OCR)
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

:RUN_OCR
cls
echo ========================================
echo  Running OCR on Local Images
echo ========================================
echo.
python scripts/qwen_ocr_processor.py
echo.
pause
goto MENU

:RUN_INTEGRATION
cls
echo ========================================
echo  Integration Tests
echo ========================================
echo.
echo  This will run OCR on a real brochure image
echo  using Ollama. Ensure Ollama is running.
echo.
call "tests\integration\run_integration_tests.bat"
echo.
pause
goto MENU

:END
cls
echo Goodbye!
timeout /t 2 /nobreak >nul
