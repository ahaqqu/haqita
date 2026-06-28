"""
Haqita D1 Seed Script.

Reads database/*.json and output/html/promo_catalog.json and generates
SQL insert statements for seeding the D1 database.

Usage:
    python scripts/seed_d1.py                    # Generate seed.sql
    python scripts/seed_d1.py --apply            # Apply directly to local D1 via wrangler
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = ROOT / "database"
OUTPUT_DIR = ROOT / "output" / "html"
SEED_FILE = ROOT / "web" / "seed.sql"

PRICE_HISTORY_SRC = DATABASE_DIR / "price_history.json"
CATALOG_SRC = DATABASE_DIR / "product_catalog.json"
ACTIVE_PROMO_SRC = OUTPUT_DIR / "active_promo.json"
PROMO_CATALOG_SRC = OUTPUT_DIR / "promo_catalog.json"

DEFAULT_STORE_COLORS = {
    "Lotte": "#0057A8",
    "Superindo": "#E8211D",
}


def load_json(path: Path, default=None):
    """Load JSON file, return default if not found."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def escape_sql(value: str) -> str:
    """Escape a string value for use in a SQL string literal.

    Doubles single quotes per SQLite string-literal rules.
    """
    return value.replace("'", "''")


def sql_value(value) -> str:
    """Format a Python value as a SQL literal.

    Returns:
        "NULL" for None, the numeric literal for ints/floats, or a
        single-quote-wrapped, escaped string for strings and JSON-encoded
        dicts/lists.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return "'" + escape_sql(json.dumps(value, ensure_ascii=False)) + "'"
    return "'" + escape_sql(str(value)) + "'"


def generate_store_inserts(history: dict) -> list[str]:
    """Generate INSERT statements for the stores table from price history.

    Extracts unique store names from the snapshot data and assigns each a
    color from output/html/active_promo.json display_hints.store_colors.
    Falls back to hardcoded colors if active_promo.json is unavailable.

    Args:
        history: Parsed price_history.json data.

    Returns:
        List of SQL INSERT OR REPLACE statements for the stores table.
    """
    snapshots = history.get("snapshots", []) if isinstance(history, dict) else []
    store_names = sorted({str(snapshot.get("store")) for snapshot in snapshots if snapshot.get("store") is not None})

    active_promo = load_json(ACTIVE_PROMO_SRC, {})
    display_hints = active_promo.get("display_hints", {}) if isinstance(active_promo, dict) else {}
    store_colors = display_hints.get("store_colors", {}) if isinstance(display_hints, dict) else {}

    statements = []
    for name in store_names:
        color = store_colors.get(name) if isinstance(store_colors, dict) else None
        if color is None:
            color = DEFAULT_STORE_COLORS.get(name)
        statements.append(
            "INSERT OR REPLACE INTO stores (name, color) VALUES ("
            + sql_value(name) + ", " + sql_value(color) + ");"
        )
    return statements


def generate_product_inserts(catalog: dict) -> list[str]:
    """Generate INSERT statements for the products table from product_catalog.json.

    Maps catalog fields to products table columns:
      canonical_key -> key
      display_name -> name
      brand -> brand
      unit -> unit
      unit_type -> unit_type
      unit_value_g -> unit_value_g
      category -> NULL (not present in catalog, populated by sync API)

    Args:
        catalog: Parsed product_catalog.json "catalog" object.

    Returns:
        List of SQL INSERT OR REPLACE statements for the products table.
    """
    statements = []
    for product_key in sorted(catalog.keys()):
        entry = catalog[product_key]
        if not isinstance(entry, dict):
            continue
        statements.append(
            "INSERT OR REPLACE INTO products (key, name, brand, category, unit, unit_type, unit_value_g) VALUES ("
            + sql_value(entry.get("canonical_key", product_key)) + ", "
            + sql_value(entry.get("display_name")) + ", "
            + sql_value(entry.get("brand")) + ", NULL, "
            + sql_value(entry.get("unit")) + ", "
            + sql_value(entry.get("unit_type")) + ", "
            + sql_value(entry.get("unit_value_g")) + ");"
        )
    return statements


def generate_price_inserts(history: dict) -> list[str]:
    """Generate INSERT statements for the prices table from price_history.json snapshots.

    Maps snapshot fields to prices table columns:
      product_key, store, price, effective_unit_price, bundle_size,
      promo (JSON-encoded array or NULL), promo_type, valid_from, valid_until,
      image_path, image_r2_url (NULL), scrape_time, date, match_method,
      match_confidence, standardized_promo (JSON-encoded object or NULL).

    Uses INSERT OR REPLACE for idempotency on (product_key, store, date).
    Missing snapshot fields are inserted as NULL. When verbose is True, a
    warning is printed for each missing field.

    Args:
        history: Parsed price_history.json data.
        verbose: Whether to print warnings for missing snapshot fields.

    Returns:
        List of SQL INSERT OR REPLACE statements for the prices table.
    """
    snapshots = history.get("snapshots", []) if isinstance(history, dict) else []
    statements = []
    price_columns = [
        "product_key",
        "store",
        "price",
        "effective_unit_price",
        "bundle_size",
        "promo",
        "promo_type",
        "valid_from",
        "valid_until",
        "image_path",
        "image_r2_url",
        "scrape_time",
        "date",
        "match_method",
        "match_confidence",
        "standardized_promo",
    ]
    required_for_warning = [
        "product_key",
        "store",
        "price",
        "effective_unit_price",
        "date",
    ]

    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue

        missing = [field for field in required_for_warning if snapshot.get(field) is None]
        if missing:
            key = snapshot.get("product_key", "<unknown>")
            print("[WARN] Snapshot for " + key + " missing fields: " + ", ".join(missing))

        values = (
            sql_value(snapshot.get("product_key")) + ", "
            + sql_value(snapshot.get("store")) + ", "
            + sql_value(snapshot.get("price")) + ", "
            + sql_value(snapshot.get("effective_unit_price")) + ", "
            + sql_value(snapshot.get("bundle_size", 1)) + ", "
            + sql_value(snapshot.get("promo")) + ", "
            + sql_value(snapshot.get("promo_type")) + ", "
            + sql_value(snapshot.get("valid_from")) + ", "
            + sql_value(snapshot.get("valid_until")) + ", "
            + sql_value(snapshot.get("image_path")) + ", NULL, "
            + sql_value(snapshot.get("scrape_time")) + ", "
            + sql_value(snapshot.get("date")) + ", "
            + sql_value(snapshot.get("match_method")) + ", "
            + sql_value(snapshot.get("match_confidence")) + ", "
            + sql_value(snapshot.get("standardized_promo"))
        )
        statements.append(
            "INSERT OR REPLACE INTO prices ("
            + ", ".join(price_columns)
            + ") VALUES ("
            + values
            + ");"
        )
    return statements


def generate_promo_inserts(promo_catalog: list) -> list[str]:
    """Generate INSERT statements for the promos table from promo_catalog.json.

    Maps promo catalog fields to promos table columns:
      key -> key
      display -> display
      type -> type
      discount_pct -> discount_pct
      max_qty -> NULL (not present in source)
      product_count -> product_count
      stores -> stores (JSON-encoded object)
      example_products -> example_products (JSON-encoded array)

    Uses INSERT OR REPLACE for idempotency on key.

    Args:
        promo_catalog: Parsed promo_catalog.json list.

    Returns:
        List of SQL INSERT OR REPLACE statements for the promos table.
    """
    statements = []
    if not isinstance(promo_catalog, list):
        return statements

    for entry in promo_catalog:
        if not isinstance(entry, dict):
            continue
        statements.append(
            "INSERT OR REPLACE INTO promos (key, display, type, discount_pct, max_qty, product_count, stores, example_products) VALUES ("
            + sql_value(entry.get("key")) + ", "
            + sql_value(entry.get("display")) + ", "
            + sql_value(entry.get("type")) + ", "
            + sql_value(entry.get("discount_pct")) + ", NULL, "
            + sql_value(entry.get("product_count")) + ", "
            + sql_value(entry.get("stores")) + ", "
            + sql_value(entry.get("example_products")) + ");"
        )
    return statements


def generate_seed_sql(history: dict, catalog: dict, promo_catalog_data: list) -> str:
    """Combine all INSERT statements into a single SQL file.

    Order: stores first (no FK dependencies), then products (referenced by
    prices), then prices, then promos.

    Args:
        history: Parsed price_history.json data.
        catalog: Parsed product_catalog.json "catalog" object.
        promo_catalog_data: Parsed promo_catalog.json list.
        verbose: Whether to propagate verbosity to price insert generation.

    Returns:
        Complete SQL seed script as a single string.
    """
    sections = [
        generate_store_inserts(history),
        generate_product_inserts(catalog),
        generate_price_inserts(history),
        generate_promo_inserts(promo_catalog_data),
    ]
    lines = []
    for section in sections:
        lines.extend(section)
    return "\n".join(lines) + "\n"


def apply_to_d1(seed_sql_path: Path):
    """Apply seed SQL to local D1 via wrangler.

    Runs: wrangler d1 execute haqita-db --local --file=<seed_sql_path>

    Args:
        seed_sql_path: Path to the generated seed.sql file.
    """
    command = ["wrangler", "d1", "execute", "haqita-db", "--local", "--file=" + str(seed_sql_path)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=ROOT / "web",
    )
    if result.returncode != 0:
        print("[ERROR] wrangler d1 execute failed:")
        print(result.stderr)
        sys.exit(1)
    print(result.stdout)


def main():
    parser = argparse.ArgumentParser(description="Haqita D1 Seed Script")
    parser.add_argument("--apply", action="store_true", help="Apply directly to local D1 via wrangler")
    args = parser.parse_args()

    if not PRICE_HISTORY_SRC.exists():
        print("[ERROR] Required file not found: " + str(PRICE_HISTORY_SRC))
        sys.exit(1)

    if not PROMO_CATALOG_SRC.exists():
        print("[WARN] Optional file not found: " + str(PROMO_CATALOG_SRC) + "; promos table will be empty.")
        print()

    # Load source data
    history = load_json(PRICE_HISTORY_SRC, {"snapshots": [], "metadata": {}})
    catalog_raw = load_json(CATALOG_SRC, {"catalog": {}})
    catalog = catalog_raw.get("catalog", {}) if isinstance(catalog_raw, dict) else {}
    promo_catalog_data = load_json(PROMO_CATALOG_SRC, [])

    # Generate SQL
    seed_sql = generate_seed_sql(history, catalog, promo_catalog_data)

    print("  Stores:   " + str(len(generate_store_inserts(history))) + " rows")
    print("  Products: " + str(len(generate_product_inserts(catalog))) + " rows")
    print("  Prices:   " + str(len(generate_price_inserts(history))) + " rows")
    print("  Promos:   " + str(len(generate_promo_inserts(promo_catalog_data))) + " rows")
    print()

    # Write seed.sql
    SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEED_FILE.write_text(seed_sql, encoding="utf-8")
    print("Wrote seed SQL to " + str(SEED_FILE))

    if args.apply:
        apply_to_d1(SEED_FILE)


if __name__ == "__main__":
    main()
