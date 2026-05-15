import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qwen_ocr_processor import extract_product_prices, extract_promo_date

STATE_DIR = Path("data/scrape")
IMAGES_DIR = STATE_DIR / "lotte"
STATE_FILE = STATE_DIR / "lotte_state.json"

LOTTE_URL = "https://www.lottemart.co.id/all-promo-mart"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

PROXY_CONFIG = {}
if os.getenv("HTTP_PROXY"):
    PROXY_CONFIG["http"] = os.getenv("HTTP_PROXY")
if os.getenv("HTTPS_PROXY"):
    PROXY_CONFIG["https"] = os.getenv("HTTPS_PROXY")


def ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def md5_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_run": None, "processed": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_html() -> str:
    print(f"[*] Fetching {LOTTE_URL} ...")
    resp = requests.get(LOTTE_URL, headers=HEADERS, proxies=PROXY_CONFIG, timeout=60)
    resp.raise_for_status()
    print(f"[OK] Got {len(resp.text)} bytes")
    return resp.text


def parse_promo_images(html: str) -> list:
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

    seen = set()
    unique = []
    for url, orig in urls:
        if url not in seen:
            seen.add(url)
            unique.append((url, orig))

    return unique


def download_image(url: str) -> bytes:
    print(f"   Downloading: {url}")
    resp = requests.get(url, headers=HEADERS, proxies=PROXY_CONFIG, timeout=120)
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
    parser = argparse.ArgumentParser(description="Lotte Promo Scraper + Qwen3-VL OCR")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report new images without OCR")
    args = parser.parse_args()

    ensure_dirs()
    state = load_state()

    print("=" * 60)
    print("  Lotte Promo Scraper")
    if args.dry_run:
        print("  Dry-run: YES (no OCR)")
    print("=" * 60)
    print()

    html = fetch_html()

    image_refs = parse_promo_images(html)
    print(f"[*] Found {len(image_refs)} promo image(s) in HTML\n")

    if not image_refs:
        print("[!] No promo images found. Exiting.")
        return

    known_hashes = {entry["md5"] for entry in state.get("processed", [])}
    seen_this_run = set()
    new_images = []
    existing_images = []
    MIN_SIZE = 50 * 1024
    MIN_DIM = 300

    for url, orig_ref in image_refs:
        try:
            data = download_image(url)
            h = md5_hash(data)

            if len(data) < MIN_SIZE:
                print(f"   [SKIP] {os.path.basename(urlparse(orig_ref).path)} — too small ({len(data)} bytes)")
                continue

            try:
                pil_img = Image.open(BytesIO(data))
                iw, ih = pil_img.size
                if iw < MIN_DIM and ih < MIN_DIM:
                    print(f"   [SKIP] {os.path.basename(urlparse(orig_ref).path)} — too small ({iw}x{ih})")
                    continue
            except Exception:
                pass

            if h in seen_this_run:
                print(f"   [SKIP] {os.path.basename(urlparse(orig_ref).path)} — duplicate content (same MD5)")
                continue
            seen_this_run.add(h)

            fname = filename_from_url(orig_ref, h)
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
            print(f"   [ERR]  Failed to process {orig_ref}: {e}")

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
    output_file.parent.mkdir(parents=True, exist_ok=True)

    ocr_results = []
    for idx, img in enumerate(new_images, 1):
        img_path = IMAGES_DIR / img["filename"]
        print(f"\n[{idx}/{len(new_images)}] [OCR] {img['filename']} ...")

        t0 = time.time()
        try:
            products = extract_product_prices(str(img_path))
            promo_date = extract_promo_date(str(img_path))
        except Exception as e:
            print(f"   [ERR] OCR failed for {img['filename']}: {e}")
            products = []
            promo_date = None
        t1 = time.time()

        result = {
            "filename": img["filename"],
            "md5": img["md5"],
            "image_url": img["image_url"],
            "products": products,
            "product_count": len(products),
            "promo_period": promo_date or None,
            "ocr_time_s": round(t1 - t0, 1),
        }
        ocr_results.append(result)
        print(f"   -> {len(products)} products in {t1-t0:.0f}s")

        if promo_date:
            print(f"   Period: {promo_date}")
        for p in products:
            brand = p.get("brand") or ""
            product = p.get("product", "?")
            price = p.get("price", "?")
            unit = p.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            tag = f"[{brand}] " if brand else ""
            print(f"   - {tag}{product}: {price}{unit_str}")

        partial_output = {
            "scrape_date": datetime.now().isoformat(),
            "source": LOTTE_URL,
            "new_images": ocr_results,
            "total_new": len(ocr_results),
            "total_skipped": len(existing_images),
            "status": f"in_progress ({idx}/{len(new_images)})",
        }
        output_file.write_text(
            json.dumps(partial_output, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        state["processed"].append(result)
        state["last_run"] = datetime.now().isoformat()
        save_state(state)

    output_file.write_text(
        json.dumps({
            "scrape_date": datetime.now().isoformat(),
            "source": LOTTE_URL,
            "new_images": ocr_results,
            "total_new": len(ocr_results),
            "total_skipped": len(existing_images),
            "status": "complete",
        }, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[*] OCR results saved to: {output_file}")
    print(f"[*] State file: {STATE_FILE}")

    total_prods = sum(r["product_count"] for r in ocr_results)
    print(f"\n[*] Done. {len(ocr_results)} new image(s), {total_prods} total product(s) extracted.")


if __name__ == "__main__":
    main()
