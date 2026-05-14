@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Lotte Promo Scraper + Qwen3-VL OCR
echo ========================================
echo.

REM Load .env file
if exist .env (
    for /f "usebackq tokens=1* delims==" %%a in (.env) do (
        if not "%%a"=="" (
            set "%%a=%%b"
        )
    )
)

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check Python dependencies
python -c "import requests, bs4" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages: requests, beautifulsoup4
    pip install requests beautifulsoup4
)

REM Check and start Ollama if needed
echo Checking Ollama status...
python -c "import requests; r=requests.get('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if errorlevel 1 (
    echo Ollama is not running. Starting Ollama...
    start /b "" "ollama" serve
    echo Waiting for Ollama to be ready...
    :wait_ollama
    timeout /t 3 /nobreak >nul
    python -c "import requests; r=requests.get('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
    if errorlevel 1 (
        goto wait_ollama
    )
    echo Ollama is now running.
) else (
    echo Ollama is already running.
)

REM Check if model exists
python -c "import requests; r=requests.get('http://localhost:11434/api/tags'); exit(0 if any('qwen3-vl:2b' in m['name'] for m in r.json().get('models',[])) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Model 'qwen3-vl:2b' not found. Pulling it now (1.9 GB)...
    ollama pull qwen3-vl:2b
    if errorlevel 1 (
        echo ERROR: Failed to pull model.
        pause
        exit /b 1
    )
)

REM Parse arguments
set DRY_RUN=
if "%1"=="--dry-run" set DRY_RUN=--dry-run
if "%1"=="-n" set DRY_RUN=--dry-run

echo.
if defined DRY_RUN (
    echo DRY-RUN MODE — will not run OCR
) else (
    echo Running full scrape + OCR
)
echo.

REM Run the scraper
python scrapers/lotte_qwen.py %DRY_RUN%

echo.
echo ========================================
echo  Done!
echo ========================================
pause
