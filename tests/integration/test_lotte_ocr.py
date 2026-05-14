"""
Integration test: OCR on a single Lotte Mart brochure image using Ollama.
Requires: Ollama running locally, qwen3-vl model installed.

Usage:
    python tests/integration/test_lotte_ocr.py [--image path/to/image.jpg] [--model model_name]

Exit codes:
    0 - all checks passed
    1 - infrastructure error (Ollama/missing model)
    2 - OCR completed but no products extracted
    3 - unexpected error
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import extract_products, validate_product
from scripts.ocr.image_preprocess import preprocess_for_ocr

OLLAMA_URL = "http://localhost:11434"
DEFAULT_IMAGE = str(Path(__file__).resolve().parent.parent.parent /
                    "data/test/lotte/image-brochure/ht1.jpeg")


def check_ollama() -> tuple[bool, list[str]]:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return True, models
    except requests.exceptions.ConnectionError:
        return False, []
    except Exception as e:
        return False, [str(e)]


def find_best_model(available: list[str], preferred: str) -> str | None:
    if preferred in available:
        return preferred
    vl_models = [m for m in available if "vl" in m.lower()]
    if vl_models:
        return vl_models[0]
    if available:
        return available[0]
    return None


def load_minimal_cfg(model_name: str) -> dict:
    try:
        import yaml
        from dotenv import load_dotenv
        load_dotenv()
        with open(Path(__file__).resolve().parent.parent.parent / "config.yaml") as f:
            cfg = yaml.safe_load(f)
        cfg["ocr"]["model_ollama"] = model_name
        import os
        env_provider = os.getenv("OCR_PROVIDER")
        if env_provider:
            cfg["ocr"]["provider"] = env_provider
        return cfg
    except Exception:
        return {
            "ocr": {
                "provider": "ollama",
                "model_ollama": model_name,
                "timeout_seconds": 120,
                "max_retries": 2,
                "temperature": 0,
                "image_min_width_px": 1400,
                "image_contrast_enhance": 1.4,
                "image_sharpness_enhance": 1.2,
            }
        }


def main():
    parser = argparse.ArgumentParser(description="Integration test: Lotte OCR on a single brochure image")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Path to Lotte brochure image")
    parser.add_argument("--model", default=None, help="Ollama model name (auto-detected if omitted)")
    parser.add_argument("--output", default=None, help="Save OCR results to this JSON file")
    args = parser.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"[!!] Image not found: {img_path}")
        sys.exit(1)

    print("=" * 60)
    print("  Integration Test: Lotte OCR on Brochure Image")
    print("=" * 60)
    print()

    print(f"[*] Image: {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB)")
    print()

    print("[*] Checking Ollama...", end=" ")
    sys.stdout.flush()
    ok, models = check_ollama()
    if not ok:
        print("FAIL")
        print("[!!] Ollama is not running. Start with: ollama serve")
        sys.exit(1)
    print("OK")
    print(f"    Available models: {models}")

    model = args.model or find_best_model(models, "qwen3-vl:7b")
    if not model:
        print("[!!] No suitable VL model found.")
        print("    Install one: ollama pull qwen3-vl:2b")
        sys.exit(1)
    if model not in models:
        print(f"[!] Requested model '{model}' not installed.")
        print(f"    Install: ollama pull {model}")
        print(f"    Or use --model to specify an available model.")
        sys.exit(1)

    print(f"[*] Using model: {model}")
    print()

    cfg = load_minimal_cfg(model)

    print("[*] Preprocessing image...", end=" ")
    sys.stdout.flush()
    t0 = time.time()
    try:
        processed = preprocess_for_ocr(str(img_path), cfg)
        print(f"OK ({time.time() - t0:.1f}s)")
        print(f"    Output: {Path(processed).name}")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(3)

    print()
    print("[*] Running OCR (this may take a while)...")
    print()
    sys.stdout.flush()
    t0 = time.time()
    products_raw = []
    ocr_error = None
    try:
        products_raw = extract_products(processed, cfg)
    except Exception as e:
        ocr_error = str(e)[:200]
        products_raw = []

    ocr_time = time.time() - t0

    print(f"[*] OCR completed in {ocr_time:.0f}s")
    if ocr_error:
        print(f"    Note: {ocr_error}")
    print()

    validated = []
    rejected = []
    for prod in products_raw:
        clean, reason = validate_product(prod, img_path.name)
        if clean:
            validated.append(clean)
        else:
            rejected.append({"raw": prod, "reason": reason})

    print(f"    Products extracted: {len(validated)}")
    print(f"    Rejected: {len(rejected)}")
    print()

    if validated:
        print("  Extracted products:")
        print()
        for i, p in enumerate(validated, 1):
            brand = p.get("brand") or ""
            tag = f"[{brand}] " if brand else ""
            unit = p.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            promo = p.get("promo", "") or ""
            promo_str = f" — {promo}" if promo else ""
            period = p.get("period", "") or ""
            period_str = f" ({period})" if period else ""
            print(f"  {i:2d}. {tag}{p['name']}{unit_str}: Rp {p['price']:,}{promo_str}{period_str}")
        print()
        result = "PASS"
        exit_code = 0
    elif ocr_error:
        print(f"  [!!] OCR failed: {ocr_error}")
        print("  This may be expected if the model is too small (e.g., 2B vs 7B).")
        result = "FAIL (OCR parse)"
        exit_code = 2
    else:
        print("  [!!] No products extracted from image.")
        print("  The model processed the image but found no products.")
        result = "FAIL (no products)"
        exit_code = 2

    if rejected:
        print(f"  Rejected items:")
        for r in rejected:
            print(f"    - {r['reason']}: {json.dumps(r['raw'], ensure_ascii=False)[:120]}")

    if args.output:
        output = {
            "image": img_path.name,
            "model": model,
            "ocr_time_s": round(ocr_time, 1),
            "products_count": len(validated),
            "rejected_count": len(rejected),
            "products": validated,
            "rejected": rejected,
        }
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[*] Results saved to: {out_path}")

    try:
        Path(processed).unlink(missing_ok=True)
    except Exception:
        pass

    print()
    print(f"  Result: {result}")
    print("=" * 60)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
