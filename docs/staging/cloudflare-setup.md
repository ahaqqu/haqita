# Cloudflare Setup

Infrastructure resources and local development environment for the `web/` Cloudflare Pages project.

## Overview

| | |
|---|---|
| **Cloudflare Account** | Angga.bariesta@gmail.com's Account (ID: `85cd0e23088e12759d05b347f0f68536`) |
| **Wrangler CLI** | v4.103.0 — installed globally via `npm install -g wrangler` |
| **D1 Database** | `haqita-db` (APAC region, ID: `29f84a9b-5666-40dc-a941-883c4f7976ad`) |
| **R2 Bucket** | `haqita-images` — brochure image storage |
| **Pages Project** | `haqita` — production URL: https://haqita.pages.dev/ |
| **Local Dev** | `wrangler pages dev --local` on `http://localhost:8787` |
| **Deploy** | `wrangler pages deploy . --project-name haqita` |

## Resources

### D1 Database

| Attribute | Value |
|---|---|
| Name | `haqita-db` |
| Binding | `DB` (in `wrangler.toml`) |
| ID | `29f84a9b-5666-40dc-a941-883c4f7976ad` |
| Region | APAC |
| Creation | `wrangler d1 create haqita-db` |
| Verify | `wrangler d1 list` |

### R2 Bucket

| Attribute | Value |
|---|---|
| Name | `haqita-images` |
| Binding | `IMAGES` (in `wrangler.toml`) |
| Public read | Enable via Cloudflare Dashboard → R2 → `haqita-images` → Settings → Public Access |
| Public URL | `https://pub-<hash>.r2.dev` (after enabling public access) |
| Creation | `wrangler r2 bucket create haqita-images` |
| Verify | `wrangler r2 bucket list` |

### Pages Project

| Attribute | Value |
|---|---|
| Name | `haqita` |
| Production URL | `https://haqita.pages.dev/` |
| Production branch | `main` |
| Pages Functions path | `web/functions/` |
| Creation | `wrangler pages project create haqita --production-branch main` |
| Verify | `wrangler pages project list` |

## Configuration

### `web/wrangler.toml`

| Key | Value | Notes |
|---|---|---|
| `name` | `haqita` | Must match Pages project name |
| `compatibility_date` | `2024-09-24` | Workers compatibility date |
| `pages_build_output_dir` | `public` | Static assets directory |
| `d1_databases[0].binding` | `DB` | D1 binding name used in code (`c.env.DB`) |
| `d1_databases[0].database_name` | `haqita-db` | D1 database name |
| `d1_databases[0].database_id` | `29f84a9b-5666-40dc-a941-883c4f7976ad` | D1 database UUID |
| `r2_buckets[0].binding` | `IMAGES` | R2 binding name used in code (`c.env.IMAGES`) |
| `r2_buckets[0].bucket_name` | `haqita-images` | R2 bucket name |

## Local Development

All commands run from the `web/` directory.

```bash
# Install dependencies (first time or after pulling changes)
npm install

# Start local dev server with live reload
npx wrangler pages dev --local

# Run TypeScript type check
npx tsc --noEmit

# Deploy to Cloudflare Pages
npx wrangler pages deploy . --project-name haqita
```

The local dev server starts at `http://localhost:8787`. Simulated D1 and R2 bindings are available in local mode.

### Verify the health endpoint

```bash
# Should return {"status":"ok","timestamp":"..."}
curl http://localhost:8787/api/health

# Should return {"error":"Not found"} with 404 status
curl http://localhost:8787/api/nonexistent
```

## Environment Variables

| Variable | Purpose | Phase |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account UUID for API calls | 1 (Infrastructure) |
| `CLOUDFLARE_API_TOKEN` | API token for Wrangler authentication | 1 (Infrastructure) |
| `SCRAPER_SECRET` | Secret for webhook-based scraper trigger | 7 (Security) |
| `R2_ACCESS_KEY_ID` | S3-compatible R2 access key | 5 (Image Upload) |
| `R2_SECRET_ACCESS_KEY` | S3-compatible R2 secret key | 5 (Image Upload) |
| `R2_BUCKET_NAME` | R2 bucket name for upload scripts | 5 (Image Upload) |

## Troubleshooting

| Problem | Solution |
|---|---|
| **Not logged in** | Run `wrangler login` to authenticate via OAuth, or set `CLOUDFLARE_API_TOKEN` environment variable. |
| **Database not listed** | Run `wrangler d1 create haqita-db` to recreate. Verify with `wrangler d1 list`. |
| **`wrangler pages dev` fails to start** | Check that `npm install` completed, `database_id` in `wrangler.toml` is correct, and `wrangler whoami` shows authenticated. |
| **`npm install` fails** | Verify Node.js v18+ is installed (`node --version`). Delete `node_modules/` and `package-lock.json`, then retry. |
