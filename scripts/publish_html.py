"""
Haqita Stage 4: Publish HTML.

Generates active_promo.json from the database and copies JSON files
to output/html/ for the browser-based UI.

Usage:
    python scripts/publish_html.py
    python scripts/publish_html.py --dry-run
    python scripts/publish_html.py --verbose
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.matching.consolidation import generate_consolidated_from_history

ROOT = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT / "output" / "html"
DATABASE_DIR = ROOT / "database"
PRICE_HISTORY_SRC = DATABASE_DIR / "price_history.json"
CATALOG_SRC = DATABASE_DIR / "product_catalog.json"


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def main():
    parser = argparse.ArgumentParser(description="Haqita Stage 4: Publish HTML")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--verbose", action="store_true", help="Show detailed file info")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] No files will be written.")
        print()

    HTML_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")

    # Load database sources
    history = load_json(PRICE_HISTORY_SRC, {"snapshots": [], "metadata": {}})
    catalog_raw = load_json(CATALOG_SRC, {"catalog": {}})
    catalog = catalog_raw.get("catalog", {})

    # Generate consolidated from database
    consolidated = generate_consolidated_from_history(history, catalog, today)

    # Enrich with review queue count
    review_path = DATABASE_DIR / "review_queue.json"
    review_data = load_json(review_path, {"items": []})
    if isinstance(review_data, dict):
        review_data = review_data.get("items", [])
    consolidated["stats"]["flagged_for_review"] = len(review_data)

    copies = [
        (consolidated, HTML_DIR / "active_promo.json", "active_promo.json"),
        (PRICE_HISTORY_SRC, HTML_DIR / "price_history.json", "price_history.json"),
        (review_path, HTML_DIR / "review_queue.json", "review_queue.json"),
    ]

    copied = 0
    warned = 0

    for data, dst, name in copies:
        if isinstance(data, Path):
            if not data.exists():
                print(f"[WARN] Source not found: {data}")
                warned += 1
                continue
            if args.dry_run:
                print(f"[WOULD COPY] {name} -> output/html/")
                if args.verbose:
                    size = data.stat().st_size
                    print(f"  Size: {size:,} bytes")
                    if dst.exists():
                        dst_size = dst.stat().st_size
                        print(f"  Destination exists: {dst_size:,} bytes")
                        print(f"  Would overwrite: {'yes' if dst_size != size else 'no (identical size)'}")
                    else:
                        print(f"  Destination: new file")
                copied += 1
            else:
                shutil.copy2(data, dst)
                print(f"[OK] {name} -> output/html/")
                if args.verbose:
                    size = data.stat().st_size
                    print(f"  Size: {size:,} bytes")
                copied += 1
        else:
            if args.dry_run:
                print(f"[WOULD GENERATE] {name} -> output/html/")
                if args.verbose:
                    size = len(json.dumps(data, ensure_ascii=False))
                    print(f"  Generated size: {size:,} bytes")
                    if dst.exists():
                        dst_size = dst.stat().st_size
                        print(f"  Destination exists: {dst_size:,} bytes")
                    else:
                        print(f"  Destination: new file")
                copied += 1
            else:
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"[OK] {name} -> output/html/ (generated from database)")
                if args.verbose:
                    size = dst.stat().st_size
                    print(f"  Size: {size:,} bytes")
                copied += 1

    if args.dry_run:
        print(f"\nDry-run complete. {copied} file(s) would be written, {warned} warning(s).")
    else:
        print(f"Publish HTML complete. {copied} file(s) written, {warned} warning(s).")


if __name__ == "__main__":
    main()
