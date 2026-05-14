@echo off
title Haqita - Grocery Price Tool
setlocal enabledelayedexpansion

:LOTTE_MENU
cls
echo ========================================
echo        Haqita - Grocery Price Tool
echo ========================================
echo.
echo  What would you like to do?
echo.
echo  [1] Run Lotte Promo Scraper
echo  [2] Run Qwen3-VL OCR on local images
echo  [3] Dry-run scraper (see new promos without OCR)
echo  [4] Exit
echo.

set /p choice="Enter your choice (1-4): "

if "%choice%"=="1" goto RUN_SCRAPE
if "%choice%"=="2" goto RUN_OCR
if "%choice%"=="3" goto RUN_DRY
if "%choice%"=="4" goto END

echo Invalid choice. Press any key to try again...
pause >nul
goto LOTTE_MENU

:RUN_SCRAPE
cls
echo ========================================
echo  Running Lotte Promo Scraper + OCR
echo ========================================
echo.
call "scripts\run_lotte_scraper.bat"
echo.
pause
goto LOTTE_MENU

:RUN_DRY
cls
echo ========================================
echo  Running Lotte Promo Scraper (DRY-RUN)
echo ========================================
echo.
call "scripts\run_lotte_scraper.bat" --dry-run
echo.
pause
goto LOTTE_MENU

:RUN_OCR
cls
echo ========================================
echo  Running Qwen3-VL OCR
echo ========================================
echo.
call "scripts\run_qwen_ocr.bat"
echo.
pause
goto LOTTE_MENU

:END
cls
echo Goodbye!
timeout /t 2 /nobreak >nul
