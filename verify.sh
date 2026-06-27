#!/usr/bin/env bash
# verify.sh — Run the full agentic verification in an isolated temp workspace.
#
# Creates /tmp/haqita_verify_*, starts dummy server, runs the pipeline in batch
# mode, syncs dummy data to production D1/R2, runs unit tests, asserts Cloudflare
# tab contents, and captures screenshots.
#
# Usage:
#   bash verify.sh                # full run, cleanup on exit
#   bash verify.sh --keep         # preserve temp workspace
#   bash verify.sh --skip-sync    # skip Cloudflare sync
#   bash verify.sh --skip-tabs    # skip tab assertions

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
KEEP=0
SKIP_SYNC=0
SKIP_TABS=0
FAILED=0
SERVER_PID=""
EVIDENCE_DIR="$ROOT/.omo/evidence"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep) KEEP=1; shift ;;
        --skip-sync) SKIP_SYNC=1; shift ;;
        --skip-tabs) SKIP_TABS=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILED=1; }

# Ensure evidence directory exists
mkdir -p "$EVIDENCE_DIR"

# ---------------------------------------------------------------------------
# 1. Create temp workspace
# ---------------------------------------------------------------------------
WORKSPACE=$(mktemp -d /tmp/haqita_verify_XXXXXX)
echo "[OK] Created workspace: $WORKSPACE"

cleanup() {
    if [[ "$KEEP" -eq 1 ]]; then
        echo "[OK] Preserved workspace: $WORKSPACE"
    else
        rm -rf "$WORKSPACE"
        echo "[OK] Removed workspace"
    fi
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo "[*] Copying repo into workspace..."
rsync -a \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='database' \
    --exclude='output' \
    --exclude='node_modules' \
    --exclude='.wrangler' \
    "$ROOT/" "$WORKSPACE/"

mkdir -p "$WORKSPACE/database/scrape/lotte" "$WORKSPACE/database/scrape/superindo"
mkdir -p "$WORKSPACE/database/ocr/lotte" "$WORKSPACE/database/ocr/superindo"
mkdir -p "$WORKSPACE/output/stage_results" "$WORKSPACE/output/html" "$WORKSPACE/output/logs"

# Use the real .env for secrets (needed for Gemini calls and Cloudflare API)
ln -sf "$ROOT/.env" "$WORKSPACE/.env"

cd "$WORKSPACE"

# ---------------------------------------------------------------------------
# 2. Start dummy server
# ---------------------------------------------------------------------------
echo "=== 2. Start dummy server ==="
"$PYTHON" agentic_engineering/dummy_server.py > /tmp/dummy_server.log 2>&1 &
SERVER_PID=$!
sleep 2

if curl -sf http://localhost:18080/lotte/all-promo-mart > /dev/null; then
    pass "Dummy server responds on port 18080"
else
    fail "Dummy server not responding"
    cat /tmp/dummy_server.log
    exit 1
fi

export LOTTE_URL=http://localhost:18080/lotte/all-promo-mart
export SUPERINDO_KATALOG_URL=http://localhost:18080/superindo/promosi/katalog-super-hemat/
export SUPERINDO_KORAN_URL=http://localhost:18080/superindo/promosi/promo-koran/

# ---------------------------------------------------------------------------
# 3. Run pipeline in batch mode
# ---------------------------------------------------------------------------
echo "=== 3. Run full pipeline (batch mode) ==="
export HAQITA_BATCH=1
export MOCK_OCR="${MOCK_OCR:-1}"
export MOCK_AI_VERIFIER="${MOCK_AI_VERIFIER:-1}"

# Run health check first
"$PYTHON" scripts/health_check.py --verbose || {
    fail "Health check failed"
    exit 1
}
pass "Health check passed"

# Run orchestrator
"$PYTHON" scripts/orchestrator.py --full --verbose || true

# Check stage statuses
echo "--- Stage status summary ---"
for f in output/stage_results/*_status.json; do
    [[ -f "$f" ]] || continue
    stage=$(basename "$f" _status.json)
    status=$("$PYTHON" -c "import json; print(json.load(open('$f')).get('status','missing'))")
    echo "  $stage: $status"
done

# Assert critical stages
if "$PYTHON" -c "
import json
s = json.load(open('output/stage_results/scrape_status.json'))
assert s['stores']['lotte']['status'] in ('new_images','no_new'), 'lotte scrape not healthy'
assert s['stores']['superindo']['status'] in ('new_images','no_new'), 'superindo scrape not healthy'
" 2>/dev/null; then
    pass "Scrape stage healthy"
else
    fail "Scrape stage not healthy"
fi

for stage_file in output/stage_results/ocr_status.json output/stage_results/consolidate_status.json output/stage_results/publish_html_status.json; do
    if [[ -f "$stage_file" ]]; then
        status=$("$PYTHON" -c "
import json
d = json.load(open('$stage_file'))
# Handle nested 'stores' status (ocr) — all stores must be complete
stores = d.get('stores')
if stores:
    store_statuses = [s.get('status') for s in stores.values()]
    print('complete' if all(s == 'complete' for s in store_statuses) else ','.join(store_statuses))
else:
    print(d.get('status', 'missing'))
")
        if [[ "$status" == "complete" ]]; then
            pass "$(basename $stage_file _status.json) stage complete"
        else
            fail "$(basename $stage_file _status.json) stage not complete (status=$status)"
        fi
    else
        fail "$stage_file missing"
    fi
done

# ---------------------------------------------------------------------------
# 4. Run sync_cloudflare (standalone sync) with DUMMY_DATA=1
# ---------------------------------------------------------------------------
if [[ "$SKIP_SYNC" -eq 0 ]]; then
    echo "=== 4. Sync dummy data to Cloudflare ==="
    export DUMMY_DATA=1
    if "$PYTHON" scripts/sync_cloudflare.py --verbose; then
        pass "Cloudflare sync completed"
    else
        fail "Cloudflare sync failed"
    fi
    unset DUMMY_DATA
else
    echo "=== 4. Skipping Cloudflare sync (--skip-sync) ==="
fi

# ---------------------------------------------------------------------------
# 5. Run unit tests (unset mock vars so they don't affect test behavior)
# ---------------------------------------------------------------------------
echo "=== 5. Matching unit tests ==="
unset MOCK_OCR MOCK_AI_VERIFIER
if "$PYTHON" -m pytest tests/matching/ -v; then
    pass "All matching unit tests passed"
else
    fail "Matching unit tests failed"
fi

# ---------------------------------------------------------------------------
# 6. Tab-content assertions and screenshots
# ---------------------------------------------------------------------------
if [[ "$SKIP_TABS" -eq 0 ]]; then
    echo "=== 6. Tab assertions and screenshots ==="
    if [[ -f "$ROOT/agentic_engineering/verify_tabs.py" ]]; then
        if "$PYTHON" "$ROOT/agentic_engineering/verify_tabs.py" \
            --active-promo "$WORKSPACE/output/html/active_promo.json" \
            --output-dir "$EVIDENCE_DIR"; then
            pass "Tab assertions passed, screenshots captured"
        else
            fail "Tab assertions failed"
        fi
    else
        echo "  [SKIP] verify_tabs.py not yet created (Todo 12)"
    fi
else
    echo "=== 6. Skipping tab assertions (--skip-tabs) ==="
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Verification summary ==="
if [[ "$FAILED" -eq 0 ]]; then
    echo "All checks passed."
    # Copy evidence log
    "$PYTHON" -c "
import json, shutil, sys
log = {'workspace': '$WORKSPACE', 'exit_code': 0, 'stages': {}}
for f in __import__('pathlib').Path('output/stage_results').glob('*_status.json'):
    stage = f.stem.replace('_status','')
    d = json.loads(f.read_text())
    log['stages'][stage] = d.get('status','unknown')
with open('$EVIDENCE_DIR/verify-summary.json', 'w') as f:
    json.dump(log, f, indent=2)
print('Evidence written to $EVIDENCE_DIR/verify-summary.json')
"
    exit 0
else
    echo "Some checks failed."
    exit 1
fi
