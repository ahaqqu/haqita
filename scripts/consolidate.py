import argparse
import glob
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.matching.normalizer import parse_unit_to_base
from scripts.matching.promo_parser import parse_promo, parse_valid_until
from scripts.matching.matcher import match_products, load_embedding_model

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
STORE_COLORS = {"Lotte": "#0057A8", "Superindo": "#E8211D"}
STORE_ORDER = ["Lotte", "Superindo"]
DISPLAY_HINTS = {
    "stores": STORE_ORDER,
    "store_colors": STORE_COLORS,
    "currency": "IDR",
    "locale": "id-ID",
}


def load_config() -> dict:
    load_dotenv()
    with open(Path(__file__).resolve().parent.parent / 'config.yaml') as f:
        cfg = yaml.safe_load(f)
    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg['ocr']['gemini_api_key'] = env_key
    return cfg


def load_latest_promos(pattern: str) -> list[dict] | None:
    files = sorted(glob.glob(str(OUTPUT_DIR / pattern)))
    if not files:
        logger.warning(f"No files matching {pattern}")
        return None
    latest = files[-1]
    logger.info(f"Loading {latest}")
    return json.loads(Path(latest).read_text(encoding="utf-8"))


def extract_store_products(data: dict, store_name: str) -> list[dict]:
    products = []
    for img in data.get("new_images", []):
        for p in img.get("products", []):
            promoresult = parse_promo(p.get("promo"), p["price"])
            products.append({
                "name": p["name"],
                "brand": p.get("brand"),
                "unit": p.get("unit"),
                "price": p["price"],
                "promo": p.get("promo"),
                "period": p.get("period"),
                "effective_unit_price": promoresult.effective_unit_price,
                "bundle_size": promoresult.unit_count,
                "promo_type": promoresult.promo_type,
                "valid_until": parse_valid_until(p.get("period")),
                "store": store_name,
                "image_source": p.get("image_source"),
            })
    return products


def build_product_key(name: str, brand: str | None, unit: str | None) -> str:
    b = brand.lower().replace(' ', '-') if brand else "unknown"
    u = unit.lower().replace(' ', '') if unit else "unknown"
    n = name.lower().replace(' ', '-')[:60]
    return f"{n}--{b}--{u}"


def compute_display_fields(store_entries: list[dict]) -> dict:
    prices = [s["effective_unit_price"] for s in store_entries]
    price_min = min(prices)
    price_max = max(prices)
    cheapest = [s for s in store_entries if s["effective_unit_price"] == price_min][0]
    other_store = [s for s in store_entries if s["store"] != cheapest["store"]]

    savings_pct = 0
    price_gap = 0
    if other_store:
        other_price = other_store[0]["effective_unit_price"]
        price_gap = other_price - price_min
        if other_price > 0:
            savings_pct = round((price_gap / other_price) * 100, 1)

    has_promo = any(s.get("promo") for s in store_entries)
    promo_entry = next((s for s in store_entries if s.get("promo")), None)
    promo_summary = f"{promo_entry['promo']} di {promo_entry['store']}" if promo_entry else None

    valid_until = min((s["valid_until"] for s in store_entries if s.get("valid_until")), default=None)

    return {
        "price_min": price_min,
        "price_max": price_max,
        "cheapest_store": cheapest["store"],
        "price_gap": price_gap,
        "savings_pct": savings_pct,
        "has_promo": has_promo,
        "promo_summary": promo_summary,
        "valid_until": valid_until,
    }


def build_store_entry(product: dict) -> dict:
    return {
        "store": product["store"],
        "price": product["price"],
        "effective_unit_price": product["effective_unit_price"],
        "bundle_size": product["bundle_size"],
        "promo": product.get("promo"),
        "promo_type": product["promo_type"],
        "period": product.get("period"),
        "valid_until": product.get("valid_until"),
    }


def atomic_write_json(data: dict, path: str) -> None:
    dir_ = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', dir=dir_, suffix='.tmp',
                                     delete=False, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path = f.name
    shutil.move(tmp_path, path)


def update_catalog(catalog: dict, all_products: list[dict], today: str) -> dict:
    for product in all_products:
        key = product['key']
        store_name = product.get('store', 'unknown')
        if key not in catalog:
            catalog[key] = {
                'canonical_key': key,
                'display_name': product['name'],
                'brand': product.get('brand'),
                'unit': product.get('unit'),
                'unit_type': None,
                'unit_value_g': None,
                'first_seen': today,
                'last_seen': today,
                'appearance_count': 1,
                'stores_found': [store_name],
                'name_variants': [{'name': product['name'], 'count': 1, 'store': store_name}],
                'confidence': 0.3,
                'manually_verified': False,
            }
        else:
            entry = catalog[key]
            entry['last_seen'] = today
            entry['appearance_count'] += 1
            if store_name not in entry['stores_found']:
                entry['stores_found'].append(store_name)
            for v in entry['name_variants']:
                if v['name'] == product['name']:
                    v['count'] += 1
                    break
            else:
                entry['name_variants'].append({'name': product['name'], 'count': 1, 'store': store_name})
            entry['confidence'] = _score_confidence(entry)
    return catalog


def _score_confidence(entry: dict) -> float:
    score = 0.0
    if entry['appearance_count'] >= 3:
        score += 0.3
    elif entry['appearance_count'] >= 2:
        score += 0.15
    if len(entry['stores_found']) >= 2:
        score += 0.3
    else:
        score += 0.1
    if len(entry['name_variants']) == 1:
        score += 0.2
    elif len(entry['name_variants']) <= 3:
        score += 0.1
    if entry.get('unit') and entry['unit'] != 'unknown':
        score += 0.1
    if entry.get('brand') and entry['brand'] != 'unknown':
        score += 0.1
    return round(min(score, 1.0), 2)


def main():
    parser = argparse.ArgumentParser(description="Consolidate and match promo data")
    parser.add_argument("--lotte-file", help="Specific Lotte JSON file path")
    parser.add_argument("--superindo-file", help="Specific Superindo JSON file path")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    args = parser.parse_args()

    cfg = load_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print("  Consolidation & Product Matching")
    print("=" * 60)
    print()

    if args.lotte_file:
        lotte_data = json.loads(Path(args.lotte_file).read_text(encoding="utf-8"))
    else:
        lotte_data = load_latest_promos("lotte_promos_*.json")

    if args.superindo_file:
        superindo_data = json.loads(Path(args.superindo_file).read_text(encoding="utf-8"))
    else:
        superindo_data = load_latest_promos("superindo_promos_*.json")

    if not lotte_data and not superindo_data:
        logger.error("No promo data found for either store. Exiting.")
        sys.exit(1)

    lotte_products = extract_store_products(lotte_data or {"new_images": []}, "Lotte")
    superindo_products = extract_store_products(superindo_data or {"new_images": []}, "Superindo")

    print(f"[*] Lotte products: {len(lotte_products)}")
    print(f"[*] Superindo products: {len(superindo_products)}")
    print()

    history_path = OUTPUT_DIR / "price_history.json"
    if history_path.exists():
        backup_path = OUTPUT_DIR / "price_history.json.backup"
        shutil.copy2(history_path, backup_path)
        logger.info(f"Backed up price_history.json")

    embedding_model = None
    try:
        embedding_model = load_embedding_model(cfg['consolidation']['embedding_model'])
    except Exception as e:
        logger.warning(f"Failed to load embedding model: {e}. Falling back to rule-based matching only.")

    matched_pairs, lotte_only, superindo_only, review_items = match_products(
        lotte_products, superindo_products, cfg, embedding_model
    )

    print(f"[*] Matched across stores: {len(matched_pairs)}")
    print(f"[*] Lotte only: {len(lotte_only)}")
    print(f"[*] Superindo only: {len(superindo_only)}")
    print(f"[*] Flagged for review: {len(review_items)}")
    print()

    products_output = []
    for pair in matched_pairs:
        a, b = pair['product_a'], pair['product_b']
        store_entries = [build_store_entry(a), build_store_entry(b)]
        name = a["name"]
        brand = a.get("brand")
        unit = a.get("unit")
        key = build_product_key(name, brand, unit)
        display = compute_display_fields(store_entries)

        product_entry = {
            "key": key,
            "name": name,
            "brand": brand,
            "unit": unit,
            "unit_type": None,
            "unit_value_g": None,
            "stores": store_entries,
            **display,
            "match_method": pair["match_method"],
            "match_confidence": pair["match_confidence"],
        }
        products_output.append(product_entry)

    singles_output = []
    for p in lotte_only:
        key = build_product_key(p["name"], p.get("brand"), p.get("unit"))
        singles_output.append({
            "key": key,
            "name": p["name"],
            "brand": p.get("brand"),
            "unit": p.get("unit"),
            "store": "Lotte",
            "price": p["price"],
            "effective_unit_price": p["effective_unit_price"],
            "promo": p.get("promo"),
            "period": p.get("period"),
            "valid_until": p.get("valid_until"),
        })
    for p in superindo_only:
        key = build_product_key(p["name"], p.get("brand"), p.get("unit"))
        singles_output.append({
            "key": key,
            "name": p["name"],
            "brand": p.get("brand"),
            "unit": p.get("unit"),
            "store": "Superindo",
            "price": p["price"],
            "effective_unit_price": p["effective_unit_price"],
            "promo": p.get("promo"),
            "period": p.get("period"),
            "valid_until": p.get("valid_until"),
        })

    consolidated = {
        "generated_at": datetime.now().isoformat(),
        "scrape_dates": {},
        "source_files": [],
        "display_hints": DISPLAY_HINTS,
        "products": products_output,
        "singles": singles_output,
        "stats": {
            "total_products_lotte": len(lotte_products),
            "total_products_superindo": len(superindo_products),
            "matched_across_stores": len(matched_pairs),
            "lotte_only": len(lotte_only),
            "superindo_only": len(superindo_only),
            "match_methods": {},
            "flagged_for_review": len(review_items),
            "validation_rejected": 0,
        },
    }

    methods = {}
    for pair in matched_pairs:
        m = pair.get("match_method", "unknown")
        methods[m] = methods.get(m, 0) + 1
    consolidated["stats"]["match_methods"] = methods

    consolidated_file = OUTPUT_DIR / f"consolidated_{timestamp}.json"
    atomic_write_json(consolidated, str(consolidated_file))
    logger.info(f"Written: {consolidated_file}")

    latest_file = OUTPUT_DIR / "consolidated_latest.json"
    atomic_write_json(consolidated, str(latest_file))
    logger.info(f"Written: {latest_file}")

    catalog_path = OUTPUT_DIR / "product_catalog.json"
    catalog = {"catalog": {}, "metadata": {}}
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    all_with_store = [
        {**p, "store": "Lotte" if p in lotte_only else ("Superindo" if p in superindo_only else p.get("store"))}
        for p in (lotte_only + superindo_only)
    ]
    all_with_store.extend([
        {**p['product_a'], "store": "Lotte", "key": build_product_key(p['product_a']['name'], p['product_a'].get('brand'), p['product_a'].get('unit'))}
        for p in matched_pairs
    ])
    all_with_store.extend([
        {**p['product_b'], "store": "Superindo", "key": build_product_key(p['product_b']['name'], p['product_b'].get('brand'), p['product_b'].get('unit'))}
        for p in matched_pairs
    ])
    catalog["catalog"] = update_catalog(catalog["catalog"], all_with_store, today)
    catalog["metadata"] = {
        "total_entries": len(catalog["catalog"]),
        "last_updated": datetime.now().isoformat(),
        "schema_version": "1.1",
    }
    atomic_write_json(catalog, str(catalog_path))
    logger.info(f"Updated: {catalog_path}")

    history = {"snapshots": [], "metadata": {}}
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    existing_entries = {(s["product_key"], s["date"], s["store"]) for s in history["snapshots"]}
    for p in all_with_store:
        entry_key = (p.get("key", ""), today, p.get("store", ""))
        if entry_key not in existing_entries:
            history["snapshots"].append({
                "product_key": p.get("key", ""),
                "name": p["name"],
                "brand": p.get("brand"),
                "unit": p.get("unit"),
                "date": today,
                "store": p.get("store", ""),
                "price": p["price"],
                "effective_unit_price": p.get("effective_unit_price", p["price"]),
                "promo": p.get("promo"),
            })
            existing_entries.add(entry_key)
    history["metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_runs": history["metadata"].get("total_runs", 0) + 1,
        "schema_version": "1.1",
    }
    atomic_write_json(history, str(history_path))
    logger.info(f"Updated: {history_path}")

    if review_items:
        review_path = OUTPUT_DIR / "review_queue.json"
        existing_reviews = []
        if review_path.exists():
            existing_reviews = json.loads(review_path.read_text(encoding="utf-8"))
        for item in review_items:
            item.pop("_idx_a", None)
            item.pop("_idx_b", None)
            item.pop("_score", None)
            existing_reviews.append(item)
        existing_reviews = existing_reviews[-100:]
        atomic_write_json(existing_reviews, str(review_path))
        logger.info(f"Updated: {review_path} ({len(existing_reviews)} total)")

    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Matched:       {len(matched_pairs)} products")
    print(f"  Lotte only:    {len(lotte_only)}")
    print(f"  Superindo only:{len(superindo_only)}")
    print(f"  For review:    {len(review_items)}")
    print(f"  Catalog:       {len(catalog['catalog'])} entries")
    print(f"  History:       {len(history['snapshots'])} snapshots")
    print(f"\n  Output: {latest_file}")
    print()


if __name__ == "__main__":
    main()
