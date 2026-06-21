# API Read Endpoints

## Overview

| Property | Value |
|----------|-------|
| Base URL | `/api/v1` |
| Version | 1.0 |
| Auth | None (public read endpoints) |
| Content-Type | `application/json` |
| Rate Limit | 100 req/min per IP (Phase 7 WAF rule) |

## Endpoints

### GET /api/v1/stores

Returns all stores.

**Query Parameters:** None

**Example Request:**
```bash
curl http://localhost:8787/api/v1/stores
```

**Example Response:**
```json
{
  "data": [
    {"name": "Lotte", "color": "#0057A8"},
    {"name": "Superindo", "color": "#E8211D"}
  ]
}
```

**Error Responses:** None (returns empty array if no stores).

---

### GET /api/v1/categories

Returns all product categories.

**Query Parameters:** None

**Example Request:**
```bash
curl http://localhost:8787/api/v1/categories
```

**Example Response:**
```json
{
  "data": []
}
```

**Note:** Categories are empty until populated by the sync API.

---

### GET /api/v1/products

Returns paginated products with filtering and sorting.

**Query Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Max results (1-100) |
| `cursor` | string | No | — | Base64-encoded pagination cursor |
| `store` | string | No | — | Filter by store name |
| `category` | string | No | — | Filter by category |
| `has_promo` | enum | No | — | `true` or `false` |
| `sort` | enum | No | `name` | `name`, `cheapest`, `savings`, `expiry` |

**Example Request:**
```bash
curl "http://localhost:8787/api/v1/products?limit=5&sort=cheapest"
```

**Example Response:**
```json
{
  "data": [
    {
      "key": "rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr",
      "name": "RinsO Detergen Bubuk Anti Noda",
      "brand": "Rinso",
      "unit": "1440 g",
      "unit_type": "weight",
      "unit_value_g": 1440.0,
      "stores": [
        {
          "store": "Lotte",
          "price": 24900,
          "effective_unit_price": 24900,
          "bundle_size": 1,
          "promo": ["DISKON 20%", "maks. 4 pck"],
          "promo_type": "discount",
          "valid_from": "2026-06-01",
          "valid_until": "2026-06-30",
          "image_path": "database/scrape/superindo/20260613/abc.jpg",
          "image_r2_url": null,
          "standardized_promo": {
            "normalized": ["DISKON 20%"],
            "types": ["discount"],
            "best_type": "discount",
            "discount_pct": 20,
            "max_qty": 4,
            "display_summary": "DISKON 20%"
          }
        }
      ],
      "price_min": 24900,
      "price_max": 29900,
      "cheapest_store": "Lotte",
      "price_gap": 5000,
      "has_promo": true,
      "valid_until": "2026-06-30"
    }
  ],
  "pagination": {
    "limit": 5,
    "cursor": "eyJvZmZzZXQiOjV9",
    "has_more": true
  }
}
```

**Error Responses:**
- `400` — Invalid query parameters (e.g., `limit=0`, `sort=invalid`)
- `500` — Internal server error

---

### GET /api/v1/products/:key

Returns a single product with all store prices.

**Query Parameters:** None

**Example Request:**
```bash
curl "http://localhost:8787/api/v1/products/rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr"
```

**Example Response:** Same shape as a single product in the products list (with `stores` array).

**Error Responses:**
- `404` — Product not found
- `500` — Internal server error

---

### GET /api/v1/products/:key/history

Returns price history for a product.

**Query Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `from` | date (YYYY-MM-DD) | No | Start date |
| `to` | date (YYYY-MM-DD) | No | End date |
| `store` | string | No | Filter by store |

**Example Request:**
```bash
curl "http://localhost:8787/api/v1/products/rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr/history?from=2026-06-01&to=2026-06-30"
```

**Example Response:**
```json
{
  "product_key": "rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr",
  "snapshots": [
    {
      "product_key": "rinso-detergen-...",
      "name": "RinsO Detergen Bubuk Anti Noda",
      "brand": "Rinso",
      "unit": "1440 g",
      "date": "2026-06-13",
      "store": "Lotte",
      "price": 24900,
      "effective_unit_price": 24900,
      "promo": ["DISKON 20%"],
      "valid_from": "2026-06-01",
      "valid_until": "2026-06-30",
      "bundle_size": 1,
      "promo_type": "discount",
      "match_method": "exact",
      "match_confidence": 1.0,
      "image_path": "database/scrape/...",
      "scrape_time": "2026-06-13T10:30:00",
      "standardized_promo": {"normalized": ["DISKON 20%"], ...}
    }
  ]
}
```

**Error Responses:**
- `404` — Product not found
- `400` — Invalid date format
- `500` — Internal server error

---

### GET /api/v1/prices

Returns raw price data with filtering.

**Query Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Max results (1-100) |
| `cursor` | string | No | — | Base64-encoded pagination cursor |
| `product_key` | string | No | — | Filter by product key |
| `store` | string | No | — | Filter by store name |

**Example Request:**
```bash
curl "http://localhost:8787/api/v1/prices?store=Superindo&limit=5"
```

**Error Responses:**
- `400` — Invalid query parameters
- `500` — Internal server error

---

### GET /api/v1/search

Searches products by name, brand, or unit.

**Query Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `q` | string | **Yes** | — | Search query (min 1 char, max 200) |
| `limit` | integer | No | 20 | Max results (1-50) |

**Example Request:**
```bash
curl "http://localhost:8787/api/v1/search?q=indomie&limit=10"
```

**Example Response:**
```json
{
  "data": [...],
  "query": "indomie",
  "count": 5
}
```

**Error Responses:**
- `400` — Missing or empty search query
- `500` — Internal server error

---

### GET /api/v1/promos

Returns all promos sorted by product count descending.

**Query Parameters:** None

**Example Request:**
```bash
curl http://localhost:8787/api/v1/promos
```

**Example Response:**
```json
{
  "data": [
    {
      "key": "diskon-20-persen",
      "display": "DISKON 20%",
      "type": "discount",
      "discount_pct": 20,
      "product_count": 64,
      "stores": {"Superindo": 64},
      "example_products": ["Rinso", "Bango"]
    }
  ]
}
```

**Error Responses:** `500` — Internal server error

---

### GET /api/v1/brochures

Returns brochure metadata grouped by image.

**Query Parameters:** None

**Example Request:**
```bash
curl http://localhost:8787/api/v1/brochures
```

**Example Response:**
```json
{
  "data": [
    {
      "image_path": "database/scrape/superindo/20260613/promo.jpg",
      "store": "Superindo",
      "date": "2026-06-13",
      "product_count": 45,
      "product_keys": ["rinso-...", "bango-..."]
    }
  ]
}
```

**Error Responses:** `500` — Internal server error

---

### GET /api/v1/stats

Returns summary statistics.

**Query Parameters:** None

**Example Request:**
```bash
curl http://localhost:8787/api/v1/stats
```

**Example Response:**
```json
{
  "total_products_lotte": 31,
  "total_products_superindo": 365,
  "matched_across_stores": 3,
  "lotte_only": 28,
  "superindo_only": 362,
  "total_products": 589
}
```

**Error Responses:** `500` — Internal server error

## Pagination

All list endpoints use cursor-based pagination:

- `cursor` is a base64-encoded JSON object `{"offset": N}`
- First request: omit `cursor` to get the first page
- Response includes `pagination.cursor` for the next page, or `null` if no more results
- `pagination.has_more` indicates if there are additional pages

```javascript
// Fetch all pages example
let cursor = null;
do {
  const params = new URLSearchParams({ limit: "100" });
  if (cursor) params.set("cursor", cursor);
  const resp = await fetch(`/api/v1/products?${params}`);
  const data = await resp.json();
  // process data.data
  cursor = data.pagination.cursor;
} while (cursor);
```

## Response Shapes

| API Field | D1 Table Column | Source JSON Field |
|-----------|----------------|-------------------|
| `product.key` | `products.key` | `catalog.canonical_key` |
| `product.name` | `products.name` | `catalog.display_name` |
| `product.brand` | `products.brand` | `catalog.brand` |
| `store_entry.price` | `prices.price` | `snapshot.price` |
| `store_entry.promo` | `prices.promo` (JSON-decoded) | `snapshot.promo` (array) |
| `store_entry.standardized_promo` | `prices.standardized_promo` (JSON-decoded) | `snapshot.standardized_promo` |

## Local Development

```bash
# Start local dev server
cd web && npx wrangler pages dev --local

# Test endpoints
curl http://localhost:8787/api/v1/health
curl http://localhost:8787/api/v1/stores
curl "http://localhost:8787/api/v1/products?limit=5"
```
