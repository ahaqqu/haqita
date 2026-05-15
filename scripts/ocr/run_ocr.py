"""
Standalone OCR — extract products from scraped brochure images.

Reads images from output/scrape/<store>/, writes JSON to output/ocr/.
Can process all images or a specific one.

Usage:
    python scripts/ocr/run_ocr.py [options]

Options:
    --store STORE          Store name: lotte or superindo (default: lotte)
    --image FILENAME       Process specific image only (default: all new)
    --dry-run              Report products without saving to file
    --no-docker            Run natively (not in Docker)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ocr.ocr_processor import extract_products, validate_product
from scripts.ocr.image_preprocess import preprocess_for_ocr

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def load_config(store: str) -> dict:
    """Load config.yaml with .env overrides."""
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    with open(Path(__file__).resolve().parent.parent.parent / 'config.yaml') as f:
        cfg = yaml.safe_load(f)
    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg['ocr']['gemini']['api_key'] = env_key
    cfg['store'] = store
    return cfg


def discover_images(scrape_dir: Path, specific: str | None = None) -> list[Path]:
    """Find images to process in scrape directory."""
    if specific:
        p = scrape_dir / specific
        if not p.exists():
            print(f"[!!] Image not found: {p}")
            return []
        return [p]
    exts = {'.jpg', '.jpeg', '.png', '.webp'}
    return sorted(p for p in scrape_dir.iterdir() if p.suffix.lower() in exts)


def run_ocr(cfg: dict, scrape_dir: Path, output_dir: Path, specific: str | None = None, dry_run: bool = False) -> None:
    """Run OCR on images from scrape directory."""
    store = cfg.get('store', 'lotte')
    provider = cfg['ocr']['provider']

    print("=" * 60)
    print(f"  OCR — {store.title()} ({provider})")
    if dry_run:
        print("  Dry-run: YES (no file saved)")
    if specific:
        print(f"  Image: {specific}")
    else:
        print("  Image: all")
    print("=" * 60)
    print()

    images = discover_images(scrape_dir, specific)
    if not images:
        print("[!!] No images found to process.")
        return

    print(f"[*] Found {len(images)} image(s)\n")

    all_products = []
    all_rejected = []

    for idx, img_path in enumerate(images, 1):
        print(f"[{idx}/{len(images)}] {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB)")

        print("    Preprocessing...", end=" ")
        sys.stdout.flush()
        try:
            processed = preprocess_for_ocr(str(img_path), cfg)
            print("OK")
        except Exception as e:
            print(f"FAIL: {e}")
            continue

        t0 = time.time()
        validated, rejected = [], []
        try:
            products_raw = extract_products(processed, cfg)
            for prod in products_raw:
                clean, reason = validate_product(prod, img_path.name)
                if clean:
                    validated.append(clean)
                else:
                    rejected.append({"raw": prod, "reason": reason})
        except Exception as e:
            print(f"    [ERR] OCR failed: {e}")
            continue

        ocr_time = time.time() - t0
        print(f"    {len(validated)} products, {len(rejected)} rejected ({ocr_time:.0f}s)")

        for p in validated:
            brand = p.get("brand") or ""
            tag = f"[{brand}] " if brand else ""
            unit = p.get("unit", "") or ""
            unit_str = f" {unit}" if unit else ""
            print(f"    - {tag}{p['name']}: Rp {p['price']:,}{unit_str}")

        all_products.extend(validated)
        all_rejected.extend(rejected)

        if str(processed) != str(img_path):
            Path(processed).unlink(missing_ok=True)
        print()

    if dry_run:
        print(f"[*] Dry-run complete: {len(all_products)} products, {len(all_rejected)} rejected")
        print("    No file saved.")
        return

    if not all_products and not all_rejected:
        print("[*] No products extracted. Nothing to save.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{store}_promos_{timestamp}.json"

    output = {
        "store": store.title(),
        "scraped_at": datetime.now().isoformat(),
        "ocr_provider": provider,
        "images_processed": len(images),
        "products": all_products,
        "rejected": all_rejected,
        "stats": {
            "products_extracted": len(all_products),
            "products_rejected": len(all_rejected),
        },
    }

    output_file.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[*] Saved to {output_file}")
    print(f"    {len(all_products)} products, {len(all_rejected)} rejected")


def main():
    parser = argparse.ArgumentParser(description='Run OCR on scraped brochure images')
    parser.add_argument('--store', type=str, default='lotte', help='Store name: lotte or superindo')
    parser.add_argument('--image', type=str, default=None, help='Process specific image only')
    parser.add_argument('--dry-run', action='store_true', help='Report products without saving')
    parser.add_argument('--no-docker', action='store_true', help='Run natively')
    args = parser.parse_args()

    cfg = load_config(args.store)
    scrape_dir = Path(f'output/scrape/{args.store}')
    output_dir = Path('output/ocr')

    run_ocr(cfg, scrape_dir, output_dir, args.image, args.dry_run)


if __name__ == '__main__':
    main()
