# D1 Database Schema

## Overview

| Property | Value |
|----------|-------|
| Database name | `haqita-db` |
| Binding name | `DB` |
| Location | Local (via `wrangler d1 execute --local`) / Cloudflare (production) |
| Schema file | `web/schema.sql` |
| Seed script | `scripts/seed_d1.py` |
| Schema version | 1.0 |

## Tables

### stores

Stores (supermarkets) with display colors.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `id` | INTEGER | NO | Auto-incrementing primary key | 1 |
| `name` | TEXT | NO | Store name (unique) | `Lotte` |
| `color` | TEXT | YES | Display color hex code | `#0057A8` |
| `created_at` | DATETIME | YES | Row creation timestamp | `2026-06-21 12:00:00` |

**Constraints:**
- `UNIQUE(name)` — no duplicate store names

### products

Product catalog entries.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `id` | INTEGER | NO | Auto-incrementing primary key | 1 |
| `key` | TEXT | NO | Canonical product key (unique) | `rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr` |
| `name` | TEXT | NO | Display name | `RinsO Detergen Bubuk Anti Noda` |
| `brand` | TEXT | YES | Brand name | `Rinso` |
| `category` | TEXT | YES | Product category | `Detergen` |
| `unit` | TEXT | YES | Unit display string | `1440 g` |
| `unit_type` | TEXT | YES | Unit type classification | `weight`, `volume`, `unit` |
| `unit_value_g` | REAL | YES | Normalized unit value in grams | `1440.0` |
| `created_at` | DATETIME | YES | Row creation timestamp | `2026-06-21 12:00:00` |

**Constraints:**
- `UNIQUE(key)` — no duplicate product keys

### prices

Core price data — append-only with upsert by unique key. Each row represents a single product at a specific store on a specific date.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `id` | INTEGER | NO | Auto-incrementing primary key | 1 |
| `product_key` | TEXT | NO | References `products.key)` | `rinso-detergen-...` |
| `store` | TEXT | NO | Store name | `Superindo` |
| `price` | INTEGER | NO | Price in IDR | `24900` |
| `effective_unit_price` | INTEGER | NO | Effective unit price in IDR | `24900` |
| `bundle_size` | INTEGER | YES | Bundle size (default 1) | `1` |
| `promo` | TEXT | YES | JSON array of promo strings | `["DISKON 20%", "maks. 4 pck"]` |
| `promo_type` | TEXT | YES | Promo type classification | `discount`, `bundle` |
| `valid_from` | TEXT | YES | Promo validity start (ISO date) | `2026-06-01` |
| `valid_until` | TEXT | YES | Promo validity end (ISO date), NULL = always active | `2026-06-30` |
| `image_path` | TEXT | YES | Original local image path | `database/scrape/superindo/20260613/abc.jpg` |
| `image_r2_url` | TEXT | YES | Public R2 URL after upload | `https://pub-hash.r2.dev/superindo/20260613/abc.jpg` |
| `scrape_time` | TEXT | YES | ISO datetime of scrape | `2026-06-13T10:30:00` |
| `date` | TEXT | NO | ISO date of price snapshot | `2026-06-13` |
| `match_method` | TEXT | YES | Matching method | `exact`, `embedding`, `ai` |
| `match_confidence` | REAL | YES | Match confidence (0.0-1.0) | `0.95` |
| `standardized_promo` | TEXT | YES | JSON object with standardized promo fields | See below |
| `created_at` | DATETIME | YES | Row creation timestamp | `2026-06-21 12:00:00` |

**Constraints:**
- `UNIQUE(product_key, store, date)` — idempotency: re-syncing the same date updates in place
- `FOREIGN KEY (product_key) REFERENCES products(key)` — referential integrity

### promos

Promo catalog — derived from the latest pipeline run.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `id` | INTEGER | NO | Auto-incrementing primary key | 1 |
| `key` | TEXT | NO | Promo key (unique) | `diskon-20-persen` |
| `display` | TEXT | NO | Display text | `DISKON 20%` |
| `type` | TEXT | YES | Promo type | `discount`, `bundle` |
| `discount_pct` | INTEGER | YES | Discount percentage | `20` |
| `max_qty` | INTEGER | YES | Maximum quantity | `4` |
| `product_count` | INTEGER | YES | Number of products with this promo | `64` |
| `stores` | TEXT | YES | JSON object mapping store to count | `{"Superindo": 64}` |
| `example_products` | TEXT | YES | JSON array of example product names | `["Rinso", "Bango"]` |
| `updated_at` | DATETIME | YES | Row update timestamp | `2026-06-21 12:00:00` |

**Constraints:**
- `UNIQUE(key)` — no duplicate promo keys

## Indexes

| Index name | Table | Columns | Purpose |
|-----------|-------|---------|---------|
| `idx_prices_product` | prices | `product_key` | Fast product price lookups |
| `idx_prices_store` | prices | `store` | Filter prices by store |
| `idx_prices_date` | prices | `date` | Date range queries |
| `idx_prices_valid_until` | prices | `valid_until` | Promo expiry filtering |
| `idx_products_category` | products | `category` | Category filtering |
| `idx_products_name` | products | `name` | Name-based search/sorting |
| `idx_promos_type` | promos | `type` | Promo type filtering |

## JSON-encoded Columns

SQLite (and by extension D1) has no native JSON column type. The following columns store JSON data as TEXT:

| Table | Column | JSON type | Example value |
|-------|--------|-----------|---------------|
| prices | `promo` | Array of strings | `["DISKON 20%", "maks. 4 pck"]` |
| prices | `standardized_promo` | Object | `{"normalized": ["DISKON 20%"], "types": ["discount"], "best_type": "discount", "discount_pct": 20, "max_qty": 4, "display_summary": "DISKON 20%"}` |
| promos | `stores` | Object | `{"Superindo": 64, "Lotte": 12}` |
| promos | `example_products` | Array of strings | `["Rinso", "Bango"]` |

## Idempotency

All `INSERT OR REPLACE` statements ensure re-running the seed script does not create duplicate rows:

- **stores**: `UNIQUE(name)` — re-inserting the same store name replaces the existing row
- **products**: `UNIQUE(key)` — re-inserting the same product key replaces the existing row
- **prices**: `UNIQUE(product_key, store, date)` — re-syncing the same date for the same product/store replaces the existing row
- **promos**: `UNIQUE(key)` — re-inserting the same promo key replaces the existing row

## Relationship to JSON Files

| D1 Table | Source JSON File | Key Mapping |
|----------|-----------------|-------------|
| stores | Extracted from `database/price_history.json` snapshots + `output/html/active_promo.json` `display_hints.store_colors` | Unique store names → store rows with colors |
| products | `database/product_catalog.json` `catalog` entries | `canonical_key` → `key`, `display_name` → `name` |
| prices | `database/price_history.json` `snapshots` | All snapshot fields mapped to price columns |
| promos | `output/html/promo_catalog.json` | `key` → `key`, `display` → `display` |

## Usage

### Apply schema to local D1

```bash
wrangler d1 execute haqita-db --local --file=./web/schema.sql
```

### Seed local D1

```bash
python scripts/seed_d1.py --apply --verbose
```

### Verify schema

```bash
# List tables
wrangler d1 execute haqita-db --local --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"

# Row counts
wrangler d1 execute haqita-db --local --command "SELECT 'stores' as tbl, COUNT(*) as cnt FROM stores UNION ALL SELECT 'products', COUNT(*) FROM products UNION ALL SELECT 'prices', COUNT(*) FROM prices UNION ALL SELECT 'promos', COUNT(*) FROM promos"

# Data integrity (no orphan prices)
wrangler d1 execute haqita-db --local --command "SELECT COUNT(*) FROM prices p WHERE NOT EXISTS (SELECT 1 FROM products WHERE key = p.product_key)"
```

### Reset local D1

```bash
wrangler d1 execute haqita-db --local --command "DROP TABLE IF EXISTS prices; DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS promos; DROP TABLE IF EXISTS stores;"
wrangler d1 execute haqita-db --local --file=./web/schema.sql
python scripts/seed_d1.py --apply
```
