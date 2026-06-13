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
echo  [1] Superindo OCR test (default image)
echo  [2] Lotte OCR test (default images)
echo  [3] Run custom image through OCR
echo  [4] Run all integration tests
echo  [5] Matching pipeline tests (pytest)
echo  [0] Back
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto TEST_SUPERINDO
if "%choice%"=="2" goto TEST_LOTTE
if "%choice%"=="3" goto TEST_CUSTOM
if "%choice%"=="4" goto TEST_ALL
if "%choice%"=="5" goto TEST_MATCHING
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
python "%SCRIPT_DIR%test_superindo_ocr.py"
set EXIT_CODE=!ERRORLEVEL!
goto SHOW_RESULT

:TEST_LOTTE
cls
echo ========================================
echo  Lotte OCR Integration Test
echo ========================================
echo.
python "%SCRIPT_DIR%test_lotte_ocr.py"
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
python "%SCRIPT_DIR%test_superindo_ocr.py" --image "%img_path%" --output "work\integration_test_!store!.json"
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
python "%SCRIPT_DIR%test_superindo_ocr.py"
if !ERRORLEVEL! neq 0 set ALL_PASSED=0
echo.
echo ----------------------------------------
echo.

echo --- Test 2: Lotte OCR ---
echo.
python "%SCRIPT_DIR%test_lotte_ocr.py"
if !ERRORLEVEL! neq 0 set ALL_PASSED=0
echo.
echo ----------------------------------------
echo.

if !ALL_PASSED! equ 1 (
    echo [PASS] All integration tests passed.
) else (
    echo [WARN] Some tests failed (exit code != 0).
    echo   Code 2 = no products found.
    echo   Code 4 = output differs from assert.
)
echo.
pause
exit /b 0

:TEST_MATCHING
cls
echo ========================================
echo  Matching Pipeline Tests (pytest)
echo ========================================
echo.
python -m pytest tests/matching/ -v
set EXIT_CODE=!ERRORLEVEL!
echo.
if !EXIT_CODE! equ 0 (
    echo [PASS] All matching tests passed.
) else (
    echo [FAIL] Some matching tests failed.
)
echo.
pause
exit /b !EXIT_CODE!

:SHOW_RESULT
echo.
if !EXIT_CODE! equ 0 (
    echo [PASS] Products extracted successfully, matches assert.
) else if !EXIT_CODE! equ 1 (
    echo [SKIP] Infrastructure not available (Gemini).
) else if !EXIT_CODE! equ 2 (
    echo [INFO] OCR ran but no products found.
) else if !EXIT_CODE! equ 3 (
    echo [FAIL] Preprocessing error.
) else if !EXIT_CODE! equ 4 (
    echo [DIFF] Products extracted but differ from assert.
) else (
    echo [FAIL] Unexpected error (exit code !EXIT_CODE!).
)
echo.
pause
exit /b !EXIT_CODE!
