# `product_catalog.json`

**Location:** `database/product_catalog.json`

**Purpose:** Auto-built registry of all known products, enriched with metadata across runs. Used to fill in missing `brand`, `unit`, `unit_type` when snapshots lack this data.

## Schema (v1.1)

```json
{
  "catalog": {
    "indomie-goreng--indomie--85g": {
      "canonical_key": "indomie-goreng--indomie--85g",
      "display_name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "unit_type": "weight",
      "unit_value_g": 85.0,
      "first_seen": "2026-05-01",
      "last_seen": "2026-05-17",
      "appearance_count": 12,
      "stores_found": ["Lotte", "Superindo"],
      "name_variants": [
        { "name": "Indomie Goreng", "count": 10, "store": "Lotte" },
        { "name": "Indomie Goreng 85g", "count": 2, "store": "Superindo" }
      ],
      "confidence": 0.85,
      "manually_verified": false
    }
  },
  "metadata": {
    "total_entries": 42,
    "last_updated": "2026-05-17T15:30:00",
    "schema_version": "1.1"
  }
}
```

## Fields

| Field | Type | Purpose |
|---|---|---|
| `canonical_key` | string | Product key (`{name}--{brand}--{unit}`) |
| `display_name` | string | Most common name seen |
| `brand` | string or null | Detected brand |
| `unit` | string or null | Detected unit (e.g., "85 g") |
| `unit_type` | string | "weight", "volume", "count", "unknown" |
| `unit_value_g` | float or null | Normalized weight in grams (for weight-type units) |
| `first_seen` | string | ISO date of first appearance |
| `last_seen` | string | ISO date of most recent appearance |
| `appearance_count` | int | Total times seen across all runs |
| `stores_found` | string[] | List of stores where this product appeared |
| `name_variants` | object[] | Different names seen, with counts and store |
| `confidence` | float | 0.0–1.0 auto-scored confidence |
| `manually_verified` | bool | Whether a human confirmed this entry |

## Confidence Scoring

| Condition | Score |
|---|---|
| 3+ appearances | +0.3 |
| 2 appearances | +0.15 |
| Found in 2+ stores | +0.3 |
| Found in 1 store | +0.1 |
| Single name variant | +0.2 |
| ≤3 name variants | +0.1 |
| Has unit | +0.1 |
| Has brand | +0.1 |

## Behavior

- **Accumulative**: Entries are created on first sighting and updated on subsequent appearances.
- **New stores**: If a product appears in a new store, the store is added to `stores_found`.
- **Name tracking**: All name variations are tracked with counts to detect OCR inconsistencies.

## Written By

Stage 3 (`consolidate.py`) — `update_catalog()` function.

## Read By

Stage 3 (`consolidate.py`) — enrichment during consolidation.
Stage 4 (`publish_html.py`) — fills missing metadata when generating `active_promo.json`.
