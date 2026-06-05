"""
Lotte Mart Promo Scraper.

Fetches promo flyers from Lotte Mart website, detects new promos via
content hashing, and downloads images for later OCR processing.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.scrapers.base_scraper import BaseScraper, DEFAULT_HEADERS, deduplicate_refs, fetch_html

# --- Store-specific configuration ---
STORE_NAME = "Lotte"
LOTTE_URL = "https://www.lottemart.co.id/all-promo-mart"

HEADERS = {
    **DEFAULT_HEADERS,
    "Accept-Language": "en-US,en;q=0.5",
}


class LotteScraper(BaseScraper):
    """Lotte Mart promo scraper — downloads images only, no OCR."""

    store_name = STORE_NAME
    headers = HEADERS

    def collect_image_refs(self) -> list[tuple[str, str]]:
        """Fetch Lotte HTML and extract promo image URLs by keyword matching."""
        html = fetch_html(LOTTE_URL, self.headers, self.proxies)
        print(f"[OK] Got {len(html)} bytes")

        soup = __import__("bs4", fromlist=["BeautifulSoup"]).BeautifulSoup(html, "html.parser")
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

        return deduplicate_refs(urls)


def main():
    parser = argparse.ArgumentParser(description="Lotte Promo Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report new images without downloading")
    args = parser.parse_args()

    scraper = LotteScraper()
    scraper.ensure_dirs()
    state = scraper.load_state()

    print("=" * 60)
    print(f"  {scraper.store_name} Promo Scraper")
    if args.dry_run:
        print("  Dry-run: YES (no download)")
    print("=" * 60)
    print()

    image_refs = scraper.collect_image_refs()
    print(f"[*] Found {len(image_refs)} promo image(s) in HTML\n")

    if not image_refs:
        print("[!] No promo images found. Exiting.")
        return

    if args.dry_run:
        # Show what would be new without downloading
        known_hashes = {e["md5"] for e in state.get("processed", [])}
        new_count = 0
        for url, orig in image_refs:
            # Can't compute MD5 without downloading, just report count
            new_count += 1
        print(f"[*] Would check {new_count} image(s) for new content.")
        return

    new_images, existing_images = scraper.download_and_classify(image_refs, state)
    print(f"\n[*] Summary: {len(new_images)} new, {len(existing_images)} already processed\n")

    if not new_images:
        print("[*] No new images to download. Exiting.")
        return

    # Update state with newly downloaded images
    for img in new_images:
        state["processed"].append(img)
    state["last_run"] = datetime.now().isoformat()
    scraper.save_state(state)

    print(f"[*] State file: {scraper.state_file}")
    print(f"[*] Images saved to: {scraper.images_dir}")
    print(f"\n[*] Done. {len(new_images)} new image(s) downloaded.")


if __name__ == "__main__":
    main()
