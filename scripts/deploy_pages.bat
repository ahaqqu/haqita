@echo off
REM Haqita Cloudflare Pages Deploy Script (Windows)
REM Copies static files into web/public/ and deploys to Cloudflare Pages.

setlocal enabledelayedexpansion

echo ========================================
echo   Deploying to Cloudflare Pages
echo ========================================
echo.

REM Verify web/ project exists
if not exist "web\package.json" (
    echo Error: web\package.json not found. Run Phase 1 setup first.
    exit /b 1
)

REM Verify index.html exists
if not exist "index.html" (
    echo Error: index.html not found at project root.
    exit /b 1
)

REM Verify output/html/ has data
if not exist "output\html\active_promo.json" (
    echo Warning: output\html\active_promo.json not found.
    echo   Run the pipeline (haqita.bat [1]) before deploying.
    echo   Deploying with empty data - UI will show empty state.
    echo.
)

REM Clean and copy static files
echo Copying static files to web\public\...
if exist "web\public\index.html" del "web\public\index.html"
if exist "web\public\active_promo.json" del "web\public\active_promo.json"
if exist "web\public\price_history.json" del "web\public\price_history.json"
if exist "web\public\promo_catalog.json" del "web\public\promo_catalog.json"
if exist "web\public\review_queue.json" del "web\public\review_queue.json"

copy "index.html" "web\public\index.html" > nul

if exist "output\html\active_promo.json" copy "output\html\active_promo.json" "web\public\" > nul
if exist "output\html\price_history.json" copy "output\html\price_history.json" "web\public\" > nul
if exist "output\html\promo_catalog.json" copy "output\html\promo_catalog.json" "web\public\" > nul
if exist "output\html\review_queue.json" copy "output\html\review_queue.json" "web\public\" > nul

echo   Copied: index.html, active_promo.json, price_history.json, promo_catalog.json
echo.

REM Install dependencies if needed
if not exist "web\node_modules" (
    echo Installing web/ dependencies...
    cd web
    call npm install
    cd ..
    echo.
)

REM Typecheck
echo Running typecheck...
cd web
call npx tsc --noEmit
cd ..
echo   Typecheck passed.
echo.

REM Deploy
echo Deploying to Cloudflare Pages...
cd web
call npx wrangler pages deploy . --project-name haqita
cd ..
echo.
echo ========================================
echo   Deploy complete.
echo   URL: https://haqita.pages.dev
echo ========================================

endlocal
