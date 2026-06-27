# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

## Workflow conventions

- **Worktrees**: All implementation work uses treehouse worktrees (`treehouse get`, `treehouse return`)
- **Branching**: Work happens in a branch, never on the default branch
- **Delivery**: Changes ship via PR through the no-mistakes pipeline (review → test → lint → push → CI)
- **Required env vars**:
  - `SCRAPER_SECRET` — Bearer token for API sync calls (Cloudflare dashboard → your worker → Settings → Secrets)
  - `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT` — R2 image upload (Cloudflare dashboard → R2 → Manage R2 API Tokens)
  - `CLOUDFLARE_API_TOKEN` — Wrangler auth for `wrangler pages deploy` (set in env, not stored in .env)
- **Pipeline stages** (in order):
  1. Scrape (`--stage scrape`) — download brochure images from stores
  2. OCR (`--stage ocr`) — extract product data from images
  3. Consolidate (`--stage consolidate`) — merge and deduplicate product records
  4. Publish HTML (`--stage publish-html`) — generate static JSON/HTML output
  5. Deploy + Sync (`--stage deploy`) — deploy API to Cloudflare Pages, then sync data to deployed API
  - The old `--stage cloudflare-sync` is deprecated; sync now runs as part of deploy.
  - Use `python scripts/orchestrator.py --full` to run all stages end-to-end.

## Pipeline fixes

### Deploy-then-sync (Stage 5)

The deploy stage now checks the deployed API version before syncing:
1. Reads local HEAD SHA via `git rev-parse HEAD`
2. Calls `GET {api_url}/version` on the deployed API (short timeout)
3. If SHA differs or the endpoint 404s/times out: sets COMMIT_SHA as a Cloudflare Pages secret, copies static files, runs typecheck, deploys via wrangler
4. After deploy, imports and calls `run_sync()` from sync_cloudflare.py to sync data

This fixes the pipeline stall where sync ran against a stale API missing v1 routes.
