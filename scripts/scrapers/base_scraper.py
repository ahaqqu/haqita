"""
Base Scraper — Shared utilities for all supermarket scrapers.

Provides: state management, image download, filename generation,
MD5 hashing, and the core scrape loop. Subclasses override only
store-specific behavior (HTML parsing, OCR, product normalization).
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

# Default HTTP headers used by all scrapers
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get_proxy_config() -> dict:
    """Build proxy config from environment variables."""
    proxies = {}
    if os.getenv("HTTP_PROXY"):
        proxies["http"] = os.getenv("HTTP_PROXY")
    if os.getenv("HTTPS_PROXY"):
        proxies["https"] = os.getenv("HTTPS_PROXY")
    return proxies


def md5_hash(data: bytes) -> str:
    """Compute MD5 hex digest of binary data."""
    return hashlib.md5(data).hexdigest()


def load_state(state_file: Path) -> dict:
    """Load scraper state JSON. Returns empty state if file doesn't exist."""
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {"last_run": None, "processed": []}


def save_state(state: dict, state_file: Path) -> None:
    """Save scraper state JSON, creating parent directories if needed."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def filename_from_url(url: str, md5_prefix: str = "") -> str:
    """
    Extract a safe filename from a URL.
    Adds MD5 prefix to prevent overwrites when same filename has different content.
    """
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if not name or "." not in name:
        name = f"promo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    if md5_prefix:
        stem, ext = os.path.splitext(name)
        name = f"{stem}_{md5_prefix[:8]}{ext}"
    return name


def download_image(url: str, headers: dict, proxies: dict, timeout: int = 120) -> bytes:
    """Download image bytes from URL."""
    resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def fetch_html(url: str, headers: dict, proxies: dict, timeout: int = 60) -> str:
    """Fetch HTML content from URL."""
    resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    return resp.text


@dataclass
class ImageEntry:
    """Metadata for a downloaded promo image."""
    filename: str
    md5: str
    image_url: str
    downloaded_at: str = ""

    def __post_init__(self):
        if not self.downloaded_at:
            self.downloaded_at = datetime.now().isoformat()


class BaseScraper:
    """
    Base class for supermarket promo scrapers.

    Subclass must implement:
    - store_name: str
    - images_dir: Path
    - state_file: Path
    - headers: dict
    - collect_image_refs() -> list[tuple[str, str]]  # (url, original_ref)
    - run_ocr(image_path: Path, entry: dict) -> tuple[list[dict], list[dict]]
    - build_output(ocr_results, skipped_count, status) -> dict
    """

    # --- Override in subclass ---
    store_name: str = "unknown"
    images_dir: Path = Path("output/scrape/unknown")
    state_file: Path = Path("output/scrape/unknown_state.json")
    headers: dict = field(default_factory=lambda: dict(DEFAULT_HEADERS))

    # --- Configurable thresholds ---
    min_image_size_kb: int = 50
    min_dimension: int = 300

    def __init__(self):
        self.proxies = get_proxy_config()

    def ensure_dirs(self) -> None:
        """Create images directory if it doesn't exist."""
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict:
        return load_state(self.state_file)

    def save_state(self, state: dict) -> None:
        save_state(state, self.state_file)

    def collect_image_refs(self) -> list[tuple[str, str]]:
        """
        Return list of (url, original_ref) tuples for promo images.
        Must be implemented by subclass.
        """
        raise NotImplementedError

    def run_ocr(self, image_path: Path, entry: dict) -> tuple[list[dict], list[dict]]:
        """
        Run OCR on an image. Returns (products, rejected).
        Must be implemented by subclass.
        """
        raise NotImplementedError

    def build_output(self, ocr_results: list, skipped_count: int, status: str) -> dict:
        """
        Build the final output dict.
        Must be implemented by subclass.
        """
        raise NotImplementedError

    def download_and_classify(
        self, image_refs: list[tuple[str, str]], state: dict
    ) -> tuple[list[dict], list[dict]]:
        """
        Download images, check size/dimensions, classify as new or existing.

        Returns: (new_images, existing_images)
        """
        known_hashes = {e["md5"] for e in state.get("processed", [])}
        seen_this_run: set[str] = set()
        new_images: list[dict] = []
        existing_images: list[dict] = []
        min_size = self.min_image_size_kb * 1024
        min_dim = self.min_dimension

        for url, orig_ref in image_refs:
            try:
                data = download_image(url, self.headers, self.proxies)
                h = md5_hash(data)

                # Size check
                if len(data) < min_size:
                    print(f"   [SKIP] {os.path.basename(urlparse(orig_ref).path)} — too small ({len(data)} bytes)")
                    continue

                # Dimension check
                try:
                    pil_img = Image.open(BytesIO(data))
                    iw, ih = pil_img.size
                    if iw < min_dim and ih < min_dim:
                        print(f"   [SKIP] {os.path.basename(urlparse(orig_ref).path)} — too small ({iw}x{ih})")
                        continue
                except Exception:
                    pass

                # Duplicate check within this run
                if h in seen_this_run:
                    print(f"   [SKIP] {os.path.basename(urlparse(orig_ref).path)} — duplicate content (same MD5)")
                    continue
                seen_this_run.add(h)

                # Save image
                fname = filename_from_url(orig_ref, h)
                dest = self.images_dir / fname
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

        return new_images, existing_images

    def run_ocr_loop(
        self, new_images: list[dict], existing_images: list[dict], output_file: Path
    ) -> list[dict]:
        """
        Run OCR on each new image, writing incremental output.
        Returns the list of OCR results.
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)
        ocr_results: list[dict] = []

        for idx, img in enumerate(new_images, 1):
            img_path = self.images_dir / img["filename"]
            print(f"\n[{idx}/{len(new_images)}] [OCR] {img['filename']} ...")

            t0 = time.time()
            try:
                products, rejected = self.run_ocr(img_path, img)
            except Exception as e:
                print(f"   [ERR] OCR failed for {img['filename']}: {e}")
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

            # Print extracted products
            for p in products:
                brand = p.get("brand") or ""
                tag = f"[{brand}] " if brand else ""
                unit = p.get("unit", "") or ""
                unit_str = f" {unit}" if unit else ""
                print(f"   - {tag}{p['name']}: {p['price']}{unit_str}")

            # Write incremental output
            output = self.build_output(ocr_results, len(existing_images), "in_progress")
            output_file.write_text(
                json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return ocr_results
