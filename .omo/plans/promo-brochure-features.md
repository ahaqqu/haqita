# promo-brochure-features - Work Plan

## TL;DR (For humans)

**What you'll get:** Three things: (1) messy promo text like "DISKON 20% EKSTRA STIKER" gets cleaned up into structured data in the database — consistent casing, split into proper categories, no typos; (2) a new "Promos" tab in the web UI that lists every promo with how many products it applies to; (3) a new "Brochures" tab that shows the actual brochure images, and clicking one shows all products extracted from it.

**Why this approach:** The promo data is currently raw OCR output — 110 variations of the same few promo types. Standardizing at the database level means both the existing pipeline and the new UI views get clean data. Tab navigation keeps everything in one page so you don't lose the existing product search.

**What it will NOT do:** Change how scraping or OCR works. Change the matching engine. Add a backend server. Modify any brochure images. Add user accounts or authentication.

**Effort:** Medium (~200-300 lines Python, ~300-400 lines HTML/CSS/JS)
**Risk:** Low-Medium — database-level rewrite needs careful testing to avoid corrupting existing snapshots
**Decisions to sanity-check:** Promo categorization logic (which strings map to which promo type) — this defines the groupings in the Promos tab.

Your next move: start work, or run a high-accuracy review first.

---

> TL;DR (machine): Medium effort. 3 features: promo standardization in consolidation pipeline, promo listing tab, brochure gallery tab. Database-level rewrite. Tab navigation.

## Scope
### Must have
1. **Backend: Promo standardization** — enhance promo_parser.py, wire into consolidation.py, add standardized_promo + promo metadata to price_history.json + active_promo.json
2. **UI: Tab navigation** — Products | Promos | Brochures tabs in index.html header, view switching with preserved state
3. **UI: Promo listing view** — grouped by promo type, product count per promo, filter by store
4. **UI: Brochure gallery view** — thumbnails grouped by store/date, click to show product cards
5. **Backward compatibility** — existing product grid and detail panel continue to work unchanged

### Must NOT have (guardrails, anti-slop, scope boundaries)
1. No changes to scrapers (scripts/scrapers/) or OCR (scripts/ocr/)
2. No changes to the 7-gate matching engine (scripts/matching/matcher.py)
3. No CSS framework or build tool additions — stay with vanilla HTML/CSS/JS
4. No backend server — stay static-file-based
5. No authentication or user system
6. No image processing/manipulation — use existing brochure images as-is
7. No changes to admin.html beyond possible header nav consistency
8. No removal or destructive modification of existing `promo` field — add `standardized_promo` alongside it
9. No type error suppressions, no `as any` equivalents in JS

## Verification strategy
- Test decision: tests-after + manual verification
- Evidence: .omo/evidence/task-*-promo-brochure-features.<ext>
- Python: `python3 -c` inline assertions for promo parsing correctness
- HTML: manual browser inspection + `lsp_diagnostics` on changed files
- Pipeline: run `python scripts/publish_html.py` and verify output JSON structure

## Execution strategy
### Parallel execution waves
- **Wave 1 (Backend):** Todo 1-3 — promo_parser enhancement, consolidation wiring, promo_catalog generation. Must complete before UI can consume new data shapes.
- **Wave 2 (UI Infrastructure):** Todo 4 — tab navigation refactor. Must complete before individual tabs.
- **Wave 3 (UI Features):** Todo 5-6 — promo listing tab and brochure gallery tab. Can be done in parallel once tabs are in place.
- **Wave 4 (Polish):** Todo 7-9 — admin header, full test, verification.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1. Enhance promo_parser.py | — | 2, 3 | — |
| 2. Wire into consolidation.py | 1 | 3 | — |
| 3. Promo catalog generation | 2 | 7 | — |
| 4. Tab navigation refactor | — | 5, 6 | 1, 2, 3 |
| 5. Promo listing tab | 4 | — | 6 |
| 6. Brochure gallery tab | 4 | — | 5 |
| 7. Full pipeline test | 3, 4, 5, 6 | 8 | — |
| 8. Final verification | 7 | — | — |

## Todos

- [ ] 1. **scripts/matching/promo_parser.py: Add comprehensive promo normalization**
  What to do:
  - Add a `normalize_promo_text(text: str) -> str` function that:
    - Converts to title case with standard formatting (DISKON → Diskon, HARGA SPESIAL → Harga Spesial, EKSTRA → Ekstra, GRATIS → Gratis, etc.)
    - Splits composite strings: "DISKON 20% EKSTRA STIKER" → ["Diskon 20%", "Ekstra Stiker"]
    - Normalizes common variants: "EXTRA STIKER" → "Ekstra Stiker", "HEMAT" → "Hemat", "MAKS" → "Maks"
    - Handles "maks." / "MAX" → "Maks."
    - Preserves numbers and prices exactly
  - Add a `categorize_promo(text: str) -> str` function that returns one of:
    - `discount_pct`: matches "Diskon X%", "Diskon X% Ekstra Stiker"
    - `discount_fixed`: matches "Hemat Rp X.XXX"
    - `bogo`: matches "Beli X Gratis Y", "X Gratis Y", "Gratis X (Beli Y Seharga)"
    - `bundle`: matches "X Lebih Hemat", "X Seharga Y", "Beli X Harga Satuan", "Harga Mulai"
    - `member_price`: matches "Khusus Member", "Member Special Price", "Ekstra Diskon Member"
    - `promo_price`: matches "Harga Spesial", "Super Promo!", "Harga Promo"
    - `freebie`: matches "Gratis Jasa", "Gratis Es Batu", "Disertai Pembelian"
    - `quantity_limit`: matches "maks. X ...", "MAX X ..." (standalone — no other promo type)
    - `special`: everything else (Fresh Deals!, Pilihan Segar, PROMO 1 HARI!, etc.)
  - Add a `standardize_promo_list(promos: list[str]) -> dict` that returns:
    ```python
    {
      "normalized": ["Diskon 20%", "Ekstra Stiker"],  # cleaned strings
      "types": ["discount_pct", "special"],             # one per entry
      "best_type": "discount_pct",                     # the most significant type
      "discount_pct": 20,                               # parsed % if available
      "max_qty": 4,                                     # parsed from "maks. X ..."
      "display_summary": "Diskon 20%"                  # human-readable summary
    }
    ```
  - Must handle null/empty input gracefully (return None or empty structure)
  - Must NOT modify base_price or effective_unit_price logic — those stay in the existing parser
  - Write unit-test-style assertions at the bottom of the file (`if __name__ == '__main__'`)
  
  References: scripts/matching/promo_parser.py (full file), database/price_history.json (110 promo strings to cover), config.yaml (no changes needed)
  Acceptance criteria: `python scripts/matching/promo_parser.py` exits 0 with no errors, all assertions pass
  QA: happy — run `python3 -c "from scripts.matching.promo_parser import normalize_promo_text, categorize_promo; print(normalize_promo_text('DISKON 20% EKSTRA STIKER'))"` → "Diskon 20%, Ekstra Stiker"
  QA: failure — run with empty string → returns empty structure, no crash
  Commit: Y | feat(promo): add promo normalization and categorization

- [ ] 2. **scripts/matching/consolidation.py: Wire promo normalization into consolidation**
  What to do:
  - In `generate_consolidated_from_history()`, after building singles and consolidated_products, add a step that:
    - Iterates all snapshots in `history['snapshots']`
    - For each snapshot with `promo`, calls `standardize_promo_list()` from promo_parser
    - Adds `standardized_promo` field to the snapshot dict
    - Writes the updated history back to `database/price_history.json`
  - Update `build_single_product()` and `build_store_entry()` to include `standardized_promo` from the snapshot data
  - Update `build_consolidated_product()` to include `standardized_promo` in store entries
  - Must ONLY modify snapshots that have promo data (skip null/empty)
  - Must NOT change existing `promo` field — only add `standardized_promo`
  - Import standardize_promo_list from promo_parser at the top of consolidation.py
  - Run lsp_diagnostics on both files after changes
  
  References: scripts/matching/consolidation.py (full file), scripts/matching/promo_parser.py (after Todo 1)
  Acceptance criteria: `python scripts/publish_html.py` runs without errors, database/price_history.json now has `standardized_promo` field on snapshots with promo data
  QA: happy — run `python3 -c "import json; d=json.load(open('database/price_history.json')); snap=[s for s in d['snapshots'] if s.get('promo')][0]; print(snap.get('standardized_promo'))"` → shows dict structure
  QA: failure — snapshot with null promo still has no standardized_promo field, no KeyError
  Commit: Y | feat(pipeline): wire promo normalization into consolidation pipeline

- [ ] 3. **scripts/publish_html.py: Add promo catalog to active_promo.json output**
  What to do:
  - After consolidation builds the output dict, add a `promo_catalog` section to the published JSON
  - Build the catalog by:
    - Iterating all singles and products in the consolidated output
    - Collecting unique promo strings from `standardized_promo.display_summary` (or `promo` fallback)
    - For each unique promo, tracking: count of products, store breakdown, promo types
    - Output structure:
    ```json
    {
      "promo_catalog": [
        {
          "key": "diskon-20-persen",
          "display": "Diskon 20%",
          "type": "discount_pct",
          "discount_pct": 20,
          "product_count": 45,
          "stores": {"Superindo": 45},
          "example_products": ["Rinso Detergen...", "Bango Kecap..."]
        },
        ...
      ]
    }
    ```
  - Sort by product_count descending so most common promos appear first
  - Limit example_products to max 5 per promo to keep JSON size reasonable
  - Store the promo_catalog in both active_promo.json and as a new file `output/html/promo_catalog.json`
  
  References: scripts/publish_html.py (full file), output/html/active_promo.json (current schema)
  Acceptance criteria: `python scripts/publish_html.py` runs, output/html/active_promo.json has `promo_catalog` array with entries, output/html/promo_catalog.json exists with same data
  QA: happy — check first entry in promo_catalog has highest product_count
  QA: failure — run without database/price_history.json → graceful error, no crash
  Commit: Y | feat(publish): add promo catalog to published output

- [ ] 4. **index.html: Add tab navigation (Products | Promos | Brochures)**
  What to do:
  - In the `<header>` section, after the logo/ freshness bar, add a tab bar:
    ```html
    <nav class="tab-bar">
      <button class="tab active" data-tab="products">Products</button>
      <button class="tab" data-tab="promos">Promos</button>
      <button class="tab" data-tab="brochures">Brochures</button>
    </nav>
    ```
  - Add CSS for `.tab-bar`, `.tab` (styled like chips but pills), `.tab.active` (green background)
  - Wrap the existing main content (search bar, controls, product-grid, loading/error states) in a `<section id="view-products" class="tab-view active">`
  - Add empty `<section id="view-promos" class="tab-view">` and `<section id="view-brochures" class="tab-view">`
  - Add JS: tab click handler that switches `active` class on tabs + views
  - Preserve state: when switching back to Products tab, restore search/filter/sort/pagination
  - Must NOT break existing hash routing for product card expansion
  - Must NOT change the product grid rendering logic

  References: index.html (full file, 1246 lines), admin.html (header pattern)
  Acceptance criteria: clicking each tab shows the correct view, Products tab still works with search/filter/sort, page load defaults to Products tab
  QA: happy — click each tab, verify content area switches, verify Products tab still has search bar and product grid
  QA: failure — load page with hash `#some-key`, verify it still expands the product card on the Products tab
  Commit: Y | feat(ui): add tab navigation for products, promos, and brochures

- [ ] 5. **index.html: Build Promo listing tab**
  What to do:
  - In `<section id="view-promos">`, build a promo listing view
  - Fetch `promo_catalog.json` (from output/html/) on tab activation, or ideally include `promo_catalog` from active_promo.json
  - Display promos grouped by type (discount, bogo, bundle, member, etc.) with type headers
  - Each promo entry shows:
    - Promo display text (e.g. "Diskon 20%")
    - Product count badge
    - Store distribution (Lotte vs Superindo count)
    - Expandable list of up to 10 example product names
  - Add store filter chips (All, Superindo, Lotte) scoped to this view
  - Clicking a product name in the expanded list navigates to the Products tab and highlights that product card
  - If promo_catalog.json has no data or fails to load, show an empty state with a message
  - Must handle the case where all promos are in one store (current state)
  - Add CSS for promo cards, type headers, product lists — match existing design system
  
  References: index.html (full file, after Todo 4), output/html/promo_catalog.json (after Todo 3)
  Acceptance criteria: Promo tab shows grouped promos with product counts, clicking product name switches to Products tab and scrolls to card
  QA: happy — load page, click Promos tab, verify all promo types shown, expand a promo to see products
  QA: failure — delete promo_catalog.json, verify Promos tab shows empty state gracefully
  Commit: Y | feat(ui): add promo listing tab with type grouping

- [ ] 6. **index.html: Build Brochure gallery tab**
  What to do:
  - In `<section id="view-brochures">`, build a brochure gallery view
  - Data source: iterate `consolidatedData.singles` (and `consolidatedData.products`) to group products by `image_path`
  - Extract unique brochures: for each unique `image_path`, collect: store name, date (from path), product count, product names
  - Display brochures grouped by store, then by date within each store
  - Each brochure entry shows:
    - Thumbnail of the brochure image (`<img>` with the `image_path` URL)
    - Product count badge
    - Store name + date label
    - Clicking expands to show product cards inline (reuse existing `buildSingleCard()` logic)
  - Brochure thumbnails should be ~200px wide, with lazy loading
  - If image fails to load, show a placeholder with the filename
  - Add store filter chips scoped to this view
  - Must handle the case where `image_path` doesn't exist or is null
  - Must NOT modify the image files — just display them
  - Add CSS for brochure cards, thumbnails, product lists
  
  References: index.html (full file, after Todo 4), database/price_history.json (image_path field), database/scrape/superindo/20260613/ (brochure images)
  Acceptance criteria: Brochure tab shows brochure thumbnails grouped by store, clicking expands to show products from that brochure
  QA: happy — load page, click Brochures tab, verify 12 thumbnails shown grouped under Superindo, expand one to see products
  QA: failure — image file missing → shows placeholder, no broken image icon
  Commit: Y | feat(ui): add brochure gallery tab with product cards

- [ ] 7. **admin.html: Add navigation header for consistency**
  What to do:
  - Update admin.html header to include the same tab-style navigation (Products, Promos, Brochures) linking back to index.html
  - Or just add a clean "← Back to Products" link to the Haqita logo
  - Keep the admin page focused on its review queue purpose
  - Must NOT change the admin functionality

  References: admin.html (full file, 522 lines), index.html (header pattern)
  Acceptance criteria: admin.html has a consistent nav link back to the main page
  QA: happy — open admin.html, verify navigation link exists and works
  QA: failure — N/A, trivial change
  Commit: Y | chore(admin): add consistent navigation header

- [ ] 8. **Full pipeline test: Verify end-to-end data flow**
  What to do:
  - Run the publish pipeline: `python scripts/publish_html.py`
  - Verify the output:
    - `database/price_history.json` has `standardized_promo` on promo snapshots
    - `output/html/active_promo.json` has `promo_catalog` section
    - `output/html/promo_catalog.json` exists with data
  - Spot-check 5 promo strings for correct normalization
  - Verify all 110 unique promo strings are covered (no Unrecognized category)
  - Ensure 25 snapshots with null promo are still untouched
  - Run `lsp_diagnostics` on all changed Python files
  - Start a local server and manually check index.html tabs render correctly
  
  References: All files modified in previous todos
  Acceptance criteria: All outputs valid, all promo strings categorized, no regressions in existing views
  QA: happy — run publish script, validate output JSON
  QA: failure — if any existing view breaks, fix before proceeding
  Commit: Y | test: verify end-to-end promo standardization and UI tabs

## Final verification wave
- [ ] F1. Plan compliance audit — compare implementation against Scope (Must have) and Must NOT have lists
- [ ] F2. Code quality review — lsp_diagnostics clean on all changed files, no type safety violations
- [ ] F3. Real manual QA — open index.html in browser, test all 3 tabs, verify existing product search/filter/sort still works
- [ ] F4. Scope fidelity — nothing from Must NOT have was implemented, all Scope items are delivered

## Commit strategy
- One commit per todo, each with conventional commit format
- Commit messages: `feat(promo):`, `feat(ui):`, `chore(admin):`, `test:`
- See each todo for exact commit message

## Success criteria
1. Running `python scripts/publish_html.py` produces clean structured promo data in both database and output
2. `output/html/promo_catalog.json` contains all unique promos with product counts
3. index.html has 3 working tabs: Products (unchanged), Promos (grouped listing), Brochures (gallery with product drill-down)
4. All 110+ raw promo strings are normalized (no unrecognized category)
5. Existing product grid, search, filter, sort, and detail panels work exactly as before
6. No changes to scraping, OCR, or matching pipeline
7. No new external dependencies
