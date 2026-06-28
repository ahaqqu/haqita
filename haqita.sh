#!/usr/bin/env bash
set -u

# Change to script directory so relative paths work
cd "$(dirname "$0")"

VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"
PYTHON=""

# Check that a suitable Python interpreter is available.
find_python() {
    local py
    for py in python3.12 python3.13 python3; do
        if command -v "$py" >/dev/null 2>&1; then
            echo "$py"
            return 0
        fi
    done
    if command -v python >/dev/null 2>&1; then
        echo "python"
        return 0
    fi
    return 1
}

# Verify Python version is >= 3.12.
check_python_version() {
    local py="$1"
    local version
    version=$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$(printf '%s\n' "3.12" "$version" | sort -V | head -n1)" != "3.12" ]]; then
        echo "Error: Python 3.12+ is required. Found $version." >&2
        echo "Install it with: sudo apt install python3.12 python3.12-venv python3-pip" >&2
        exit 1
    fi
    if [[ "$(printf '%s\n' "3.14" "$version" | sort -V | head -n1)" == "3.14" ]]; then
        echo "Warning: Python $version is newer than tested (3.12-3.13). Some ML packages may fail to import." >&2
        echo "If you hit import errors, install Python 3.12 or 3.13." >&2
    fi
}

# Parse requirements.txt and return package names (strip versions/comments/extras).
parse_requirements() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        return 0
    fi
    grep -v '^#' "$file" | grep -v '^$' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' | sed -E 's/([A-Za-z0-9_.-]+).*/\1/'
}

# Check that required packages from requirements.txt are installed.
python_deps_ok() {
    local py="$1"
    local missing=()
    local pkg

    while IFS= read -r pkg; do
        [[ -z "$pkg" ]] && continue
        if ! "$py" -m pip show "$pkg" >/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done < <(parse_requirements "$REQUIREMENTS")

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Missing packages: ${missing[*]}" >&2
        return 1
    fi
    return 0
}

# Install or update the virtual environment and dependencies.
setup_environment() {
    echo "========================================"
    echo "  Haqita Setup"
    echo "========================================"
    echo

    local py
    py=$(find_python) || {
        echo "Error: Python is not installed or not in PATH." >&2
        echo "Install Python 3.12+ with: sudo apt update && sudo apt install python3.12 python3.12-venv python3-pip" >&2
        exit 1
    }
    check_python_version "$py"

    if ! "$py" -c "import ensurepip" >/dev/null 2>&1; then
        echo "The 'venv' module is not available for $py." >&2
        if command -v sudo >/dev/null 2>&1 && command -v apt >/dev/null 2>&1; then
            read -rp "Install it with sudo apt install ${py}-venv? [Y/n]: " answer
            if [[ -z "$answer" || "$answer" =~ ^[Yy]$ ]]; then
                sudo apt update
                sudo apt install -y "${py}-venv" python3-pip
                if ! "$py" -c "import ensurepip" >/dev/null 2>&1; then
                    echo "Error: failed to install the venv module." >&2
                    exit 1
                fi
            else
                echo "Install it manually with: sudo apt install ${py}-venv python3-pip" >&2
                exit 1
            fi
        else
            echo "Install it with: sudo apt install ${py}-venv python3-pip" >&2
            exit 1
        fi
    fi

    if [[ -d "$VENV_DIR" && ! -x "$VENV_DIR/bin/pip" ]]; then
        echo "Existing virtual environment is incomplete; recreating..."
        rm -rf "$VENV_DIR"
    fi

    if [[ ! -d "$VENV_DIR" ]]; then
        echo "Creating virtual environment in $VENV_DIR..."
        "$py" -m venv "$VENV_DIR"
    fi

    PYTHON="$VENV_DIR/bin/python"

    echo "Upgrading pip..."
    "$PYTHON" -m pip install --upgrade pip

    if [[ -f "$REQUIREMENTS" ]]; then
        echo "Installing dependencies from $REQUIREMENTS..."
        "$PYTHON" -m pip install -r "$REQUIREMENTS"
    else
        echo "Warning: $REQUIREMENTS not found. Skipping package installation." >&2
    fi

    if ! python_deps_ok "$PYTHON"; then
        echo "Error: dependency installation appears incomplete." >&2
        exit 1
    fi

    # Optional sanity check: warn if any installed package cannot actually be imported.
    echo "Checking imports..."
    local req_list
    req_list=$(parse_requirements "$REQUIREMENTS" | paste -sd ' ' -)
    PYTHON_REQUIREMENTS="$req_list" "$PYTHON" -c "
import importlib.util, os, sys

# Distribution name -> import module for packages that don't follow the default rule.
IMPORT_NAMES = {
    'beautifulsoup4': 'bs4',
    'Pillow': 'PIL',
    'PyYAML': 'yaml',
    'python-dotenv': 'dotenv',
    'google-genai': 'google.genai',
    'scikit-learn': 'sklearn',
}

def dist_to_module(dist):
    return IMPORT_NAMES.get(dist, dist.replace('-', '_'))

reqs = os.environ.get('PYTHON_REQUIREMENTS', '')
for dist in reqs.split():
    mod = dist_to_module(dist)
    try:
        if importlib.util.find_spec(mod) is None:
            print(f'Warning: {dist} is installed but module {mod!r} cannot be imported.', file=sys.stderr)
    except Exception as e:
        print(f'Warning: {dist} is installed but importing {mod!r} failed: {e}', file=sys.stderr)
" 2>&1 || true

    echo
    echo "Setup complete."
    echo
}

# Ensure PYTHON points to an interpreter with all required packages.
ensure_environment() {
    if [[ -x "$VENV_DIR/bin/python" ]] && python_deps_ok "$VENV_DIR/bin/python"; then
        PYTHON="$VENV_DIR/bin/python"
        return 0
    fi
    setup_environment
}

# Allow explicit reinstallation via --setup flag.
if [[ "${1:-}" == "--setup" ]]; then
    setup_environment
    echo "You can now run ./haqita.sh"
    exit 0
fi

ensure_environment

# Load .env if it exists
if [[ -f .env ]]; then
    # Export all non-empty, non-comment lines
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        key=$(echo "$key" | sed 's/[[:space:]]*$//')
        value=$(echo "$value" | sed 's/^[[:space:]]*//')
        export "$key=$value"
    done < .env
fi

pause() {
    read -n1 -rsp "Press any key to continue..."
    echo
}

# Batch mode — run the full pipeline non-interactively, then exit
if [[ "${HAQITA_BATCH:-0}" == "1" ]] || [[ "${1:-}" == "--batch" ]]; then
    if [[ "${1:-}" == "--batch" ]]; then
        shift
    fi
    clear
    echo "========================================"
    echo "  Running Full Pipeline (batch mode)"
    echo "========================================"
    echo
    $PYTHON scripts/orchestrator.py --full "$@"
    echo "========================================"
    echo "  Pipeline complete (batch mode)."
    echo "========================================"
    exit 0
fi

menu() {
    while true; do
        clear
        echo "========================================"
        echo "        Haqita - Grocery Price Tool"
        echo "========================================"
        echo
        echo "  [1] Run full pipeline"
        echo "  [2] Stage 1: Scrape"
        echo "  [3] Stage 2: OCR"
        echo "  [4] Stage 3: Consolidation"
        echo "  [5] Stage 4: Publish HTML"
        echo "  [6] Sync to Cloudflare"
        echo "  [7] Stage 5: Deploy + Sync"
        echo "  [8] Start HTTP server"
        echo "  [9] Tests"
        echo "  [10] Health check"
        echo "  [0] Exit"
        echo
        read -rp "Your choice: " choice
        case "$choice" in
            1) full_pipeline_menu ;;
            2) stage_scrape ;;
            3) stage_ocr ;;
            4) stage_consolidation ;;
            5) stage_publish_html ;;
             6) stage_cloudflare_sync ;;
            7) stage_deploy ;;
            8) http_server ;;
            9) stage_tests ;;
            10) health_check ;;
            0) end_script ;;
            *) echo "Invalid choice. Press any key to try again..."; pause ;;
        esac
    done
}

full_pipeline_menu() {
    clear
    echo "========================================"
    echo "  Running Full Pipeline"
    echo "========================================"
    echo
    echo "  Stage 1: Scrape all stores"
    echo "  Stage 2: OCR all scraped images"
    echo "  Stage 3: Consolidate (update database)"
    echo "  Stage 4: Publish HTML"
    echo "  Stage 5: Deploy + Sync (merge of old Sync & Deploy)"
    echo
    echo "  [1] Run full pipeline"
    echo "  [2] Resume from last failed stage"
    echo "  [0] Back"
    echo
    read -rp "Your choice: " fp_choice
    case "$fp_choice" in
        1) full_pipeline; break ;;
        2) full_pipeline_resume; break ;;
        0) return ;;
        *) echo "Invalid choice. Press any key to try again..."; pause ;;
    esac
}

full_pipeline() {
    clear
    echo "========================================"
    echo "  Running Full Pipeline"
    echo "========================================"
    echo
    read -n1 -rsp "Press any key to start, or Ctrl+C to cancel..."
    echo
    $PYTHON scripts/orchestrator.py --full
    echo "========================================"
    echo "  Pipeline complete."
    echo "========================================"
    echo
    pause
}

full_pipeline_resume() {
    clear
    echo "========================================"
    echo "  Full Pipeline - Resume"
    echo "========================================"
    echo
    echo "  Checking stage status..."
    echo
    $PYTHON scripts/orchestrator.py --full --resume
    echo "========================================"
    echo "  Resume complete."
    echo "========================================"
    echo
    pause
}

stage_scrape() {
    while true; do
        clear
        echo "========================================"
        echo "  Stage 1: Scrape"
        echo "========================================"
        echo
        echo "  [1] Scrape all stores"
        echo "  [2] Scrape Lotte Mart only"
        echo "  [3] Scrape Superindo only"
        echo "  [0] Back"
        echo
        read -rp "Your choice: " scrape_choice
        case "$scrape_choice" in
            1) scrape_all ;;
            2) scrape_lotte ;;
            3) scrape_superindo ;;
            0) break ;;
            *) echo "Invalid choice. Press any key to try again..."; pause ;;
        esac
    done
}

scrape_lotte() {
    clear
    echo "========================================"
    echo "  Scrape Lotte Mart"
    echo "========================================"
    echo
    $PYTHON scripts/scrapers/lotte.py
    echo
    pause
}

scrape_superindo() {
    clear
    echo "========================================"
    echo "  Scrape Superindo"
    echo "========================================"
    echo
    $PYTHON scripts/scrapers/superindo.py
    echo
    pause
}

scrape_all() {
    clear
    echo "========================================"
    echo "  Scrape All Stores"
    echo "========================================"
    echo
    echo "--- Lotte Mart ---"
    $PYTHON scripts/scrapers/lotte.py
    echo
    echo "--- Superindo ---"
    $PYTHON scripts/scrapers/superindo.py
    echo
    pause
}

stage_ocr() {
    while true; do
        clear
        echo "========================================"
        echo "  Stage 2: OCR"
        echo "========================================"
        echo
        echo "  [1] OCR all images (both stores)"
        echo "  [2] OCR Lotte images"
        echo "  [3] OCR Superindo images"
        echo "  [4] OCR specific image"
        echo "  [0] Back"
        echo
        read -rp "Your choice: " ocr_choice
        case "$ocr_choice" in
            1) ocr_both ;;
            2) ocr_lotte ;;
            3) ocr_superindo ;;
            4) ocr_specific ;;
            0) break ;;
            *) echo "Invalid choice. Press any key to try again..."; pause ;;
        esac
    done
}

ocr_lotte() {
    clear
    echo "========================================"
    echo "  OCR - Lotte"
    echo "========================================"
    echo
    $PYTHON scripts/ocr/run_ocr.py --store lotte
    echo
    pause
}

ocr_superindo() {
    clear
    echo "========================================"
    echo "  OCR - Superindo"
    echo "========================================"
    echo
    $PYTHON scripts/ocr/run_ocr.py --store superindo
    echo
    pause
}

ocr_both() {
    clear
    echo "========================================"
    echo "  OCR - Both Stores"
    echo "========================================"
    echo
    echo "--- Lotte ---"
    $PYTHON scripts/ocr/run_ocr.py --store lotte
    echo
    echo "--- Superindo ---"
    $PYTHON scripts/ocr/run_ocr.py --store superindo
    echo
    pause
}

ocr_specific() {
    clear
    echo "========================================"
    echo "  OCR - Specific Image"
    echo "========================================"
    echo
    echo "  Lotte images:"
    find database/scrape/lotte -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) 2>/dev/null || true
    echo
    echo "  Superindo images:"
    find database/scrape/superindo -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) 2>/dev/null || true
    echo
    echo "  Lotte OCR results:"
    ls database/ocr/lotte/*.json 2>/dev/null || true
    echo
    echo "  Superindo OCR results:"
    ls database/ocr/superindo/*.json 2>/dev/null || true
    echo
    read -rp "Enter filename: " img
    [[ -z "$img" ]] && return
    read -rp "Store (lotte/superindo): " store
    [[ -z "$store" ]] && store=lotte
    echo
    $PYTHON scripts/ocr/run_ocr.py --store "$store" --image "$img"
    echo
    pause
}

stage_consolidation() {
    while true; do
        clear
        echo "========================================"
        echo "  Stage 3: Consolidation"
        echo "========================================"
        echo
        echo "  [1] Run consolidation"
        echo "  [2] Custom input directory"
        echo "  [0] Back"
        echo
        read -rp "Your choice: " cons_choice
        case "$cons_choice" in
            1) consolidate_run ;;
            2) consolidate_custom ;;
            0) break ;;
            *) echo "Invalid choice. Press any key to try again..."; pause ;;
        esac
    done
}

consolidate_run() {
    clear
    echo "========================================"
    echo "  Running Consolidation"
    echo "========================================"
    echo
    $PYTHON scripts/consolidate.py
    echo
    pause
}

consolidate_custom() {
    clear
    echo "========================================"
    echo "  Consolidation - Custom Input Directory"
    echo "========================================"
    echo
    read -rp "Input directory: " dir
    [[ -z "$dir" ]] && dir=output
    $PYTHON scripts/consolidate.py --input-dir "$dir"
    echo
    pause
}

stage_publish_html() {
    clear
    echo "========================================"
    echo "  Stage 4: Publish HTML"
    echo "========================================"
    echo
    $PYTHON scripts/publish_html.py
    echo
    pause
}

stage_cloudflare_sync() {
    clear
    echo "========================================"
    echo "  Sync to Cloudflare"
    echo "========================================"
    echo
    $PYTHON scripts/sync_cloudflare.py
    echo
    pause
}

stage_deploy() {
    clear
    echo "========================================"
    echo "  Stage 5: Deploy + Sync"
    echo "========================================"
    echo
    $PYTHON scripts/deploy.py
    echo
    pause
}

stage_tests() {
    while true; do
        clear
        echo "========================================"
        echo "  Tests"
        echo "========================================"
        echo
        echo "  [1] Integration tests (OCR)"
        echo "  [2] Matching pipeline tests"
        echo "  [0] Back"
        echo
        read -rp "Your choice: " test_choice
        case "$test_choice" in
            1) test_integration ;;
            2) test_matching ;;
            0) break ;;
            *) echo "Invalid choice. Press any key to try again..."; pause ;;
        esac
    done
}

test_integration() {
    clear
    echo "========================================"
    echo "  Integration Tests (OCR)"
    echo "========================================"
    echo
    if [[ -f tests/integration/run_integration_tests.sh ]]; then
        bash tests/integration/run_integration_tests.sh
    else
        echo "tests/integration/run_integration_tests.sh not found."
    fi
    echo
    pause
}

test_matching() {
    clear
    echo "========================================"
    echo "  Matching Pipeline Tests"
    echo "========================================"
    echo
    $PYTHON -m pytest tests/matching/ -v
    echo
    pause
}

health_check() {
    clear
    echo "========================================"
    echo "  Health Check"
    echo "========================================"
    echo
    $PYTHON scripts/health_check.py
    echo
    pause
}

http_server() {
    clear
    echo "========================================"
    echo "  HTTP Server"
    echo "  Open http://localhost:8080/index.html"
    echo "  Press Ctrl+C to stop"
    echo "========================================"
    echo
    $PYTHON -m http.server 8080
}

end_script() {
    clear
    echo "Goodbye!"
    sleep 2
    exit 0
}

menu
