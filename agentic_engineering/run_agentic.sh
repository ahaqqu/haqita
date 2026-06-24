#!/usr/bin/env bash
# Run the haqita pipeline against dummy supermarket sites in an isolated
# workspace. The real database/ and output/ directories are never touched.
#
# The script:
# 1. Creates a temp copy of the repo under /tmp/haqita_dummy_<pid>.
# 2. Creates fresh database/ and output/ dirs inside the temp workspace.
# 3. Starts the dummy HTTP server from the temp workspace.
# 4. Runs health check and the full pipeline using the original venv.
# 5. Prints the workspace path and key result files.
#
# Usage:
#   agentic_engineering/dummy/run_agentic.sh
#   bash agentic_engineering/run_agentic.sh --keep    # do not delete temp workspace

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
KEEP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep) KEEP=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

WORKSPACE=$(mktemp -d /tmp/haqita_dummy_XXXXXX)
echo "[OK] Created isolated workspace: $WORKSPACE"

cleanup() {
    if [[ "$KEEP" -eq 0 ]]; then
        rm -rf "$WORKSPACE"
        echo "[OK] Removed isolated workspace"
    else
        echo "[OK] Kept isolated workspace: $WORKSPACE"
    fi
}
trap cleanup EXIT

echo "[*] Copying repo into workspace (excluding heavy dirs)..."
rsync -a \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='database' \
    --exclude='output' \
    --exclude='node_modules' \
    --exclude='.wrangler' \
    "$REPO_ROOT/" "$WORKSPACE/"

# Fresh dummy database and output dirs.
mkdir -p "$WORKSPACE/database/scrape/lotte" "$WORKSPACE/database/scrape/superindo"
mkdir -p "$WORKSPACE/database/ocr/lotte" "$WORKSPACE/database/ocr/superindo"
mkdir -p "$WORKSPACE/output/stage_results" "$WORKSPACE/output/html" "$WORKSPACE/output/logs"

# Use the original .env for secrets.
ln -sf "$REPO_ROOT/.env" "$WORKSPACE/.env"

cd "$WORKSPACE"

export LOTTE_URL=http://localhost:18080/lotte/all-promo-mart
export SUPERINDO_KATALOG_URL=http://localhost:18080/superindo/promosi/katalog-super-hemat/
export SUPERINDO_KORAN_URL=http://localhost:18080/superindo/promosi/promo-koran/

echo "[*] Starting dummy server..."
"$PYTHON" agentic_engineering/dummy_server.py > /tmp/dummy_server.log 2>&1 &
SERVER_PID=$!
sleep 2

if ! curl -sf http://localhost:18080/lotte/all-promo-mart > /dev/null; then
    echo "[!] Dummy server failed to start"
    cat /tmp/dummy_server.log
    exit 1
fi

echo "[*] Running health check..."
"$PYTHON" scripts/health_check.py --verbose

echo "[*] Running full pipeline..."
"$PYTHON" scripts/orchestrator.py --full --verbose || true

echo ""
echo "=== Stage status summary ==="
for f in output/stage_results/*_status.json; do
    [[ -f "$f" ]] || continue
    stage=$(basename "$f" _status.json)
    status=$("$PYTHON" -c "import json; print(json.load(open('$f')).get('status','missing'))")
    echo "  $stage: $status"
done

echo ""
echo "=== End result files ==="
for f in output/html/active_promo.json output/html/promo_catalog.json output/html/price_history.json output/html/review_queue.json; do
    if [[ -f "$f" ]]; then
        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
        echo "  $f ($size bytes)"
    else
        echo "  $f MISSING"
    fi
done

echo ""
echo "Workspace: $WORKSPACE"
