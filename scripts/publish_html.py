"""
Haqita Stage 4: Publish HTML.

Copies derived JSON files to output/html/ for the browser-based UI.
This stage is isolated so it can later read from a database server
instead of intermediate JSON files.

Usage:
    python scripts/publish_html.py
    python scripts/publish_html.py --dry-run
    python scripts/publish_html.py --verbose
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT / "output" / "html"
CONSOLIDATED_SRC = ROOT / "output" / "consolidation" / "consolidated_latest.json"
PRICE_HISTORY_SRC = ROOT / "database" / "price_history.json"


def main():
    parser = argparse.ArgumentParser(description="Haqita Stage 4: Publish HTML")
    parser.add_argument("--dry-run", action="store_true", help="Preview copies without making changes")
    parser.add_argument("--verbose", action="store_true", help="Show detailed file info")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] No files will be copied.")
        print()

    HTML_DIR.mkdir(parents=True, exist_ok=True)

    copies = [
        (CONSOLIDATED_SRC, HTML_DIR / "consolidated_latest.json"),
        (PRICE_HISTORY_SRC, HTML_DIR / "price_history.json"),
    ]

    copied = 0
    warned = 0

    for src, dst in copies:
        if not src.exists():
            print(f"[WARN] Source not found: {src}")
            warned += 1
            continue

        if args.dry_run:
            print(f"[WOULD COPY] {src.name} -> output/html/")
            if args.verbose:
                size = src.stat().st_size
                print(f"  Size: {size:,} bytes")
                if dst.exists():
                    dst_size = dst.stat().st_size
                    print(f"  Destination exists: {dst_size:,} bytes")
                    print(f"  Would overwrite: {'yes' if dst_size != size else 'no (identical size)'}")
                else:
                    print(f"  Destination: new file")
            copied += 1
        else:
            shutil.copy2(src, dst)
            print(f"[OK] {src.name} -> output/html/")
            if args.verbose:
                size = src.stat().st_size
                print(f"  Size: {size:,} bytes")
            copied += 1

    if args.dry_run:
        print(f"\nDry-run complete. {copied} file(s) would be copied, {warned} warning(s).")
    else:
        print(f"Publish HTML complete. {copied} file(s) copied, {warned} warning(s).")


if __name__ == "__main__":
    main()
