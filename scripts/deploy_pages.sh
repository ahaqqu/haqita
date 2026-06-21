#!/usr/bin/env bash
set -euo pipefail

# Haqita Cloudflare Pages Deploy Script
# Copies static files into web/public/ and deploys to Cloudflare Pages.

cd "$(dirname "$0")/.."

WEB_DIR="web"
PUBLIC_DIR="$WEB_DIR/public"
HTML_OUTPUT="output/html"

echo "========================================"
echo "  Deploying to Cloudflare Pages"
echo "========================================"
echo

# Verify web/ project exists
if [[ ! -f "$WEB_DIR/package.json" ]]; then
    echo "Error: $WEB_DIR/package.json not found. Run Phase 1 setup first."
    exit 1
fi

# Verify index.html exists
if [[ ! -f "index.html" ]]; then
    echo "Error: index.html not found at project root."
    exit 1
fi

# Verify output/html/ has data
if [[ ! -f "$HTML_OUTPUT/active_promo.json" ]]; then
    echo "Warning: $HTML_OUTPUT/active_promo.json not found."
    echo "  Run the pipeline (haqita.sh [1]) before deploying."
    echo "  Deploying with empty data — UI will show empty state."
    echo
fi

# Clean and copy static files
echo "Copying static files to $PUBLIC_DIR/..."
rm -f "$PUBLIC_DIR/index.html"
rm -f "$PUBLIC_DIR/active_promo.json"
rm -f "$PUBLIC_DIR/price_history.json"
rm -f "$PUBLIC_DIR/promo_catalog.json"
rm -f "$PUBLIC_DIR/review_queue.json"

cp "index.html" "$PUBLIC_DIR/index.html"

if [[ -f "$HTML_OUTPUT/active_promo.json" ]]; then
    cp "$HTML_OUTPUT/active_promo.json" "$PUBLIC_DIR/"
fi
if [[ -f "$HTML_OUTPUT/price_history.json" ]]; then
    cp "$HTML_OUTPUT/price_history.json" "$PUBLIC_DIR/"
fi
if [[ -f "$HTML_OUTPUT/promo_catalog.json" ]]; then
    cp "$HTML_OUTPUT/promo_catalog.json" "$PUBLIC_DIR/"
fi
if [[ -f "$HTML_OUTPUT/review_queue.json" ]]; then
    cp "$HTML_OUTPUT/review_queue.json" "$PUBLIC_DIR/"
fi

echo "  Copied: index.html, active_promo.json, price_history.json, promo_catalog.json"
echo

# Install dependencies if needed
if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    echo "Installing web/ dependencies..."
    (cd "$WEB_DIR" && npm install)
    echo
fi

# Typecheck
echo "Running typecheck..."
(cd "$WEB_DIR" && npx tsc --noEmit)
echo "  Typecheck passed."
echo

# Deploy
echo "Deploying to Cloudflare Pages..."
(cd "$WEB_DIR" && npx wrangler pages deploy . --project-name haqita)
echo
echo "========================================"
echo "  Deploy complete."
echo "  URL: https://haqita.pages.dev"
echo "========================================"
