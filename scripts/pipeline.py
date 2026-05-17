"""
Full pipeline — Docker entry point.
Runs scrape → OCR → consolidation sequentially.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.scrapers.lotte import main as lotte_main
from scripts.scrapers.superindo import main as superindo_main
from scripts.ocr.run_ocr import main as ocr_main
from scripts.consolidate import main as consolidate_main
from scripts.publish_html import main as publish_html_main

def _run_stage(name, func, *args):
    print()
    print("=" * 60)
    print(f"  Stage: {name}")
    print("=" * 60)
    print()
    func(*args)

if __name__ == "__main__":
    print("=" * 60)
    print("  Full Pipeline (Docker)")
    print("  Scrape → OCR → Consolidate")
    print("=" * 60)

    # Stage 1: Scrape
    _run_stage("Scrape — Lotte", lotte_main)
    _run_stage("Scrape — Superindo", superindo_main)

    # Stage 2: OCR
    sys.argv = ["run_ocr.py", "--store", "lotte"]
    _run_stage("OCR — Lotte", ocr_main)

    sys.argv = ["run_ocr.py", "--store", "superindo"]
    _run_stage("OCR — Superindo", ocr_main)

    # Stage 3: Consolidate
    sys.argv = ["consolidate.py"]
    _run_stage("Consolidate", consolidate_main)

    # Stage 4: Publish HTML
    sys.argv = ["publish_html.py"]
    _run_stage("Publish HTML", publish_html_main)

    print()
    print("=" * 60)
    print("  Pipeline complete.")
    print("=" * 60)
