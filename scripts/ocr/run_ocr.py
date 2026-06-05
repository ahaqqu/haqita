"""
Standalone OCR — extract products from scraped brochure images.

Reads images from output/scrape/<store>/, writes JSON to output/ocr/.
Tracks processed images in output/ocr/<store>_ocr_state.json to avoid
re-OCR-ing the same images (saves API quota).

Usage:
    python scripts/ocr/run_ocr.py [options]

Options:
    --store STORE          Store name: lotte or superindo (default: lotte)
    --image FILENAME       Process specific image only (default: all new)
    --dry-run              Report products without saving to file
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.config import load_config
from scripts.ocr.ocr_processor import extract_products, validate_product
from scripts.ocr.gemini_client import QuotaExhaustedError

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# OCR state directory
OCR_STATE_DIR = Path("database/ocr")


def load_ocr_state(store: str) -> dict:
    """Load OCR state. Tracks which images have been OCR'd."""
    state_file = OCR_STATE_DIR / store / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding='utf-8'))
    return {'processed': [], 'last_run': None}


def save_ocr_state(store: str, state: dict) -> None:
    """Save OCR state."""
    OCR_STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = OCR_STATE_DIR / store / "state.json"
    state_file.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )


def discover_images(scrape_dir: Path, state: dict, specific: str | None = None) -> tuple[list[Path], list[str], int]:
    """
    Find images to process. Skips already-OCR'd images.

    Returns: (new_images_to_process, already_processed_filenames, total_count)
    """
    processed = set(state.get('processed', []))

    if specific:
        p = scrape_dir / specific
        if not p.exists():
            print(f"[!!] Image not found: {p}")
            return [], [], 0
        if p.name in processed:
            print(f"[!] Image '{p.name}' was already OCR'd. Processing anyway (specific request).")
            return [p], [], 1
        return [p], [], 1

    exts = {'.jpg', '.jpeg', '.png', '.webp'}
    all_images = sorted(p for p in scrape_dir.rglob('*') if p.is_file() and p.suffix.lower() in exts)

    new = [p for p in all_images if p.name not in processed]
    old = [p.name for p in all_images if p.name in processed]
    return new, old, len(all_images)


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
    print("=" * 60)
    print()

    if not scrape_dir.exists():
        print(f"[!!] Scrape directory not found: {scrape_dir}")
        print("    Run Stage 1 (Scrape) first.")
        return

# Load state to skip already-processed images
    state = load_ocr_state(store)
    new_images, processed_images, total_images = discover_images(scrape_dir, state, specific)

    if specific:
        # Specific image: process it regardless of state
        images_to_process = new_images if new_images else [scrape_dir / specific]
        processed_count = 0
    else:
        images_to_process = new_images
        processed_count = len(processed_images)
        if processed_count > 0:
            print(f"[*] {processed_count} image(s) already OCR'd (skipped)")

    if not images_to_process:
        if specific:
            print(f"[!!] Image not found: {specific}")
        else:
            if processed_count > 0:
                print(f"[*] No new images to OCR. All {processed_count} image(s) already processed.")
            elif total_images > 0:
                print(f"[*] No new images to OCR. All {total_images} image(s) already processed.")
            else:
                print("[*] No brochure images found in scrape directory.")
                print("    Run Scrape to download new brochures.")
        return

    print(f"[*] Found {len(images_to_process)} new image(s) to process\n")

    all_products = []
    all_rejected = []
    processed_filenames = []
    quota_exhausted = None

    for idx, img_path in enumerate(images_to_process, 1):
        print(f"[{idx}/{len(images_to_process)}] {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB)")

        print(f"    Processing image [{idx}/{len(images_to_process)}] {img_path.name} ({img_path.stat().st_size / 1024:.0f} KB) for OCR to {provider}")

        t0 = time.time()
        validated, rejected = [], []
        try:
            products_raw = extract_products(str(img_path), cfg)
            for prod in products_raw:
                clean, reason = validate_product(prod, img_path.name)
                if clean:
                    clean['image_path'] = str(img_path).replace('\\', '/')
                    validated.append(clean)
                else:
                    prod['image_path'] = str(img_path).replace('\\', '/')
                    rejected.append({"raw": prod, "reason": reason})
        except QuotaExhaustedError as e:
            print(f"    [ERR] {provider.title()} daily quota exhausted. Stopping OCR for remaining images.")
            print(f"    {e}")
            quota_exhausted = str(e)
            break
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
        processed_filenames.append(img_path.name)
        print()

    if quota_exhausted:
        skipped = len(images_to_process) - len(processed_filenames)
        print(f"[*] {skipped} image(s) skipped due to quota exhaustion")

    if dry_run:
        print(f"[*] Dry-run complete: {len(all_products)} products, {len(all_rejected)} rejected")
        print("    No file saved. State not updated.")
        if quota_exhausted:
            raise QuotaExhaustedError("Daily quota exhausted — OCR stopped")
        return

    if not all_products and not all_rejected and not quota_exhausted:
        print("[*] No products extracted. Nothing to save.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{store}_promos_{timestamp}.json"

    output = {
        "store": store.title(),
        "scraped_at": datetime.now().isoformat(),
        "ocr_provider": provider,
        "images_processed": len(images_to_process),
        "images": processed_filenames,
        "products": all_products,
        "rejected": all_rejected,
        "stats": {
            "products_extracted": len(all_products),
            "products_rejected": len(all_rejected),
        },
    }
    if quota_exhausted:
        output["quota_exhausted"] = quota_exhausted

    output_file.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Update state
    state['processed'].extend(processed_filenames)
    state['last_run'] = datetime.now().isoformat()
    save_ocr_state(store, state)

    print(f"[*] Saved to {output_file}")
    print(f"[*] State updated: {len(processed_filenames)} image(s) marked as processed")
    print(f"    Total: {len(all_products)} products, {len(all_rejected)} rejected")

    if quota_exhausted:
        raise QuotaExhaustedError("Daily quota exhausted — OCR stopped")


def main():
    parser = argparse.ArgumentParser(description='Run OCR on scraped brochure images')
    parser.add_argument('--store', type=str, default='lotte', help='Store name: lotte or superindo')
    parser.add_argument('--image', type=str, default=None, help='Process specific image only')
    parser.add_argument('--dry-run', action='store_true', help='Report products without saving')
    args = parser.parse_args()

    cfg = load_config(store=args.store)
    scrape_dir = Path(f'database/scrape/{args.store}')
    output_dir = Path(f'database/ocr/{args.store}')

    run_ocr(cfg, scrape_dir, output_dir, args.image, args.dry_run)


if __name__ == '__main__':
    main()
