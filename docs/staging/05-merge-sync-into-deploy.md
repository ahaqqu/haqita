# Haqita: Fix Pipeline Sync-Orphans API Deploy

## Problem

The pipeline's Stage 5 (sync to Cloudflare API) and Stage 6 (deploy to Cloudflare Pages) have the wrong ordering and no version awareness:

```
Stage 4 (Publish HTML) → Stage 5 (Sync to Cloudflare) → Stage 6 (Deploy)
```

Stage 5 blindly POSTs to `https://haqita.pages.dev/api/v1/sync/batch` without checking whether the API at that URL has the sync routes. If the Cloudflare Pages Functions are stale (missing the v1 routes added in later commits), Stage 5 fails with a 404:

```
[sync_batch] Transient error: API error (404): {"error":"Not found"}
```

## Solution: Merge sync into deploy (now Stage 5: Deploy + Sync)

Combine deploy + sync into one deploy-then-sync step so the API is always up to date before data is pushed.

### Flow

```
             ┌─────────────────────────────┐
             │  Get local HEAD SHA          │
             │  (git rev-parse HEAD)        │
             └──────────┬──────────────────┘
                        │
                        ▼
             ┌─────────────────────────────┐
             │  Call GET /api/v1/version    │
             │  on deployed API             │
             └──────────┬──────────────────┘
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
       ┌──────────────┐    ┌──────────────┐
       │ SHA matches  │    │ SHA differs  │
       │ (or 404)     │    │ or 404       │
       └──────┬───────┘    └──────┬───────┘
              │ skip deploy       │ deploy:
              │                    │ 1. Set COMMIT_SHA
              │                    │ 2. Copy static → public/
              │                    │ 3. wrangler pages deploy
              │                    └──────┬───────┘
              │                           │
              └──────────┬────────────────┘
                         ▼
              ┌─────────────────────────────┐
              │  Sync data to API           │
              │  (call sync_cloudflare.py)  │
              └─────────────────────────────┘
```

### Files to change

| File | Change |
|---|---|
| `web/functions/api/[[route]].ts` | Add `GET /api/v1/version` returning `c.env.COMMIT_SHA \|\| c.env.CF_PAGES_COMMIT_SHA \|\| "unknown"` |
| `scripts/sync_cloudflare.py` | Expose `run_sync(api_url, secret)` as a callable; keep CLI `main()` for direct use |
| `scripts/deploy.py` | Add version check logic; import and call sync after deploy; set COMMIT_SHA secret before deploy |
| `scripts/orchestrator.py` | Merge sync into deploy (now Stage 5: Deploy + Sync runs both) |
| `.env.example` | Add `CLOUDFLARE_API_TOKEN`, ensure all credentials documented |

### Auth & credentials

- `CLOUDFLARE_API_TOKEN`: Wrangler auth for `wrangler pages deploy` (set in env, not .env — sensitive)
- `SCRAPER_SECRET`: Bearer token for sync API calls
- `COMMIT_SHA`: Set by deploy.py as a Cloudflare Pages secret before each deploy

### AGENTS.md conventions

The project's AGENTS.md should document:
- Workflow: treehouse worktree → branch → commit → no-mistakes → PR
- Pipeline stages and order
- Required env vars and where to get them
