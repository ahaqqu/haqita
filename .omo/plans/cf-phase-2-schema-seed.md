# Phase 2: D1 Schema & Seed Data

## TL;DR (For humans)

**What you'll get:** A D1 database with the complete schema (stores, products, prices, promos tables with indexes) and seed data populated from the existing `database/*.json` files. A Python seed script that can re-generate seed data from any pipeline run.

**Why this approach:** The schema must match the existing JSON data structures exactly so the API can serve the same data the static UI already shows. Seeding from the existing pipeline output validates the schema before any API code is written.

**What it will NOT do:** Implement API endpoints (Phase 3), implement sync endpoints (Phase 4), or create the Python sync script (Phase 5).

**Effort:** Medium (~3-4 hours: schema design, seed script, tests, documentation)
**Risk:** Low — schema is applied to local D1 only; production D1 is seeded via the sync API in Phase 5

---

## Scope

### Must have
1. `web/schema.sql` with all tables, indexes, and constraints matching the existing JSON data structures
2. `scripts/seed_d1.py` that reads `database/price_history.json`, `database/product_catalog.json`, and `output/html/promo_catalog.json` and generates SQL insert statements
3. Schema applied to local D1 (`wrangler d1 execute --local`)
4. Seed data applied to local D1
5. Unit tests for the seed script (`tests/cloudflare/test_seed_d1.py`)
6. Documentation at `docs/database/d1-schema.md`

### Must NOT have
1. No API route handlers — that is Phase 3
2. No production D1 seeding — production is seeded via sync API in Phase 5
3. No modifications to existing `database/*.json` files
4. No schema changes beyond what plan.md specifies (lines 238-306)
5. No ORM or query builder — use raw SQL with parameterized queries only

---

## Verification strategy
- **Test decision:** TDD for seed script + SQL verification for schema
- **Evidence:** SQL query outputs showing correct table structure and row counts
- **Schema verification:** `wrangler d1 execute haqita-db --local --command "SELECT name FROM sqlite_master WHERE type='table'"`
- **Data verification:** `wrangler d1 execute haqita-db --local --command "SELECT COUNT(*) FROM prices"` — count must match source JSON snapshot count

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Create schema.sql | Phase 1 complete | 3, 4 | 2 |
| 2. Create seed_d1.py | Phase 1 complete | 3 | 1 |
| 3. Apply schema + seed to local D1 | 1, 2 | 5, 6 | — |
| 4. Write unit tests | 2 | 5 | 3 |
| 5. Write documentation | 1, 3 | — | 4 |
| 6. Final verification | 3, 4, 5 | — | — |

---

## Todos

### Todo 1: Create web/schema.sql

**What to do:**

Create `web/schema.sql` with the following content. This schema is derived from plan.md:238-306 and validated against the actual JSON structures in `database/price_history.json` (schema v1.2) and `database/product_catalog.json` (schema v1.1).

```sql
-- Haqita D1 Schema
-- Derived from database/price_history.json (v1.2) and database/product_catalog.json (v1.1)
-- Applied via: wrangler d1 execute haqita-db --local --file=./web/schema.sql

-- Stores (supermarkets)
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Products (catalog entries)
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    unit TEXT,
    unit_type TEXT,
    unit_value_g REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Prices (core data, append-only with upsert by unique key)
-- Idempotency: UNIQUE(product_key, store, date) — re-syncing the same date updates in place
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_key TEXT NOT NULL,
    store TEXT NOT NULL,
    price INTEGER NOT NULL,
    effective_unit_price INTEGER NOT NULL,
    bundle_size INTEGER DEFAULT 1,
    promo TEXT,                       -- JSON array of promo strings, or NULL
    promo_type TEXT,
    valid_from TEXT,                  -- ISO date YYYY-MM-DD, or NULL
    valid_until TEXT,                 -- ISO date YYYY-MM-DD, or NULL (NULL = always active)
    image_path TEXT,                  -- Original local path for traceability
    image_r2_url TEXT,                -- Public R2 URL after upload (set by Phase 5)
    scrape_time TEXT,                 -- ISO datetime
    date TEXT NOT NULL,               -- ISO date YYYY-MM-DD
    match_method TEXT,                -- "exact", "embedding", "ai", or NULL
    match_confidence REAL,            -- 0.0-1.0, or NULL
    standardized_promo TEXT,          -- JSON object, or NULL
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_key, store, date),
    FOREIGN KEY (product_key) REFERENCES products(key)
);

-- Promo catalog (derived from latest run)
CREATE TABLE IF NOT EXISTS promos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    display TEXT NOT NULL,
    type TEXT,
    discount_pct INTEGER,
    max_qty INTEGER,
    product_count INTEGER DEFAULT 0,
    stores TEXT,                      -- JSON object {store: count}
    example_products TEXT,            -- JSON array of strings
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_prices_product ON prices(product_key);
CREATE INDEX IF NOT EXISTS idx_prices_store ON prices(store);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_prices_valid_until ON prices(valid_until);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_promos_type ON promos(type);
```

**Key schema decisions (all from plan.md, validated against actual data):**
- `promo` is stored as TEXT (JSON array) because D1/SQLite has no native JSON type. Example: `'["DISKON 20%", "maks. 4 pck"]'` or `NULL`.
- `standardized_promo` is stored as TEXT (JSON object) or NULL. It is absent (NULL) when `promo` is NULL.
- `image_path` stores the original local path (e.g., `database/scrape/superindo/20260613/abc.jpg`) for traceability.
- `image_r2_url` is NULL initially — populated by Phase 5 sync script after R2 upload.
- `date`, `valid_from`, `valid_until` use TEXT (ISO date `YYYY-MM-DD`) — SQLite has no native DATE type.
- `scrape_time` uses TEXT (ISO datetime) — microsecond precision preserved as string.
- `UNIQUE(product_key, store, date)` enforces idempotency — re-syncing the same date updates in place via `INSERT OR REPLACE`.

**References:** plan.md:238-306 (D1 schema), database/price_history.json (actual snapshot fields: product_key, name, brand, unit, date, store, price, effective_unit_price, promo, valid_from, valid_until, bundle_size, promo_type, match_method, match_confidence, image_path, scrape_time, standardized_promo), database/product_catalog.json (actual catalog fields: canonical_key, display_name, brand, unit, unit_type, unit_value_g), output/html/promo_catalog.json (actual promo fields: key, display, type, discount_pct, product_count, stores, example_products)

**Acceptance criteria:**
- `web/schema.sql` exists with the exact SQL shown above
- `wrangler d1 execute haqita-db --local --file=./web/schema.sql` succeeds without errors
- **Log message clarity:** `wrangler d1 execute` output shows each `CREATE TABLE` and `CREATE INDEX` statement executing successfully
- **Failure handling:** If `wrangler d1 execute` fails with "no such table," the schema was not applied — re-run the command. If it fails with "table already exists," add `IF NOT EXISTS` (already included in the schema).
- **Code quality:**
  - All `CREATE TABLE` and `CREATE INDEX` statements use `IF NOT EXISTS` — schema is idempotent
  - Foreign key constraint on `prices.product_key` references `products(key)`
  - `UNIQUE` constraint on `(product_key, store, date)` enforces idempotency
  - All columns that can be NULL are documented with comments
  - No `SELECT *` in any queries — always specify columns explicitly
- **Unit test coverage:** Schema correctness is verified via SQL queries in Todo 6, not unit tests. The seed script (Todo 2) has unit tests.

**QA:**
- Happy: `wrangler d1 execute haqita-db --local --file=./web/schema.sql` succeeds, then `wrangler d1 execute haqita-db --local --command "SELECT name FROM sqlite_master WHERE type='table'"` shows `stores`, `products`, `prices`, `promos` → pass
- Failure: Schema execution fails → check SQL syntax, check D1 database exists (`wrangler d1 list`)

**Commit:** Y | feat(db): add D1 schema with stores, products, prices, promos tables

---

### Todo 2: Create scripts/seed_d1.py

**What to do:**

Create `scripts/seed_d1.py` following the existing script pattern (see `scripts/publish_html.py` for the template — argparse, `--dry-run`, `--verbose`, print output, return 0 on success).

The script reads the existing JSON database files and generates SQL insert statements that can be applied to D1 via `wrangler d1 execute`.

**File structure:**
```python
"""
Haqita D1 Seed Script.

Reads database/*.json and output/html/promo_catalog.json and generates
SQL insert statements for seeding the D1 database.

Usage:
    python scripts/seed_d1.py                    # Generate seed.sql
    python scripts/seed_d1.py --dry-run          # Preview without writing
    python scripts/seed_d1.py --verbose          # Show row counts per table
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


def load_json(path: Path, default=None):
    """Load JSON file, return default if not found."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def generate_store_inserts(history: dict) -> list[str]:
    """Generate INSERT statements for stores table from price history.
    
    Extracts unique store names and their colors from display_hints in active_promo.json.
    Falls back to hardcoded colors if display_hints not available.
    """
    # ... implementation: iterate snapshots, extract unique store names
    # ... use display_hints.store_colors from active_promo.json for colors
    # ... return list of SQL INSERT strings with parameterized values
    pass


def generate_product_inserts(catalog: dict) -> list[str]:
    """Generate INSERT statements for products table from product_catalog.json.
    
    Maps catalog fields to products table columns:
      canonical_key -> key
      display_name -> name
      brand -> brand
      unit -> unit
      unit_type -> unit_type
      unit_value_g -> unit_value_g
      category -> NULL (not in catalog, populated by sync API)
    """
    # ... implementation: iterate catalog entries, map fields
    pass


def generate_price_inserts(history: dict) -> list[str]:
    """Generate INSERT statements for prices table from price_history.json snapshots.
    
    Maps snapshot fields to prices table columns:
      product_key -> product_key
      store -> store
      price -> price
      effective_unit_price -> effective_unit_price
      bundle_size -> bundle_size (default 1)
      promo -> promo (JSON-encoded array, or NULL)
      promo_type -> promo_type
      valid_from -> valid_from
      valid_until -> valid_until
      image_path -> image_path
      scrape_time -> scrape_time
      date -> date
      match_method -> match_method
      match_confidence -> match_confidence
      standardized_promo -> standardized_promo (JSON-encoded object, or NULL)
    
    Uses INSERT OR REPLACE for idempotency on (product_key, store, date).
    """
    # ... implementation: iterate snapshots, map fields, JSON-encode promo and standardized_promo
    pass


def generate_promo_inserts(promo_catalog: list) -> list[str]:
    """Generate INSERT statements for promos table from promo_catalog.json.
    
    Maps promo catalog fields to promos table columns:
      key -> key
      display -> display
      type -> type
      discount_pct -> discount_pct
      product_count -> product_count
      stores -> stores (JSON-encoded object)
      example_products -> example_products (JSON-encoded array)
    
    Uses INSERT OR REPLACE for idempotency on key.
    """
    # ... implementation: iterate promo entries, map fields, JSON-encode stores and example_products
    pass


def generate_seed_sql(history: dict, catalog: dict, promo_catalog_data: list) -> str:
    """Combine all INSERT statements into a single SQL file.
    
    Order: stores first (no FK deps), then products (referenced by prices), then prices, then promos.
    """
    # ... implementation: call all generate_* functions, combine with semicolons
    pass


def apply_to_d1(seed_sql_path: Path, dry_run: bool):
    """Apply seed SQL to local D1 via wrangler.
    
    Runs: wrangler d1 execute haqita-db --local --file=<seed_sql_path>
    """
    # ... implementation: subprocess.run wrangler command, check return code
    pass


def main():
    parser = argparse.ArgumentParser(description="Haqita D1 Seed Script")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    parser.add_argument("--verbose", action="store_true", help="Show row counts per table")
    parser.add_argument("--apply", action="store_true", help="Apply directly to local D1 via wrangler")
    args = parser.parse_args()

    # Load source data
    history = load_json(DATABASE_DIR / "price_history.json", {"snapshots": [], "metadata": {}})
    catalog_raw = load_json(DATABASE_DIR / "product_catalog.json", {"catalog": {}})
    catalog = catalog_raw.get("catalog", {})
    promo_catalog_data = load_json(OUTPUT_DIR / "promo_catalog.json", [])

    if args.dry_run:
        print("[DRY-RUN] No files will be written.")
        print()

    # Generate SQL
    seed_sql = generate_seed_sql(history, catalog, promo_catalog_data)

    if args.verbose:
        print(f"  Stores:   {len(generate_store_inserts(history))} rows")
        print(f"  Products: {len(generate_product_inserts(catalog))} rows")
        print(f"  Prices:   {len(generate_price_inserts(history))} rows")
        print(f"  Promos:   {len(generate_promo_inserts(promo_catalog_data))} rows")
        print()

    if args.dry_run:
        print(f"Would write {len(seed_sql)} bytes to {SEED_FILE}")
        return

    # Write seed.sql
    SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEED_FILE.write_text(seed_sql, encoding="utf-8")
    print(f"Wrote seed SQL to {SEED_FILE}")

    if args.apply:
        apply_to_d1(SEED_FILE, args.dry_run)


if __name__ == "__main__":
    main()
```

**Implementation details (the implementer must fill in the `pass` blocks):**

1. **`generate_store_inserts(history)`**: Iterate `history["snapshots"]`, extract unique `store` values. Load `output/html/active_promo.json` to get `display_hints.store_colors` (e.g., `{"Lotte": "#0057A8", "Superindo": "#E8211D"}`). Generate: `INSERT OR REPLACE INTO stores (name, color) VALUES ('Lotte', '#0057A8');`

2. **`generate_product_inserts(catalog)`**: Iterate `catalog` dict (keyed by product_key). Map `canonical_key` → `key`, `display_name` → `name`, `brand` → `brand`, `unit` → `unit`, `unit_type` → `unit_type`, `unit_value_g` → `unit_value_g`. `category` is not in the catalog — set to `NULL`. Generate: `INSERT OR REPLACE INTO products (key, name, brand, unit, unit_type, unit_value_g, category) VALUES ('...', '...', '...', '...', '...', 85.0, NULL);`

3. **`generate_price_inserts(history)`**: Iterate `history["snapshots"]`. For each snapshot, JSON-encode `promo` (array → `json.dumps(promo)` or `NULL`) and `standardized_promo` (object → `json.dumps(standardized_promo)` or `NULL` if absent). Generate: `INSERT OR REPLACE INTO prices (product_key, store, price, effective_unit_price, bundle_size, promo, promo_type, valid_from, valid_until, image_path, scrape_time, date, match_method, match_confidence, standardized_promo) VALUES (...);`

4. **`generate_promo_inserts(promo_catalog_data)`**: Iterate the promo_catalog list. JSON-encode `stores` (object → `json.dumps`) and `example_products` (array → `json.dumps`). Generate: `INSERT OR REPLACE INTO promos (key, display, type, discount_pct, product_count, stores, example_products) VALUES (...);`

5. **SQL escaping**: All string values must be escaped by replacing single quotes with two single quotes (`'` → `''`). This is the SQLite standard for string literals. Do NOT use Python f-strings for SQL generation — use string concatenation with explicit escaping.

6. **`apply_to_d1(seed_sql_path, dry_run)`**: Run `subprocess.run(["wrangler", "d1", "execute", "haqita-db", "--local", f"--file={seed_sql_path}"], capture_output=True, text=True, cwd=ROOT)`. Check `result.returncode != 0` for errors. Print `result.stdout` on success, `result.stderr` on failure.

**References:** scripts/publish_html.py (template pattern: argparse, load_json, main()), database/price_history.json (snapshot schema with 18 fields), database/product_catalog.json (catalog schema with 12 fields), output/html/promo_catalog.json (promo catalog schema with 7 fields), plan.md:238-306 (D1 schema)

**Acceptance criteria:**
- `python scripts/seed_d1.py --dry-run --verbose` prints row counts for stores, products, prices, promos without writing any files
- `python scripts/seed_d1.py` creates `web/seed.sql` with valid SQL
- `python scripts/seed_d1.py --apply` applies the seed to local D1 and prints success
- Row counts match source data: stores=2, products=589, prices=599, promos=50 (based on current data)
- **Log message clarity:**
  - `--dry-run` mode prints: `[DRY-RUN] No files will be written.` followed by row counts
  - `--verbose` mode prints: `  Stores:   2 rows`, `  Products: 589 rows`, etc. (aligned columns)
  - `--apply` mode prints: `Wrote seed SQL to <path>` then wrangler output
  - Error messages include the file path and specific error (e.g., `Error reading database/price_history.json: <exception>`)
- **Failure handling:**
  - If `database/price_history.json` doesn't exist: print error, exit 1 — do NOT create an empty database
  - If `output/html/promo_catalog.json` doesn't exist: warn but continue (promos table will be empty)
  - If `wrangler d1 execute` fails: print stderr, exit 1 — do NOT silently continue
  - If a snapshot has a missing field: use `NULL` for that column, log a warning in `--verbose` mode
- **Code quality:**
  - Follow `scripts/publish_html.py` pattern exactly: `sys.path.insert`, `ROOT = Path(__file__).resolve().parent.parent`, `load_json()` helper, argparse with `--dry-run` and `--verbose`
  - All SQL values are properly escaped (single quotes doubled)
  - Use `INSERT OR REPLACE` for idempotency — re-running the seed does not create duplicates
  - No `SELECT *` anywhere — explicit column lists
  - Type hints on all function signatures
  - Docstrings on all functions explaining what they do and what they return
  - No external dependencies beyond stdlib (`json`, `argparse`, `subprocess`, `pathlib`)
- **Unit test coverage:** See Todo 4 for test specifications
- **Documentation:** See Todo 5 for `docs/database/d1-schema.md`

**QA:**
- Happy: `python scripts/seed_d1.py --apply --verbose` prints row counts, creates seed.sql, applies to D1 → pass
- Failure: `database/price_history.json` missing → script exits 1 with clear error message

**Commit:** Y | feat(db): add D1 seed script that reads existing JSON database

---

### Todo 3: Apply schema and seed to local D1

**What to do:**

1. Apply the schema:
   ```bash
   wrangler d1 execute haqita-db --local --file=./web/schema.sql
   ```

2. Generate and apply seed data:
   ```bash
   python scripts/seed_d1.py --apply --verbose
   ```

3. Verify table structure:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
   ```
   **Expected:** `stores`, `products`, `prices`, `promos` (plus `sqlite_sequence` and `_cf_KV` if present)

4. Verify row counts:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT 'stores' as tbl, COUNT(*) as cnt FROM stores UNION ALL SELECT 'products', COUNT(*) FROM products UNION ALL SELECT 'prices', COUNT(*) FROM prices UNION ALL SELECT 'promos', COUNT(*) FROM promos"
   ```

5. Spot-check data:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT * FROM stores"
   wrangler d1 execute haqita-db --local --command "SELECT key, name, brand FROM products LIMIT 5"
   wrangler d1 execute haqita-db --local --command "SELECT product_key, store, price, date FROM prices LIMIT 5"
   wrangler d1 execute haqita-db --local --command "SELECT key, display, type, product_count FROM promos LIMIT 5"
   ```

**References:** web/schema.sql (from Todo 1), scripts/seed_d1.py (from Todo 2)

**Acceptance criteria:**
- Schema application succeeds without errors
- Seed application succeeds without errors
- Table list shows: `stores`, `products`, `prices`, `promos`
- Row counts match: stores=2, products=589, prices=599, promos=50 (or whatever the current data has)
- Spot-check queries return valid data with correct field values
- **Log message clarity:** `wrangler d1 execute` output shows SQL statements executing and row counts
- **Failure handling:** If seed fails, check `web/seed.sql` for SQL syntax errors. If schema fails, check `web/schema.sql`. Both are fixable by re-running.
- **Code quality:** No manual SQL editing — all SQL is generated by the seed script
- **Unit test coverage:** N/A — this is a manual verification step

**QA:**
- Happy: All queries return expected data → pass
- Failure: Row counts don't match → check seed script for data mapping errors

**Commit:** N — this is a local D1 operation, no file changes to commit (seed.sql is generated and can be committed separately)

---

### Todo 4: Write unit tests for seed script

**What to do:**

Create `tests/cloudflare/test_seed_d1.py` following the existing test pattern (see `tests/matching/test_publish_html.py` for the template — class-based `Test*` with `test_*` methods, `unittest.mock.patch` for mocking, `assert` for assertions, `tmp_path` for temp files).

Also create `tests/cloudflare/__init__.py` (empty file).

**Test structure:**
```python
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestGenerateStoreInserts:
    """Tests for generate_store_inserts()."""

    def test_extracts_unique_stores_from_snapshots(self):
        """Should return one INSERT per unique store name."""
        # ... create a mock history dict with snapshots from "Lotte" and "Superindo"
        # ... call generate_store_inserts(history)
        # ... assert len(result) == 2
        # ... assert "Lotte" in result[0] and "Superindo" in result[1]

    def test_includes_store_colors_from_display_hints(self):
        """Should include color from display_hints if available."""
        # ... create mock history with display_hints.store_colors
        # ... assert the INSERT includes the color value

    def test_handles_single_store(self):
        """Should work with only one store."""
        # ... create mock history with only "Superindo" snapshots
        # ... assert len(result) == 1

    def test_handles_empty_history(self):
        """Should return empty list for empty history."""
        # ... create mock history with empty snapshots
        # ... assert result == []

    def test_uses_insert_or_replace_for_idempotency(self):
        """Should use INSERT OR REPLACE, not INSERT."""
        # ... call generate_store_inserts with mock data
        # ... assert "INSERT OR REPLACE" in result[0]


class TestGenerateProductInserts:
    """Tests for generate_product_inserts()."""

    def test_maps_catalog_fields_to_table_columns(self):
        """Should map canonical_key->key, display_name->name, etc."""
        # ... create mock catalog with one entry
        # ... call generate_product_inserts(catalog)
        # ... assert the INSERT contains the correct column names and values

    def test_sets_category_to_null(self):
        """Category is not in the catalog — should be NULL."""
        # ... assert "NULL" appears in the category position

    def test_handles_null_brand(self):
        """Should handle null brand values."""
        # ... create mock catalog entry with brand=None
        # ... assert the INSERT handles it correctly

    def test_handles_empty_catalog(self):
        """Should return empty list for empty catalog."""
        # ... assert result == []


class TestGeneratePriceInserts:
    """Tests for generate_price_inserts()."""

    def test_maps_all_snapshot_fields(self):
        """Should map all 15 snapshot fields to prices table columns."""
        # ... create a mock snapshot with all fields populated
        # ... call generate_price_inserts(history)
        # ... assert the INSERT contains all column names

    def test_json_encodes_promo_array(self):
        """Should JSON-encode the promo array."""
        # ... create mock snapshot with promo=["DISKON 20%", "maks. 4 pck"]
        # ... assert the INSERT contains '["DISKON 20%", "maks. 4 pck"]' (JSON-encoded)

    def test_handles_null_promo(self):
        """Should use NULL for null promo."""
        # ... create mock snapshot with promo=None
        # ... assert the INSERT contains NULL for promo column

    def test_json_encodes_standardized_promo(self):
        """Should JSON-encode the standardized_promo object."""
        # ... create mock snapshot with standardized_promo dict
        # ... assert the INSERT contains JSON-encoded object

    def test_handles_missing_standardized_promo(self):
        """Should use NULL when standardized_promo is absent."""
        # ... create mock snapshot without standardized_promo key
        # ... assert the INSERT contains NULL for standardized_promo column

    def test_uses_insert_or_replace(self):
        """Should use INSERT OR REPLACE for idempotency."""
        # ... assert "INSERT OR REPLACE" in result[0]

    def test_escapes_single_quotes_in_values(self):
        """Should escape single quotes in string values."""
        # ... create mock snapshot with name containing a single quote (e.g., "Jeruk's")
        # ... assert the INSERT contains "Jeruk''s" (doubled quote)


class TestGeneratePromoInserts:
    """Tests for generate_promo_inserts()."""

    def test_maps_promo_catalog_fields(self):
        """Should map key, display, type, discount_pct, product_count."""
        # ... create mock promo catalog entry
        # ... assert the INSERT contains correct values

    def test_json_encodes_stores_object(self):
        """Should JSON-encode the stores dict."""
        # ... create mock entry with stores={"Superindo": 64}
        # ... assert the INSERT contains '{"Superindo": 64}' (JSON-encoded)

    def test_json_encodes_example_products_array(self):
        """Should JSON-encode the example_products array."""
        # ... create mock entry with example_products=["Rinso", "Bango"]
        # ... assert the INSERT contains '["Rinso", "Bango"]' (JSON-encoded)

    def test_handles_empty_promo_catalog(self):
        """Should return empty list for empty catalog."""
        # ... assert result == []


class TestGenerateSeedSql:
    """Tests for generate_seed_sql()."""

    def test_combines_all_inserts_in_correct_order(self):
        """Should output stores first, then products, then prices, then promos."""
        # ... create mock data for all tables
        # ... call generate_seed_sql(history, catalog, promo_catalog_data)
        # ... assert stores INSERTs appear before products INSERTs, etc.

    def test_each_statement_ends_with_semicolon(self):
        """Every INSERT statement must end with a semicolon."""
        # ... split the SQL by semicolon
        # ... assert each non-empty statement is valid


class TestMainFunction:
    """Tests for main() CLI behavior."""

    def test_dry_run_does_not_write_file(self, tmp_path, monkeypatch):
        """--dry-run should not create seed.sql."""
        # ... monkeypatch SEED_FILE to tmp_path / "seed.sql"
        # ... mock sys.argv for --dry-run
        # ... call main()
        # ... assert not (tmp_path / "seed.sql").exists()

    def test_verbose_prints_row_counts(self, capsys, monkeypatch):
        """--verbose should print row counts for each table."""
        # ... mock sys.argv for --verbose
        # ... call main()
        # ... captured = capsys.readouterr()
        # ... assert "Stores:" in captured.out
        # ... assert "Products:" in captured.out
        # ... assert "Prices:" in captured.out
        # ... assert "Promos:" in captured.out
```

**References:** tests/matching/test_publish_html.py (test pattern template — class-based Test*, test_* methods, capsys, monkeypatch, tmp_path), tests/matching/test_consolidate.py (more complex test patterns with mocking), scripts/seed_d1.py (the module under test)

**Acceptance criteria:**
- `tests/cloudflare/__init__.py` exists (empty file)
- `tests/cloudflare/test_seed_d1.py` exists with all test classes shown above
- `python -m pytest tests/cloudflare/test_seed_d1.py -v` passes all tests with 0 failures
- **Log message clarity:** pytest output shows each test name and pass/fail status. No tests should be skipped.
- **Failure handling:**
  - Tests for null/empty/missing values must pass — the seed script must not crash on edge cases
  - Test for single-quote escaping must pass — SQL injection prevention
  - Test for `INSERT OR REPLACE` must pass — idempotency verification
- **Code quality:**
  - Follow `tests/matching/test_publish_html.py` pattern: class-based `Test*` with `test_*` methods
  - Use `unittest.mock.patch` for mocking external dependencies
  - Use `tmp_path` for temp file operations
  - Use `capsys` for capturing stdout
  - Use `monkeypatch` for env/argv overrides
  - `sys.path.insert(0, ...)` at top of file for imports
  - All assertions use plain `assert` (no `self.assertEqual`)
  - Test names are descriptive: `test_<what_it_tests>`
  - No `@pytest.mark.skip` or `pytest.skip()` — all tests must run
- **Unit test coverage:** This IS the unit test file. Coverage requirements:
  - `generate_store_inserts`: 5 tests (unique stores, colors, single store, empty, idempotency)
  - `generate_product_inserts`: 4 tests (field mapping, null category, null brand, empty)
  - `generate_price_inserts`: 7 tests (all fields, JSON encoding, null handling, idempotency, escaping)
  - `generate_promo_inserts`: 4 tests (field mapping, JSON encoding, empty)
  - `generate_seed_sql`: 2 tests (ordering, semicolons)
  - `main`: 2 tests (dry-run, verbose)
  - **Total: 24 tests minimum**

**QA:**
- Happy: `python -m pytest tests/cloudflare/test_seed_d1.py -v` shows 24+ passed → pass
- Failure: Any test fails → fix the seed script (not the test) until all tests pass

**Commit:** Y | test(cloudflare): add unit tests for D1 seed script

---

### Todo 5: Write documentation

**What to do:**

Create `docs/database/d1-schema.md` following the existing documentation pattern (see `docs/database/price_history.md` for the template).

**Document structure:**
1. **H1 title:** `# D1 Database Schema`
2. **Overview table:** Database name, Binding name, Location, Schema file, Seed script, Schema version
3. **Tables section:** For each table (stores, products, prices, promos), include:
   - Table name and purpose
   - Column table: column name, type, nullable, description, example value
   - Constraints: UNIQUE, FOREIGN KEY
   - Indexes
4. **JSON-encoded columns section:** Explain that `promo`, `standardized_promo`, `stores`, `example_products` are stored as TEXT with JSON content, and show example values
5. **Idempotency section:** Explain the `INSERT OR REPLACE` pattern and the `UNIQUE(product_key, store, date)` constraint
6. **Relationship to JSON files section:** Table mapping D1 tables to their source JSON files:
   - `stores` ← extracted from `price_history.json` snapshots + `active_promo.json` display_hints
   - `products` ← `product_catalog.json` catalog entries
   - `prices` ← `price_history.json` snapshots
   - `promos` ← `output/html/promo_catalog.json`
7. **Usage section:** Commands for applying schema and seed data

**References:** docs/database/price_history.md (documentation template), web/schema.sql (from Todo 1), scripts/seed_d1.py (from Todo 2), plan.md:238-306 (schema design rationale)

**Acceptance criteria:**
- `docs/database/d1-schema.md` exists and follows the structure above
- All column descriptions match the actual schema in `web/schema.sql`
- **Log message clarity:** Documentation includes exact commands for schema application and verification
- **Failure handling:** Documentation notes that `INSERT OR REPLACE` handles re-seeding without duplicates
- **Code quality:** Documentation matches the style of existing `docs/database/*.md` files — ATX headings, pipe tables, fenced code blocks
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Open `docs/database/d1-schema.md` — all sections present, all column descriptions match schema → pass
- Failure: Column type in docs doesn't match schema → fix the documentation

**Commit:** Y | docs: add D1 schema documentation

---

### Todo 6: Final verification

**What to do:**

Run the complete verification checklist:

1. Verify schema is applied:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
   ```
   **Expected:** `products`, `prices`, `promos`, `stores` (alphabetical order)

2. Verify indexes are created:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
   ```
   **Expected:** `idx_prices_product`, `idx_prices_store`, `idx_prices_date`, `idx_prices_valid_until`, `idx_products_category`, `idx_products_name`, `idx_promos_type` (plus auto-indexes for UNIQUE constraints)

3. Verify row counts:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT 'stores' as tbl, COUNT(*) as cnt FROM stores UNION ALL SELECT 'products', COUNT(*) FROM products UNION ALL SELECT 'prices', COUNT(*) FROM prices UNION ALL SELECT 'promos', COUNT(*) FROM promos"
   ```
   **Expected:** stores=2, products matches catalog entry count, prices matches snapshot count, promos matches promo_catalog entry count

4. Verify data integrity — prices reference valid products:
   ```bash
   wrangler d1 execute haqita-db --local --command "SELECT COUNT(*) FROM prices p WHERE NOT EXISTS (SELECT 1 FROM products WHERE key = p.product_key)"
   ```
   **Expected:** 0 (all price product_keys exist in products table)

5. Verify idempotency — re-run seed and check counts don't change:
   ```bash
   python scripts/seed_d1.py --apply --verbose
   wrangler d1 execute haqita-db --local --command "SELECT COUNT(*) FROM prices"
   ```
   **Expected:** Same count as before re-run (INSERT OR REPLACE updates in place)

6. Run unit tests:
   ```bash
   python -m pytest tests/cloudflare/test_seed_d1.py -v
   ```
   **Expected:** All tests pass

**References:** All previous todos

**Acceptance criteria:**
- All 6 verification steps pass with expected output
- **Log message clarity:** Each query returns clear, unambiguous results
- **Failure handling:** If data integrity check fails (step 4), some product_keys in prices don't exist in products — check the seed script's product generation for missing entries
- **Documentation:** Verification confirms `docs/database/d1-schema.md` is accurate

**QA:**
- Happy: All 6 steps pass → Phase 2 complete
- Failure: Any step fails → fix the issue in the corresponding todo, re-run verification

**Commit:** Y | test: verify D1 schema and seed data are correct

---

## Final verification wave
- [ ] F1. Plan compliance audit — all Must have items delivered, no Must NOT have items present
- [ ] F2. Code quality review — `tsc --noEmit` clean on web/, `python -m pytest tests/cloudflare/ -v` all pass, no `any` types, SQL values properly escaped
- [ ] F3. Real manual QA — `wrangler d1 execute` queries return correct data, row counts match source JSON
- [ ] F4. Scope fidelity — no API routes, no production D1 changes, no ORM, no schema modifications beyond plan.md

---

## Commit strategy
- One commit per todo (Todos 1, 2, 4, 5, 6)
- Commit messages: `feat(db):`, `test(cloudflare):`, `docs:`, `test:`
- Todo 3 (apply schema + seed) does not produce a commit — it is a local D1 operation

---

## Success criteria
1. `web/schema.sql` exists with 4 tables and 7 indexes
2. `scripts/seed_d1.py` generates valid SQL from existing JSON data
3. `python -m pytest tests/cloudflare/test_seed_d1.py -v` passes 24+ tests
4. Local D1 has correct row counts matching source JSON
5. `docs/database/d1-schema.md` documents all tables, columns, and relationships
6. Re-running seed script is idempotent — no duplicate rows
