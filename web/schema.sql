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
