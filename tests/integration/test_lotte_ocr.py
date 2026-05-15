"""
Integration test: OCR on Lotte Mart brochure images.
Reads all images from data/test/lotte/image-brochure/.
Compares output against tests/integration/asserts/<provider>/lotte/<image>.json.

Usage:
    python tests/integration/test_lotte_ocr.py [--image path/to/image.jpg]

Exit codes:
    0 - all images pass
    1 - infrastructure error
    2 - OCR ran but no products extracted
    3 - preprocessing error
    4 - products extracted but differ from assert
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tests.integration.test_base import run_store_tests

STORE = "lotte"
IMAGE_DIR = Path(__file__).resolve().parent.parent.parent / "data/test/lotte/image-brochure"
ASSERTS_DIR = Path(__file__).resolve().parent / "asserts"


def main():
    parser = argparse.ArgumentParser(description="Integration test: OCR on Lotte brochure images")
    parser.add_argument("--image", nargs="*", default=None, help="Specific image(s) to test")
    args = parser.parse_args()

    images = None
    if args.image:
        images = [Path(p) for p in args.image]

    exit_code = run_store_tests(STORE, IMAGE_DIR, ASSERTS_DIR, images=images)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
