# Phase 3 — HTML Display

## Current State

**Implemented (Phase 1 & 2):**
- Scrapers for Lotte Mart & Superindo (`scripts/scrapers/`)
- OCR pipeline with Ollama/Gemini support (`scripts/ocr/`)
- Product matching pipeline with 6 gates (`scripts/matching/`)
- Consolidation script (`scripts/consolidate.py`) that outputs:
  - `output/consolidation/consolidated_latest.json` (and dated versions)
  - `database/product_catalog.json`
  - `database/price_history.json`
  - `database/review_queue.json`
- Orchestrator (`scripts/orchestrator.py`) with 3 stages: scrape → ocr → consolidate
- Interactive menu (`haqita.bat`) with all pipeline stages
- No `index.html` exists yet

## Design Reference

Based on `docs/mockup/haqita-ux.html` — a mobile-first mockup with:
- Warm earthy background (`#e8e6e0`), green accent (`#2d7a4f`), red (`#c0392b`), amber (`#b45309`)
- Typography: Plus Jakarta Sans (body), DM Mono (prices)
- White cards with rounded corners (12px), subtle shadows
- Store dots with color coding, green savings pill badges
- Best deal highlight cards with gradient backgrounds
- Mini bar charts for price history

The `index.html` adapts this visual language for a **desktop browser** (responsive grid, not phone frames).

## JSON Output Path

Per project convention, HTML-only outputs go to `output/html/`:
- `output/html/consolidated_latest.json` — copy from `output/consolidation/`
- `output/html/price_history.json` — copy from `database/`

A new **Stage 4: Publish HTML** script (`scripts/publish_html.py`) handles these copies.
`consolidate.py` is not modified — the publish stage is isolated so it can later read from
a database server instead of JSON files.

**Important:** `index.html` uses `fetch()` to load JSON files via HTTP. Opening the file
directly from the filesystem (`file://`) will fail in most browsers due to CORS
restrictions. Users must serve the project root via HTTP:
```
python -m http.server 8080
```
Then open `http://localhost:8080` in a browser. Alternatives: VS Code Live Server, `npx serve .`

## UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Haqita                                      [Last updated] │
├─────────────────────────────────────────────────────────────┤
│  🟢 Prices updated 2 hours ago                              │  ← freshness bar
├─────────────────────────────────────────────────────────────┤
│  [🔍 Search products...]                                    │  ← search bar
├─────────────────────────────────────────────────────────────┤
│  [All] [Lotte] [Superindo]    Sort: Cheapest ▼             │  ← filter + sort
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │ Product Card │  │ Product Card │  │   Card            │ │  ← responsive grid
│  │              │  │              │  │                   │ │    (3-col → 2-col → 1-col)
│  └──────────────┘  └──────────────┘  └───────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Lotte: 42 products · Superindo: 38 · Matched: 15          │  ← footer stats
└─────────────────────────────────────────────────────────────┘
```

## Product Card Designs

### Matched Card (cross-store comparison)

```
┌─────────────────────────────────────────┐
│  Indomie Goreng              Rp 3.100   │
│  85 g                          cheapest  │
│                                         │
│  ● Lotte     3.100   (Dapat 5 pcs)      │
│  ● Superindo 3.500                      │
│                                         │
│  [Save Rp 400 (11%) vs Superindo]       │
│  Valid until 20 May 2026                │
└─────────────────────────────────────────┘
```

- Store dots with brand colors (Lotte `#0057A8`, Superindo `#E8211D`)
- Cheapest price in green (`#2d7a4f`), DM Mono font
- Savings tag as green pill badge
- Click to expand detail panel

### Single-store Card

```
┌─────────────────────────────────────────┐
│  ABC Kecap Manis                        │
│  600 ml                                 │
│                                         │
│  ● Lotte     Rp 18.900                  │
│  (Only available at Lotte)              │
│  Valid until 20 May 2026                │
└─────────────────────────────────────────┘
```

### Expanded Detail Panel (click card)

```
┌─────────────────────────────────────────────────────┐
│  Indomie Goreng · 85 g                              │
│                                                     │
│  Price Comparison                                   │
│  ┌─────────────────────────────────────────────┐   │
│  │ ● Lotte     Rp 3.100  ✓ Cheapest            │   │  ← green border
│  │   Dapat 5 pcs · Rp 620/pc                   │   │
│  ├─────────────────────────────────────────────┤   │
│  │ ● Superindo Rp 3.500  +Rp 400               │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  Price Trend                                        │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐           │  ← bar chart (CSS)
│  │      │  │      │  │  ██  │  │  ██  │           │
│  │  ██  │  │  ██  │  │  ██  │  │  ██  │           │
│  └──────┘  └──────┘  └──────┘  └──────┘           │
│   14 May    21 May    28 May    4 Jun              │
│                                                     │
│  Match confidence: 100% (exact match)               │
└─────────────────────────────────────────────────────┘
```

### Empty State

```
┌─────────────────────────────────────────┐
│                                         │
│           No data yet                   │
│   Run the pipeline to scrape and        │
│   consolidate product prices.           │
│                                         │
└─────────────────────────────────────────┘
```

### No Results (search)

```
┌─────────────────────────────────────────┐
│                                         │
│       No products match "xyz"           │
│   Try a different search term.          │
│                                         │
└─────────────────────────────────────────┘
```

## CSS Design Tokens

```css
--green: #2d7a4f;
--green-light: #e8f5ee;
--green-mid: #4a9e6a;
--red: #c0392b;
--red-light: #fdf0ee;
--amber: #b45309;
--amber-light: #fef3cd;
--gray-50: #f4f4f2;
--gray-100: #e8e8e4;
--gray-300: #c0bfb8;
--gray-500: #8a8880;
--gray-700: #4a4945;
--gray-900: #1a1916;
--off-white: #f9f9f7;
--radius: 12px;
--radius-sm: 8px;
--shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
--shadow: 0 4px 16px rgba(0,0,0,0.08);
--shadow-lg: 0 8px 32px rgba(0,0,0,0.12);

/* Print styles */
@media print {
  #search-bar, #controls, #load-more, .freshness-bar { display: none; }
  #product-grid { display: block; }
  .product-card { break-inside: avoid; page-break-inside: avoid; }
  .product-card:nth-child(10n) { page-break-after: always; }
  body { background: white; color: black; }
  .product-card { box-shadow: none; border: 1px solid #ccc; }
  footer::after { content: "Printed: " attr(data-timestamp); }
}
```

## JavaScript Logic

| Function | Purpose |
|---|---|
| `loadData()` | Fetch JSON files with `Promise.allSettled()`, validation, and retry logic |
| `validateData(data, type)` | Validate JSON schema — returns `{valid: bool, error: string}` |
| `getDefaultDisplayHints()` | Fallback defaults when `display_hints` is missing or incomplete |
| `retryFetch(url, retries=3, delay=1000)` | Retry failed fetches individually with exponential backoff |
| `renderError(msg)` | Show error state with retry button when fetch fails |
| `renderWarning(msg)` | Show warning banner when only one of two fetches fails |
| `renderLoading()` | Show skeleton while data loads |
| `formatIDR(n)` | `3100` → `"Rp 3.100"` (uses fallback `display_hints.currency` = "Rp") |
| `formatDate(isoDate)` | `"2026-05-20"` → `"20 May 2026"` (uses fallback `display_hints.locale` = "en-ID") |
| `searchProducts(query)` | Filter products by name/brand/unit (debounced 200ms) |
| `renderCards(data, filter, sortBy, searchQuery, page, pageSize)` | Main render loop with pagination |
| `renderPagination(total, page, pageSize)` | Render "Load More" button or pagination controls |
| `loadMore()` | Append next page of products to grid |
| `isProductInStore(product, store)` | Unified handler for `.stores[]` array and `.store` string |
| `normalizeProduct(product)` | Normalize any product type to standard internal format with `.stores` array |
| `buildMatchedCard(product)` | Matched product card HTML |
| `buildSingleCard(product)` | Single-store card HTML |
| `expandCard(key)` | Toggle detail panel with comparison + chart, updates URL hash |
| `drawBarChart(canvas, productKey, history)` | Canvas 2D bar chart — noop if <2 snapshots or key not found |
| `validatePriceHistoryKey(productKey)` | Check product key exists in price_history before rendering chart |
| `setupKeyboardNav()` | Add `role="button"`, `tabindex="0"`, Enter/Space handlers to cards |
| `setupHashRouting()` | Set up hash routing AFTER data loads to prevent race condition |
| `applyHashAfterLoad()` | Apply hash expansion once data is ready (called from `loadData()` completion) |
| `renderEmptyState()` | Empty state (no data — prompt to run pipeline) |
| `renderNoResults(query)` | No search matches found |
| `renderFooterStats(stats, displayHints)` | Footer with product counts, store names from fallback `display_hints.stores`, review queue warning |
| `startAutoRefresh(intervalMs=300000)` | Auto-refresh data every 5 minutes, update freshness bar |
| `updateFreshnessBar(timestamp)` | Update "Prices updated X ago" display |
| Store filter | All / Lotte / Superindo (chip toggle) — uses `isProductInStore()` |
| Sort controls | Name / Cheapest / Savings / Expiry (singles sort to bottom for Savings) |

## Implementation Steps

### Step 1: Create `output/html/.gitkeep`

Ensure the directory exists for HTML outputs.

### Step 2: Create `scripts/publish_html.py` — Stage 4

New script that copies JSON files to `output/html/` for the HTML display:
- `output/consolidation/consolidated_latest.json` → `output/html/consolidated_latest.json`
- `database/price_history.json` → `output/html/price_history.json`

Simple script (~50 lines), uses `shutil.copy2` for copies. Each stage stays isolated:
the publish stage has no knowledge of consolidation internals, and in the future it can
read from a database server instead of intermediate JSON files.

### Step 3: Wire Stage 4 into the pipeline

Update the following files so Stage 4 runs after consolidation:

**`scripts/orchestrator.py`** — add `run_publish_html()` function and wire into `--full`:
- Stage 1: Scrape → Stage 2: OCR → Stage 3: Consolidate → Stage 4: Publish HTML
- Add `--stage publish-html` to the `choices` list in argparse (line 250)
- Also wire Stage 4 into the `--resume` path (after line 321)

**`scripts/pipeline.py`** — add Stage 4 call after consolidation (~line 43):
```python
# Stage 4: Publish HTML
sys.argv = ["publish_html.py"]
_run_stage("Publish HTML", publish_html_main)
```

**`haqita.bat`** — add menu entries for Stage 4:
- Option [7] in the main menu for Stage 4
- Sub-options: run normally, dry-run, verbose
- Docker mode support via a `publish-html` compose service

**`docker/docker-compose.yml`** — add `publish-html` service and update `pipeline` service:
```yaml
publish-html:
  <<: *base
  command: python scripts/publish_html.py

pipeline:
  <<: *base
  command: python scripts/pipeline.py  # already includes stage 4 after pipeline.py update
```

### Step 4: Create `index.html`

**File:** `C:\Fun\Projects\haqita\index.html`

Single self-contained file (~800-1000 lines): HTML + CSS + vanilla JS.

**Structure:**
- `<header>`: Haqita wordmark, freshness bar
- `<div id="loading">`: Loading skeleton, shown immediately during data fetch
- `<div id="search-bar">`: Search input with placeholder "Search products..."
- `<div id="controls">`: Filter chips (All / Lotte / Superindo) + sort dropdown
- `<main id="product-grid">`: Responsive CSS Grid for product cards
- `<div id="error-state">`: Error message with retry button when fetch fails
- `<div id="empty-state">`: Empty data (no products at all — prompt to run pipeline)
- `<div id="no-results">`: Search yielded no matches
- `<footer>`: Scrape dates, product counts, review queue warning
- **No external dependencies** — all CSS and JS embedded

**Data Loading:**
- `loadData()` fetches both JSON files with `Promise.allSettled()` so one failure
  doesn't block the other
- Each fetch goes through `retryFetch(url, retries=3, delay=1000)` which retries
  failed requests individually with exponential backoff
- After fetch, `validateData(data, type)` validates the JSON structure:
  - Checks required fields: `display_hints`, `products`, `stats` for consolidated
  - Checks required fields: object or array structure for price_history
  - Invalid data triggers error state with descriptive message
- Shows the loading skeleton immediately on page load
- On complete failure: shows error state with retry button
- On partial failure (e.g., `price_history.json` fails but `consolidated_latest.json`
  loads): renders available data with a warning banner and individual retry button
- **Display Hints Fallback**: If `display_hints` is missing or incomplete:
  ```javascript
  function getDefaultDisplayHints() {
    return {
      currency: "Rp",
      locale: "en-ID",
      stores: { lotte: "Lotte Mart", superindo: "Superindo" },
      store_colors: { lotte: "#0057A8", superindo: "#E8211D" }
    };
  }
  ```
- `setupHashRouting()` is called AFTER `loadData()` completes via `applyHashAfterLoad()`
  to prevent race condition where hash expansion tries to render before data exists

**Features:**
- **Search bar**: Real-time filtering by product name, brand, unit. Debounced 200ms.
  Shows "No results" state when nothing matches.
- **Dual-schema store filter**: `isProductInStore(product, store)` + `normalizeProduct()`
  converts any product type to internal format with `.stores` array, preventing schema
  fragility when new product types are added.
- Responsive grid: 3 columns at 1200px+, 2 at 768px+, 1 at < 768px
- Store filter chips (All / Lotte / Superindo) — works in combination with search
- Sort controls (Name / Cheapest / Savings / Expiry) — for Savings sort, single-store
  products (no `price_gap`) sort to the bottom
- **Pagination**: "Load More" button loads 20 products at a time. Prevents performance
  issues with large catalogs (100+ products). Maintains scroll position on filter/sort.
- **Keyboard accessibility**: `role="button"`, `tabindex="0"`, Enter/Space handlers on
  all expandable cards (not just click)
- **URL hash routing**: Expanding a card sets `#product-key` in the URL hash; loading
  the page with a hash auto-expands that card after data loads, enabling shareable deep links
- Canvas 2D price trend chart via `drawBarChart(canvas, productKey, history)`:
  - Noop and hidden when `< 2` snapshots exist
  - `validatePriceHistoryKey(productKey)` checks key exists before rendering chart —
    shows "No history available" message if key not found
- Low confidence badge (shown only when `match_confidence < 0.80`)
- Empty state when no data (shows instructions to run the pipeline)
- Footer stats with review queue warning when `stats.flagged_for_review > 0`
- **Auto-refresh**: `startAutoRefresh(intervalMs=300000)` fetches fresh data every 5
  minutes. Freshness bar updates to show "Prices updated X ago" — users see updates
  without manual reload. Only refreshes when tab is visible (uses `visibilitychange`).
- **Print stylesheet**: `@media print` rules hide search, filters, and "Load More" button;
  single-column layout; page break after every 10 products; includes timestamp footer

**Usage Notes:**
- `index.html` uses `fetch()` which requires an HTTP server — cannot be opened as `file://`
- Start with: `python -m http.server 8080` then open `http://localhost:8080`
- Or use VS Code Live Server, or `npx serve .`

### Step 5: Create sample test data

Create `output/html/consolidated_latest.json` with realistic test data (2 matched products,
2 singles) that mirrors the exact output structure from `consolidate.py`, including
`display_hints`, `products` (with `stores[]`), `singles` (with `store` string), and `stats`.

Create `output/html/price_history.json` with at least one product having ≥2 snapshots so
the bar chart can be visually verified during development.

## Files to Create/Modify

| File | Action | Description |
|---|---|---|
| `output/html/.gitkeep` | **Create** | Ensure directory exists |
| `scripts/publish_html.py` | **Create** | Stage 4: copy JSON to `output/html/` |
| `scripts/orchestrator.py` | Modify | Add Stage 4 (`--stage publish-html`, `--full`, `--resume` paths) |
| `scripts/pipeline.py` | Modify | Add Stage 4 after consolidation |
| `haqita.bat` | Modify | Add menu entries for Stage 4 |
| `docker/docker-compose.yml` | Modify | Add `publish-html` service, update `pipeline` service |
| `index.html` | **Create** | ~800-1000 lines: HTML + CSS + vanilla JS with search, keyboard nav, URL hashes |
| `output/html/consolidated_latest.json` | **Create** | Sample test data (mirrors real `consolidate.py` output structure) |
| `output/html/price_history.json` | **Create** | Sample price history (≥1 product with ≥2 entries for chart testing) |

## Out of Scope (Future Phases)

- Category chips
- Bottom navigation
- Brosur upload
- User accounts / avatar
