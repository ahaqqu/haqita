import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import extract_products, validate_product
from scripts.ocr.image_preprocess import preprocess_for_ocr

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

STATE_DIR = Path("data/scrape")
IMAGES_DIR = STATE_DIR / "superindo"
STATE_FILE = STATE_DIR / "superindo_state.json"

REGION_FILTER = "jabodetabek-palembang"
MIN_SIZE = 50 * 1024
MIN_DIM = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_run": None, "processed": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def md5_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def fetch_html(url: str) -> str:
    logger.info(f"Fetching {url} ...")
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    logger.info(f"Got {len(resp.text)} bytes")
    return resp.text


def parse_swiper_images(html: str, fancybox_filter: str) -> list[tuple[str, str]]:
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

    seen = set()
    unique = []
    for url, orig in urls:
        if url not in seen:
            seen.add(url)
            unique.append((url, orig))

    return unique


def parse_page_images(html: str, url: str) -> list[tuple[str, str]]:
    """Route to the right parser based on URL path."""
    if "promo-koran" in url.lower():
        return parse_swiper_images(html, "promo-koran")
    return parse_swiper_images(html, REGION_FILTER)


def download_image(url: str) -> bytes:
    logger.info(f"   Downloading: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    return resp.content


def filename_from_url(url: str, md5_prefix: str = "") -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if not name or "." not in name:
        name = f"promo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    if md5_prefix:
        stem, ext = os.path.splitext(name)
        name = f"{stem}_{md5_prefix[:8]}{ext}"
    return name


def main():
    parser = argparse.ArgumentParser(description="Superindo Promo Scraper + Qwen3-VL OCR")
    parser.add_argument("--dry-run", action="store_true", help="Check for new images without OCR")
    parser.add_argument("--url", help="Single URL override (for testing a specific page)")
    args = parser.parse_args()

    ensure_dirs()
    state = load_state()
    cfg = _load_config()

    urls = [args.url] if args.url else cfg["scrapers"]["superindo"]["urls"]

    print("=" * 60)
    print("  Superindo Promo Scraper")
    if args.dry_run:
        print("  Dry-run: YES (no OCR)")
    print("=" * 60)
    print()

    all_image_refs = []
    for url in urls:
        print(f"[*] Processing: {url}")
        html = fetch_html(url)
        refs = parse_page_images(html, url)
        label = "katalog" if "promo-koran" not in url.lower() else "koran"
        print(f"    Found {len(refs)} image(s) from {label} page\n")
        all_image_refs.extend(refs)

    if not all_image_refs:
        print("[!] No promo images found. Exiting.")
        return

    seen = set()
    deduped = []
    for url, orig in all_image_refs:
        if url not in seen:
            seen.add(url)
            deduped.append((url, orig))

    if len(deduped) < len(all_image_refs):
        print(f"[*] Deduplicated: {len(all_image_refs)} → {len(deduped)} unique images\n")

    known_hashes = {entry["md5"] for entry in state.get("processed", [])}
    seen_this_run = set()
    new_images = []
    existing_images = []

    for url, orig_ref in deduped:
        try:
            data = download_image(url)
            h = md5_hash(data)

            if len(data) < MIN_SIZE:
                print(f"   [SKIP] {os.path.basename(url)} — too small ({len(data)} bytes)")
                continue

            try:
                pil_img = Image.open(BytesIO(data))
                iw, ih = pil_img.size
                if iw < MIN_DIM and ih < MIN_DIM:
                    print(f"   [SKIP] {os.path.basename(url)} — too small ({iw}x{ih})")
                    continue
            except Exception:
                pass

            if h in seen_this_run:
                print(f"   [SKIP] {os.path.basename(url)} — duplicate content (same MD5)")
                continue
            seen_this_run.add(h)

            fname = filename_from_url(url, h)
            dest = IMAGES_DIR / fname
            if not dest.exists():
                dest.write_bytes(data)

            entry = {
                "filename": fname,
                "md5": h,
                "image_url": orig_ref,
                "downloaded_at": datetime.now().isoformat(),
            }

            if h in known_hashes:
                existing_images.append(entry)
                print(f"   [SKIP] {fname} — already processed (MD5 match)")
            else:
                new_images.append(entry)
                print(f"   [NEW]  {fname} — will OCR")

        except Exception as e:
            print(f"   [ERR]  Failed to process {url}: {e}")

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
    output_file = Path("output") / f"superindo_promos_{timestamp}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    ocr_results = []

    for idx, img in enumerate(new_images, 1):
        img_path = IMAGES_DIR / img["filename"]
        print(f"\n[{idx}/{len(new_images)}] [OCR] {img['filename']} ...")

        t0 = time.time()
        try:
            processed_path = preprocess_for_ocr(str(img_path), cfg)
            products_raw = extract_products(processed_path, cfg)
            validated = []
            rejected = []
            for prod in products_raw:
                clean, reason = validate_product(prod, img["filename"])
                if clean:
                    validated.append(clean)
                else:
                    rejected.append({"raw": prod, "reason": reason, "image_source": img["filename"]})
            products = validated
        except Exception as e:
            logger.error(f"OCR failed for {img['filename']}: {e}")
            products = []
            rejected = []
        t1 = time.time()

        result = {
            "filename": img["filename"],
            "md5": img["md5"],
            "image_url": img["image_url"],
            "products": products,
            "rejected": rejected,
            "product_count": len(products),
            "ocr_time_s": round(t1 - t0, 1),
        }
        ocr_results.append(result)
        print(f"   -> {len(products)} products in {t1 - t0:.0f}s")

        for p in products:
            brand = p.get("brand") or ""
            tag = f"[{brand}] " if brand else ""
            unit = p.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            print(f"   - {tag}{p['name']}: {p['price']}{unit_str}")

        partial_output = _build_output(ocr_results, len(existing_images), idx, len(new_images))
        output_file.write_text(json.dumps(partial_output, indent=2, ensure_ascii=False), encoding="utf-8")

        state["processed"].append(result)
        state["last_run"] = datetime.now().isoformat()
        save_state(state)

    final_output = _build_output(ocr_results, len(existing_images), len(new_images), len(new_images), status="complete")
    output_file.write_text(json.dumps(final_output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[*] OCR results saved to: {output_file}")
    print(f"[*] State file: {STATE_FILE}")

    total_prods = sum(r["product_count"] for r in ocr_results)
    print(f"\n[*] Done. {len(ocr_results)} new image(s), {total_prods} total product(s) extracted.")


def _load_config() -> dict:
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    with open(Path(__file__).resolve().parent.parent.parent / 'config.yaml') as f:
        cfg = yaml.safe_load(f)
    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider
    if 'gemini' in cfg['ocr'] and not cfg['ocr']['gemini'].get('api_key'):
        env_key = os.getenv('GEMINI_API_KEY')
        if env_key:
            cfg['ocr']['gemini']['api_key'] = env_key
    cfg['store'] = 'superindo'
    return cfg


def _build_output(ocr_results: list, skipped_count: int, current: int, total: int, status: str = "in_progress") -> dict:
    return {
        "scrape_date": datetime.now().isoformat(),
        "source": "superindo.co.id",
        "mode": "live",
        "new_images": ocr_results,
        "total_new": len(ocr_results),
        "total_skipped": skipped_count,
        "status": status,
    }


if __name__ == "__main__":
    main()
