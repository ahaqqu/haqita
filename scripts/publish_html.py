"""
Haqita Stage 4: Publish HTML.

Copies derived JSON files to output/html/ for the browser-based UI.
This stage is isolated so it can later read from a database server
instead of intermediate JSON files.

Usage:
    python scripts/publish_html.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT / "output" / "html"
CONSOLIDATED_SRC = ROOT / "output" / "consolidation" / "consolidated_latest.json"
PRICE_HISTORY_SRC = ROOT / "database" / "price_history.json"


def main():
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    copies = [
        (CONSOLIDATED_SRC, HTML_DIR / "consolidated_latest.json"),
        (PRICE_HISTORY_SRC, HTML_DIR / "price_history.json"),
    ]

    for src, dst in copies:
        if not src.exists():
            print(f"[WARN] Source not found: {src}")
            continue
        shutil.copy2(src, dst)
        print(f"[OK] {src.name} -> output/html/")

    print("Publish HTML complete.")


if __name__ == "__main__":
    main()
