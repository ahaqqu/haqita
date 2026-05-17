"""
Haqita Stage 4: Publish HTML.

Active promo JSON.

Generates active_promo.json from database/ and copies JSON files
to output/html/ for the browser-based UI.

Usage:
    python scripts/publish_html.py
    python scripts/publish_html.py --dry-run
    python scripts/publish_html.py --verbose
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

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


def generate_consolidated_from_history(history: dict, catalog: dict, today: str) -> dict:
    """
    Rebuild active_promo.json from database/price_history.json + product_catalog.json.
    """
    snapshots = history.get("snapshots", [])

    active = []
    for snap in snapshots:
        vu = snap.get("valid_until")
        if vu is None or vu >= today:
            active.append(snap)

    latest = {}
    for snap in active:
        pkey = snap.get("product_key") or snap.get("key", "")
        store = snap.get("store", "")
        key = (pkey, store)
        if key not in latest or snap.get("date", "") > latest[key].get("date", ""):
            latest[key] = snap

    product_groups = {}
    for (pkey, store), snap in latest.items():
        if pkey not in product_groups:
            product_groups[pkey] = []
        product_groups[pkey].append(snap)

    consolidated_products = []
    singles = []

    for pkey, stores_snaps in product_groups.items():
        cat = catalog.get(pkey, {})

        name = stores_snaps[0].get("name", "")
        brand = stores_snaps[0].get("brand") or cat.get("brand")
        unit = stores_snaps[0].get("unit") or cat.get("unit")
        unit_type_str = stores_snaps[0].get("unit_type", cat.get("unit_type", "unknown"))
        unit_value_g = stores_snaps[0].get("unit_value_g", cat.get("unit_value_g"))

        if len(stores_snaps) >= 2:
            store_entries = []
            for snap in stores_snaps:
                store_entries.append({
                    "store": snap["store"],
                    "price": snap.get("price", 0),
                    "effective_unit_price": snap.get("effective_unit_price", snap.get("price", 0)),
                    "bundle_size": snap.get("bundle_size", 1),
                    "promo": snap.get("promo"),
                    "promo_type": snap.get("promo_type", "single"),
                    "valid_from": snap.get("valid_from"),
                    "valid_until": snap.get("valid_until"),
                    "image_path": snap.get("image_path"),
                })

            eff_prices = [s["effective_unit_price"] for s in store_entries if s["effective_unit_price"] > 0]
            price_min = min(eff_prices) if eff_prices else 0
            price_max = max(eff_prices) if eff_prices else 0
            cheapest = None
            if eff_prices:
                cheapest_store = min(store_entries, key=lambda s: s["effective_unit_price"] if s["effective_unit_price"] > 0 else float("inf"))
                cheapest = cheapest_store["store"]
            price_gap = price_max - price_min if price_min > 0 else 0
            savings_pct = round((price_gap / price_max * 100), 1) if price_max > 0 else 0.0

            has_promo = any(s["promo"] for s in store_entries)
            promo_parts = []
            for s in store_entries:
                if s["promo"]:
                    promo_parts.append(f"{s['promo']} di {s['store']}")
            promo_summary = "; ".join(promo_parts) if promo_parts else ""

            valid_dates = [s["valid_until"] for s in store_entries if s["valid_until"]]
            valid_until = min(valid_dates) if valid_dates else None

            match_method = None
            match_confidence = None
            for snap in stores_snaps:
                mm = snap.get("match_method")
                mc = snap.get("match_confidence")
                if mm and (match_method is None or mc > match_confidence):
                    match_method = mm
                    match_confidence = mc

            consolidated_products.append({
                "key": pkey,
                "name": name,
                "brand": brand,
                "unit": unit,
                "unit_type": unit_type_str,
                "unit_value_g": unit_value_g,
                "stores": store_entries,
                "price_min": price_min,
                "price_max": price_max,
                "cheapest_store": cheapest,
                "price_gap": price_gap,
                "savings_pct": savings_pct,
                "has_promo": has_promo,
                "promo_summary": promo_summary,
                "valid_until": valid_until,
                "match_method": match_method or "unknown",
                "match_confidence": match_confidence or 0.5,
            })
        else:
            snap = stores_snaps[0]
            singles.append({
                "key": pkey,
                "name": name,
                "brand": brand,
                "unit": unit,
                "unit_type": unit_type_str,
                "unit_value_g": unit_value_g,
                "store": snap["store"],
                "price": snap.get("price", 0),
                "effective_unit_price": snap.get("effective_unit_price", snap.get("price", 0)),
                "promo": snap.get("promo"),
                "valid_from": snap.get("valid_from"),
                "valid_until": snap.get("valid_until"),
                "image_path": snap.get("image_path"),
            })

    matched_count = len(consolidated_products)
    lotte_count = sum(1 for s in singles if s["store"] == "Lotte")
    superindo_count = sum(1 for s in singles if s["store"] == "Superindo")

    match_methods = {}
    for p in consolidated_products:
        m = p.get("match_method", "unknown")
        match_methods[m] = match_methods.get(m, 0) + 1

    return {
        "generated_at": datetime.now().isoformat(),
        "scrape_dates": {},
        "source_files": [],
        "display_hints": {
            "stores": ["Lotte", "Superindo"],
            "store_colors": {"Lotte": "#0057A8", "Superindo": "#E8211D"},
            "currency": "IDR",
            "locale": "id-ID",
        },
        "products": consolidated_products,
        "singles": singles,
        "stats": {
            "total_products_lotte": matched_count + lotte_count,
            "total_products_superindo": matched_count + superindo_count,
            "matched_across_stores": matched_count,
            "lotte_only": lotte_count,
            "superindo_only": superindo_count,
            "match_methods": match_methods,
            "flagged_for_review": 0,
            "validation_rejected": 0,
        },
    }


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
