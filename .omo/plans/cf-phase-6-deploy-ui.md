# Phase 6: Static HTML Deployment & API Integration

## TL;DR (For humans)

**What you'll get:** The existing `index.html` deployed to Cloudflare Pages, updated to consume the Hono API for dynamic data while keeping static JSON as a fallback. A deploy script that copies static files into `web/public/` and runs `wrangler pages deploy`. The deployed site is accessible at `https://haqita.pages.dev`.

**Why this approach:** Deploying the existing static HTML first (before any React rewrite) lets us validate the full stack — Pages, Functions, D1, R2 — with the proven UI. The hybrid approach (API-first with static fallback) ensures the site works even if the API is temporarily down.

**What it will NOT do:** Rewrite the UI in React (Phase 3 of original plan), add new UI features, or configure security (Phase 7).

**Effort:** Medium (~3-4 hours: deploy script, index.html API integration, deployment, documentation)
**Risk:** Low — static HTML is proven; API integration is additive with fallback

---

## Scope

### Must have
1. `scripts/deploy_pages.sh` (and `.bat`) that copies `index.html` + `output/html/*.json` into `web/public/` and runs `wrangler pages deploy`
2. `index.html` updated to fetch from `/api/v1/` endpoints first, with static JSON fallback to `output/html/*.json`
3. Deployed site accessible at `https://haqita.pages.dev`
4. API endpoints accessible from same origin (`/api/v1/products`, etc.)
5. Documentation at `docs/staging/deploy-pages.md`

### Must NOT have
1. No React rewrite — that is the original Phase 3
2. No new UI features — only API integration with existing features
3. No removal of static JSON fallback — it stays as a safety net
4. No changes to the API endpoints — they are finalized in Phases 3-4
5. No security configuration — that is Phase 7

---

## Verification strategy
- **Test decision:** manual verification via deployed URL + curl
- **Evidence:** deployed URL screenshots and curl outputs
- **API integration verified:** UI loads data from API, falls back to static JSON if API is down
- **Deployment verified:** `curl https://haqita.pages.dev/` returns the HTML page; `curl https://haqita.pages.dev/api/v1/health` returns 200

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Create deploy script | Phase 5 | 3 | 2 |
| 2. Update index.html for API consumption | Phase 3 | 3 | 1 |
| 3. Deploy to Cloudflare Pages | 1, 2 | 4, 5 | — |
| 4. Write documentation | 3 | 5 | — |
| 5. Final verification | 3, 4 | — | — |

---

## Todos

### Todo 1: Create deploy script

**What to do:**

Create `scripts/deploy_pages.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Haqita Cloudflare Pages Deploy Script
# Copies static files into web/public/ and deploys to Cloudflare Pages.

cd "$(dirname "$0")/.."

WEB_DIR="web"
PUBLIC_DIR="$WEB_DIR/public"
HTML_OUTPUT="output/html"

echo "========================================"
echo "  Deploying to Cloudflare Pages"
echo "========================================"
echo

# Verify web/ project exists
if [[ ! -f "$WEB_DIR/package.json" ]]; then
    echo "Error: $WEB_DIR/package.json not found. Run Phase 1 setup first."
    exit 1
fi

# Verify index.html exists
if [[ ! -f "index.html" ]]; then
    echo "Error: index.html not found at project root."
    exit 1
fi

# Verify output/html/ has data
if [[ ! -f "$HTML_OUTPUT/active_promo.json" ]]; then
    echo "Warning: $HTML_OUTPUT/active_promo.json not found."
    echo "  Run the pipeline (haqita.sh [1]) before deploying."
    echo "  Deploying with empty data — UI will show empty state."
    echo
fi

# Clean and copy static files
echo "Copying static files to $PUBLIC_DIR/..."
rm -f "$PUBLIC_DIR/index.html"
rm -f "$PUBLIC_DIR/active_promo.json"
rm -f "$PUBLIC_DIR/price_history.json"
rm -f "$PUBLIC_DIR/promo_catalog.json"
rm -f "$PUBLIC_DIR/review_queue.json"

cp "index.html" "$PUBLIC_DIR/index.html"

if [[ -f "$HTML_OUTPUT/active_promo.json" ]]; then
    cp "$HTML_OUTPUT/active_promo.json" "$PUBLIC_DIR/"
fi
if [[ -f "$HTML_OUTPUT/price_history.json" ]]; then
    cp "$HTML_OUTPUT/price_history.json" "$PUBLIC_DIR/"
fi
if [[ -f "$HTML_OUTPUT/promo_catalog.json" ]]; then
    cp "$HTML_OUTPUT/promo_catalog.json" "$PUBLIC_DIR/"
fi
if [[ -f "$HTML_OUTPUT/review_queue.json" ]]; then
    cp "$HTML_OUTPUT/review_queue.json" "$PUBLIC_DIR/"
fi

echo "  Copied: index.html, active_promo.json, price_history.json, promo_catalog.json"
echo

# Install dependencies if needed
if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    echo "Installing web/ dependencies..."
    (cd "$WEB_DIR" && npm install)
    echo
fi

# Typecheck
echo "Running typecheck..."
(cd "$WEB_DIR" && npx tsc --noEmit)
echo "  Typecheck passed."
echo

# Deploy
echo "Deploying to Cloudflare Pages..."
(cd "$WEB_DIR" && npx wrangler pages deploy . --project-name haqita)
echo
echo "========================================"
echo "  Deploy complete."
echo "  URL: https://haqita.pages.dev"
echo "========================================"
```

Also create `scripts/deploy_pages.bat` for Windows (same logic, batch syntax).

Make the shell script executable: `chmod +x scripts/deploy_pages.sh`

**References:** plan.md:489-510 (repository layout — web/public/ populated at deploy time), plan.md:515 (copy index.html and output/html/*.json into web/public/), haqita.sh (script pattern — echo banners, error checks)

**Acceptance criteria:**
- `scripts/deploy_pages.sh` exists and is executable
- `./scripts/deploy_pages.sh` copies `index.html` and `output/html/*.json` into `web/public/`
- If `web/node_modules/` doesn't exist, the script runs `npm install` first
- The script runs `tsc --noEmit` before deploying — fails if type errors
- The script runs `wrangler pages deploy` and prints the deployment URL
- `scripts/deploy_pages.bat` exists with equivalent logic for Windows
- **Log message clarity:**
  - `Copying static files to web/public/...` → `Copied: index.html, active_promo.json, ...`
  - `Running typecheck...` → `Typecheck passed.`
  - `Deploying to Cloudflare Pages...` → deployment URL
  - Warning messages for missing files (but not fatal errors)
- **Failure handling:**
  - `web/package.json` missing → error, exit 1
  - `index.html` missing → error, exit 1
  - `output/html/active_promo.json` missing → warning, continue (UI shows empty state)
  - `tsc --noEmit` fails → error, exit 1 (don't deploy broken code)
  - `wrangler pages deploy` fails → error from wrangler, exit 1
- **Code quality:**
  - `set -euo pipefail` — strict bash mode (exit on error, undefined vars, pipe failures)
  - `cd "$(dirname "$0")/.."` — always run from project root
  - Idempotent — `rm -f` before `cp` ensures clean state
  - Follows `haqita.sh` echo banner pattern
- **Unit test coverage:** N/A — deploy script verified manually
- **Documentation:** Todo 4

**QA:**
- Happy: `./scripts/deploy_pages.sh` runs and deploys → pass
- Failure: `index.html` missing → error, exit 1 → pass

**Commit:** Y | feat(deploy): add Cloudflare Pages deploy script

---

### Todo 2: Update index.html to consume API with static fallback

**What to do:**

Update the `loadData()` function in `index.html` to try the API first, then fall back to static JSON files. The key change is in the data loading section (currently lines 1182-1252).

**Current loading pattern** (line 1187-1190):
```javascript
const OUTPUT_PATH = "output/html";
const SAMPLE_PATH = "data/sample/html";
const consLoad = await tryLoadWithFallback(OUTPUT_PATH, SAMPLE_PATH, "active_promo.json");
const histLoad = await tryLoadWithFallback(OUTPUT_PATH, SAMPLE_PATH, "price_history.json");
```

**New loading pattern** — API-first with static fallback:
```javascript
// API-first loading with static JSON fallback.
// Try the API first (same origin: /api/v1/...). If it fails, fall back to static JSON.
const API_BASE = "/api/v1";
const STATIC_PATH = "output/html";
const SAMPLE_PATH = "data/sample/html";

async function loadFromAPI(endpoint) {
    try {
        const resp = await retryFetch(`${API_BASE}${endpoint}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn(`API ${endpoint} failed, falling back to static JSON`);
        return null;
    }
}

// Try API for consolidated product data, fall back to static JSON
let consData = null;
let consSource = "api";
consData = await loadFromAPI("/products?limit=100");
if (!consData || !consData.data) {
    consSource = "static";
    const consLoad = await tryLoadWithFallback(STATIC_PATH, SAMPLE_PATH, "active_promo.json");
    if (consLoad.data) {
        consData = consLoad.data;
        consSource = consLoad.from;
    }
}

// Try API for price history, fall back to static JSON
let histData = null;
let histSource = "api";
histData = await loadFromAPI("/prices?limit=100");
if (!histData || !histData.data) {
    histSource = "static";
    const histLoad = await tryLoadWithFallback(STATIC_PATH, SAMPLE_PATH, "price_history.json");
    if (histLoad.data) {
        histData = { snapshots: histLoad.data.snapshots || [] };
        histSource = histLoad.from;
    }
}
```

**Key changes:**
1. The API returns products in a paginated `{data: [...], pagination: {...}}` format, while the static JSON has `{products: [...], singles: [...], ...}`. When loading from the API, transform the response to match the existing data structure:
```javascript
if (consSource === "api" && consData) {
    // Transform API response to match static JSON shape
    const products = consData.data || [];
    consolidatedData = {
        products: products.filter(p => p.stores && p.stores.length > 1),
        singles: products.filter(p => !p.stores || p.stores.length <= 1),
        stats: {},  // Will be loaded separately if needed
        display_hints: { stores: {}, store_colors: {}, currency: "IDR" },
        generated_at: new Date().toISOString(),
    };
} else if (consData) {
    consolidatedData = consData;
}
```

2. Add a data source indicator in the UI (small text in the header showing "Data from: API" or "Data from: static"):
```html
<!-- Add near the freshness bar in the header -->
<span id="data-source" style="font-size: 0.75rem; color: var(--gray-500); margin-left: 0.5rem;"></span>
```
```javascript
// In loadData(), after determining the source:
document.getElementById("data-source").textContent = `(${consSource === "api" ? "API" : "static"})`;
```

3. The auto-refresh (every 5 minutes) should also use the API-first pattern — this is automatic since `loadData(true)` calls the same function.

4. **Do NOT change** any of the builder functions (`buildMatchedCard`, `buildSingleCard`, `buildDetailPanel`, `renderCards`, `renderPromos`, `renderBrochures`). They consume `consolidatedData` which has the same shape regardless of source.

5. **Do NOT remove** the `tryLoadWithFallback` function or the `data/sample/html` fallback — they are the last resort if both API and static JSON fail.

**References:** index.html:1182-1252 (loadData function), index.html:705-710 (retryFetch), index.html:712-723 (tryLoadWithFallback), index.html:754-763 (normalizeProduct — handles both stores[] and single store), web/functions/api/[[route]].ts (API response shapes from Phase 3)

**Acceptance criteria:**
- When API is available: UI loads data from `/api/v1/products` and `/api/v1/prices`, shows "(API)" indicator
- When API is down: UI falls back to `output/html/active_promo.json` and `price_history.json`, shows "(static)" indicator
- When both API and static JSON are available: API is preferred
- Auto-refresh (5 minutes) uses the same API-first pattern
- All existing features still work: search, filter, sort, tabs, expandable cards, price charts
- No console errors in the browser console
- **Log message clarity:** `console.warn("API /products failed, falling back to static JSON")` when API fails — this is the only console output, and it's a warning, not an error
- **Failure handling:**
  - API returns non-200 → fall back to static JSON
  - API returns malformed JSON → fall back to static JSON
  - API network timeout → `retryFetch` retries 3 times, then falls back
  - Static JSON also fails → show error state (existing behavior)
  - `data/sample/html` is the last resort (existing behavior)
- **Code quality:**
  - `loadFromAPI` is a new async function that wraps `retryFetch` with error handling
  - No `any` types in JavaScript (not applicable, but no implicit globals)
  - The transformation from API response to `consolidatedData` shape is explicit and documented
  - Existing functions (`tryLoadWithFallback`, `retryFetch`) are reused, not duplicated
  - The data source indicator is minimal and non-intrusive
  - No CSS framework additions — uses existing CSS variables
- **Unit test coverage:** N/A — index.html is vanilla JS, verified via manual browser testing
- **Documentation:** Todo 4

**QA:**
- Happy: Start API + serve static files → UI loads from API, shows "(API)" → pass
- Failure: Stop API, reload → UI falls back to static JSON, shows "(static)" → pass
- Failure: Remove both API and static JSON → UI shows error state → pass

**Commit:** Y | feat(ui): add API-first data loading with static JSON fallback

---

### Todo 3: Deploy to Cloudflare Pages

**What to do:**

1. Ensure the pipeline has been run (so `output/html/*.json` exists):
   ```bash
   python scripts/publish_html.py
   ```

2. Ensure local D1 has seed data (from Phase 2):
   ```bash
   python scripts/seed_d1.py --apply
   ```

3. Run the deploy script:
   ```bash
   ./scripts/deploy_pages.sh
   ```

4. Verify the deployment:
   ```bash
   # Check the HTML page is served
   curl -s -o /dev/null -w "%{http_code}" https://haqita.pages.dev/
   # Expected: 200

   # Check the API health endpoint
   curl -s https://haqita.pages.dev/api/v1/health
   # Expected: {"status":"ok","timestamp":"..."}

   # Check the API products endpoint
   curl -s "https://haqita.pages.dev/api/v1/products?limit=5" | python3 -m json.tool
   # Expected: paginated product list

   # Check the API stores endpoint
   curl -s https://haqita.pages.dev/api/v1/stores | python3 -m json.tool
   # Expected: {"data": [{"name": "Lotte", ...}, {"name": "Superindo", ...}]}
   ```

5. Open `https://haqita.pages.dev` in a browser and verify:
   - Products tab loads and shows product cards
   - Search works
   - Store filter works
   - Sort works
   - Expandable cards show price comparison and charts
   - Promos tab shows promo listing
   - Brochures tab shows brochure thumbnails
   - Data source indicator shows "(API)"

**References:** scripts/deploy_pages.sh (from Todo 1), web/functions/api/[[route]].ts (from Phases 3-4), index.html (from Todo 2)

**Acceptance criteria:**
- `curl https://haqita.pages.dev/` returns 200 with HTML content
- `curl https://haqita.pages.dev/api/v1/health` returns 200 with `{"status":"ok"}`
- `curl https://haqita.pages.dev/api/v1/products?limit=5` returns 200 with product data
- Browser shows the UI with data loaded from the API
- All UI features work: search, filter, sort, tabs, cards, charts
- Data source indicator shows "(API)"
- **Log message clarity:** API responses are clean JSON; HTML page loads without console errors
- **Failure handling:** If deployment fails, wrangler prints the error; check `wrangler whoami` and project name
- **Code quality:** Deployment is reproducible via `./scripts/deploy_pages.sh`
- **Unit test coverage:** N/A — deployment verified via curl and browser
- **Documentation:** Todo 4

**QA:**
- Happy: Deployed URL returns 200, API works, UI renders → pass
- Failure: API returns 404 → check Pages Functions deployment, check `web/functions/api/[[route]].ts` is included

**Commit:** Y | deploy: deploy static HTML and API to Cloudflare Pages

---

### Todo 4: Write documentation

**What to do:**

Create `docs/staging/deploy-pages.md` following the existing documentation pattern.

**Document structure:**
1. **H1 title:** `# Deploy to Cloudflare Pages`
2. **Overview table:** Deploy script, URL, Project name, Production branch, Build output
3. **Prerequisites section:** Phase 1-5 must be complete, pipeline must have been run, local D1 seeded
4. **Deploy Process section:** Step-by-step:
   - Step 1: Run pipeline (`python scripts/publish_html.py`)
   - Step 2: Run deploy script (`./scripts/deploy_pages.sh`)
   - Step 3: Verify deployment (curl commands)
   - Step 4: Browser verification (checklist of UI features)
5. **What Gets Deployed section:** Table of files copied to `web/public/` and their source
6. **API Integration section:** How `index.html` loads data (API-first, static fallback), data source indicator
7. **Rollback section:** How to roll back (redeploy previous version via `wrangler pages deployment list` and `wrangler pages deployment rollback`)
8. **Troubleshooting section:** Table of common issues (blank page, API 404, CORS errors, etc.)

**References:** docs/staging/publish-html.md (documentation template), scripts/deploy_pages.sh (from Todo 1), index.html (from Todo 2), plan.md:489-520 (repository layout and deployment strategy)

**Acceptance criteria:**
- `docs/staging/deploy-pages.md` exists with all 8 sections
- Includes exact curl commands for verification
- **Log message clarity:** Documentation includes expected output for each command
- **Failure handling:** Troubleshooting table covers: blank page, API 404, static JSON 404, deployment failed
- **Code quality:** Matches existing `docs/staging/*.md` style
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Open `docs/staging/deploy-pages.md` — all sections present → pass
- Failure: Missing section → add it

**Commit:** Y | docs: add Cloudflare Pages deployment documentation

---

### Todo 5: Final verification

**What to do:**

Run the complete verification checklist:

1. Verify local build:
   ```bash
   cd web && npx tsc --noEmit
   ```
   **Expected:** Exits 0.

2. Verify deploy script:
   ```bash
   ./scripts/deploy_pages.sh
   ```
   **Expected:** Copies files, typecheck passes, deploys to Cloudflare Pages.

3. Verify deployed URL:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://haqita.pages.dev/
   # Expected: 200
   curl -s https://haqita.pages.dev/api/v1/health
   # Expected: {"status":"ok"}
   curl -s "https://haqita.pages.dev/api/v1/products?limit=5" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Products: {len(d[\"data\"])}, has_more: {d[\"pagination\"][\"has_more\"]}')"
   # Expected: Products: 5, has_more: True
   curl -s https://haqita.pages.dev/api/v1/stores | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Stores: {[s[\"name\"] for s in d[\"data\"]]}')"
   # Expected: Stores: ['Lotte', 'Superindo']
   ```

4. Verify UI in browser:
   - Open `https://haqita.pages.dev`
   - Products tab shows product cards
   - Search for "indomie" → shows matching products
   - Filter by "Superindo" → shows only Superindo products
   - Sort by "Cheapest" → products ordered by price
   - Click a product card → expands with price comparison and chart
   - Promos tab shows promo listing
   - Brochures tab shows brochure thumbnails
   - Data source indicator shows "(API)"

5. Verify fallback (optional — stop API and reload):
   - In a local dev environment, stop `wrangler pages dev`
   - Serve only static files: `python -m http.server 8080`
   - Open `http://localhost:8080`
   - UI should load from static JSON, showing "(static)" indicator

**References:** All previous todos

**Acceptance criteria:**
- All 5 verification steps pass
- Deployed site is accessible and functional
- API endpoints work from the same origin
- UI loads data from API with static fallback
- **Log message clarity:** No console errors in browser
- **Failure handling:** Fallback to static JSON works when API is unavailable
- **Documentation:** Verification confirms `docs/staging/deploy-pages.md` is accurate

**QA:**
- Happy: All steps pass → Phase 6 complete
- Failure: Deployed URL returns 404 → check Pages project name, check `wrangler pages project list`

**Commit:** Y | test: verify Cloudflare Pages deployment and API integration

---

## Final verification wave
- [ ] F1. Plan compliance audit — deploy script exists, index.html updated, site deployed
- [ ] F2. Code quality review — `tsc --noEmit` clean, index.html has no console errors, fallback logic works
- [ ] F3. Real manual QA — deployed URL loads, API works, all UI features functional, fallback works
- [ ] F4. Scope fidelity — no React rewrite, no new UI features, static fallback preserved

---

## Commit strategy
- One commit per todo (Todos 1-5)
- Commit messages: `feat(deploy):`, `feat(ui):`, `deploy:`, `docs:`, `test:`

---

## Success criteria
1. `./scripts/deploy_pages.sh` deploys to Cloudflare Pages successfully
2. `https://haqita.pages.dev/` returns 200 with the HTML page
3. `https://haqita.pages.dev/api/v1/health` returns `{"status":"ok"}`
4. `https://haqita.pages.dev/api/v1/products?limit=5` returns 5 products
5. UI loads data from API with "(API)" indicator, falls back to static JSON with "(static)" indicator
6. All existing UI features work: search, filter, sort, tabs, expandable cards, price charts
7. `docs/staging/deploy-pages.md` documents the deployment process
