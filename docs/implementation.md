# Implementation Plan — Multi-Store Promo Scraper & Price Comparison

## Overview

Scrape promo brochures from Lotte Mart and Superindo, extract product data using Qwen3-VL OCR,
normalize product names across stores, consolidate into a unified dataset, and display price
comparisons in a dynamic HTML page — with historical price tracking for trend analysis.

```
                    ┌──────────────┐
                    │  Lotte Mart  │
                    │  Website     │
                    └──────┬───────┘
                           │ GET /all-promo-mart
                           ▼
                    ┌──────────────┐     ┌──────────────────┐
                    │ lotte_qwen   │────>│ lotte_promos_    │
                    │ .py scraper  │     │ 20260514_*.json  │
                    └──────────────┘     └────────┬─────────┘
                                                  │
                    ┌──────────────┐              │
                    │  Superindo   │              │
                    │  Website     │              │
                    └──────┬───────┘              │
                           │ GET /katalog-        │
                           │ super-hemat          │
                           ▼                      │
                    ┌──────────────┐     ┌────────┴─────────┐
                    │ superindo_   │     │ superindo_promos_│
                    │ qwen.py      │────>│ 20260514_*.json  │
                    │ scraper      │     └────────┬─────────┘
                    └──────────────┘              │
                                                  │
                                                  ▼
                    ┌──────────────────────────────────────┐
                    │          consolidate.py               │
                    │                                      │
                    │  1. Load both JSONs                   │
                    │  2. Rule-based name normalization     │
                    │  3. AI fuzzy matching (qwen3:4b)      │
                    │  4. Build unified product list        │
                    │  5. Update price_history.json         │
                    │  6. Write consolidated_*.json         │
                    │  7. Copy to consolidated_latest.json  │
                    └──────────────────┬───────────────────┘
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼              ▼
                ┌────────────┐ ┌────────────┐ ┌────────────┐
                │consolidated│ │consolidated│ │price_      │
                │_20260514_  │ │_latest.json│ │history.json│
                │*.json      │ │(for HTML)  │ │(trends)    │
                └────────────┘ └────────────┘ └──────┬─────┘
                                                     │
                                                     ▼
                                          ┌──────────────────────┐
                                          │    index.html        │
                                          │  (dynamic JS)        │
                                          │                      │
                                          │  - Product list      │
                                          │  - Price comparison  │
                                          │  - Store badges      │
                                          │  - Price trends      │
                                          └──────────────────────┘
```

---

## Data Storage

```
output/
├── lotte_promos_20260514_073937.json        # Lotte OCR — per run, never overwritten
├── superindo_promos_20260514_081500.json    # Superindo OCR — per run, never overwritten
├── consolidated_20260514_082000.json        # Merged data — per run, never overwritten
├── consolidated_latest.json                 # Symlink/copy of latest (for HTML fetch)
└── price_history.json                       # Accumulated over time (appended each run)
```

### price_history.json format

```json
{
  "product_history": [
    {
      "product_key": "indomie-goreng--indomie",
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "snapshots": [
        {"date": "2026-05-07", "store": "Lotte", "price": 3100, "promo": "DAPAT 5 pcs"},
        {"date": "2026-05-07", "store": "Superindo", "price": 3500, "promo": null},
        {"date": "2026-05-14", "store": "Lotte", "price": 3000, "promo": null},
        {"date": "2026-05-14", "store": "Superindo", "price": 3400, "promo": null}
      ]
    }
  ]
}
```

---

## Implementation Phases

### Phase 1 — Superindo Scraper

**Goal:** Scrape promo images from Superindo catalog website and extract products via Qwen3-VL OCR.

**Files to create:**
- `scripts/scrapers/superindo_qwen.py`

**Details:**

Superindo has two promo pages:

| Page | URL | Content type |
|---|---|---|
| Katalog Super Hemat | `/promosi/katalog-super-hemat/` | Regional brochure images in a swiper slider |
| Promo Koran | `/promosi/promo-koran/` | Single newspaper promo image |

**Scraper flow:**

```
1. Fetch GET https://www.superindo.co.id/promosi/katalog-super-hemat/
2. Parse HTML with BeautifulSoup
3. Find all .swiper-slide a.fancybox elements
4. Extract image URLs from href attributes
5. Filter: only scrape the default/active region (Jabodetabek & Palembang)
6. Download images to data/scape/superindo/<md5_prefix>_<filename>
7. Compute MD5 hash, compare with data/scape/superindo_state.json
8. For new images: run Qwen3-VL OCR (reuse functions from qwen_ocr_processor.py)
9. Save results to output/superindo_promos_YYYYMMDD_HHMMSS.json
```

**HTML structure to parse:**

```html
<div class="swiper-slide">
  <a class="fancybox"
     data-fancybox="jabodetabek-palembang"
     href="https://www.superindo.co.id/images/katalog/6a04...DKI.jpg">
    <img src="https://www.superindo.co.id/images/katalog/6a04...DKI.jpg">
  </a>
</div>
```

The `data-fancybox` attribute value indicates the region. We filter for `jabodetabek-palembang`.

**State file:** `data/scape/superindo_state.json` (separate from Lotte)
```json
{
  "last_run": "2026-05-14T08:15:00",
  "processed": [
    {"filename": "katalog_abc123.jpeg", "md5": "abc123...", "product_count": 8}
  ]
}
```

**Reusable code from Lotte scraper:**
- `md5_hash()`, `load_state()`, `save_state()`, `filename_from_url()`
- `extract_product_prices()`, `extract_promo_date()` from `qwen_ocr_processor.py`
- Image filtering (size > 50KB, dimensions > 300px)

**Testing:**

| Test | Method |
|---|---|
| HTML parsing | Save a local copy of the Superindo page, run BeautifulSoup parsing in isolation |
| Image download | Run scraper in dry-run mode (`--dry-run`) to verify URLs are extracted correctly |
| OCR on a single image | Manually download one catalog image and run `extract_product_prices()` on it |
| Full run | `python scripts/scrapers/superindo_qwen.py` with `LOTTE_TEST_MODE=false` |
| Duplicate detection | Run twice — second run should skip all images (MD5 match) |

**Dry-run support:** Same as Lotte scraper — `--dry-run` flag fetches and reports new images without OCR.

---

### Phase 2 — Consolidation & Normalization

**Goal:** Merge Lotte + Superindo products into a unified dataset with deduplication and AI-powered name normalization.

**Files to create:**
- `scripts/consolidate.py`

**Steps:**

```
1. Load latest lotte_promos_*.json
2. Load latest superindo_promos_*.json
3. Load existing price_history.json (create if not exists)
4. Apply rule-based normalization to all product names
5. Group products by (normalized_name, brand)
6. For unmatched products: AI fuzzy matching via qwen3:4b
7. Build consolidated product list
8. Update price_history.json with today's snapshots
9. Write consolidated_YYYYMMDD_HHMMSS.json
10. Copy to consolidated_latest.json
```

**Rule-based normalization (deterministic, catches ~80%):**

```
1. Strip unit suffixes: " 1 kg", " 500 ml", " 6 x 45 ml", " 200 g", " 2 L"
2. Strip "Rp" from price strings
3. Strip brand prefix from product name if brand field exists
4. Lowercase and strip whitespace
5. Remove punctuation differences (/, -, .)
```

Example matching:
```
Lotte: "Indomie Goreng Ayam Geprek 85 g"  → normalized: "indomie goreng ayam geprek"
Superindo: "Indomie Goreng Ayam Geprek"    → normalized: "indomie goreng ayam geprek"
Result: MATCH ✓
```

**AI fuzzy matching (catches remaining ~20%):**

For products that didn't find an exact match after rule-based normalization, batch-send them to `qwen3:4b`:

```
Prompt:
You are matching grocery products across stores.
Do these two product names refer to the same item? Answer yes or no only.

Product A (Store: Lotte): "ILGUSTO Bratwurst Original 360 g"
Product B (Store: Superindo): "Bratwurst Sosis 360g"
```

**Model:** `ollama pull qwen3:4b` (~2.5 GB Q4_K_M) — text-only model, runs on CPU, ~2-5s per batch of 50 pairs.

**Consolidated output format:**

```json
{
  "generated_at": "2026-05-14T08:20:00",
  "scrape_date_lotte": "2026-05-14T07:39:37",
  "scrape_date_superindo": "2026-05-14T08:15:00",
  "store_files": [
    "lotte_promos_20260514_073937.json",
    "superindo_promos_20260514_081500.json"
  ],
  "products": [
    {
      "key": "indomie-goreng-ayam-geprek--indomie",
      "name": "Indomie Goreng Ayam Geprek",
      "brand": "Indomie",
      "unit": "85 g",
      "stores": [
        {
          "store": "Lotte",
          "price": 3100,
          "promo": "DAPAT 5 pcs",
          "period": "7 - 20 Mei 2026"
        },
        {
          "store": "Superindo",
          "price": 3500,
          "promo": null,
          "period": "12 - 25 Mei 2026"
        }
      ],
      "price_min": 3100,
      "price_max": 3500,
      "cheapest_store": "Lotte",
      "price_gap": 400
    }
  ],
  "stats": {
    "total_products": 45,
    "matched_across_stores": 12,
    "lotte_only": 20,
    "superindo_only": 13,
    "ai_matches": 3
  }
}
```

**Testing:**

| Test | Method |
|---|---|
| Rule-based normalization | Create a test file with known product name pairs, verify matching |
| AI normalization | Run consolidate with 3-5 intentionally different product names, verify model correctly matches/mismatches |
| No-overwrite | Run consolidate twice — verify new timestamped file each time |
| Price history append | Run consolidate twice — verify price_history.json has 2 entries per product |
| Latest copy | Verify consolidated_latest.json is overwritten (not appended) |

---

### Phase 3 — Dynamic HTML Display + Price History

**Goal:** Display consolidated product data with price comparisons and trend visualization.

**Files to create:**
- `index.html` (dynamic, standalone, fetches JSON at runtime)

**How it works:**

```
User opens index.html in browser
        │
        ▼
  JS fetches /output/consolidated_latest.json
  and /output/price_history.json
        │
        ▼
  Renders product list with store comparison badges
        │
        ▼
  Click on a product → shows per-store price comparison
  with price trend chart (if history exists)
```

**UI sections (based on docs/mockup/haqita-ux.html):**

1. **Header:** Haqita branding, last updated timestamp, store filters (Lotte / Superindo / All)
2. **Product cards:** Each card shows:
   - Product name + brand
   - Cheapest price (green)
   - Store badges (colored dots: Lotte blue, Superindo green)
   - Savings indicator (e.g., "Rp 400 lebih murah dari Superindo")
3. **Product detail (expandable):**
   - Price comparison rows per store
   - Price difference indicators
   - Promo text
   - Mini price trend chart (from price_history.json)
4. **Footer:** Sources, last scrape date

**Design:**
- Based on the mockup color palette (green accent, neutral grays, DM Mono for prices)
- Responsive layout (desktop + mobile)
- No external dependencies — vanilla JS + CSS (inlined in a single HTML file)

**Price trend chart:**
- Simple line chart drawn on HTML5 Canvas
- X-axis: dates
- Y-axis: price
- One line per store (different colors)
- Shows up only when 2+ data points exist

**Testing:**

| Test | Method |
|---|---|
| JSON fetch | Open index.html in browser, verify products load |
| Empty state | Remove all JSON files, verify page shows "No data" gracefully |
| Error state | Corrupt JSON, verify error message shown |
| Trend chart | After 2 consolidate runs, verify chart appears with 2 data points per store |
| Mobile | Open on phone / resize browser, verify responsive layout |
| Cross-browser | Test in Chrome + Firefox + Edge |

---

### Phase 4 — Integration & Menu

**Goal:** Wire everything together with `haqita.bat` menu and update documentation.

**Files to update:**
- `haqita.bat` — add new menu options
- `docs/lotte_scraper.md` — no changes needed (already complete)
- `docs/superindo_scraper.md` — new documentation
- `README.md` — update project structure

**Updated haqita.bat menu:**

```
========================================
       Haqita - Grocery Price Tool
========================================

What would you like to do?

[1] Run Lotte Promo Scraper
[2] Run Qwen3-VL OCR on local images
[3] Dry-run scraper (see new promos without OCR)

[4] Run Superindo Promo Scraper
[5] Dry-run Superindo scraper

[6] Consolidate & Generate HTML
[7] Full Pipeline (Lotte + Superindo + Consolidate)

[8] Exit
```

**Full pipeline (option 7) runs sequentially:**
1. Lotte scraper (with OCR)
2. Superindo scraper (with OCR)
3. Consolidation + normalization
4. Report summary: "X products, Y matched across stores"

---

## Summary

| Phase | Deliverables | Effort |
|---|---|---|
| 1 — Superindo scraper | `superindo_qwen.py` | ~300 lines, reuses existing OCR infra |
| 2 — Consolidation | `consolidate.py`, pull `qwen3:4b` | ~400 lines |
| 3 — HTML + trends | `index.html` | ~300 lines (JS + CSS + HTML) |
| 4 — Integration | Update `haqita.bat`, add docs | ~50 lines |

**Models required:**
- `qwen3-vl:2b` (already have) — for OCR on images
- `qwen3:4b` (new) — for text-based product name normalization (CPU only, ~2.5 GB)

**Storage growth:**
- Each scrape run: ~6 images × ~1 MB = ~6 MB per store per run
- price_history.json: ~100 KB per run (grows linearly over time)
