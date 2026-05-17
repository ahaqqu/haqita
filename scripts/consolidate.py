"""
Consolidation script — merge OCR results from Lotte & Superindo,
match same products across stores, write to database.

Usage:
    python scripts/consolidate.py [options]

Options:
    --input-dir DIR          Auto-detect store from filename, pick latest per store
    --lotte-dir DIR          Explicit Lotte input directory
    --superindo-dir DIR      Explicit Superindo input directory
    --dry-run                Preview without database update
    --verbose                Write detailed match results to log file
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.matching.matcher import load_embedding_model, match_products
from scripts.matching.normalizer import parse_unit_to_base, unit_type
from scripts.matching.promo_parser import parse_promo, parse_period
from scripts.matching.consolidation import generate_consolidated_from_history

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config.yaml with .env overrides."""
    import yaml
    from dotenv import load_dotenv
    load_dotenv()

    config_path = Path(__file__).resolve().parent.parent / 'config.yaml'
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider

    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg['ocr']['gemini']['api_key'] = env_key

    env_ai = os.getenv('AI_VERIFIER_PROVIDER')
    if env_ai:
        cfg['consolidation']['ai_verifier']['provider'] = env_ai

    return cfg


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_latest(input_dir: Path, store_prefix: str) -> Path | None:
    """Find the most recent JSON file matching store_prefix in input_dir."""
    if not input_dir.exists():
        return None
    pattern = re.compile(rf'^{store_prefix}.*\.json$', re.IGNORECASE)
    candidates = [f for f in input_dir.iterdir() if pattern.match(f.name)]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def extract_products(data: dict) -> list[dict]:
    """Extract products[] from either schema (wrapper or raw)."""
    if 'products' in data:
        return data['products']
    return []


# ---------------------------------------------------------------------------
# Product key generation
# ---------------------------------------------------------------------------

def make_product_key(name: str, brand: str | None, unit: str | None) -> str:
    """Generate a stable, URL-safe key for a product."""
    name_slug = re.sub(r'[^a-z0-9]+', '-', name.lower().strip()).strip('-')
    brand_slug = re.sub(r'[^a-z0-9]+', '-', (brand or '').lower().strip()).strip('-')
    unit_slug = re.sub(r'[^a-z0-9]+', '-', (unit or '').lower().strip()).strip('-')
    return f"{name_slug}--{brand_slug}--{unit_slug}"


def make_product_key_compat(name: str, brand: str | None = None, unit: str | None = None) -> str:
    """Alias for make_product_key (used by normalizer imports)."""
    return make_product_key(name, brand, unit)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def atomic_write_json(data: dict, path: str) -> None:
    """Write JSON atomically: write to temp, then rename."""
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=dir_, suffix='.tmp',
                                     delete=False, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path = f.name
    shutil.move(tmp_path, path)


# ---------------------------------------------------------------------------
# Catalog update
# ---------------------------------------------------------------------------

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


def update_catalog(catalog: dict, all_products: list[dict], today: str) -> dict:
    for product in all_products:
        key = product['key']
        if key not in catalog:
            catalog[key] = {
                'canonical_key': key,
                'display_name': product['name'],
                'brand': product.get('brand'),
                'unit': product.get('unit'),
                'unit_type': product.get('unit_type'),
                'unit_value_g': product.get('unit_value_g'),
                'first_seen': today,
                'last_seen': today,
                'appearance_count': 1,
                'stores_found': [product['store']],
                'name_variants': [{'name': product['name'], 'count': 1, 'store': product['store']}],
                'confidence': 0.3,
                'manually_verified': False,
            }
        else:
            entry = catalog[key]
            entry['last_seen'] = today
            entry['appearance_count'] += 1
            if product['store'] not in entry['stores_found']:
                entry['stores_found'].append(product['store'])
            for v in entry['name_variants']:
                if v['name'] == product['name']:
                    v['count'] += 1
                    break
            else:
                entry['name_variants'].append({'name': product['name'], 'count': 1, 'store': product['store']})
            entry['confidence'] = _score_confidence(entry)
    return catalog


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

def load_price_history(path: Path) -> dict:
    if path.exists():
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {'snapshots': [], 'metadata': {'last_updated': '', 'total_runs': 0, 'schema_version': '1.2'}}


def append_to_price_history(history: dict, products: list[dict], today: str) -> dict:
    existing = set()
    for snap in history.get('snapshots', []):
        existing.add((snap['product_key'], snap['date'], snap['store']))

    for p in products:
        pkey = p.get('product_key') or p.get('key', '')
        key = (pkey, today, p['store'])
        if key not in existing:
            history['snapshots'].append({
                'product_key': pkey,
                'name': p['name'],
                'brand': p.get('brand'),
                'unit': p.get('unit'),
                'date': today,
                'store': p['store'],
                'price': p['price'],
                'effective_unit_price': p.get('effective_unit_price', p['price']),
                'promo': p.get('promo'),
                'valid_from': p.get('valid_from'),
                'valid_until': p.get('valid_until'),
                'bundle_size': p.get('bundle_size', 1),
                'promo_type': p.get('promo_type', 'single'),
                'match_method': p.get('match_method'),
                'match_confidence': p.get('match_confidence'),
                'image_path': p.get('image_path'),
                'scrape_time': p.get('scrape_time'),
            })
            existing.add(key)

    history['metadata']['last_updated'] = datetime.now().isoformat()
    history['metadata']['total_runs'] = history['metadata'].get('total_runs', 0) + 1
    return history


# ---------------------------------------------------------------------------
# Main consolidation flow
# ---------------------------------------------------------------------------

def consolidate(cfg: dict, lotte_dir: Path | None, superindo_dir: Path | None, database_dir: Path, dry_run: bool = False, verbose: bool = False, log_file: Path | None = None) -> None:
    t_start = time.time()

    if verbose and log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger('consolidate_verbose')
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_file, encoding='utf-8', mode='w')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.addHandler(fh)
    else:
        logger = None

    if dry_run:
        print("[*] Dry-run mode: database will not be updated\n")

    # 1. Discover input files
    lotte_file = discover_latest(lotte_dir, 'lotte') if lotte_dir else None
    superindo_file = discover_latest(superindo_dir, 'superindo') if superindo_dir else None

    # 2. Load products
    lotte_products = []
    superindo_products = []
    lotte_date = None
    superindo_date = None

    if lotte_file:
        print(f"[*] Loading Lotte products from {lotte_file.name} ...", end=" ")
        sys.stdout.flush()
        with open(lotte_file, encoding='utf-8') as f:
            lotte_data = json.load(f)
        lotte_products = extract_products(lotte_data)
        lotte_date = lotte_data.get('scraped_at', '')
        print(f"{len(lotte_products)} products")
    else:
        print("[!] No Lotte input file found")

    if superindo_file:
        print(f"[*] Loading Superindo products from {superindo_file.name} ...", end=" ")
        sys.stdout.flush()
        with open(superindo_file, encoding='utf-8') as f:
            superindo_data = json.load(f)
        superindo_products = extract_products(superindo_data)
        superindo_date = superindo_data.get('scraped_at', '')
        print(f"{len(superindo_products)} products")
    else:
        print("[!] No Superindo input file found")

    if not lotte_products and not superindo_products:
        print("[!!] No products found in either store. Aborting.")
        return

    # 3. Parse promo text and compute effective unit prices
    print("[*] Parsing promo text and computing effective unit prices ...")
    for p in lotte_products:
        promo = parse_promo(p.get('promo'), p.get('price', 0))
        p['_promo_result'] = promo
        p['_effective_unit_price'] = promo.effective_unit_price
        p['_bundle_size'] = promo.unit_count
        p['_promo_type'] = promo.promo_type
        p['_valid_from'], p['_valid_until'] = parse_period(p.get('period'))

    for p in superindo_products:
        promo = parse_promo(p.get('promo'), p.get('price', 0))
        p['_promo_result'] = promo
        p['_effective_unit_price'] = promo.effective_unit_price
        p['_bundle_size'] = promo.unit_count
        p['_promo_type'] = promo.promo_type
        p['_valid_from'], p['_valid_until'] = parse_period(p.get('period'))

    # 4. Load embedding model if Gate 4 enabled
    embedding_model = None
    if cfg.get('consolidation', {}).get('gates', {}).get('gate4_embedding', True):
        model_name = cfg.get('consolidation', {}).get('embedding_model', 'paraphrase-multilingual-MiniLM-L12-v2')
        embedding_model = load_embedding_model(model_name)

    # 5. Run matching pipeline
    print("[*] Running matching pipeline ...")
    matched_pairs, lotte_only, superindo_only, review_items, gate_rejections = match_products(
        lotte_products, superindo_products, cfg, embedding_model,
    )

    if logger:
        logger.info("=== Matching Pipeline Results ===")
        logger.info("Matched pairs: %d", len(matched_pairs))
        for mp in matched_pairs:
            logger.info("  MATCH [%s] %s (Lotte) <-> %s (Superindo)",
                        mp['match_method'],
                        mp['lotte'].get('name', ''),
                        mp['superindo'].get('name', ''))
        logger.info("Lotte only: %d", len(lotte_only))
        for p in lotte_only:
            logger.info("  LOTTE_ONLY: %s", p.get('name', ''))
        logger.info("Superindo only: %d", len(superindo_only))
        for p in superindo_only:
            logger.info("  SUPERINDO_ONLY: %s", p.get('name', ''))
        logger.info("Review queue: %d", len(review_items))
        for r in review_items:
            logger.info("  REVIEW [%s]: %s <-> %s",
                        r.get('reason', ''),
                        r.get('product_a', {}).get('name', ''),
                        r.get('product_b', {}).get('name', ''))
        logger.info("Gate rejections: %d", len(gate_rejections))
        for rej in gate_rejections:
            logger.info("  REJECTED [%s] %s (Lotte) vs %s (Superindo): %s",
                        rej['gate'],
                        rej['lotte'],
                        rej['superindo'],
                        rej['reason'])

    # 6. Build consolidated output
    print("[*] Building consolidated output ...")
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    consolidated_products = []
    for mp in matched_pairs:
        la = mp['lotte']
        sb = mp['superindo']
        key = make_product_key(la.get('name', ''), la.get('brand'), la.get('unit'))

        unit_parsed = parse_unit_to_base(la.get('unit'))
        unit_type_str = unit_parsed[1] if unit_parsed else (unit_type(la.get('unit')) or 'unknown')
        unit_value = unit_parsed[0] if unit_parsed else None

        stores = [
            {
                'store': 'Lotte',
                'price': la.get('price', 0),
                'effective_unit_price': la.get('_effective_unit_price', la.get('price', 0)),
                'bundle_size': la.get('_bundle_size', 1),
                'promo': la.get('promo'),
                'promo_type': la.get('_promo_type', 'single'),
                'valid_from': la.get('_valid_from'),
                'valid_until': la.get('_valid_until'),
                'image_path': la.get('image_path'),
            },
            {
                'store': 'Superindo',
                'price': sb.get('price', 0),
                'effective_unit_price': sb.get('_effective_unit_price', sb.get('price', 0)),
                'bundle_size': sb.get('_bundle_size', 1),
                'promo': sb.get('promo'),
                'promo_type': sb.get('_promo_type', 'single'),
                'valid_from': sb.get('_valid_from'),
                'valid_until': sb.get('_valid_until'),
                'image_path': sb.get('image_path'),
            },
        ]

        eff_prices = [s['effective_unit_price'] for s in stores if s['effective_unit_price'] > 0]
        price_min = min(eff_prices) if eff_prices else 0
        price_max = max(eff_prices) if eff_prices else 0
        cheapest = None
        if eff_prices:
            cheapest_store = min(stores, key=lambda s: s['effective_unit_price'] if s['effective_unit_price'] > 0 else float('inf'))
            cheapest = cheapest_store['store']
        price_gap = price_max - price_min if price_min > 0 else 0
        savings_pct = round((price_gap / price_max * 100), 1) if price_max > 0 else 0.0

        has_promo = any(s['promo'] for s in stores)
        promo_parts = []
        for s in stores:
            if s['promo']:
                promo_parts.append(f"{s['promo']} di {s['store']}")
        promo_summary = '; '.join(promo_parts) if promo_parts else ''

        valid_dates = [s['valid_until'] for s in stores if s['valid_until']]
        valid_until = min(valid_dates) if valid_dates else None

        consolidated_products.append({
            'key': key,
            'name': la.get('name', ''),
            'brand': la.get('brand'),
            'unit': la.get('unit'),
            'unit_type': unit_type_str,
            'unit_value_g': unit_value,
            'stores': stores,
            'price_min': price_min,
            'price_max': price_max,
            'cheapest_store': cheapest,
            'price_gap': price_gap,
            'savings_pct': savings_pct,
            'has_promo': has_promo,
            'promo_summary': promo_summary,
            'valid_until': valid_until,
            'match_method': mp['match_method'],
            'match_confidence': mp['match_confidence'],
        })

    # Build singles
    singles = []
    for p in lotte_only:
        key = make_product_key(p.get('name', ''), p.get('brand'), p.get('unit'))
        unit_parsed = parse_unit_to_base(p.get('unit'))
        unit_type_str = unit_parsed[1] if unit_parsed else (unit_type(p.get('unit')) or 'unknown')
        unit_value = unit_parsed[0] if unit_parsed else None

        singles.append({
            'key': key,
            'name': p.get('name', ''),
            'brand': p.get('brand'),
            'unit': p.get('unit'),
            'unit_type': unit_type_str,
            'unit_value_g': unit_value,
            'store': 'Lotte',
            'price': p.get('price', 0),
            'effective_unit_price': p.get('_effective_unit_price', p.get('price', 0)),
            'promo': p.get('promo'),
            'valid_from': p.get('_valid_from'),
            'valid_until': p.get('_valid_until'),
            'image_path': p.get('image_path'),
        })

    for p in superindo_only:
        key = make_product_key(p.get('name', ''), p.get('brand'), p.get('unit'))
        unit_parsed = parse_unit_to_base(p.get('unit'))
        unit_type_str = unit_parsed[1] if unit_parsed else (unit_type(p.get('unit')) or 'unknown')
        unit_value = unit_parsed[0] if unit_parsed else None

        singles.append({
            'key': key,
            'name': p.get('name', ''),
            'brand': p.get('brand'),
            'unit': p.get('unit'),
            'unit_type': unit_type_str,
            'unit_value_g': unit_value,
            'store': 'Superindo',
            'price': p.get('price', 0),
            'effective_unit_price': p.get('_effective_unit_price', p.get('price', 0)),
            'promo': p.get('promo'),
            'valid_from': p.get('_valid_from'),
            'valid_until': p.get('_valid_until'),
            'image_path': p.get('image_path'),
        })

    # 7. Update database, then generate consolidated output from it
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if not dry_run:
        database_dir.mkdir(parents=True, exist_ok=True)

        # 7a. Update product catalog
        catalog_path = database_dir / 'product_catalog.json'
        catalog_data = {}
        if catalog_path.exists():
            with open(catalog_path, encoding='utf-8') as f:
                catalog_data = json.load(f).get('catalog', {})

        all_products_for_catalog = []
        for p in consolidated_products:
            all_products_for_catalog.append({
                'key': p['key'], 'name': p['name'], 'brand': p.get('brand'),
                'unit': p.get('unit'), 'unit_type': p.get('unit_type'),
                'unit_value_g': p.get('unit_value_g'), 'store': 'both',
            })
        for p in singles:
            all_products_for_catalog.append({
                'key': p['key'], 'name': p['name'], 'brand': p.get('brand'),
                'unit': p.get('unit'), 'unit_type': p.get('unit_type'),
                'unit_value_g': p.get('unit_value_g'), 'store': p['store'],
            })

        catalog = update_catalog(catalog_data, all_products_for_catalog, today)
        catalog_output = {
            'catalog': catalog,
            'metadata': {
                'total_entries': len(catalog),
                'last_updated': datetime.now().isoformat(),
                'schema_version': '1.1',
            },
        }
        print(f"[*] Updating product_catalog.json: {len(catalog)} entries")
        atomic_write_json(catalog_output, str(catalog_path))

        # 7b. Append to price history
        history_path = database_dir / 'price_history.json'
        backup_path = database_dir / 'price_history.json.backup'

        if history_path.exists():
            shutil.copy2(str(history_path), str(backup_path))

        history = load_price_history(history_path)
        history_snapshots = []
        for p in consolidated_products:
            for s in p['stores']:
                history_snapshots.append({
                    'product_key': p['key'], 'name': p['name'], 'brand': p.get('brand'),
                    'unit': p.get('unit'), 'store': s['store'],
                    'price': s['price'], 'effective_unit_price': s['effective_unit_price'],
                    'promo': s.get('promo'),
                    'valid_from': s.get('valid_from'),
                    'valid_until': s.get('valid_until'),
                    'bundle_size': s.get('bundle_size', 1),
                    'promo_type': s.get('promo_type', 'single'),
                    'match_method': p.get('match_method'),
                    'match_confidence': p.get('match_confidence'),
                    'image_path': s.get('image_path'),
                    'scrape_time': lotte_date if s['store'] == 'Lotte' else superindo_date,
                })
        for p in singles:
            history_snapshots.append({
                'product_key': p['key'], 'name': p['name'], 'brand': p.get('brand'),
                'unit': p.get('unit'), 'store': p['store'],
                'price': p['price'], 'effective_unit_price': p.get('effective_unit_price', p['price']),
                'promo': p.get('promo'),
                'valid_from': p.get('valid_from'),
                'valid_until': p.get('valid_until'),
                'bundle_size': 1,
                'promo_type': 'single',
                'match_method': None,
                'match_confidence': None,
                'image_path': p.get('image_path'),
                'scrape_time': lotte_date if p['store'] == 'Lotte' else superindo_date,
            })

        history = append_to_price_history(history, history_snapshots, today)
        print(f"[*] Appending to price_history.json: {len(history_snapshots)} snapshots")
        atomic_write_json(history, str(history_path))

        # 7c. Generate consolidated output from database (includes carry-forward of still-valid promos)
        print("[*] Generating consolidated output from database ...")
        consolidated = generate_consolidated_from_history(history, catalog, today)
        consolidated['scrape_dates'] = {
            'Lotte': lotte_date or '',
            'Superindo': superindo_date or '',
        }
        consolidated['source_files'] = [
            lotte_file.name if lotte_file else '',
            superindo_file.name if superindo_file else '',
        ]
        consolidated['stats']['total_products_lotte'] = len(lotte_products)
        consolidated['stats']['total_products_superindo'] = len(superindo_products)
        consolidated['stats']['flagged_for_review'] = len(review_items)

        # 7d. Review queue
        review_path = database_dir / 'review_queue.json'
        review_data = []
        if review_path.exists():
            with open(review_path, encoding='utf-8') as f:
                review_data = json.load(f)
        if isinstance(review_data, dict):
            review_data = review_data.get('items', [])

        max_review = cfg.get('monitoring', {}).get('review_queue_max', 100)
        for item in review_items:
            review_data.append({
                'detected_at': datetime.now().isoformat(),
                'reason': item.get('reason', 'unknown'),
                'product_a': item.get('product_a', {}),
                'product_b': item.get('product_b', {}),
            })
        review_data = review_data[-max_review:]

        print(f"[*] Review queue: {len(review_data)} items")
        atomic_write_json({'items': review_data}, str(review_path))
    else:
        # Dry-run: build consolidated directly from matching results (no database update)
        match_methods = {}
        for mp in matched_pairs:
            m = mp['match_method']
            match_methods[m] = match_methods.get(m, 0) + 1

        consolidated = {
            'generated_at': datetime.now().isoformat(),
            'scrape_dates': {
                'Lotte': lotte_date or '',
                'Superindo': superindo_date or '',
            },
            'source_files': [
                lotte_file.name if lotte_file else '',
                superindo_file.name if superindo_file else '',
            ],
            'display_hints': {
                'stores': {'Lotte': 'Lotte Mart', 'Superindo': 'Superindo'},
                'store_colors': {'Lotte': '#0057A8', 'Superindo': '#E8211D'},
                'currency': 'IDR',
                'locale': 'id-ID',
            },
            'products': consolidated_products,
            'singles': singles,
            'stats': {
                'total_products_lotte': len(lotte_products),
                'total_products_superindo': len(superindo_products),
                'matched_across_stores': len(matched_pairs),
                'lotte_only': len(lotte_only),
                'superindo_only': len(superindo_only),
                'match_methods': match_methods,
                'flagged_for_review': len(review_items),
                'validation_rejected': 0,
            },
        }

    # 8. Print summary
    elapsed = time.time() - t_start
    print()
    print("========================================")
    print("  Consolidation Summary")
    print("========================================")
    print(f"  Lotte products:     {len(lotte_products)}")
    print(f"  Superindo products: {len(superindo_products)}")
    print(f"  Matched:            {len(matched_pairs)}")
    print(f"  Lotte only:         {len(lotte_only)}")
    print(f"  Superindo only:     {len(superindo_only)}")
    print(f"  Review queue:       {len(review_data)}")
    print(f"  Time:               {elapsed:.1f}s")
    print("========================================")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Consolidate grocery prices across stores')
    parser.add_argument('--input-dir', type=str, help='Auto-detect store from filename')
    parser.add_argument('--lotte-dir', type=str, help='Explicit Lotte input directory')
    parser.add_argument('--superindo-dir', type=str, help='Explicit Superindo input directory')
    parser.add_argument('--dry-run', action='store_true', help='Preview without database update')
    parser.add_argument('--verbose', action='store_true', help='Write detailed match results to log file')
    args = parser.parse_args()

    cfg = load_config()
    database_dir = Path('database')

    log_file = None
    if args.verbose:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = database_dir / 'logs' / f'consolidate_{timestamp}.log'

    if args.input_dir:
        lotte_dir = Path(args.input_dir)
        superindo_dir = Path(args.input_dir)
    else:
        lotte_dir = Path(args.lotte_dir) if args.lotte_dir else Path('database/ocr/lotte')
        superindo_dir = Path(args.superindo_dir) if args.superindo_dir else Path('database/ocr/superindo')

    consolidate(cfg, lotte_dir, superindo_dir, database_dir, args.dry_run, args.verbose, log_file)


if __name__ == '__main__':
    main()
