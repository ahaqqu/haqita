# Jakarta Supermarket Grocery Price Tracker — Technical Plan

## Project Overview

A consumer-facing web application to track and compare grocery prices across supermarkets in Jakarta. The current system is a local Python pipeline that produces static JSON + HTML files. This plan migrates the project to a Cloudflare-hosted architecture **incrementally**: keep the proven local pipeline, deploy the existing static HTML UI first, and add a Cloudflare-backed dynamic layer behind it. React and a full SPA rewrite are explicitly deferred.

**Current state:** local pipeline (`scrape → OCR → consolidate → publish-html`) writes to `database/` and `output/html/`.  
**Target state:** same local pipeline plus a new **Stage 5 (Cloudflare sync)** that pushes data to a Hono API backed by D1/R2. The existing `index.html` is deployed to Cloudflare Pages and consumes the API where dynamic features need it.

**Scope constraints for this plan:**
- Keep local JSON databases (`database/*.json`) unchanged.
- Static HTML UI first; React migration is a later phase.
- Target audience is **1–10 internal users**, not a public launch.
- Astro scraper plan and admin review queue are **out of scope**.
- Database contents are considered test data; a full pipeline rerun is acceptable instead of a JSON → D1 migration.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Laptop (local)                              │
│  ┌─────────┐   ┌─────────┐   ┌─────────────┐   ┌─────────────────────┐  │
│  │ Scrape  │──▶│  OCR    │──▶│ Consolidate │──▶│ Publish HTML        │  │
│  │ (Lotte, │   │ (Gemini)│   │ (7-gate     │   │ (output/html/*.json)│  │
│  │Superindo)│   │         │   │ matching)   │   └─────────────────────┘  │
│  └─────────┘   └─────────┘   └─────────────┘            │                │
│                                                         ▼                │
│                                               ┌─────────────────────┐    │
│                                               │ Stage 5: Sync to    │    │
│                                               │ Cloudflare          │    │
│                                               │ (scripts/sync_cf.py)│    │
│                                               └─────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ POST /api/v1/sync/* + image uploads
┌─────────────────────────────────────────────────────────────────────────┐
│                           Cloudflare (free tier)                         │
│                                                                          │
│  ┌─────────────────────┐        ┌─────────────────────┐                 │
│  │  Cloudflare Pages   │◄──────▶│  Cloudflare Workers │                 │
│  │  Static HTML UI     │        │  Hono API           │                 │
│  │  (index.html +      │        │                     │                 │
│  │   output/html/)     │        │                     │                 │
│  └─────────────────────┘        └──────────┬──────────┘                 │
│                                            │                            │
│                              ┌─────────────┴─────────────┐              │
│                              ▼                           ▼              │
│                     ┌─────────────────┐        ┌─────────────────┐      │
│                     │  Cloudflare D1  │        │  Cloudflare R2  │      │
│                     │  Prices, Stores,│        │  Product/brochure│      │
│                     │  Products, Promos│       │  images         │      │
│                     └─────────────────┘        └─────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **Frontend (Web)** | Existing static `index.html` + vanilla JS | Deployed to Cloudflare Pages first |
| **Future Frontend** | React + TypeScript | Phase 3 — only after static HTML is live and stable |
| **Backend API** | Hono (TypeScript) on Cloudflare Workers | REST API, sync receiver |
| **Database** | Cloudflare D1 (SQLite) | Product prices, stores, products, promo catalog |
| **Image Storage** | Cloudflare R2 | Product/brochure images (see options below) |
| **Auth** | Scraper-only secret; optional Cloudflare Access for Pages | Internal use, no user accounts |
| **Scraper** | Python (existing) | Runs weekly on laptop; new Stage 5 pushes to Cloudflare |
| **Local pipeline DB** | JSON files (`database/*.json`) | Unchanged; remains the local source of truth |

---

## Local Pipeline (Unchanged)

The existing pipeline continues to work exactly as today:

1. **Stage 1 — Scrape**: downloads brochure images → `database/scrape/<store>/<YYYYMMDD>/`
2. **Stage 2 — OCR**: extracts products with Gemini → `database/ocr/<store>/`
3. **Stage 3 — Consolidate**: matches products, writes `database/price_history.json`, `database/product_catalog.json`, `database/review_queue.json`
4. **Stage 4 — Publish HTML**: generates `output/html/active_promo.json`, `price_history.json`, `promo_catalog.json`, `review_queue.json`

### New: Stage 5 — Cloudflare Sync

Add `scripts/sync_cloudflare.py` that pushes the latest consolidated data to Cloudflare **without modifying local files**.

Responsibilities:
- Read `output/html/active_promo.json` and `database/price_history.json`.
- Upsert stores, products, prices, and promo catalog into D1 via Hono API.
- Upload new/updated brochure images to R2 (depending on chosen image option).
- Emit a sync report (counts inserted/updated/skipped, errors).

Behavior:
- Idempotent: re-running Stage 5 must not duplicate prices or products.
- Dry-run mode: preview what would be synced.
- Resume-friendly: track uploaded image hashes / synced snapshot IDs locally in `database/sync_state.json`.
- Failure handling: local files are never modified; API/R2 failures are logged and do not break the pipeline.

Trigger options:
- Manual: `python scripts/sync_cloudflare.py`
- Menu item in `haqita.sh` / `haqita.bat`
- Optional: run automatically after Stage 4 when `--sync` flag is passed

---

## API Design (Versioned REST)

The API must support the same features the current static UI already exposes.

### Public read endpoints

```
GET    /api/v1/products              # List products
GET    /api/v1/products/:key         # Product detail
GET    /api/v1/products/:key/history # Price history for product
GET    /api/v1/prices                # Latest prices (filter by product_key, store)
GET    /api/v1/stores                # List stores
GET    /api/v1/categories            # List categories
GET    /api/v1/search?q=:query       # Search products by name/brand/unit
GET    /api/v1/promos                # Promo catalog (grouped, with counts)
GET    /api/v1/brochures             # Brochure gallery metadata
GET    /api/v1/stats                 # Summary stats (matched, lotte-only, etc.)
```

### Query parameters

- `GET /api/v1/products`
  - `limit` (default 20, max 100)
  - `cursor` (base64 offset for pagination)
  - `store` (filter by store name)
  - `category` (filter by category)
  - `has_promo` (boolean)
  - `sort` (`name`, `cheapest`, `savings`, `expiry`)

- `GET /api/v1/products/:key/history`
  - `from`, `to` ISO date range
  - `store` (optional)

- `GET /api/v1/search`
  - `q` (required)
  - `limit` (default 20, max 50)

### Protected write endpoints

```
POST   /api/v1/sync/batch            # Stage 5 pushes product/price/promo batch
POST   /api/v1/sync/images          # Stage 5 registers or uploads images
```

#### `POST /api/v1/sync/batch`

Request body:
```json
{
  "source": "haqita-pipeline-v1",
  "sync_run_id": "20260621_120000",
  "stores": [
    { "name": "Lotte", "color": "#0057A8" },
    { "name": "Superindo", "color": "#E8211D" }
  ],
  "products": [
    {
      "key": "indomie-goreng--indomie--85g",
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "category": "Mie Instan",
      "unit_type": "weight",
      "unit_value_g": 85
    }
  ],
  "prices": [
    {
      "product_key": "indomie-goreng--indomie--85g",
      "store": "Lotte",
      "price": 15500,
      "effective_unit_price": 3100,
      "bundle_size": 5,
      "promo": ["DAPAT 5 pcs"],
      "promo_type": "bundle_buy",
      "valid_from": null,
      "valid_until": "2026-06-20",
      "image_path": "database/scrape/lotte/20260620/promo_abc.jpg",
      "scrape_time": "2026-06-20T09:00:00",
      "date": "2026-06-20",
      "match_method": "exact",
      "match_confidence": 1.0,
      "standardized_promo": { "best_type": "bundle", "display_summary": "Dapat 5 pcs" }
    }
  ],
  "promos": [
    {
      "key": "dapat-5-pcs",
      "display": "Dapat 5 pcs",
      "type": "bundle",
      "product_count": 12,
      "stores": {"Lotte": 12},
      "example_products": ["Indomie Goreng", "Mie Sedap"]
    }
  ]
}
```

Idempotency rule: a price is uniquely identified by `(product_key, store, date)`. On duplicate, update in place.

#### `POST /api/v1/sync/images`

Two possible designs (choose in Stage 5 implementation):

**Option A — manifest-only:**
```json
{
  "images": [
    { "local_path": "database/scrape/lotte/20260620/promo_abc.jpg", "r2_key": "lotte/20260620/promo_abc.jpg" }
  ]
}
```
The actual upload happens directly from the laptop to R2; the API just records the public URL.

**Option B — direct upload through Hono:**
```json
{
  "images": [
    { "r2_key": "lotte/20260620/promo_abc.jpg", "base64": "..." }
  ]
}
```
Simpler credentials, but Workers request body limits (100 MB on paid, 1 MB on free) make this risky for large brochures. **Not recommended.**

---

## Database Schema (D1 — SQLite)

The schema must preserve the fields the current UI and pipeline already depend on.

```sql
-- Stores (supermarkets)
CREATE TABLE stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Products
CREATE TABLE products (
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
CREATE TABLE prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_key TEXT NOT NULL,
    store TEXT NOT NULL,
    price INTEGER NOT NULL,
    effective_unit_price INTEGER NOT NULL,
    bundle_size INTEGER DEFAULT 1,
    promo TEXT,                       -- JSON array of promo strings
    promo_type TEXT,
    valid_from TEXT,
    valid_until TEXT,
    image_path TEXT,
    image_r2_url TEXT,
    scrape_time TEXT,
    date TEXT NOT NULL,
    match_method TEXT,
    match_confidence REAL,
    standardized_promo TEXT,          -- JSON object
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_key, store, date),
    FOREIGN KEY (product_key) REFERENCES products(key)
);

-- Promo catalog (derived from latest run)
CREATE TABLE promos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    display TEXT NOT NULL,
    type TEXT,
    discount_pct INTEGER,
    max_qty INTEGER,
    product_count INTEGER DEFAULT 0,
    stores TEXT,                      -- JSON object {store: count}
    example_products TEXT,            -- JSON array
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_prices_product ON prices(product_key);
CREATE INDEX idx_prices_store ON prices(store);
CREATE INDEX idx_prices_date ON prices(date);
CREATE INDEX idx_prices_valid_until ON prices(valid_until);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_promos_type ON promos(type);
```

Notes:
- `image_path` stores the original local path for traceability.
- `image_r2_url` stores the public R2 URL after upload.
- `standardized_promo` is stored as JSON because its shape is stable and already validated by `promo_parser.py`.

---

## Data Flow

### Consumer → Data
```
Browser
  │
  ▼ GET /api/v1/products, /api/v1/promos, /api/v1/brochures, /api/v1/stats
Hono API (Cloudflare Workers)
  │
  ▼ SQL SELECT
Cloudflare D1
  │
  ▼ JSON Response
index.html renders cards, promos, brochures
```

### Scraper → Cloudflare (Weekly)
```
Python pipeline (Stages 1–4) → output/html/*.json + database/*.json
  │
  ▼ Stage 5: scripts/sync_cloudflare.py
  │   Authorization: Bearer <SCRAPER_SECRET>
  ▼
Hono API
  │
  ├─► SQL INSERT / UPDATE ──► D1
  └─► image upload manifest ──► R2
```

### Static HTML deployment
```
output/html/*  ──┐
index.html     ──┼──► Cloudflare Pages deploy
other assets   ──┘
```

The static HTML can be deployed either:
- as a **pure static site** that loads JSON from the Hono API, or
- as a **hybrid** where Pages also serves the latest `active_promo.json` fallback if the API is down.

---

## Image Handling: Option A (Chosen)

The current pipeline stores brochure images locally at `database/scrape/<store>/<YYYYMMDD>/<file>`. For a hosted UI, these images must become reachable URLs.

**Decision: use Option A — upload to R2 from the laptop.**

**How it works:**
- Stage 5 computes the MD5 of each image referenced by the latest prices.
- New/changed images are uploaded directly from the laptop to R2 using the S3-compatible API (`boto3` or `rclone`).
- Stage 5 sends the R2 public URL to `POST /api/v1/sync/images` so D1 can store it in `prices.image_r2_url`.
- `index.html` uses `image_r2_url` for brochure links and thumbnails.

**Why Option A over the others:**
- It keeps image storage separate from the Pages deployment, so static deploys stay small and fast.
- It scales cleanly if the project ever becomes public.
- It avoids the complexity of a hybrid fallback and the bloat of copying images into Pages on every deploy.

**Implementation note:** `scripts/sync_cloudflare.py` should record uploaded image keys/hashes in `database/sync_state.json` so only changed images are re-uploaded on subsequent runs.

---

## Security

Threat model: internal tool, 1–10 users, scraper runs from a trusted laptop. No public user accounts. Admin/review queue is out of scope.

| Layer | Implementation |
|-------|---------------|
| **Scraper Auth** | `SCRAPER_SECRET` env var, passed as `Authorization: Bearer <token>` in Stage 5. Hono middleware rejects missing/invalid tokens with 401. |
| **Consumer Access** | Public read endpoints; no authentication required for browsing prices. |
| **Pages Access (optional)** | Restrict Cloudflare Pages to internal users via Cloudflare Access (zero-trust) if the site should not be discoverable publicly. |
| **API Rate Limiting** | Cloudflare WAF rule: limit `POST /api/v1/sync/*` to a small number of requests per minute from the laptop's public IP range. General read endpoints get a higher, reasonable limit. |
| **CORS** | Not needed in Phase 1 because UI and API share the same origin (`https://haqita.pages.dev`). If the API is later split to a separate Worker, restrict `Access-Control-Allow-Origin` to the Pages domain. |
| **Input Validation** | Hono validates `sync/batch` body with Zod: required fields, price ranges, valid date strings, enum checks for `promo_type` and `match_method`. |
| **Secret Rotation** | `SCRAPER_SECRET` stored in Cloudflare Workers secrets (`wrangler secret put`) and in the laptop's `.env`. Document rotation procedure. |
| **SQL Injection** | Use D1 parameterized queries only; never concatenate user input into SQL. |
| **Image Upload** | If Option A is used, R2 bucket policy should allow public read but restrict writes to the sync credentials. Do not accept image uploads from public users. |

**Out of scope:** user accounts, OAuth, admin auth, review-queue permissions.

---

## Cost Estimate (1–10 internal users)

| Component | Free Tier | Likely Usage | Cost |
|-----------|-----------|--------------|------|
| Cloudflare Pages | Unlimited requests, 500 builds/mo | Static site for internal users | **$0** |
| Cloudflare Workers | 100,000 requests/day | ~500–2,000/day (1–10 users) | **$0** |
| Cloudflare D1 | 5M reads, 100K writes/day | Tiny internal usage | **$0** |
| Cloudflare R2 | 10 GB storage, 10M reads/mo | Brochure images if Option A | **$0** |
| Cloudflare Access (optional) | 50 users free | Internal access policy | **$0** |
| **Total** | | | **$0/month** |

Assumptions:
- Each user loads the site 1–3 times/day.
- Stage 5 runs once per week and makes < 100 API calls.
- Images are cached by Cloudflare; most views hit cache.
- No large-scale scraping or public sharing.

If usage grows to 1,000 users, revisit caching and the D1/Workers free-tier limits.

---

## Development Phases

### Phase 1: Static HTML + API Backend (MVP)
- [ ] Set up Cloudflare project: Pages, Workers, D1, R2.
- [ ] Create D1 schema and seed with sample data from a pipeline run.
- [ ] Build Hono API with all public read endpoints.
- [ ] Build protected `POST /api/v1/sync/batch` and `/api/v1/sync/images` endpoints.
- [ ] Build `scripts/sync_cloudflare.py` Stage 5 and wire it into `haqita.sh` / `haqita.bat`.
- [ ] Deploy existing `index.html` + `output/html/` to Cloudflare Pages.
- [ ] Update `index.html` to consume the API for dynamic data where beneficial, while keeping static JSON fallback.
- [ ] Add security middleware and rate limiting.
- [ ] Verify end-to-end: run pipeline → sync → browse deployed site.

### Phase 2: Dynamic features & polish
- [ ] Server-side search with pagination.
- [ ] Server-side price history for charts.
- [ ] Promo and brochure endpoints consumed by the existing Promos/Brochures tabs.
- [ ] Image handling Option A fully implemented (R2 upload from laptop).
- [ ] Add Web Analytics (free) to understand internal usage.

### Phase 3: React migration (deferred)
- [ ] Build React + TypeScript SPA on Cloudflare Pages.
- [ ] Reuse Hono API and D1 schema.
- [ ] Reimplement all current UI features: search, filter, sort, tabs, expandable cards, price charts.
- [ ] Deprecate or redirect static `index.html`.

### Phase 4: Scale / public launch (future)
- [ ] Add more stores to scraper.
- [ ] Implement caching layer (KV or Cache API) for popular queries.
- [ ] Add user-facing features only if needed (favorites, alerts, etc.).

---

## Testing Strategy

### Unit tests
- `tests/sync/test_sync_cloudflare.py`: validate request building, idempotency key generation, image URL rewriting.
- `tests/api/test_validation.py`: Zod schemas for `sync/batch` body.

### API contract tests
- Run Hono API locally via `wrangler dev` with a local D1 database.
- Test each endpoint against a known fixture dataset.
- Verify pagination cursors and search ranking.

### Integration tests
- End-to-end: run full local pipeline → run Stage 5 sync → query API → assert counts match `active_promo.json`.
- Image upload test (dry-run mode): verify manifest is correct without uploading.

### Static UI tests
- Serve `index.html` locally with `python -m http.server` pointing at local API.
- Manual check: Products tab, Promos tab, Brochures tab, search, sort, expandable cards, price charts.

### Pre-deployment checklist
- [ ] `wrangler deploy` to staging Pages/Workers.
- [ ] Run Stage 5 against staging.
- [ ] Verify all endpoints return expected JSON.
- [ ] Verify images load correctly.
- [ ] Check security headers and CORS.

---

## Local Development Guide

### Prerequisites
- Node.js 20+ and npm/pnpm
- Python 3.12+ (for the local pipeline)
- Cloudflare account
- Wrangler CLI: `npm install -g wrangler`
- Gemini API key in `.env`

### Repository layout (target)
```
haqita/
├── index.html                # Existing static UI — stays at repo root
├── scripts/                  # Existing Python pipeline
│   ├── sync_cloudflare.py    # NEW: Stage 5
│   └── ...
├── web/                      # NEW: Cloudflare Pages project
│   ├── public/               # Populated at deploy time from repo root / output/html
│   │   ├── index.html        # copied from repo root
│   │   ├── active_promo.json # copied from output/html/
│   │   ├── price_history.json
│   │   └── ...
│   ├── functions/            # Hono API as Cloudflare Pages Functions
│   │   └── api/[[route]].ts
│   ├── wrangler.toml
│   └── package.json
├── database/                 # Existing local JSON DB (unchanged)
├── output/html/              # Existing static output (unchanged)
├── tests/                    # Existing + new tests
└── plan.md
```

**Why keep `index.html` at the repo root?**
- The current local development workflow (`python -m http.server 8080` serving `index.html`) keeps working without path changes.
- `haqita.sh` / `haqita.bat` menus and the existing static-file fallback logic are unaffected.
- The Cloudflare Pages deploy step simply copies `index.html` and `output/html/*.json` into `web/public/` before running `wrangler pages deploy`.

**Why Hono as Pages Functions instead of a separate Worker?**
- One project, one deploy command, one domain. API routes are served from the same origin as the UI (`https://haqita.pages.dev/api/v1/...`).
- No CORS complexity because UI and API share the same origin.
- Easier to maintain for a single internal app. If the API needs to be reused by a mobile app or external client later, it can be extracted into a standalone Worker with minimal changes.

### Local D1
```bash
# Create local D1 database
wrangler d1 create haqita-local

# Apply schema
wrangler d1 execute haqita-local --local --file=./web/schema.sql

# Seed with fixture data
wrangler d1 execute haqita-local --local --file=./web/seed.sql
```

### Local API
```bash
cd web
npm install
wrangler dev --local
```
API will be available at `http://localhost:8787`.

### Local static UI with API
```bash
# Terminal 1: run API
wrangler dev --local

# Terminal 2: serve static files
python -m http.server 8080
```
Open `http://localhost:8080` and configure the UI to call `http://localhost:8787/api/v1/...`.

### Running Stage 5 locally
```bash
# Dry-run preview
python scripts/sync_cloudflare.py --dry-run

# Actual sync to local/staging API
python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1
```

### Environment variables
Create `.env` in project root (do not commit):
```env
GEMINI_API_KEY=...
SCRAPER_SECRET=...            # shared between laptop and Cloudflare
CLOUDFLARE_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...          # if using Option A
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
```

On Cloudflare, set `SCRAPER_SECRET` via:
```bash
wrangler secret put SCRAPER_SECRET
```

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **Static HTML first** | Existing `index.html` already has search, tabs, charts, and filters. Deploying it avoids a rewrite and lets us validate the backend early. |
| **Keep local JSON DB** | The pipeline is proven; adding a sync stage is lower risk than replacing the storage layer. Local files remain the source of truth. |
| **D1 normalized schema** | Supports server-side pagination, search, and history queries that the static JSON files cannot do efficiently. |
| **React deferred to Phase 3** | Avoids a large frontend rewrite before the API and data flow are validated. |
| **1–10 internal users** | Simplifies security and cost; free tier is more than sufficient. |
| **Astro / admin out of scope** | Astro plan is outdated; admin review queue is unfinished. Revisit after core architecture is stable. |
| **Pages Functions, same origin** | Hono API lives in `web/functions/` and serves from the same domain as the UI. Avoids CORS and keeps deploy simple. |

---

## Migration Safety

| Component | Lock-in Risk | Mitigation |
|-----------|-------------|------------|
| Hono API | Low | Standard REST, portable to Express/Fastify/any Node framework. |
| D1 (SQLite) | Low | Standard SQL; local pipeline JSON files remain the source of truth. |
| R2 (S3-compatible) | None | Standard S3 API; swap to AWS S3/MinIO/Backblaze instantly. |
| Static HTML frontend | None | Standard HTML/CSS/JS; can be replaced by React later. |

---

## Assumptions

- 1–10 internal users browse prices; no user-generated content.
- Scraper runs weekly from a trusted laptop.
- Product catalog is managed by the pipeline, not by users.
- Images are required for brochure thumbnails but can be served via R2 or Pages.
- A full pipeline rerun is acceptable to populate D1; no JSON migration script is needed.

---

## Open Questions — Resolved

| # | Question | Decision |
|---|----------|----------|
| 1 | Image-handling option | **Option A** — direct R2 upload from laptop. |
| 2 | `index.html` location | **Keep at repo root**; copy into `web/public/` at deploy time. |
| 3 | Hono API deployment | **Pages Functions** (`web/functions/api/`), same origin as UI. |
| 4 | CORS origin | Not applicable in Phase 1 (same origin). Future default: `https://haqita.pages.dev`. |
| 5 | Internal-only access | **Model 1** — private URL + scraper secret; Cloudflare Access not used. |

---

## Internal-Only Access Options

"Internal-only access" means limiting who can view the site. Since the read API is intentionally public and there are no user accounts, there are three practical models:

### Model 1: Security through obscurity (default for this plan)
- Deploy Pages to a non-publicized `*.pages.dev` URL.
- Do not link it from public places.
- Protect the write path with `SCRAPER_SECRET`.
- **Pros:** zero setup, zero cost, fastest to implement.  
- **Cons:** anyone with the URL can view prices. For grocery prices this is acceptable.

### Model 2: Cloudflare Access (zero-trust login)
- Enable Cloudflare Access on the Pages domain.
- Add a policy allowing only specific email addresses or identity providers.
- Visitors see a login screen before the site loads.
- **Pros:** real access control; free for up to 50 users.  
- **Cons:** extra setup (identity provider or one-time PIN); adds friction for internal users; overkill for 1–10 people sharing a URL.

### Model 3: Simple password gate on Pages
- Add a small Cloudflare Worker or Pages Function in front of the HTML that checks a shared password cookie.
- **Pros:** no external identity provider needed.  
- **Cons:** not real security (token can be shared/leaked); extra code to maintain.

**Decision: use Model 1** for this plan. The site is deployed to a non-publicized `*.pages.dev` URL, read endpoints remain public, and the write path is protected by `SCRAPER_SECRET`. Revisit Model 2 only if the URL is accidentally shared publicly or if the project launches to a broader audience.

---

*Plan updated: 2026-06-21*
*Target: 1–10 internal users, $0/month hosting cost, static-HTML-first deployment*
