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

A new **Stage 4: Publish HTML** script handles these copies. `consolidate.py` is not modified.

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
```

## JavaScript Logic

| Function | Purpose |
|---|---|
| `loadData()` | Fetch `output/html/consolidated_latest.json` + `price_history.json` |
| `formatIDR(n)` | `3100` → `"Rp 3.100"` (Indonesian locale) |
| `formatDate(isoDate)` | `"2026-05-20"` → `"20 May 2026"` |
| `searchProducts(query)` | Filter products by name/brand/unit (debounced 200ms) |
| `renderCards(data, filter, sortBy, searchQuery)` | Main render loop |
| `buildMatchedCard(product)` | Matched product card HTML |
| `buildSingleCard(product)` | Single-store card HTML |
| `expandCard(key)` | Toggle detail panel with comparison + chart |
| `drawBarChart(canvas, productKey, history)` | Canvas 2D bar chart for price trends |
| Store filter | All / Lotte / Superindo (chip toggle) |
| Sort controls | Name / Cheapest / Savings / Expiry |

## Implementation Steps

### Step 1: Create `output/html/.gitkeep`

Ensure the directory exists for HTML outputs.

### Step 2: Create `scripts/publish_html.py` — Stage 4

New script that copies JSON files to `output/html/` for the HTML display:
- `output/consolidation/consolidated_latest.json` → `output/html/consolidated_latest.json`
- `database/price_history.json` → `output/html/price_history.json`

Simple script (~50 lines), uses `shutil.copy2` for copies.

### Step 3: Update `orchestrator.py` — add Stage 4

Add `run_publish_html()` function and wire it into the full pipeline:
- Stage 1: Scrape
- Stage 2: OCR
- Stage 3: Consolidate
- **Stage 4: Publish HTML** (new)

Add `--stage publish-html` option. Stage 4 always runs after consolidation in full pipeline.

### Step 4: Create `index.html`

**File:** `C:\Fun\Projects\haqita\index.html`

Single self-contained file (~600 lines): HTML + CSS + vanilla JS.

**Structure:**
- `<header>`: Haqita wordmark, freshness bar
- `<div id="search-bar">`: Search input with placeholder "Search products..."
- `<div id="controls">`: Filter chips (All / Lotte / Superindo) + sort dropdown
- `<main id="product-grid">`: Responsive CSS Grid for product cards
- `<footer>`: Scrape dates, product counts, review queue warning
- **No external dependencies** — all CSS and JS embedded

**Features:**
- **Search bar**: Real-time filtering by product name, brand, unit. Debounced 200ms. Shows "No results" state when nothing matches.
- Responsive grid: 3 columns at 1200px+, 2 at 768px+, 1 at < 768px
- Store filter chips (All / Lotte / Superindo) — works in combination with search
- Sort controls (Name / Cheapest / Savings / Expiry)
- Click card to expand/collapse detail panel
- Canvas 2D price trend chart (visible when ≥2 history entries)
- Low confidence badge (shown only when `match_confidence < 0.80`)
- Empty state when no data
- Graceful error handling on fetch failure

### Step 5: Create sample test data

Create `output/html/consolidated_latest.json` with realistic test data (2 matched products, 2 singles) so the HTML can be tested immediately without running the full pipeline.

## Files to Create/Modify

| File | Action | Description |
|---|---|---|
| `output/html/.gitkeep` | **Create** | Ensure directory exists |
| `scripts/publish_html.py` | **Create** | Stage 4: copy JSON to output/html/ |
| `scripts/orchestrator.py` | Modify | Add Stage 4 to pipeline |
| `index.html` | **Create** | ~600 lines: HTML + CSS + vanilla JS with search |
| `output/html/consolidated_latest.json` | **Create** | Sample test data |

## Out of Scope (Future Phases)

- Category chips
- Bottom navigation
- Brosur upload
- User accounts / avatar
