"""
Shared integration test utilities for OCR testing.

Both Lotte and Superindo integration tests use this module.
Assert files are read from: data/test/<store>/ocr-result/<provider>/<image>.json
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import extract_products, validate_product
from tests.integration.compare_results import load_asserts, compare_results

# Base test data directory
TEST_DATA_DIR = Path("data/test")

# Output directory for integration test results
OUTPUT_DIR = Path("work/tests")


def load_config(store: str) -> dict:
    """Load config.yaml with .env overrides."""
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    with open(Path(__file__).resolve().parent.parent.parent / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    if "gemini" in cfg["ocr"] and not cfg["ocr"]["gemini"].get("api_key"):
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            cfg["ocr"]["gemini"]["api_key"] = env_key
    cfg["store"] = store
    return cfg


def check_provider(cfg: dict) -> bool:
    """Check if Gemini API key is available."""
    api_key = cfg["ocr"].get("gemini", {}).get("api_key") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[!!] GEMINI_API_KEY not set in .env")
        return False
    return True


def run_ocr_on_image(
    img_path: Path,
    cfg: dict,
    output_dir: Path,
) -> tuple[int, str]:
    """
    Run OCR on a single image, compare against assert, write output.

    Returns: (exit_code, result_label)
    """
    store = cfg.get("store", "unknown")

    print(f"[*] Image: {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB)")
    print()

    print("[*] Running OCR...")
    sys.stdout.flush()
    t0 = time.time()
    validated, rejected, ocr_error = [], [], None

    try:
        products_raw = extract_products(str(img_path), cfg)
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
            pr = f" -- {promo}" if promo else ""
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

    # Build actual result dict
    actual_result = {
        "image": img_path.name, "provider": "gemini",
        "ocr_time_s": round(ocr_time, 1),
        "products_count": len(validated), "rejected_count": len(rejected),
        "products": validated, "rejected": rejected,
    }

    # Write output to work/tests/<store>/<image_stem>.json
    output_path = output_dir / store / f"{img_path.stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(actual_result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Compare against assert if available (from data/test/<store>/ocr-result/gemini/)
    expected = load_asserts(TEST_DATA_DIR, "gemini", store, img_path.stem)
    if expected:
        print()
        print("[*] Comparing against expected result...")
        diffs = compare_results(actual_result, expected)
        if diffs:
            print(f"  [!!] {len(diffs)} difference(s) found:")
            for d in diffs:
                print(d)
            result = "DIFF"
            exit_code = 4
        else:
            print("  [OK] Output matches expected result.")

    print(f"\n  Result: {result}")
    return exit_code, result


def run_store_tests(
    store: str,
    image_dir: Path,
    output_dir: Path = OUTPUT_DIR,
    images: list[Path] = None,
) -> int:
    """
    Run integration tests for all images in a store's image directory.

    Returns: exit code (0 = all pass)
    """
    cfg = load_config(store)

    print("=" * 60)
    print(f"  Integration Test: {store} OCR (gemini)")
    print("=" * 60)
    print()

    print("[*] Checking provider...", end=" ")
    sys.stdout.flush()
    if not check_provider(cfg):
        return 1
    print("OK")
    print()

    # Discover images
    if images is None:
        if not image_dir.exists():
            print(f"[!!] Image directory not found: {image_dir}")
            return 1
        images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})

    if not images:
        print(f"[!!] No images found in {image_dir}")
        return 1

    print(f"[*] Found {len(images)} image(s) to test\n")

    all_exit = 0
    for img_path in images:
        if not img_path.exists():
            print(f"[!!] Skipping -- image not found: {img_path}")
            continue

        print("-" * 40)
        code, result = run_ocr_on_image(img_path, cfg, output_dir)
        if code != 0:
            all_exit = code
        print()

    return all_exit
