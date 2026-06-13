#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXIT_CODE=0

# Prefer project venv if it exists
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON=python3
fi

pause() {
    read -n1 -rsp "Press any key to continue..."
    echo
}

show_result() {
    local code="$1"
    echo
    case "$code" in
        0) echo "[PASS] Products extracted successfully, matches assert." ;;
        1) echo "[SKIP] Infrastructure not available (Gemini)." ;;
        2) echo "[INFO] OCR ran but no products found." ;;
        3) echo "[FAIL] Preprocessing error." ;;
        4) echo "[DIFF] Products extracted but differ from assert." ;;
        *) echo "[FAIL] Unexpected error (exit code $code)." ;;
    esac
    echo
    pause
    exit "$code"
}

test_superindo() {
    clear
    echo "========================================"
    echo "  Superindo OCR Integration Test"
    echo "========================================"
    echo
    $PYTHON "$SCRIPT_DIR/test_superindo_ocr.py"
    EXIT_CODE=$?
    show_result "$EXIT_CODE"
}

test_lotte() {
    clear
    echo "========================================"
    echo "  Lotte OCR Integration Test"
    echo "========================================"
    echo
    $PYTHON "$SCRIPT_DIR/test_lotte_ocr.py"
    EXIT_CODE=$?
    show_result "$EXIT_CODE"
}

test_custom() {
    clear
    echo "========================================"
    echo "  OCR Integration Test (custom image)"
    echo "========================================"
    echo
    read -rp "Enter image path: " img_path
    if [[ -z "$img_path" ]]; then
        echo "No path entered. Aborting."
        pause
        exit 1
    fi
    if [[ ! -f "$img_path" ]]; then
        echo "File not found: $img_path"
        pause
        exit 1
    fi
    read -rp "Store name for output file [lotte/superindo]: " store
    [[ -z "$store" ]] && store=custom
    echo
    $PYTHON "$SCRIPT_DIR/test_superindo_ocr.py" --image "$img_path" --output "work/integration_test_${store}.json"
    EXIT_CODE=$?
    show_result "$EXIT_CODE"
}

test_all() {
    clear
    echo "========================================"
    echo "  Running All Integration Tests"
    echo "========================================"
    echo
    local all_passed=1

    echo "--- Test 1: Superindo OCR ---"
    echo
    $PYTHON "$SCRIPT_DIR/test_superindo_ocr.py" || all_passed=0
    echo
    echo "----------------------------------------"
    echo

    echo "--- Test 2: Lotte OCR ---"
    echo
    $PYTHON "$SCRIPT_DIR/test_lotte_ocr.py" || all_passed=0
    echo
    echo "----------------------------------------"
    echo

    if [[ "$all_passed" -eq 1 ]]; then
        echo "[PASS] All integration tests passed."
    else
        echo "[WARN] Some tests failed (exit code != 0)."
        echo "  Code 2 = no products found."
        echo "  Code 4 = output differs from assert."
    fi
    echo
    pause
}

test_matching() {
    clear
    echo "========================================"
    echo "  Matching Pipeline Tests (pytest)"
    echo "========================================"
    echo
    $PYTHON -m pytest tests/matching/ -v
    EXIT_CODE=$?
    echo
    if [[ "$EXIT_CODE" -eq 0 ]]; then
        echo "[PASS] All matching tests passed."
    else
        echo "[FAIL] Some matching tests failed."
    fi
    echo
    pause
    exit "$EXIT_CODE"
}

clear
echo "========================================"
echo "  Haqita - Integration Tests"
echo "========================================"
echo
echo "  [1] Superindo OCR test (default image)"
echo "  [2] Lotte OCR test (default images)"
echo "  [3] Run custom image through OCR"
echo "  [4] Run all integration tests"
echo "  [5] Matching pipeline tests (pytest)"
echo "  [0] Back"
echo
read -rp "Your choice: " choice

case "$choice" in
    1) test_superindo ;;
    2) test_lotte ;;
    3) test_custom ;;
    4) test_all ;;
    5) test_matching ;;
    0) exit 0 ;;
    *) echo "Invalid choice."; pause ; exit 1 ;;
esac
