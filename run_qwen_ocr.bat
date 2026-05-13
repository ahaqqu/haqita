@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Qwen3-VL Product Promo OCR Processor
echo  Runs on Windows with Ollama + Qwen3-VL 2B
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Check if requests library is installed
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Installing required package: requests
    pip install requests
)

REM Check if Pillow is installed
python -c "from PIL import Image" >nul 2>&1
if errorlevel 1 (
    echo Installing required package: Pillow
    pip install Pillow
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
        echo ERROR: Failed to pull model. Check your internet connection.
        pause
        exit /b 1
    )
)

echo.
echo Starting Qwen3-VL OCR processing...
echo.
python qwen_ocr_processor.py

echo.
echo ========================================
echo  Processing complete!
echo ========================================
pause
