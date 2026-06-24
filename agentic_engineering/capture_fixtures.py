#!/usr/bin/env python3
"""
Capture real OCR and AI verifier fixtures from Gemini.

Usage:
    CAPTURE_FIXTURES=1 .venv/bin/python agentic_engineering/capture_fixtures.py
    .venv/bin/python agentic_engineering/capture_fixtures.py            # dry-run

When CAPTURE_FIXTURES is set:
  - Runs real OCR on every image in agentic_engineering/images/
  - Writes normalized fixture JSON to agentic_engineering/mocks/ocr_fixtures/
  - Captures real AI verifier responses for ambiguous pairs

Default (dry-run): prints what would be captured without calling Gemini.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import load_config
from dotenv import load_dotenv

load_dotenv()

FIXTURES_DIR = ROOT / "agentic_engineering" / "mocks" / "ocr_fixtures"
IMAGES_DIR = ROOT / "agentic_engineering" / "images"
CAPTURE = os.getenv("CAPTURE_FIXTURES") == "1"


def _base_name(stem: str) -> str:
    """Strip the MD5 suffix that base_scraper.filename_from_url appends."""
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 8 and all(c in "0123456789abcdef" for c in parts[1]):
        return parts[0]
    return stem


def capture_ocr_fixtures() -> None:
    """Run real OCR on all images and write fixtures."""
    from scripts.ocr.gemini_client import call_gemini_ocr

    cfg = load_config()
    image_files = sorted(IMAGES_DIR.rglob("*.*"))

    if not image_files:
        print("[!] No images found in agentic_engineering/images/")
        return

    for img_path in image_files:
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue

        rel = img_path.relative_to(IMAGES_DIR)
        store = rel.parts[0]  # "lotte" or "superindo"
        stem = _base_name(img_path.stem)

        fixture_dir = FIXTURES_DIR / store
        fixture_dir.mkdir(parents=True, exist_ok=True)
        fixture_file = fixture_dir / f"{stem}.json"

        if not CAPTURE:
            print(f"  [DRY-RUN] Would OCR {rel} -> {fixture_file}")
            continue

        print(f"  [*] OCRing {rel}...")
        try:
            # Temporarily override store in cfg for correct prompt
            cfg["store"] = store
            products = call_gemini_ocr(str(img_path), cfg)

            fixture = {"source": str(img_path), "products": products}
            fixture_file.write_text(
                json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"  [OK] Wrote {fixture_file} ({len(products)} products)")
        except Exception as e:
            print(f"  [FAIL] {rel}: {e}")


def main() -> None:
    print("=== OCR Fixture Capture ===")

    if CAPTURE:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[!] GEMINI_API_KEY not set. Cannot capture real OCR data.")
            sys.exit(1)
        print("[*] CAPTURE_FIXTURES=1: Running real Gemini calls")
    else:
        print("[*] Dry-run mode. Set CAPTURE_FIXTURES=1 to capture real data.")

    capture_ocr_fixtures()

    print("")
    print("=== Done ===")


if __name__ == "__main__":
    main()
