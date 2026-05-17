"""
Ollama setup helper — ensure Ollama is running and model is available.

Usage:
    python scripts/setup_ollama.py [--check-only]
"""

import argparse
import subprocess
import sys
import time
import urllib.request
import json


OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"


def check_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_model_installed(model: str) -> bool:
    """Check if the model is already installed."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("models", [])
            return any(m.get("name", "").startswith(model.split(":")[0]) for m in models)
    except Exception:
        return False


def start_ollama_background() -> bool:
    """Start Ollama serve in background."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        print("[*] Ollama server starting...")
        time.sleep(3)
        return check_ollama_running()
    except Exception as e:
        print(f"[!] Failed to start Ollama: {e}")
        return False


def pull_model(model: str) -> bool:
    """Pull the Ollama model."""
    print(f"[*] Pulling model: {model} (this may take a few minutes)...")
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            print(f"[OK] Model {model} installed")
            return True
        else:
            print(f"[!] Failed to pull model: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("[!] Timeout pulling model")
        return False
    except Exception as e:
        print(f"[!] Error pulling model: {e}")
        return False


def setup_ollama(model: str = DEFAULT_MODEL, check_only: bool = False) -> bool:
    """Ensure Ollama is running and model is available."""
    import os
    run_mode = os.getenv("RUN_MODE", "").lower()
    is_docker = run_mode == "docker"

    print(f"=== Ollama Setup ===")

    # Check if running
    if not check_ollama_running():
        print("[!] Ollama not running")
        if check_only:
            return False
        if is_docker:
            print("[!] In Docker mode. Please start Ollama on host and set OLLAMA_BASE_URL.")
            return False
        print("[*] Attempting to start Ollama...")
        if not start_ollama_background():
            print("[!] Could not start Ollama. Please run 'ollama serve' manually.")
            return False
    else:
        print("[OK] Ollama is running")

    # Check if model installed
    if not check_model_installed(model):
        print(f"[!] Model '{model}' not installed")
        if check_only:
            return False
        if is_docker:
            print("[!] In Docker mode. Run 'ollama pull {model}' on host first.")
            return False
        if not pull_model(model):
            print("[!] Could not pull model automatically")
            return False
    else:
        print(f"[OK] Model '{model}' is available")

    print("[OK] Ollama ready")
    return True


def main():
    parser = argparse.ArgumentParser(description="Setup Ollama for Haqita")
    parser.add_argument("--check-only", action="store_true", help="Only check, don't start/pull")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to ensure (default: qwen2.5vl:7b)")
    args = parser.parse_args()

    success = setup_ollama(model=args.model, check_only=args.check_only)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()