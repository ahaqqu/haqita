# `price_history.json`

**Location:** `database/price_history.json`

**Purpose:** Append-only log of every price snapshot seen across all pipeline runs. Used by Stage 4 (`publish_html.py`) to generate `active_promo.json` by filtering for still-valid promos.

## Schema (v1.2)

```json
{
  "snapshots": [
    {
      "product_key": "indomie-goreng--indomie--85g",
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "date": "2026-05-17",
      "store": "Lotte",
      "price": 15500,
      "effective_unit_price": 3100,
      "promo": "DAPAT 5 pcs",
      "promo_type": "bundle_buy",
      "valid_from": "2026-05-07",
      "valid_until": "2026-05-20",
      "bundle_size": 5,
      "match_method": "exact",
      "match_confidence": 1.0,
      "image_path": "database/scrape/lotte/promo_abc123.jpg",
      "scrape_time": "2026-05-17T08:00:00"
    }
  ],
  "metadata": {
    "last_updated": "2026-05-17T15:30:00",
    "total_runs": 5,
    "schema_version": "1.2"
  }
}
```

## Fields

| Field | Type | Purpose |
|---|---|---|
| `product_key` | string | Stable slug: `{name}--{brand}--{unit}` |
| `name` | string | Product display name |
| `brand` | string or null | Detected brand |
| `unit` | string or null | Detected unit (e.g., "85 g") |
| `date` | string | ISO date of the snapshot |
| `store` | string | Store name (Lotte, Superindo) |
| `price` | int | Raw price in IDR |
| `effective_unit_price` | int | Price per unit after promo (e.g., bundle division) |
| `promo` | string or null | Raw promo text as scraped |
| `promo_type` | string | "bundle_buy", "get_free", "discount_pct", "discount_fixed", "multi_price", "single" |
| `valid_from` | string or null | ISO date when promo starts |
| `valid_until` | string or null | ISO date when promo expires (null = always active) |
| `bundle_size` | int | Units per bundle (1 for non-bundle promos) |
| `match_method` | string or null | "exact", "embedding", "ai", or null |
| `match_confidence` | float or null | 0.0–1.0 confidence score |
| `image_path` | string or null | Path to source brochure image |
| `scrape_time` | string or null | ISO timestamp of the original scrape |

## Behavior

- **Append-only**: New snapshots are added each run; old ones are never deleted.
- **Dedup**: Same `(product_key, date, store)` is not duplicated within a single run.
- **Carry-forward**: Expired snapshots remain in history for price trend charts.
- **Active filter**: Stage 4 filters snapshots where `valid_until >= today` OR `valid_until is null`.

## Written By

Stage 3 (`consolidate.py`) — `append_to_price_history()` function.

## Read By

Stage 4 (`publish_html.py`) — `generate_consolidated_from_history()` function.
