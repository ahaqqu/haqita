import json
import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "ocr_fixtures"


def _base_name(stem: str) -> str:
    """Strip the MD5 suffix that base_scraper.filename_from_url appends."""
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 8 and all(c in "0123456789abcdef" for c in parts[1]):
        return parts[0]
    return stem


def mock_ocr(image_path: str) -> list[dict]:
    """Return synthetic OCR fixtures based on image filename."""
    filename = _base_name(Path(image_path).stem)
    store_dir = None

    if filename.startswith("HD-"):
        store_dir = FIXTURES_DIR / "lotte"
    else:
        store_dir = FIXTURES_DIR / "superindo"

    fixture_file = store_dir / f"{filename}.json"
    if not fixture_file.exists():
        raise FileNotFoundError(f"No OCR fixture for {image_path} (looked at {fixture_file})")

    data = json.loads(fixture_file.read_text(encoding="utf-8"))
    return data.get("products", [])
