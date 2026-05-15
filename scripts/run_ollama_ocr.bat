@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Ollama Product Promo OCR Processor
echo  Runs on Windows with Ollama + Qwen3-VL
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed
    pause
    exit /b 1
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    pip install requests
)

python -c "from PIL import Image" >nul 2>&1
if errorlevel 1 (
    pip install Pillow
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

echo.
echo Starting OCR...
echo.
python "%~dp0ollama_ocr_processor.py"

echo.
pause