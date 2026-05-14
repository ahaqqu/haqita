import logging
import os
import shutil
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check(label: str, ok: bool, critical: bool = False) -> bool:
    status = "PASS" if ok else ("FAIL" if critical else "WARN")
    icon = "[OK]" if ok else ("[!!]" if critical else "[!]")
    print(f"  {icon} {label}: {status}")
    return ok if critical else True


def main():
    load_dotenv()

    print("=" * 60)
    print("  Haqita — Health Check")
    print("=" * 60)
    print()

    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if not cfg_path.exists():
        print("  [!!] config.yaml not found")
        sys.exit(1)
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    provider = os.getenv("OCR_PROVIDER", cfg.get("ocr", {}).get("provider", "ollama"))
    all_ok = True

    print(f"  OCR provider: {provider}")
    print()

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        all_ok &= check("GEMINI_API_KEY set", bool(api_key), critical=True)
    else:
        print("  [*] Checking Ollama...")
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            ollama_ok = resp.status_code == 200
            all_ok &= check("Ollama service", ollama_ok, critical=True)

            if ollama_ok:
                models = {m["name"] for m in resp.json().get("models", [])}
                required = [cfg["ocr"]["model_ollama"], cfg["consolidation"]["ai_model"]]
                for model in required:
                    found = any(model in m for m in models)
                    all_ok &= check(f"Model: {model}", found, critical=True)
        except requests.exceptions.ConnectionError:
            all_ok &= check("Ollama service", False, critical=True)

    print()
    print("  [*] Checking environment...")

    output_dir = Path("output")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        test_file = output_dir / ".health_check_tmp"
        test_file.write_text("ok")
        test_file.unlink()
        all_ok &= check("Output directory writable", True, critical=True)
    except Exception:
        all_ok &= check("Output directory writable", False, critical=True)

    try:
        usage = shutil.disk_usage(output_dir)
        free_gb = usage.free / (1024 ** 3)
        all_ok &= check(f"Disk space: {free_gb:.1f} GB free", free_gb > 1, critical=False)
    except Exception:
        pass

    print()
    print("  [*] Checking internet connectivity...")
    try:
        resp = requests.head("https://www.lottemart.co.id", timeout=10)
        all_ok &= check("Lotte Mart reachable", resp.status_code < 500, critical=False)
    except requests.RequestException:
        all_ok &= check("Lotte Mart reachable", False, critical=False)

    try:
        resp = requests.head("https://www.superindo.co.id", timeout=10)
        all_ok &= check("Superindo reachable", resp.status_code < 500, critical=False)
    except requests.RequestException:
        all_ok &= check("Superindo reachable", False, critical=False)

    print()
    if all_ok:
        print("  All checks passed.")
    else:
        print("  Some non-critical checks failed (see WARN above).")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
