# Pre-Deployment Checklist

Run through this checklist before each deployment to production.

## Infrastructure

- [ ] `wrangler whoami` shows correct account
- [ ] `wrangler d1 list` shows `haqita-db`
- [ ] `wrangler r2 bucket list` shows `haqita-images`
- [ ] `wrangler pages project list` shows `haqita`
- [ ] `wrangler pages secret list --project-name haqita` shows `SCRAPER_SECRET`

## Code Quality

- [ ] `cd web && npx tsc --noEmit` exits 0
- [ ] `cd web && npx vitest run` all tests pass
- [ ] `python -m pytest tests/cloudflare/ -v` all tests pass
- [ ] No `any` types in TypeScript code
- [ ] No SQL string interpolation — all queries use `bind()`

## Data

- [ ] `python scripts/publish_html.py` runs successfully
- [ ] `output/html/active_promo.json` exists with data
- [ ] `output/html/promo_catalog.json` exists with data
- [ ] `database/price_history.json` has recent snapshots

## Security

- [ ] SCRAPER_SECRET is set in Cloudflare and .env
- [ ] Security headers middleware is active (verify with `curl -I`)
- [ ] WAF rate limiting rules are configured (if available on plan)

## Deployment

- [ ] `python scripts/deploy.py --target cloudflare` runs successfully (deploys + syncs)
- [ ] Stage 5 deploy status in `output/stage_results/deploy_status.json` is `complete` (includes sync results)
- [ ] `curl https://haqita.pages.dev/` returns 200
- [ ] `curl https://haqita.pages.dev/api/v1/health` returns {"status":"ok"}
- [ ] `curl https://haqita.pages.dev/api/v1/version` returns the expected commit SHA
- [ ] `curl https://haqita.pages.dev/api/v1/stores` returns store data
- [ ] Browser: UI loads, all tabs work, search/filter/sort functional

## E2E Pipeline

- [ ] `./haqita.sh` → **[1] Run full pipeline** completes all 5 stages
- [ ] Local UI at `http://localhost:8080` loads and shows products (left running in detached mode by the pipeline)
- [ ] Local API at `http://localhost:8787/api/v1/health` returns {"status":"ok"}
- [ ] Detached servers cleaned up via option **[8] → [2] Stop** or `python scripts/deploy.py --stop-local`
- [ ] (Optional) With `deploy.cloudflare: true`, production UI at `https://haqita.pages.dev` loads

## Post-Deployment

- [ ] `curl https://haqita.pages.dev/api/v1/products?limit=5` returns 5 products
- [ ] Security headers present in production responses
- [ ] No console errors in browser
