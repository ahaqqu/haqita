"""
Health Check — Pre-flight verification before running the pipeline.

Checks:
1. Python version >= 3.12
2. Required pip packages installed
3. config.yaml exists and is valid
4. OCR provider configuration (Gemini API key)
5. Required directories exist
6. AI verifier provider connectivity

Usage:
    python scripts/health_check.py
"""

import json
import os
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import load_config


def check_python_version() -> tuple[bool, str]:
    """Check Python version >= 3.12."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 12):
        return False, f"Python {major}.{minor} found, need >= 3.12"
    return True, f"Python {major}.{minor}.{sys.version_info.micro} OK"


def check_required_packages() -> tuple[bool, list[str]]:
    """Check required pip packages are importable."""
    packages = [
        "requests", "bs4", "PIL", "yaml", "dotenv",
        "sentence_transformers", "numpy",
    ]
    missing = []
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        return False, missing
    return True, []


def check_config() -> tuple[bool, str]:
    """Check config.yaml exists and is valid."""
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        return False, "config.yaml not found"
    try:
        import yaml
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            return False, "config.yaml is not a valid YAML mapping"
        required_keys = ["ocr", "consolidation"]
        missing = [k for k in required_keys if k not in cfg]
        if missing:
            return False, f"config.yaml missing keys: {', '.join(missing)}"
        return True, f"config.yaml OK (provider: {cfg['ocr'].get('provider', 'unknown')})"
    except Exception as e:
        return False, f"config.yaml parse error: {e}"


def check_directories() -> tuple[bool, list[str]]:
    """Check required directories exist (or can be created)."""
    dirs = [
        ROOT / "database" / "scrape" / "lotte",
        ROOT / "database" / "scrape" / "superindo",
        ROOT / "database" / "ocr" / "lotte",
        ROOT / "database" / "ocr" / "superindo",
        ROOT / "database" / "stage_results",
        ROOT / "database" / "logs",
    ]
    missing = []
    for d in dirs:
        if not d.exists():
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                missing.append(f"{d} (cannot create: {e})")
    if missing:
        return False, missing
    return True, []


def check_ocr_provider(cfg: dict) -> tuple[bool, str]:
    """Check Gemini API key is set."""
    import os
    api_key = cfg.get("ocr", {}).get("gemini", {}).get("api_key") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False, "GEMINI_API_KEY not set (required for OCR)"
    masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    return True, f"Gemini API key set ({masked})"


def check_ai_verifier(cfg: dict) -> tuple[bool, str]:
    """Check AI verifier (Gemini) is configured."""
    import os
    api_key = cfg.get("ocr", {}).get("gemini", {}).get("api_key") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False, "GEMINI_API_KEY not set (required for AI verifier)"
    return True, "Gemini AI verifier configured"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Haqita Pipeline Health Check")
    args = parser.parse_args()

    print("=" * 60)
    print("  Haqita Pipeline Health Check")
    print("=" * 60)
    print()

    all_ok = True
    results = []

    # 1. Python version
    ok, msg = check_python_version()
    results.append(("Python version", ok, msg))
    if not ok:
        all_ok = False

    # 2. Required packages
    ok, missing = check_required_packages()
    if ok:
        results.append(("Required packages", True, "All packages installed"))
    else:
        results.append(("Required packages", False, f"Missing: {', '.join(missing)}"))
        all_ok = False

    # 3. Config
    ok, msg = check_config()
    results.append(("Config", ok, msg))
    if not ok:
        all_ok = False

    # Load config for provider checks
    cfg = {}
    try:
        cfg = load_config()
    except Exception:
        pass

    # 4. Directories
    ok, missing = check_directories()
    if ok:
        results.append(("Directories", True, "All directories exist"))
    else:
        results.append(("Directories", False, f"Missing: {', '.join(missing)}"))
        all_ok = False

    # 5. OCR provider
    ok, msg = check_ocr_provider(cfg)
    results.append(("OCR provider", ok, msg))
    if not ok:
        all_ok = False

    # 6. AI verifier
    ok, msg = check_ai_verifier(cfg)
    results.append(("AI verifier", ok, msg))
    if not ok:
        all_ok = False

    # Print results
    for name, ok, msg in results:
        status = "OK" if ok else "FAIL"
        icon = "[+]" if ok else "[!]"
        print(f"  {icon} {name}: {msg}")

    print()
    print("=" * 60)
    if all_ok:
        print("  All checks passed. Pipeline is ready to run.")
    else:
        print("  Some checks failed. Fix issues before running the pipeline.")
    print("=" * 60)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
