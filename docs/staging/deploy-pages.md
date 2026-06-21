# Deploy to Cloudflare Pages

## Overview

| Property | Value |
|----------|-------|
| Deploy script | `scripts/deploy_pages.sh` (Linux/Mac) / `scripts/deploy_pages.bat` (Windows) |
| URL | `https://haqita.pages.dev` |
| Project name | `haqita` |
| Production branch | `main` |
| Build output | `web/public/` |

## Prerequisites

- Phases 1-5 complete
- Pipeline has been run (`python scripts/publish_html.py`)
- Local D1 seeded (`python scripts/seed_d1.py --apply`)
- `cd web && npx tsc --noEmit` passes
- `cd web && npx vitest run` passes
- `python -m pytest tests/cloudflare/ -v` passes

## Deploy Process

### Step 1: Run pipeline

```bash
python scripts/publish_html.py
```

This generates `output/html/active_promo.json` and copies other JSON files.

### Step 2: Run deploy script

```bash
./scripts/deploy_pages.sh
```

This script:
1. Verifies `web/package.json`, `index.html`, and `output/html/` exist
2. Copies `index.html` and `output/html/*.json` into `web/public/`
3. Installs npm dependencies if needed
4. Runs `tsc --noEmit` (fails if type errors)
5. Runs `wrangler pages deploy . --project-name haqita`

### Step 3: Verify deployment

```bash
# Check HTML page
curl -s -o /dev/null -w "%{http_code}" https://haqita.pages.dev/
# Expected: 200

# Check API health
curl -s https://haqita.pages.dev/api/v1/health
# Expected: {"status":"ok","timestamp":"..."}

# Check API products
curl -s "https://haqita.pages.dev/api/v1/products?limit=5" | python3 -m json.tool
# Expected: paginated product list

# Check API stores
curl -s https://haqita.pages.dev/api/v1/stores | python3 -m json.tool
# Expected: {"data": [{"name": "Lotte", ...}, {"name": "Superindo", ...}]}
```

### Step 4: Browser verification

Open `https://haqita.pages.dev` and verify:

- [ ] Products tab loads and shows product cards
- [ ] Search works
- [ ] Store filter works
- [ ] Sort works
- [ ] Expandable cards show price comparison and charts
- [ ] Promos tab shows promo listing
- [ ] Brochures tab shows brochure thumbnails
- [ ] Data source indicator shows "(API)"

## What Gets Deployed

| File | Source | Purpose |
|------|--------|---------|
| `public/index.html` | Root `index.html` | Main UI |
| `public/active_promo.json` | `output/html/active_promo.json` | Static fallback data |
| `public/price_history.json` | `output/html/price_history.json` | Static fallback history |
| `public/promo_catalog.json` | `output/html/promo_catalog.json` | Static fallback promos |
| `public/review_queue.json` | `output/html/review_queue.json` | Admin review data |
| `functions/api/[[route]].ts` | `web/functions/api/` | API endpoint handlers |

## API Integration

The deployed `index.html` loads data using an API-first strategy:

1. Try `GET /api/v1/products` and `GET /api/v1/prices`
2. If API fails, fall back to static JSON files (`public/*.json`)
3. If both fail, show error state

A small data source indicator in the header shows "(API)" or "(static)" to indicate the current data source.

## Rollback

To roll back to a previous deployment:

```bash
# List deployments
npx wrangler pages deployment list --project-name haqita

# Roll back to a specific deployment ID
npx wrangler pages deployment rollback <deployment-id> --project-name haqita
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Blank page | Static files not copied | Re-run `./scripts/deploy_pages.sh` |
| API returns 404 | Pages Functions not deployed | Check `web/functions/api/` exists, re-deploy |
| Static JSON 404 | Pipeline not run | Run `python scripts/publish_html.py` first |
| Deployment failed | Authentication or project issue | Check `wrangler whoami`, check project name |
| CORS errors | Same-origin violation | Verify page and API are on same domain |
