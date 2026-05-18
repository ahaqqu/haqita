"""
Superindo Promo Scraper.

Fetches promo flyers from Superindo website (Katalog Super Hemat + Promo Koran),
detects new promos via content hashing, and downloads images for later OCR processing.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.scrapers.base_scraper import BaseScraper, DEFAULT_HEADERS, deduplicate_refs, fetch_html

# --- Store-specific configuration ---
STORE_NAME = "Superindo"
REGION_FILTER = "jabodetabek-palembang"


class SuperindoScraper(BaseScraper):
    """Superindo promo scraper — downloads images only, no OCR."""

    store_name = STORE_NAME
    headers = DEFAULT_HEADERS

    def __init__(self, urls: list[str] = None):
        super().__init__()
        self.urls = urls or [
            "https://www.superindo.co.id/promosi/katalog-super-hemat/",
            "https://www.superindo.co.id/promosi/promo-koran/",
        ]

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

        deduped = deduplicate_refs(all_refs)
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


def main():
    parser = argparse.ArgumentParser(description="Superindo Promo Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Check for new images without downloading")
    parser.add_argument("--url", help="Single URL override (for testing a specific page)")
    args = parser.parse_args()

    scraper = SuperindoScraper()
    scraper.ensure_dirs()
    state = scraper.load_state()

    # Support single URL override
    if args.url:
        scraper.urls = [args.url]

    print("=" * 60)
    print(f"  {scraper.store_name} Promo Scraper")
    if args.dry_run:
        print("  Dry-run: YES (no download)")
    print("=" * 60)
    print()

    image_refs = scraper.collect_image_refs()

    if not image_refs:
        print("[!] No promo images found. Exiting.")
        return

    if args.dry_run:
        print(f"[*] Would check {len(image_refs)} image(s) for new content.")
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
