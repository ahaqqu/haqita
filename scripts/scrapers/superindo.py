"""
Superindo Promo Scraper + OCR.

Fetches promo flyers from Superindo website (Katalog Super Hemat + Promo Koran),
detects new promos via content hashing, and extracts product data using OCR.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Add project root to path for OCR module imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import extract_products, validate_product
from scripts.ocr.image_preprocess import preprocess_for_ocr
from scripts.scrapers.base_scraper import BaseScraper, DEFAULT_HEADERS, fetch_html

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Store-specific configuration ---
STORE_NAME = "Superindo"
STATE_DIR = Path("output/scrape")
IMAGES_DIR = STATE_DIR / "superindo"
STATE_FILE = STATE_DIR / "superindo_state.json"
REGION_FILTER = "jabodetabek-palembang"


def _load_config() -> dict:
    """Load config.yaml with .env overrides."""
    load_dotenv()
    cfg_path = Path(__file__).resolve().parent.parent.parent / 'config.yaml'
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg['ocr']['gemini']['api_key'] = env_key
    return cfg


class SuperindoScraper(BaseScraper):
    """Superindo promo scraper using swiper/fancybox image detection."""

    store_name = STORE_NAME
    images_dir = IMAGES_DIR
    state_file = STATE_FILE
    headers = DEFAULT_HEADERS

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.urls = cfg["scrapers"]["superindo"]["urls"]

    def collect_image_refs(self) -> list[tuple[str, str]]:
        """Fetch all configured URLs and extract promo image URLs."""
        all_refs = []
        for url in self.urls:
            print(f"[*] Processing: {url}")
            html = fetch_html(url, self.headers, self.proxies)
            refs = self._parse_page_images(html, url)
            label = "katalog" if "promo-koran" not in url.lower() else "koran"
            print(f"    Found {len(refs)} image(s) from {label} page\n")
            all_refs.extend(refs)

        # Deduplicate across pages
        seen = set()
        deduped = []
        for url, orig in all_refs:
            if url not in seen:
                seen.add(url)
                deduped.append((url, orig))

        if len(deduped) < len(all_refs):
            print(f"[*] Deduplicated: {len(all_refs)} → {len(deduped)} unique images\n")

        return deduped

    def _parse_page_images(self, html: str, url: str) -> list[tuple[str, str]]:
        """Route to the right parser based on URL path."""
        if "promo-koran" in url.lower():
            return self._parse_swiper_images(html, "promo-koran")
        return self._parse_swiper_images(html, REGION_FILTER)

    @staticmethod
    def _parse_swiper_images(html: str, fancybox_filter: str) -> list[tuple[str, str]]:
        """Parse swiper-slide fancybox images filtered by data-fancybox value."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []

        for slide in soup.select(".swiper-slide"):
            link = slide.select_one("a.fancybox")
            if not link:
                continue
            fbox = link.get("data-fancybox", "")
            if fbox != fancybox_filter:
                continue
            href = link.get("href", "")
            if href:
                urls.append((href, href))

        return urls

    def run_ocr(self, image_path: Path, entry: dict) -> tuple[list[dict], list[dict]]:
        """Run OCR on a Superindo brochure image with validation."""
        processed_path = preprocess_for_ocr(str(image_path), self.cfg)
        products_raw = extract_products(processed_path, self.cfg)

        validated = []
        rejected = []
        for prod in products_raw:
            clean, reason = validate_product(prod, entry["filename"])
            if clean:
                validated.append(clean)
            else:
                rejected.append({"raw": prod, "reason": reason, "image_source": entry["filename"]})

        # Clean up processed temp file (only if different from source)
        if processed_path != str(image_path):
            Path(processed_path).unlink(missing_ok=True)
        return validated, rejected

    def build_output(self, ocr_results: list, skipped_count: int, status: str) -> dict:
        """Build Superindo-specific output dict."""
        return {
            "scrape_date": datetime.now().isoformat(),
            "source": "superindo.co.id",
            "mode": "live",
            "new_images": ocr_results,
            "total_new": len(ocr_results),
            "total_skipped": skipped_count,
            "status": status,
        }


def main():
    parser = argparse.ArgumentParser(description="Superindo Promo Scraper + OCR")
    parser.add_argument("--dry-run", action="store_true", help="Check for new images without OCR")
    parser.add_argument("--url", help="Single URL override (for testing a specific page)")
    args = parser.parse_args()

    cfg = _load_config()
    scraper = SuperindoScraper(cfg)
    scraper.ensure_dirs()
    state = scraper.load_state()

    # Support single URL override
    if args.url:
        scraper.urls = [args.url]

    print("=" * 60)
    print(f"  {scraper.store_name} Promo Scraper")
    if args.dry_run:
        print("  Dry-run: YES (no OCR)")
    print("=" * 60)
    print()

    image_refs = scraper.collect_image_refs()

    if not image_refs:
        print("[!] No promo images found. Exiting.")
        return

    new_images, existing_images = scraper.download_and_classify(image_refs, state)
    print(f"\n[*] Summary: {len(new_images)} new, {len(existing_images)} already processed\n")

    if args.dry_run:
        if new_images:
            print("New images (would OCR):")
            for img in new_images:
                print(f"  - {img['filename']} ({img['md5'][:12]}...)")
        else:
            print("Nothing new to process.")
        return

    if not new_images:
        print("[*] No new images to OCR. Exiting.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path("output/ocr") / f"superindo_promos_{timestamp}.json"

    ocr_results = scraper.run_ocr_loop(new_images, existing_images, output_file)

    # Write final output with complete status
    final_output = scraper.build_output(ocr_results, len(existing_images), "complete")
    output_file.write_text(
        json.dumps(final_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Update state
    state["processed"].extend(ocr_results)
    state["last_run"] = datetime.now().isoformat()
    scraper.save_state(state)

    print(f"\n[*] OCR results saved to: {output_file}")
    print(f"[*] State file: {scraper.state_file}")

    total_prods = sum(r["product_count"] for r in ocr_results)
    print(f"\n[*] Done. {len(ocr_results)} new image(s), {total_prods} total product(s) extracted.")


if __name__ == "__main__":
    main()
