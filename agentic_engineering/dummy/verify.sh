#!/usr/bin/env bash
# Comprehensive verification for the dummy supermarket agentic-engineering setup.
#
# This script:
# 1. Starts the dummy server.
# 2. Verifies the dummy HTML pages are reachable and contain expected image refs.
# 3. Verifies Lotte and Superindo scrapers discover the expected brochure images.
# 4. Optionally runs the full local pipeline (set RUN_PIPELINE=1).
# 5. Optionally asserts against the Cloudflare-deployed app (set CLOUDFLARE_VERIFY=1).
#
# Usage:
#   agentic_engineering/dummy/verify.sh
#   RUN_PIPELINE=1 agentic_engineering/dummy/verify.sh
#   MOCK_OCR=1 MOCK_AI_VERIFIER=1 RUN_PIPELINE=1 agentic_engineering/dummy/verify.sh
#   RUN_PIPELINE=1 CLOUDFLARE_VERIFY=1 agentic_engineering/dummy/verify.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-.venv/bin/python}"
SERVER_PID=""
FAILED=0

cleanup() {
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILED=1; }

# ---------------------------------------------------------------------------
# 1. Start dummy server
# ---------------------------------------------------------------------------
echo "=== 1. Start dummy server ==="
"$PYTHON" agentic_engineering/dummy/dummy_server.py > /tmp/dummy_server.log 2>&1 &
SERVER_PID=$!
sleep 2

if curl -sf http://localhost:18080/lotte/all-promo-mart > /dev/null; then
    pass "Dummy server responds on port 18080"
else
    fail "Dummy server does not respond on port 18080"
    cat /tmp/dummy_server.log
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Verify dummy pages contain expected image references
# ---------------------------------------------------------------------------
echo "=== 2. Verify dummy page contents ==="

LOTTE_HTML=$(curl -sf http://localhost:18080/lotte/all-promo-mart)
for img in HD-1_a23cff43.jpeg HD-2_7bbd2862.jpeg HD-3_9b977567.jpeg; do
    if echo "$LOTTE_HTML" | grep -q "$img"; then
        pass "Lotte page references $img"
    else
        fail "Lotte page missing $img"
    fi
done

KATALOG_HTML=$(curl -sf http://localhost:18080/superindo/promosi/katalog-super-hemat/)
for img in "6a3265e518c31HEMAT_E_25_(8)_DKI_1edfc525.jpg" "6a3265e510171HEMAT_E_25_(1)_DKI_6d2d6244.jpg"; do
    if echo "$KATALOG_HTML" | grep -qF "$img"; then
        pass "Superindo katalog page references $img"
    else
        fail "Superindo katalog page missing $img"
    fi
done

KORAN_HTML=$(curl -sf http://localhost:18080/superindo/promosi/promo-koran/)
if echo "$KORAN_HTML" | grep -q "ajhttd1921jun975WS-REV_5e2d6aba.jpg"; then
    pass "Superindo koran page references ajhttd1921jun975WS-REV_5e2d6aba.jpg"
else
    fail "Superindo koran page missing ajhttd1921jun975WS-REV_5e2d6aba.jpg"
fi

# ---------------------------------------------------------------------------
# 3. Verify scrapers discover expected images
# ---------------------------------------------------------------------------
echo "=== 3. Verify scraper discovery ==="

export LOTTE_URL=http://localhost:18080/lotte/all-promo-mart
export SUPERINDO_KATALOG_URL=http://localhost:18080/superindo/promosi/katalog-super-hemat/
export SUPERINDO_KORAN_URL=http://localhost:18080/superindo/promosi/promo-koran/

LOTTE_OUT=$("$PYTHON" scripts/scrapers/lotte.py --dry-run)
if echo "$LOTTE_OUT" | grep -q "Found 3 promo image(s)"; then
    pass "Lotte scraper discovers 3 images"
else
    fail "Lotte scraper did not discover 3 images"
    echo "$LOTTE_OUT"
fi

SUPERINDO_OUT=$("$PYTHON" scripts/scrapers/superindo.py --dry-run)
if echo "$SUPERINDO_OUT" | grep -q "Would check 3 image(s)"; then
    pass "Superindo scraper discovers 3 images total (2 katalog + 1 koran)"
else
    fail "Superindo scraper did not discover 3 images"
    echo "$SUPERINDO_OUT"
fi

# ---------------------------------------------------------------------------
# 4. Optional: run full local pipeline and verify acceptance criteria
# ---------------------------------------------------------------------------
if [[ "${RUN_PIPELINE:-0}" == "1" ]]; then
    echo "=== 4. Run full local pipeline ==="
    export MOCK_OCR="${MOCK_OCR:-0}"
    export MOCK_AI_VERIFIER="${MOCK_AI_VERIFIER:-0}"
    "$PYTHON" scripts/health_check.py --verbose || { fail "Health check failed"; exit 1; }
    pass "Health check passed"

    "$PYTHON" scripts/orchestrator.py --full --verbose || true

    echo "--- Stage status summary ---"
    for f in output/stage_results/*_status.json; do
        [[ -f "$f" ]] || continue
        stage=$(basename "$f" _status.json)
        status=$("$PYTHON" -c "import json,sys; d=json.load(open('$f')); print(d.get('status','missing'))")
        echo "  $stage: $status"
    done

    if "$PYTHON" -c "import json; s=json.load(open('output/stage_results/scrape_status.json')); assert s['stores']['lotte']['status'] in ('new_images','no_new') and s['stores']['superindo']['status'] in ('new_images','no_new')" 2>/dev/null; then
        pass "Scrape stage healthy"
    else
        fail "Scrape stage not healthy"
    fi

    if [[ -f output/html/active_promo.json ]]; then
        pass "output/html/active_promo.json exists"
    else
        fail "output/html/active_promo.json missing"
    fi

    echo "--- Tab content checks ---"
    if "$PYTHON" -c "import json; d=json.load(open('output/html/active_promo.json')); assert len(d.get('products',[]))>0, 'no products'" 2>/dev/null; then
        pass "Products tab has content"
    else
        fail "Products tab empty or missing"
    fi

    if "$PYTHON" -c "import json; d=json.load(open('output/html/active_promo.json')); assert len(d.get('promo_catalog',[]))>0, 'no promos'" 2>/dev/null; then
        pass "Promos tab has content"
    else
        fail "Promos tab empty or missing"
    fi

    if "$PYTHON" -c "import json; d=json.load(open('output/html/active_promo.json')); stores=[s for p in d.get('products',[])+d.get('singles',[]) for s in p.get('stores',[])]; assert any(s.get('image_path') for s in stores), 'no brochure image paths'" 2>/dev/null; then
        pass "Brochures tab has content"
    else
        fail "Brochures tab empty or missing"
    fi
else
    echo "=== 4. Skipping full pipeline (set RUN_PIPELINE=1 to run) ==="
fi

# ---------------------------------------------------------------------------
# 5. Optional: assert against Cloudflare-deployed application
# ---------------------------------------------------------------------------
if [[ "${CLOUDFLARE_VERIFY:-0}" == "1" ]]; then
    echo "=== 5. Verify Cloudflare-deployed app ==="
    CF_BASE=$("$PYTHON" -c "import yaml; print(yaml.safe_load(open('config.yaml'))['cloudflare_sync'].get('api_url','https://haqita.pages.dev/api/v1').rsplit('/api',1)[0])")
    echo "Cloudflare base URL: $CF_BASE"

    if curl -sf "${CF_BASE}/" > /dev/null; then
        pass "Cloudflare Pages root returns 200"
    else
        fail "Cloudflare Pages root unreachable"
    fi

    HEALTH=$(curl -sf "${CF_BASE}/api/v1/health" || echo '{}')
    if echo "$HEALTH" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok'; print('OK')" 2>/dev/null; then
        pass "Cloudflare API health OK"
    else
        fail "Cloudflare API health check failed: $HEALTH"
    fi

    STATS=$(curl -sf "${CF_BASE}/api/v1/stats" || echo '{}')
    if echo "$STATS" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); assert 'total_products_lotte' in d; print('OK')" 2>/dev/null; then
        pass "Cloudflare API stats endpoint returns data"
    else
        fail "Cloudflare API stats endpoint missing expected fields: $STATS"
    fi

    PRODUCTS=$(curl -sf "${CF_BASE}/api/v1/products?limit=1" || echo '{}')
    if echo "$PRODUCTS" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d.get('data'),list); print('OK')" 2>/dev/null; then
        pass "Cloudflare API products endpoint returns data"
    else
        fail "Cloudflare API products endpoint missing expected fields: $PRODUCTS"
    fi

    PROMOS=$(curl -sf "${CF_BASE}/api/v1/promos" || echo '{}')
    if echo "$PROMOS" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d.get('data'),list); print('OK')" 2>/dev/null; then
        pass "Cloudflare API promos endpoint returns data"
    else
        fail "Cloudflare API promos endpoint missing expected fields: $PROMOS"
    fi

    BROCHURES=$(curl -sf "${CF_BASE}/api/v1/brochures" || echo '{}')
    if echo "$BROCHURES" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d.get('data'),list); print('OK')" 2>/dev/null; then
        pass "Cloudflare API brochures endpoint returns data"
    else
        fail "Cloudflare API brochures endpoint missing expected fields: $BROCHURES"
    fi
else
    echo "=== 5. Skipping Cloudflare verification (set CLOUDFLARE_VERIFY=1 to run) ==="
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "=== Verification complete ==="
if [[ "$FAILED" -eq 0 ]]; then
    echo "All checks passed."
    exit 0
else
    echo "Some checks failed."
    exit 1
fi
