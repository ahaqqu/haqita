#!/usr/bin/env bash
# agentic_engineering/prepare.sh — Install deps, verify .env, gate on unit tests.
#
# Usage:
#   bash agentic_engineering/prepare.sh
#
# Exits non-zero if:
#   - Python 3.12+ is not found
#   - Virtual environment creation fails
#   - .env is missing GEMINI_API_KEY
#   - Unit tests fail

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Haqita Prepare ==="
echo ""

# 1. Ensure venv exists and deps are installed
if [[ -x .venv/bin/python ]]; then
    PYTHON=".venv/bin/python"
    echo "[OK] Virtual environment found at .venv"
else
    echo "[*] Creating virtual environment..."
    for py in python3.12 python3.13 python3; do
        if command -v "$py" >/dev/null 2>&1; then
            "$py" -m venv .venv
            PYTHON=".venv/bin/python"
            echo "[OK] Created .venv with $py"
            break
        fi
    done
    if [[ ! -x .venv/bin/python ]]; then
        echo "[!] Python 3.12+ not found. Install it with: sudo apt install python3.12 python3.12-venv python3-pip" >&2
        exit 1
    fi
fi

# Verify Python version
version=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$(printf '%s\n' "3.12" "$version" | sort -V | head -n1)" != "3.12" ]]; then
    echo "[!] Python 3.12+ required. Found $version." >&2
    exit 1
fi
echo "[OK] Python $version"

# Install dependencies
if [[ -f requirements.txt ]]; then
    echo "[*] Installing dependencies from requirements.txt..."
    "$PYTHON" -m pip install --upgrade pip -q
    "$PYTHON" -m pip install -r requirements.txt -q
    echo "[OK] Dependencies installed"
fi

# 2. Verify .env has GEMINI_API_KEY
if [[ ! -f .env ]]; then
    echo "[!] .env file not found. Create one with GEMINI_API_KEY=your_key" >&2
    exit 1
fi

if ! grep -q '^GEMINI_API_KEY=' .env 2>/dev/null && ! grep -q '^export GEMINI_API_KEY=' .env 2>/dev/null; then
    echo "[!] .env is missing GEMINI_API_KEY. Add GEMINI_API_KEY=your_key to .env" >&2
    exit 1
fi
echo "[OK] GEMINI_API_KEY found in .env"

# 3. Run unit tests as a gate
echo "[*] Running matching pipeline unit tests..."
if "$PYTHON" -m pytest tests/matching/ -v 2>&1; then
    echo "[OK] All matching unit tests passed"
else
    echo "[!] Matching unit tests failed. Fix them before proceeding." >&2
    exit 1
fi

echo ""
echo "=== Ready ==="
echo "You can now run: ./haqita.sh"
