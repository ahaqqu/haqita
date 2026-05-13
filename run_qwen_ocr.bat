@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Qwen2.5VL Product Promo OCR Processor
echo  Runs on Windows with Ollama + Qwen2.5VL
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

REM Default QWN_MODEL if not set
if not defined QWN_MODEL set QWN_MODEL=3b
echo Model: Qwen2.5VL %QWN_MODEL%
echo.

REM Map model name
if "%QWN_MODEL%"=="7b" (
    set OLLAMA_MODEL=qwen2.5vl:7b
) else (
    set OLLAMA_MODEL=qwen2.5vl:3b
)

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
python -c "import requests; r=requests.get('http://localhost:11434/api/tags'); models=[m['name'] for m in r.json().get('models',[])]; exit(0 if '%OLLAMA_MODEL%' in models else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Model '%OLLAMA_MODEL%' not found. Pulling it now...
    echo This may take a while (several GB download).
    ollama pull %OLLAMA_MODEL%
    if errorlevel 1 (
        echo ERROR: Failed to pull model. Check your internet connection.
        pause
        exit /b 1
    )
)

echo.
echo Starting Qwen2.5VL OCR processing...
echo.

REM Pass QWN_MODEL to Python and run
set QWN_MODEL=%QWN_MODEL%
python qwen_ocr_processor.py

echo.
echo ========================================
echo  Processing complete!
echo ========================================
pause
