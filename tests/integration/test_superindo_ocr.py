"""
Integration test: OCR on a Superindo brochure image.
Reads OCR provider from config.yaml and .env (OCR_PROVIDER).
Works with both Ollama and Gemini.

Usage:
    python tests/integration/test_superindo_ocr.py [--image path/to/image.jpg]

Exit codes:
    0 - products extracted
    1 - infrastructure error (Ollama/Gemini not available)
    2 - OCR ran but no products extracted
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import extract_products, validate_product
from scripts.ocr.image_preprocess import preprocess_for_ocr

DEFAULT_IMAGE = str(Path(__file__).resolve().parent.parent.parent /
                    "data/test/superindo/image-brochure/sample_katalog_1.jpg")


def load_config() -> dict:
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    with open(Path(__file__).resolve().parent.parent.parent / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    env_provider = os.getenv("OCR_PROVIDER")
    if env_provider:
        cfg["ocr"]["provider"] = env_provider
    if "gemini" in cfg["ocr"] and not cfg["ocr"]["gemini"].get("api_key"):
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            cfg["ocr"]["gemini"]["api_key"] = env_key
    cfg["store"] = "superindo"
    return cfg


def check_provider(cfg: dict) -> bool:
    provider = cfg["ocr"]["provider"]
    if provider == "ollama":
        import requests
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            model = cfg["ocr"]["ollama"]["model"]
            if model not in models:
                print(f"[!!] Required model '{model}' not installed.")
                print(f"    Install: ollama pull {model}")
                return False
            return True
        except requests.exceptions.ConnectionError:
            print("[!!] Ollama is not running.")
            return False
    elif provider == "gemini":
        api_key = cfg["ocr"]["gemini"].get("api_key") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[!!] GEMINI_API_KEY not set in .env")
            return False
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Integration test: OCR on a Superindo brochure image")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Path to brochure image")
    parser.add_argument("--output", default="work/integration_test_superindo.json", help="Save results to JSON")
    args = parser.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"[!!] Image not found: {img_path}")
        sys.exit(1)

    cfg = load_config()
    provider = cfg["ocr"]["provider"]

    print("=" * 60)
    print(f"  Integration Test: Superindo OCR ({provider})")
    print("=" * 60)
    print()
    print(f"[*] Image: {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB)")
    print()

    print("[*] Checking provider...", end=" ")
    sys.stdout.flush()
    if not check_provider(cfg):
        sys.exit(1)
    print("OK")
    print()

    print("[*] Preprocessing image...", end=" ")
    sys.stdout.flush()
    try:
        processed = preprocess_for_ocr(str(img_path), cfg)
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(3)

    print()
    print("[*] Running OCR...")
    sys.stdout.flush()
    t0 = time.time()
    validated, rejected, ocr_error = [], [], None

    try:
        products_raw = extract_products(processed, cfg)
        for prod in products_raw:
            clean, reason = validate_product(prod, img_path.name)
            if clean:
                validated.append(clean)
            else:
                rejected.append({"raw": prod, "reason": reason})
    except Exception as e:
        ocr_error = str(e)[:200]

    ocr_time = time.time() - t0
    print(f"[*] OCR completed in {ocr_time:.0f}s")
    print()
    print(f"    Products: {len(validated)}  Rejected: {len(rejected)}")
    print()

    if validated:
        print("  Extracted products:")
        for i, p in enumerate(validated, 1):
            unit = p.get("unit", "") or ""
            u = f"  {unit}" if unit else ""
            promo = p.get("promo", "") or ""
            pr = f" — {promo}" if promo else ""
            print(f"  {i:2d}. {p['name']}{u}: Rp {p['price']:,}{pr}")
        result = "PASS"
        exit_code = 0
    elif ocr_error:
        print(f"  [!!] {ocr_error}")
        result = "FAIL"
        exit_code = 2
    else:
        print("  [!!] No products extracted.")
        result = "FAIL"
        exit_code = 2

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps({
                "image": img_path.name, "provider": provider,
                "ocr_time_s": round(ocr_time, 1),
                "products_count": len(validated), "rejected_count": len(rejected),
                "products": validated, "rejected": rejected,
            }, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    Path(processed).unlink(missing_ok=True)
    print(f"\n  Result: {result}")
    print("=" * 60)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
