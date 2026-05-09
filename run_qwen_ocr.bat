@echo off
echo ========================================
echo  Qwen2-VL Product Promo OCR Processor
echo  Runs on Windows with Ollama + Qwen2-VL
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

REM Check if Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Ollama does not appear to be running
    echo.
    echo Please start Ollama first:
    echo   1. Open a new terminal and run: ollama serve
    echo   2. Or check if Ollama is installed: https://ollama.com/download
    echo.
    echo Attempting to continue anyway...
    echo.
)

REM Run the Qwen2-VL processor
echo Starting Qwen2-VL OCR processing...
echo.
python qwen_ocr_processor.py

echo.
echo ========================================
echo Processing complete!
echo ========================================
pause
