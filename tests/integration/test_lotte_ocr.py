"""
Integration test: OCR on a Lotte Mart brochure image.
Reads OCR provider from config.yaml and .env (OCR_PROVIDER).
Works with both Ollama and Gemini.

Usage:
    python tests/integration/test_lotte_ocr.py [--image path/to/image.jpg]

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

IMAGE_DIR = Path(__file__).resolve().parent.parent.parent / "data/test/lotte/image-brochure"
ALL_IMAGES = sorted(str(p) for p in IMAGE_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})


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
    cfg["store"] = "lotte"
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


def run_on_image(img_path: Path, cfg: dict, output_path: Path | None) -> tuple[int, str]:
    provider = cfg["ocr"]["provider"]
    print("=" * 60)
    print(f"  Integration Test: Lotte OCR ({provider})")
    print("=" * 60)
    print()
    print(f"[*] Image: {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB)")
    print()

    print("[*] Preprocessing image...", end=" ")
    sys.stdout.flush()
    try:
        processed = preprocess_for_ocr(str(img_path), cfg)
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        return 3, img_path.name

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

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
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
    return exit_code, img_path.name


def main():
    parser = argparse.ArgumentParser(description="Integration test: OCR on Lotte brochure images")
    parser.add_argument("--image", nargs="*", default=ALL_IMAGES, help="Brochure image(s) to process")
    parser.add_argument("--output-dir", default="work", help="Directory to save JSON results")
    args = parser.parse_args()

    cfg = load_config()

    print("[*] Checking provider...", end=" ")
    sys.stdout.flush()
    if not check_provider(cfg):
        sys.exit(1)
    print("OK")
    print()

    all_exit = 0
    for img in args.image:
        img_path = Path(img)
        if not img_path.exists():
            print(f"[!!] Skipping — image not found: {img_path}")
            continue
        output = Path(args.output_dir) / f"integration_test_lotte_{img_path.stem}.json"
        code, _ = run_on_image(img_path, cfg, output)
        if code != 0:
            all_exit = code
        print()

    sys.exit(all_exit)


if __name__ == "__main__":
    main()
