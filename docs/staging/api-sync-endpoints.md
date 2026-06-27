# API Sync Endpoints

## Overview

| Property | Value |
|----------|-------|
| Base URL | `/api/v1` |
| Auth | Bearer token (`SCRAPER_SECRET`) |
| Content-Type | `application/json` |
| Rate Limit | 10 req/min per IP (Phase 7 WAF rule) |

## Authentication

All sync endpoints require a Bearer token set via the `SCRAPER_SECRET` environment variable.

```bash
# Include in request header:
Authorization: Bearer <your-scraper-secret>
```

The secret is set in Cloudflare via:
```bash
cd web && npx wrangler pages secret put SCRAPER_SECRET --project-name haqita
```

For local development, set it in `web/.dev.vars`:
```
SCRAPER_SECRET=dev-secret-for-local-testing
```

## POST /api/v1/sync/batch

Upserts stores, products, prices, and promos in a single batch. Idempotent — re-sending the same batch does not create duplicates.

### Request Body Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | Yes | Source identifier (e.g., `haqita-pipeline-v1`) |
| `sync_run_id` | string | Yes | Unique sync run ID (e.g., `20260621_120000`) |
| `dummy_data` | boolean | No | `true` marks all rows in this batch as dummy data (default `false`) |
| `stores` | array | No | Array of store objects (default `[]`) |
| `products` | array | No | Array of product objects (default `[]`) |
| `prices` | array | No | Array of price objects (default `[]`) |
| `promos` | array | No | Array of promo objects (default `[]`) |

**Store object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Store name |
| `color` | string | No | Display color hex code |

**Product object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Canonical product key |
| `name` | string | Yes | Display name |
| `brand` | string (nullable) | No | Brand name |
| `category` | string (nullable) | No | Product category |
| `unit` | string | No | Unit display string |
| `unit_type` | string (nullable) | No | Unit type classification |
| `unit_value_g` | number (nullable) | No | Normalized unit value in grams |

**Price object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product_key` | string | Yes | References a product key |
| `store` | string | Yes | Store name |
| `price` | integer | Yes | Price in IDR (must be positive) |
| `effective_unit_price` | integer | Yes | Effective unit price in IDR |
| `bundle_size` | integer | No | Bundle size (default 1) |
| `promo` | array (nullable) | No | Array of promo strings, or null |
| `promo_type` | string (nullable) | No | Promo type |
| `valid_from` | string (nullable) | No | ISO date YYYY-MM-DD |
| `valid_until` | string (nullable) | No | ISO date YYYY-MM-DD |
| `image_path` | string (nullable) | No | Local image path |
| `scrape_time` | string | No | ISO datetime |
| `date` | string | Yes | ISO date YYYY-MM-DD |
| `match_method` | string (nullable) | No | Matching method |
| `match_confidence` | number (nullable) | No | Match confidence 0.0-1.0 |
| `standardized_promo` | object (nullable) | No | Standardized promo object |

**Promo object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Promo key |
| `display` | string | Yes | Display text |
| `type` | string (nullable) | No | Promo type |
| `discount_pct` | integer (nullable) | No | Discount percentage |
| `max_qty` | integer (nullable) | No | Maximum quantity |
| `product_count` | integer | No | Product count (default 0) |
| `stores` | object | No | Object mapping store names to counts |
| `example_products` | array | No | Array of example product names |

### Example Request

```bash
curl -X POST \
  -H "Authorization: Bearer dev-secret-for-local-testing" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "haqita-pipeline-v1",
    "sync_run_id": "20260621_120000",
    "stores": [{"name": "Lotte", "color": "#0057A8"}],
    "products": [
      {
        "key": "rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr",
        "name": "RinsO Detergen Bubuk Anti Noda",
        "brand": "Rinso",
        "unit": "1440 g",
        "unit_type": "weight",
        "unit_value_g": 1440.0
      }
    ],
    "prices": [
      {
        "product_key": "rinso-detergen-...",
        "store": "Lotte",
        "price": 24900,
        "effective_unit_price": 24900,
        "bundle_size": 1,
        "promo": ["DISKON 20%"],
        "scrape_time": "2026-06-21T09:00:00",
        "date": "2026-06-21"
      }
    ],
    "promos": []
  }' \
  http://localhost:8787/api/v1/sync/batch
```

### Example Response (200)

```json
{
  "sync_run_id": "20260621_120000",
  "stores": {"inserted": 0, "updated": 1, "skipped": 0},
  "products": {"inserted": 1, "updated": 0, "skipped": 0},
  "prices": {"inserted": 1, "updated": 0, "skipped": 0},
  "promos": {"inserted": 0, "updated": 0, "skipped": 0},
  "errors": []
}
```

### Error Responses

- `400` — Invalid JSON body or validation failure
- `401` — Missing or invalid Authorization header
- `207` — Partial success (some rows failed, errors in response)

### Idempotency

Re-sending the exact same batch produces the same result without creating duplicates. This is achieved via `INSERT OR REPLACE` with `UNIQUE` constraints:

- **stores**: `UNIQUE(name)`
- **products**: `UNIQUE(key)`
- **prices**: `UNIQUE(product_key, store, date)`
- **promos**: `UNIQUE(key)`

## POST /api/v1/sync/images

Records R2 URLs for uploaded images in the `prices.image_r2_url` column.

### Request Body Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `images` | array | Yes | Array of image objects (min 1) |

**Image object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `local_path` | string | Yes | Original local path (matches `prices.image_path`) |
| `r2_key` | string | Yes | R2 object key |
| `r2_url` | string (url) | No | Public R2 URL (derived from r2_key if not provided) |

### Example Request

```bash
curl -X POST \
  -H "Authorization: Bearer dev-secret-for-local-testing" \
  -H "Content-Type: application/json" \
  -d '{
    "images": [
      {
        "local_path": "database/scrape/superindo/20260613/promo.jpg",
        "r2_key": "superindo/20260613/promo.jpg",
        "r2_url": "https://pub-hash.r2.dev/superindo/20260613/promo.jpg"
      }
    ]
  }' \
  http://localhost:8787/api/v1/sync/images
```

### Example Response (200)

```json
{
  "updated": 45,
  "skipped": 0,
  "errors": []
}
```

### Error Responses

- `400` — Invalid JSON body or validation failure
- `401` — Missing or invalid Authorization header
- `207` — Partial success (some images failed)

## Sync Response Format

| Field | Type | Description |
|-------|------|-------------|
| `sync_run_id` | string | Matches the request |
| `stores` | object | Insert/update/skip counts |
| `products` | object | Insert/update/skip counts |
| `prices` | object | Insert/update/skip counts |
| `promos` | object | Insert/update/skip counts |
| `errors` | array | Array of error objects with `table`, `key`, `error` |

## Local Testing

```bash
# Start local dev server
cd web && npx wrangler pages dev --local

# Test auth
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8787/api/v1/sync/batch -d '{}'
# Expected: 401

# Test with valid auth
curl -s -X POST \
  -H "Authorization: Bearer dev-secret-for-local-testing" \
  -H "Content-Type: application/json" \
  -d '{"source":"test","sync_run_id":"t1","stores":[],"products":[],"prices":[],"promos":[]}' \
  http://localhost:8787/api/v1/sync/batch | python3 -m json.tool
```
