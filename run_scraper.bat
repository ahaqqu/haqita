@echo off
REM Haqita Lotte Scraper Runner
REM Loads environment variables from .env file and runs Docker

REM Create logs directory if it doesn't exist
if not exist "data\logs" mkdir data\logs

REM Load environment variables from .env file
for /f "tokens=*" %%a in (.env) do (
    for /f "tokens=1,2 delims==" %%b in ("%%a") do (
        set %%b=%%c
    )
)

REM Run Docker with loaded environment variables
docker run --rm -v "%cd%:/app" -e LOTTE_OCR_ENGINE=%LOTTE_OCR_ENGINE% -e GOOGLE_API_KEY=%GOOGLE_API_KEY% -e LOTTE_MAX_IMAGES=%LOTTE_MAX_IMAGES% -e LOTTE_TEST_MODE=%LOTTE_TEST_MODE% haqita-scraper > data/logs/scraper.log 2>&1

echo Scraper completed. Check data/logs/scraper.log for output and data/products.csv for results.