"""
Lotte Mart Promo Scraper + OCR.

Fetches promo flyers from Lotte Mart website, detects new promos via
content hashing, and extracts product data using OCR.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.scrapers.base_scraper import BaseScraper, DEFAULT_HEADERS, fetch_html
from scripts.ocr.image_preprocess import preprocess_for_ocr
from scripts.ocr.ollama_client import call_ollama_ocr, extract_promo_date

# --- Store-specific configuration ---
STORE_NAME = "Lotte"
STATE_DIR = Path("data/scrape")
IMAGES_DIR = STATE_DIR / "lotte"
STATE_FILE = STATE_DIR / "lotte_state.json"
LOTTE_URL = "https://www.lottemart.co.id/all-promo-mart"

HEADERS = {
    **DEFAULT_HEADERS,
    "Accept-Language": "en-US,en;q=0.5",
}


def _normalize_lotte_products(
    raw_products: list[dict], image_source: str, promo_date: str | None
) -> list[dict]:
    """
    Add missing fields to OCR output to match the standard product schema.

    New client already returns: name (str), brand (str|None), unit (str|None),
    price (int), promo (str|None). We add: period, image_source, ocr_raw_price,
    ocr_confidence.
    """
    normalized = []
    for raw in raw_products:
        price = raw.get("price")
        if price is None:
            continue

        normalized.append({
            "name": str(raw.get("name", "")).strip(),
            "brand": str(raw["brand"]).strip() if raw.get("brand") else None,
            "unit": str(raw["unit"]).strip() if raw.get("unit") else None,
            "price": int(price),
            "promo": str(raw["promo"]).strip() if raw.get("promo") else None,
            "period": promo_date or None,
            "image_source": image_source,
            "ocr_raw_price": str(price),
            "ocr_confidence": 1.0,
        })
    return normalized


class LotteScraper(BaseScraper):
    """Lotte Mart promo scraper using keyword-based image detection."""

    store_name = STORE_NAME
    images_dir = IMAGES_DIR
    state_file = STATE_FILE
    headers = HEADERS

    def __init__(self, cfg: dict = None):
        super().__init__()
        self.cfg = cfg or {"ocr": {"provider": "ollama", "ollama": {"preprocess": True}}}

    def collect_image_refs(self) -> list[tuple[str, str]]:
        """Fetch Lotte HTML and extract promo image URLs by keyword matching."""
        html = fetch_html(LOTTE_URL, self.headers, self.proxies)
        print(f"[OK] Got {len(html)} bytes")

        soup = BeautifulSoup(html, "html.parser")
        urls = []
        keywords = {"promo", "flyer", "catalog", "katalog", "ht"}
        exclude_ext = {".gif"}

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue

            src_lower = src.lower()
            if any(src_lower.endswith(ext) for ext in exclude_ext):
                continue
            if any(k in src_lower for k in keywords):
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://www.lottemart.co.id" + src
                urls.append((src, src))

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for url, orig in urls:
            if url not in seen:
                seen.add(url)
                unique.append((url, orig))

        return unique

    def run_ocr(self, image_path: Path, entry: dict) -> tuple[list[dict], list[dict]]:
        """Run OCR on a Lotte brochure image with preprocessing."""
        processed_path = preprocess_for_ocr(str(image_path), self.cfg)
        products_raw = call_ollama_ocr(str(processed_path), self.cfg)
        promo_date = extract_promo_date(str(processed_path), self.cfg)
        products = _normalize_lotte_products(
            products_raw, entry["filename"], promo_date
        )
        # Clean up processed temp file if different from original
        if processed_path != str(image_path):
            Path(processed_path).unlink(missing_ok=True)
        return products, []

    def build_output(self, ocr_results: list, skipped_count: int, status: str) -> dict:
        """Build Lotte-specific output dict."""
        return {
            "scrape_date": datetime.now().isoformat(),
            "source": LOTTE_URL,
            "new_images": ocr_results,
            "total_new": len(ocr_results),
            "total_skipped": skipped_count,
            "status": status,
        }


def _load_config() -> dict:
    """Load config.yaml with .env overrides."""
    import yaml
    from dotenv import load_dotenv
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


def main():
    parser = argparse.ArgumentParser(description="Lotte Promo Scraper + OCR")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report new images without OCR")
    args = parser.parse_args()

    cfg = _load_config()
    scraper = LotteScraper(cfg)
    scraper.ensure_dirs()
    state = scraper.load_state()

    print("=" * 60)
    print(f"  {scraper.store_name} Promo Scraper")
    if args.dry_run:
        print("  Dry-run: YES (no OCR)")
    print("=" * 60)
    print()

    image_refs = scraper.collect_image_refs()
    print(f"[*] Found {len(image_refs)} promo image(s) in HTML\n")

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
    output_file = Path("output") / f"lotte_promos_{timestamp}.json"

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
