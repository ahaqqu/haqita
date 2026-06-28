"""
Haqita Stage 4: Publish HTML.

Generates active_promo.json from the database and copies JSON files
to output/html/ for the browser-based UI.

Usage:
    python scripts/publish_html.py
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
    args = parser.parse_args()

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

    promo_map: dict[str, dict] = {}
    for item_list in (consolidated.get("products", []), consolidated.get("singles", [])):
        for item in item_list:
            stores = item.get("stores", [item])
            for se in stores if isinstance(stores, list) else [item]:
                sp = se.get("standardized_promo") or item.get("standardized_promo")
                if sp and sp.get("display_summary"):
                    key = sp["display_summary"].lower().replace(" ", "-").replace("%", "persen").replace(".", "-").replace("!", "")
                    display = sp["display_summary"]
                    store_name = se.get("store", item.get("store", "unknown"))
                    if key not in promo_map:
                        promo_map[key] = {
                            "key": key,
                            "display": display,
                            "type": sp["best_type"],
                            "discount_pct": sp.get("discount_pct"),
                            "product_count": 0,
                            "stores": {},
                            "example_products": [],
                        }
                    promo_map[key]["product_count"] += 1
                    promo_map[key]["stores"][store_name] = promo_map[key]["stores"].get(store_name, 0) + 1
                    if len(promo_map[key]["example_products"]) < 5:
                        promo_map[key]["example_products"].append(item.get("name", ""))

    promo_catalog = sorted(promo_map.values(), key=lambda x: -x["product_count"])
    consolidated["promo_catalog"] = promo_catalog

    copies = [
        (consolidated, HTML_DIR / "active_promo.json", "active_promo.json"),
        (promo_catalog, HTML_DIR / "promo_catalog.json", "promo_catalog.json"),
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
            shutil.copy2(data, dst)
            size = data.stat().st_size
            print(f"[OK] {name} -> output/html/ ({size:,} bytes)")
            copied += 1
        else:
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            size = dst.stat().st_size
            print(f"[OK] {name} -> output/html/ (generated from database, {size:,} bytes)")
            copied += 1

    print(f"Publish HTML complete. {copied} file(s) written, {warned} warning(s).")


if __name__ == "__main__":
    main()
