@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Lotte Promo Scraper + OCR
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed
    pause
    exit /b 1
)

python -c "import requests, bs4" >nul 2>&1
if errorlevel 1 (
    pip install requests beautifulsoup4
)

echo Checking Ollama status...
python -c "import requests; r=requests.get(\"http://localhost:11434/api/tags\", timeout=3)" >nul 2>&1
if errorlevel 1 goto :start_ollama
echo Ollama already running
goto :check_model

:start_ollama
echo Ollama not running, starting...
start /b "" "ollama" serve

:wait_ollama
timeout /t 3 >nul
python -c "import requests; r=requests.get(\"http://localhost:11434/api/tags\", timeout=3)" >nul 2>&1
if errorlevel 1 goto :wait_ollama
echo Ollama started

:check_model
python "%~dp0check_model.py" "qwen3-vl:2b" >nul 2>&1
if errorlevel 1 (
    echo Model not found, pulling...
    ollama pull qwen3-vl:2b
)

set DRY_RUN=
if "%1"=="--dry-run" set DRY_RUN=--dry-run
if "%1"=="-n" set DRY_RUN=--dry-run

echo.
if defined DRY_RUN (
    echo Dry-run mode
) else (
    echo Running full scrape
)
echo.
python "%~dp0scrapers\lotte.py" %DRY_RUN%

echo.
pause