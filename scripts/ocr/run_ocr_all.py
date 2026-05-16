"""
OCR all stores — Docker entry point.
Runs OCR for Lotte and Superindo sequentially.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ocr.run_ocr import main as ocr_main

if __name__ == "__main__":
    import argparse

    print("=" * 60)
    print("  OCR All Stores (Docker)")
    print("=" * 60)
    print()

    # Run Lotte
    print("--- Lotte ---")
    sys.argv = ["run_ocr.py", "--store", "lotte"]
    ocr_main()
    print()

    # Run Superindo
    print("--- Superindo ---")
    sys.argv = ["run_ocr.py", "--store", "superindo"]
    ocr_main()
    print()

    print("OCR complete.")
