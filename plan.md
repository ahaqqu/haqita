# Jakarta Supermarket Grocery Price Tracker — Technical Plan

## Project Overview
A consumer-facing web application to track and compare grocery prices across supermarkets in Jakarta, targeting ~1,000 users. Built for zero hosting cost on Cloudflare's free tier.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Cloudflare    │     │   Cloudflare    │     │     Laptop      │
│     Pages       │◄────│    Workers      │◄────│  Python Scraper │
│  React (Web)    │     │  Hono (API)     │     │  (via Hono API) │
│ Consumer Facing │     │                 │     │  Runs Weekly    │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────┴────────┐
                        │   Cloudflare    │
                        │   D1 (SQLite)   │
                        │  Prices, Stores │
                        └─────────────────┘
                                 │
                        ┌────────┴────────┐
                        │   Cloudflare    │
                        │   R2 (Images)   │
                        │ Product Photos  │
                        └─────────────────┘
```

---

## Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **Frontend (Web)** | React + TypeScript | Consumer-facing price browser |
| **Backend API** | Hono (TypeScript) | REST API on Cloudflare Workers |
| **Database** | Cloudflare D1 (SQLite) | Product prices, stores, products |
| **Image Storage** | Cloudflare R2 | Product images, static assets |
| **Auth** | None required | Public access for all users |
| **Scraper** | Python (existing) | Runs weekly on laptop, pushes data via Hono API |
| **Future Mobile** | React Native | Long-term goal, separate phase |

---

## API Design (Versioned REST)

```
GET    /api/v1/products              # List all products
GET    /api/v1/products/:id          # Product detail
GET    /api/v1/prices?product=:id    # Price history for product
GET    /api/v1/stores                # List stores
GET    /api/v1/stores/:id/prices     # Prices at specific store
GET    /api/v1/categories            # List categories (Minyak, Beras, etc.)
GET    /api/v1/search?q=:query       # Search products by name
POST   /api/v1/sync-prices           # Scraper pushes batch data (protected by secret)
```

---

## Data Flow

### Scraper → Database (Weekly)
```
Python Scraper (Laptop)
    │
    │ Runs weekly (manual trigger or cron)
    ▼ POST /api/v1/sync-prices
    │   Authorization: Bearer <SCRAPER_SECRET>
    ▼
Hono API (Cloudflare Workers)
    │
    ▼ SQL INSERT / UPDATE
Cloudflare D1 (SQLite)
```

### Consumer → Data
```
Browser (Consumer)
    │
    ▼ GET /api/v1/products
    ▼ GET /api/v1/prices
    ▼ GET /api/v1/stores
    ▼ ...
Hono API (Cloudflare Workers)
    │
    ▼ SQL SELECT
Cloudflare D1 (SQLite)
    │
    ▼ JSON Response
Consumer sees prices
```

---

## Database Schema (D1 — SQLite)

```sql
-- Stores (supermarkets)
CREATE TABLE stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- "Superindo", "Giant", "Hero", etc.
    location TEXT,                -- "Jakarta Selatan", "Jakarta Barat", etc.
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Products
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- "Minyak Goreng Bimoli 2L"
    category TEXT,                -- "Minyak", "Beras", "Gula", "Susu", etc.
    unit TEXT,                    -- "2L", "1kg", "500gr", "1 pack"
    image_key TEXT,               -- R2 object key for product image
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Prices (core data)
CREATE TABLE prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    price INTEGER NOT NULL,       -- in IDR, store as integer (e.g., 15000)
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

-- Indexes for performance
CREATE INDEX idx_prices_product ON prices(product_id);
CREATE INDEX idx_prices_store ON prices(store_id);
CREATE INDEX idx_prices_recorded ON prices(recorded_at);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_name ON products(name);
```

---

## Security

| Layer | Implementation |
|-------|---------------|
| **Scraper Auth** | Bearer token (`SCRAPER_SECRET` env var), checked in Hono middleware. Only the scraper can write data. |
| **Consumer Access** | Public — no authentication required. Anyone can browse prices. |
| **API Rate Limiting** | Cloudflare built-in rate limiting to prevent abuse |
| **CORS** | Restrict to known origins (your domain) |
| **Input Sanitization** | Hono validates all scraper input before database insert |

---

## Scraper Specification

| Detail | Value |
|--------|-------|
| **Location** | Your laptop |
| **Frequency** | Weekly |
| **Trigger** | Manual or local cron job |
| **Data target** | Hono API endpoint (`POST /api/v1/sync-prices`) |
| **Auth** | Bearer token in header |
| **Payload** | Batch of price records |

```python
# Example scraper output format
{
  "prices": [
    {"product_id": 1, "store_id": 3, "price": 15000},
    {"product_id": 2, "store_id": 3, "price": 22000},
    ...
  ]
}
```

---

## Cost Estimate

| Component | Free Tier | Likely Usage | Cost |
|-----------|-----------|--------------|------|
| Cloudflare Pages | Unlimited requests, 500 builds/mo | Static site for 1,000 users | **$0** |
| Cloudflare Workers | 100,000 requests/day | ~10-30K/day (1,000 users) | **$0** |
| Cloudflare D1 | 5M reads, 100K writes/day | Price queries, weekly writes | **$0** |
| Cloudflare R2 | 10 GB storage, 10M reads/mo | Product images | **$0** |
| **Total** | | | **$0/month** |

---

## Development Phases

### Phase 1: MVP — Consumer Web App
- [ ] Set up Cloudflare project (Pages + Workers + D1 + R2)
- [ ] Create D1 schema and seed with initial store/product data
- [ ] Build Hono API with public read endpoints
- [ ] Build protected `POST /api/v1/sync-prices` endpoint for scraper
- [ ] Build React frontend — consumer price browser
  - Product listing with filters (category, store)
  - Price comparison table
  - Price history chart
  - Search functionality
- [ ] Connect Python scraper to Hono API
- [ ] Deploy and test with sample data

### Phase 2: Polish & Content
- [ ] Add product images (upload to R2)
- [ ] Improve UI/UX (responsive design, loading states)
- [ ] Add more supermarkets to scraper
- [ ] SEO optimization for Jakarta grocery keywords
- [ ] Analytics (Cloudflare Web Analytics — free)

### Phase 3: Mobile App (Long-term, separate phase)
- [ ] React Native app
- [ ] Reuse API client + types from web project
- [ ] Rewrite UI components for mobile
- [ ] Publish to App Store / Play Store

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **Cloudflare over Vercel/Netlify** | Unlimited bandwidth, no egress fees, D1/R2 native integration |
| **Hono over raw Workers** | Express-like syntax, portable to other platforms, TypeScript-first |
| **D1 over external Postgres** | Free tier sufficient, zero config, edge-replicated, standard SQL |
| **React over Flutter** | Larger ecosystem, easier hiring, shared language with Hono (TypeScript) |
| **No user auth** | Public price browser — consumers just view data, no login friction |
| **Laptop scraper, weekly** | Zero cost, sufficient for price tracking (prices don't change daily), easy to automate later |
| **Mobile as separate phase** | Focus on web MVP first, mobile is long-term goal with shared API |

---

## Migration Safety

| Component | Lock-in Risk | Mitigation |
|-----------|-------------|------------|
| Hono API | Low | Standard REST, portable to Express/Fastify/any Node framework |
| D1 (SQLite) | Low | Standard SQL, dump to file, import to Postgres/SQLite easily |
| R2 (S3-compatible) | None | Standard S3 API, swap to AWS S3/MinIO/Backblaze instantly |
| React frontend | None | Standard React, deploy anywhere |

---

## Assumptions

- 1,000 users browse prices but do not submit data (read-only public app)
- Scraper runs weekly and pushes all current prices (full refresh or incremental)
- Product catalog is managed by you (seeded manually, not user-generated)
- Images are optional for MVP (can be added in Phase 2)

---

*Plan created: 2026-06-20*
*Target: 1,000 users, $0/month hosting cost, consumer-facing public price browser*
