@echo off
title Haqita - Integration Tests
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..\..
set EXIT_CODE=0

cls
echo ========================================
echo   Haqita - Integration Tests
echo ========================================
echo.
echo  This will run OCR on a real brochure image
echo  using Ollama. Ensure Ollama is running.
echo.

echo  [1] Run OCR integration test (default image)
echo  [2] Run OCR integration test (custom image)
echo  [3] Run all integration tests
echo  [0] Back
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto TEST_DEFAULT
if "%choice%"=="2" goto TEST_CUSTOM
if "%choice%"=="3" goto TEST_ALL
if "%choice%"=="0" exit /b 0

echo Invalid choice.
pause
goto :EOF

:TEST_DEFAULT
cls
echo ========================================
echo  OCR Integration Test (default image)
echo ========================================
echo.
echo  Image: data/test/superindo/image-brochure/sample_katalog_1.jpg
echo.
python "%SCRIPT_DIR%test_ocr_image.py" --output "%PROJECT_DIR%\output\integration_test_result.json"
set EXIT_CODE=!ERRORLEVEL!
echo.
if !EXIT_CODE! equ 0 (
    echo [PASS] All checks passed.
) else if !EXIT_CODE! equ 1 (
    echo [FAIL] Infrastructure error (Ollama/model).
) else if !EXIT_CODE! equ 2 (
    echo [FAIL] OCR completed but no products extracted.
) else (
    echo [FAIL] Unexpected error (exit code !EXIT_CODE!).
)
echo.
echo  Results saved to: output\integration_test_result.json
echo.
pause
exit /b !EXIT_CODE!

:TEST_CUSTOM
cls
echo ========================================
echo  OCR Integration Test (custom image)
echo ========================================
echo.
set /p img_path="Enter image path: "
if "%img_path%"=="" (
    echo No path entered. Aborting.
    pause
    exit /b 1
)
if not exist "%img_path%" (
    echo File not found: %img_path%
    pause
    exit /b 1
)
echo.
python "%SCRIPT_DIR%test_ocr_image.py" --image "%img_path%" --output "%PROJECT_DIR%\output\integration_test_result.json"
set EXIT_CODE=!ERRORLEVEL!
echo.
if !EXIT_CODE! equ 0 (
    echo [PASS]
) else (
    echo [FAIL] (exit code !EXIT_CODE!)
)
echo.
pause
exit /b !EXIT_CODE!

:TEST_ALL
cls
echo ========================================
echo  Running All Integration Tests
echo ========================================
echo.

set ALL_PASSED=1

echo --- Test 1: OCR on default brochure image ---
echo.
python "%SCRIPT_DIR%test_ocr_image.py" --output "%PROJECT_DIR%\output\integration_test_result.json"
if !ERRORLEVEL! neq 0 (
    set ALL_PASSED=0
    echo [FAIL] Test 1 failed.
)
echo.
echo ----------------------------------------
echo.

if !ALL_PASSED! equ 1 (
    echo.
    echo [PASS] All integration tests passed.
) else (
    echo.
    echo [FAIL] Some integration tests failed.
)
echo.
pause
exit /b 0
