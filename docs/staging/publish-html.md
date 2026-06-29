# Stage 4: Publish HTML

Generates `active_promo.json` from the database and copies JSON files to `output/html/` for the browser-based UI.

## Overview

| | |
|---|---|
| **Input** | `database/price_history.json` — accumulated price snapshots |
| | `database/product_catalog.json` — product metadata |
| | `database/review_queue.json` — for flagged count |
| **Output** | `output/html/active_promo.json` (generated from database, always overwritten) |
| | `output/html/price_history.json` (copy from database) |
| | `output/html/review_queue.json` (copy from database, for admin UI) |


## Architecture

Stage 4 is isolated from Stage 3. Stage 3 writes only to `database/`. Stage 4 reads from `database/` and produces the HTML-ready outputs:

```
database/price_history.json  (append-only snapshots with valid_until)
database/product_catalog.json (product metadata)
database/review_queue.json    (flagged items)
        │
        ▼
publish_html.py → generate_consolidated_from_history()
        │
        ├──→ output/html/active_promo.json      (generated, safe to delete)
        ├──→ output/html/price_history.json      (copy, safe to delete)
        └──→ output/html/review_queue.json       (copy, for admin UI)
```

## How `active_promo.json` is Generated

`active_promo.json` is a **derived view** — it must be regeneratable from `database/`.
The `output/` directory is safe to delete; `database/` is the source of truth.

### Generation Logic

```python
def generate_consolidated_from_history(history, catalog, today):
    """
    1. Filter snapshots: valid_until >= today OR valid_until is null (treat as active)
    2. Get latest snapshot per (product_key, store) — dedup by date
    3. Group by product_key:
       - 2+ stores → matched product (build stores[] array)
       - 1 store → single
    4. Compute display fields: price_min, price_max, cheapest_store, price_gap, savings_pct
    5. Return consolidated dict with same schema as Stage 3 output
    """
```

### Key Behavior

- **Carry-forward**: Still-valid promos from previous runs appear even if dropped from the current scrape, because `price_history.json` is append-only.
- **Expired filtering**: Snapshots with `valid_until < today` are excluded.
- **Null valid_until**: Treated as always active (regular price, no expiry).
- **Deduplication**: Picks the latest snapshot per `(product_key, store)` by `date`.

## Output Schema: `active_promo.json`

Same schema as Stage 3's internal consolidated output:

```json
{
  "generated_at": "2026-05-17T15:30:00",
  "scrape_dates": { "Lotte": "2026-05-17T08:00:00", "Superindo": "2026-05-17T08:15:00" },
  "source_files": ["lotte_promos.json", "superindo_promos.json"],
  "display_hints": {
    "stores": ["Lotte", "Superindo"],
    "store_colors": { "Lotte": "#0057A8", "Superindo": "#E8211D" },
    "currency": "IDR"
  },
  "products": [
    {
      "key": "indomie-goreng--indomie--85g",
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "stores": [
        { "store": "Lotte", "price": 15500, "effective_unit_price": 3100, "bundle_size": 5, "promo": ["DAPAT 5 pcs"], "valid_until": "2026-05-20", "image_path": "database/scrape/lotte/..." },
        { "store": "Superindo", "price": 3500, "effective_unit_price": 3500, "promo": null, "valid_until": null, "image_path": "database/scrape/superindo/..." }
      ],
      "price_min": 3100,
      "price_max": 3500,
      "cheapest_store": "Lotte",
      "price_gap": 400,
      "savings_pct": 11.4,
      "match_method": "exact",
      "match_confidence": 1.0
    }
  ],
  "singles": [
    { "key": "...", "name": "...", "store": "Lotte", "price": 18900, "valid_until": null }
  ],
  "stats": {
    "total_products_lotte": 42,
    "total_products_superindo": 38,
    "matched_across_stores": 15,
    "lotte_only": 27,
    "superindo_only": 23,
    "flagged_for_review": 3
  }
}
```

## Usage

Via `./haqita.sh` → Option [5] → Publish HTML (runs immediately):

```
python scripts/publish_html.py
```

## Viewing the HTML UI

The HTML UI lives in `web/public/` (the single source of truth for both local dev and Cloudflare Pages). Stage 5 (`deploy.py`) stages the JSON files into `web/public/output/html/` and serves `web/public/` on port 8080. For a one-off static preview without running the full Stage 5 deploy:

```bash
python -m http.server 8080 --directory web/public
```

Then open `http://localhost:8080` in a browser. The `index.html` fetches `output/html/active_promo.json` and `output/html/price_history.json` via relative `fetch()` — so the JSONs must be staged at `web/public/output/html/` first (run `python scripts/deploy.py --target local --detached` to stage them, or copy them manually from `output/html/`).

> Opening `index.html` directly via `file://` will fail due to CORS. An HTTP server is required.

## Future

Stage 4 is isolated so it can later read from a database server instead of JSON files. The publish stage has no knowledge of consolidation internals — it only knows the database schema.
