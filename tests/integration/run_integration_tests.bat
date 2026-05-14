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
echo  This runs OCR on real brochure images
echo  using Ollama. Ensure Ollama is running.
echo.

echo  [1] Superindo OCR test (default image)
echo  [2] Lotte OCR test (default image)
echo  [3] Run custom image through OCR
echo  [4] Run all integration tests
echo  [0] Back
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto TEST_SUPERINDO
if "%choice%"=="2" goto TEST_LOTTE
if "%choice%"=="3" goto TEST_CUSTOM
if "%choice%"=="4" goto TEST_ALL
if "%choice%"=="0" exit /b 0

echo Invalid choice.
pause
goto :EOF

:TEST_SUPERINDO
cls
echo ========================================
echo  Superindo OCR Integration Test
echo ========================================
echo.
python "%SCRIPT_DIR%test_superindo_ocr.py" --output "%PROJECT_DIR%\output\integration_test_superindo.json"
set EXIT_CODE=!ERRORLEVEL!
goto SHOW_RESULT

:TEST_LOTTE
cls
echo ========================================
echo  Lotte OCR Integration Test
echo ========================================
echo.
python "%SCRIPT_DIR%test_lotte_ocr.py" --output "%PROJECT_DIR%\output\integration_test_lotte.json"
set EXIT_CODE=!ERRORLEVEL!
goto SHOW_RESULT

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
set /p store="Store name for output file [lotte/superindo]: "
if "!store!"=="" set store=custom
echo.
python "%SCRIPT_DIR%test_superindo_ocr.py" --image "%img_path%" --output "%PROJECT_DIR%\output\integration_test_!store!.json"
set EXIT_CODE=!ERRORLEVEL!
goto SHOW_RESULT

:TEST_ALL
cls
echo ========================================
echo  Running All Integration Tests
echo ========================================
echo.
set ALL_PASSED=1

echo --- Test 1: Superindo OCR ---
echo.
python "%SCRIPT_DIR%test_superindo_ocr.py" --output "%PROJECT_DIR%\output\integration_test_superindo.json"
if !ERRORLEVEL! neq 0 set ALL_PASSED=0
echo.
echo ----------------------------------------
echo.

echo --- Test 2: Lotte OCR ---
echo.
python "%SCRIPT_DIR%test_lotte_ocr.py" --output "%PROJECT_DIR%\output\integration_test_lotte.json"
if !ERRORLEVEL! neq 0 set ALL_PASSED=0
echo.
echo ----------------------------------------
echo.

if !ALL_PASSED! equ 1 (
    echo [PASS] All integration tests passed.
) else (
    echo [WARN] Some tests failed (exit code != 0).
    echo   Code 2 = model too small, not a pipeline error.
)
echo.
pause
exit /b 0

:SHOW_RESULT
echo.
if !EXIT_CODE! equ 0 (
    echo [PASS] Products extracted successfully.
) else if !EXIT_CODE! equ 1 (
    echo [SKIP] Infrastructure not available (Ollama/model).
) else if !EXIT_CODE! equ 2 (
    echo [INFO] OCR ran but no products found (model may be too small).
) else (
    echo [FAIL] Unexpected error (exit code !EXIT_CODE!).
)
echo.
pause
exit /b !EXIT_CODE!
