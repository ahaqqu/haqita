# Phase 1: Cloudflare Infrastructure Setup

## TL;DR (For humans)

**What you'll get:** A fully configured Cloudflare project with D1 database, R2 bucket, and Pages project ready for development. A `web/` directory scaffolded with Hono, TypeScript, Zod, and Wrangler configuration that can run locally via `wrangler dev`.

**Why this approach:** Cloudflare infrastructure must exist before any code can be deployed or tested. Setting up and verifying each resource independently prevents debugging compound failures later. The `web/` scaffold establishes the project structure that all subsequent phases build into.

**What it will NOT do:** Create database schemas (Phase 2), implement API endpoints (Phases 3-4), deploy any HTML (Phase 6), or configure security (Phase 7).

**Effort:** Low (~1-2 hours, mostly CLI commands and config files)
**Risk:** Low — infrastructure setup is reversible; resources can be deleted and recreated

**Target location for this file:** `docs/plan/phases/phase-1-cloudflare-infrastructure.md` (copy from `.omo/plans/` when starting work)

---

## Scope

### Must have
1. Wrangler CLI installed and authenticated (`wrangler whoami` succeeds)
2. D1 database created (`haqita-db`)
3. R2 bucket created (`haqita-images`)
4. Cloudflare Pages project created (`haqita`)
5. `web/` directory scaffolded with `package.json`, `wrangler.toml`, `tsconfig.json`, and directory structure
6. `wrangler dev` starts locally without errors
7. Documentation at `docs/staging/cloudflare-setup.md`

### Must NOT have
1. No database schema or seed data — that is Phase 2
2. No API route handlers — that is Phases 3-4
3. No HTML files copied into `web/public/` — that is Phase 6
4. No `SCRAPER_SECRET` configured — that is Phase 7
5. No Cloudflare WAF rules or rate limiting — that is Phase 7
6. No modifications to existing Python scripts or `index.html`
7. No `.gitignore` changes that exclude `web/node_modules/` — see Todo 5 for the specific entries to add

---

## Verification strategy
- **Test decision:** verification-by-command (each todo ends with a CLI command that must succeed)
- **Evidence:** save command outputs as proof
- **Every resource** is verified by a `wrangler` list command that shows it exists
- **Local dev** is verified by starting `wrangler dev` and hitting `http://localhost:8787/` with `curl`

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Install & authenticate Wrangler | — | 2, 3, 4 | — |
| 2. Create D1 database | 1 | 5 | 3, 4 |
| 3. Create R2 bucket | 1 | 5 | 2, 4 |
| 4. Create Pages project | 1 | 5 | 2, 3 |
| 5. Scaffold web/ project | 2, 3, 4 | 6, 7 | — |
| 6. Write documentation | 5 | — | 7 |
| 7. Final verification | 5, 6 | — | — |

---

## Todos

### Todo 1: Install Wrangler CLI and authenticate

**What to do:**
1. Install Wrangler CLI globally:
   ```bash
   npm install -g wrangler
   ```
2. Authenticate with your Cloudflare account:
   ```bash
   wrangler login
   ```
   This opens a browser window. Click "Allow" to grant Wrangler access.
3. Verify authentication:
   ```bash
   wrangler whoami
   ```

**References:** plan.md:486 (Wrangler CLI prerequisite), Cloudflare docs: https://developers.cloudflare.com/workers/wrangler/

**Acceptance criteria:**
- `wrangler --version` prints a version number (e.g., `3.x.x` or `4.x.x`)
- `wrangler whoami` prints your Cloudflare account email and account ID
- **Log message clarity:** `wrangler whoami` output includes a table with your email and account ID — if it says "not logged in" or shows an error, authentication failed
- **Failure handling:** If `wrangler login` fails (browser doesn't open), use `CLOUDFLARE_API_TOKEN` env var instead: set it in `.env` as `CLOUDFLARE_API_TOKEN=your_token` and run `CLOUDFLARE_API_TOKEN=your_token wrangler whoami` to verify
- **Documentation:** Record the account ID shown by `wrangler whoami` — it is needed in Todo 5 for `wrangler.toml`

**QA:**
- Happy: `wrangler whoami` shows account email and ID → pass
- Failure: `wrangler whoami` says "not logged in" → re-run `wrangler login` or use `CLOUDFLARE_API_TOKEN` env var

**Commit:** N — no code changes yet, infrastructure setup only

---

### Todo 2: Create D1 database

**What to do:**
1. Create the D1 database:
   ```bash
   wrangler d1 create haqita-db
   ```
2. **Record the output** — Wrangler prints a `[[d1_databases]]` binding block that looks like:
   ```toml
   [[d1_databases]]
   binding = "DB"
   database_name = "haqita-db"
   database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   ```
   Save the `database_id` value — it is needed in Todo 5 for `wrangler.toml`.
3. Verify the database exists:
   ```bash
   wrangler d1 list
   ```

**References:** plan.md:68 (D1 for prices, stores, products, promos), Cloudflare D1 docs: https://developers.cloudflare.com/d1/

**Acceptance criteria:**
- `wrangler d1 list` output includes `haqita-db` with a database ID
- **Log message clarity:** `wrangler d1 create` output includes the database name, ID, and a success confirmation
- **Failure handling:** If `wrangler d1 create` fails with "database already exists," run `wrangler d1 list` to find the existing database ID and use that. If it fails with "unauthorized," re-run `wrangler login`.
- **Code quality:** The database name `haqita-db` uses lowercase with hyphens, matching Cloudflare naming conventions

**QA:**
- Happy: `wrangler d1 list` shows `haqita-db` → pass
- Failure: `wrangler d1 list` does not show `haqita-db` → re-run `wrangler d1 create haqita-db`

**Commit:** N — infrastructure setup only

---

### Todo 3: Create R2 bucket

**What to do:**
1. Create the R2 bucket for brochure images:
   ```bash
   wrangler r2 bucket create haqita-images
   ```
2. Verify the bucket exists:
   ```bash
   wrangler r2 bucket list
   ```
3. Enable public read access for the bucket (so brochure image URLs are publicly accessible):
   - Go to Cloudflare dashboard → R2 → `haqita-images` → Settings → Public Access → Enable
   - The bucket URL will be `https://pub-<hash>.r2.dev` or a custom domain
   - Record this URL — it is needed in Phase 5 for image upload

**References:** plan.md:69 (R2 for product/brochure images), plan.md:357-375 (Option A — R2 upload from laptop), Cloudflare R2 docs: https://developers.cloudflare.com/r2/

**Acceptance criteria:**
- `wrangler r2 bucket list` output includes `haqita-images`
- **Log message clarity:** `wrangler r2 bucket create` output includes the bucket name and a success confirmation
- **Failure handling:** If the bucket already exists, `wrangler r2 bucket create` returns an error — use the existing bucket. If it fails with "unauthorized," re-run `wrangler login`.
- **Documentation:** Record the public R2 URL (from dashboard) for use in Phase 5

**QA:**
- Happy: `wrangler r2 bucket list` shows `haqita-images` → pass
- Failure: `wrangler r2 bucket list` does not show `haqita-images` → re-run `wrangler r2 bucket create haqita-images`

**Commit:** N — infrastructure setup only

---

### Todo 4: Create Cloudflare Pages project

**What to do:**
1. Create the Pages project:
   ```bash
   wrangler pages project create haqita --production-branch main
   ```
   - `--production-branch main` means deploys from the `main` branch go to the production URL.
2. Verify the project exists:
   ```bash
   wrangler pages project list
   ```

**References:** plan.md:65 (static HTML deployed to Cloudflare Pages), plan.md:517-520 (Pages Functions, same origin), Cloudflare Pages docs: https://developers.cloudflare.com/pages/

**Acceptance criteria:**
- `wrangler pages project list` output includes `haqita` with production branch `main`
- **Log message clarity:** `wrangler pages project create` output includes the project name and a success confirmation with the `.pages.dev` URL
- **Failure handling:** If the project already exists, use the existing project. If it fails with "unauthorized," re-run `wrangler login`. If the project name is taken (by another Cloudflare account), use `haqita-grocery` as an alternative.
- **Documentation:** Record the `.pages.dev` URL for later deployment verification

**QA:**
- Happy: `wrangler pages project list` shows `haqita` → pass
- Failure: `wrangler pages project list` does not show `haqita` → re-run `wrangler pages project create haqita --production-branch main`

**Commit:** N — infrastructure setup only

---

### Todo 5: Scaffold web/ project

**What to do:**

1. Create the directory structure:
   ```
   web/
   ├── package.json
   ├── wrangler.toml
   ├── tsconfig.json
   ├── functions/
   │   └── api/
   │       └── [[route]].ts    ← Hono catch-all route handler
   └── public/
       └── .gitkeep            ← Empty placeholder so directory is tracked
   ```

2. Create `web/package.json`:
   ```json
   {
     "name": "haqita-web",
     "version": "0.1.0",
     "private": true,
     "scripts": {
       "dev": "wrangler pages dev --local",
       "deploy": "wrangler pages deploy . --project-name haqita",
       "typecheck": "tsc --noEmit"
     },
     "dependencies": {
       "hono": "^4.6.0",
       "zod": "^3.23.0"
     },
     "devDependencies": {
       "@cloudflare/workers-types": "^4.20240924.0",
       "typescript": "^5.6.0",
       "wrangler": "^3.78.0"
     }
   }
   ```

3. Create `web/tsconfig.json`:
   ```json
   {
     "compilerOptions": {
       "target": "ES2022",
       "module": "ES2022",
       "moduleResolution": "bundler",
       "strict": true,
       "esModuleInterop": true,
       "skipLibCheck": true,
       "forceConsistentCasingInFileNames": true,
       "types": ["@cloudflare/workers-types"],
       "lib": ["ES2022"],
       "outDir": "./dist",
       "noEmit": true,
       "resolveJsonModule": true,
       "isolatedModules": true,
       "noUncheckedIndexedAccess": true
     },
     "include": ["functions/**/*.ts"],
     "exclude": ["node_modules"]
   }
   ```

4. Create `web/wrangler.toml` — replace `DATABASE_ID` with the actual ID from Todo 2:
   ```toml
   name = "haqita"
   compatibility_date = "2024-09-24"
   pages_build_output_dir = "public"

   [[d1_databases]]
   binding = "DB"
   database_name = "haqita-db"
   database_id = "DATABASE_ID_FROM_TODO_2"

   [[r2_buckets]]
   binding = "IMAGES"
   bucket_name = "haqita-images"
   ```

5. Create `web/functions/api/[[route]].ts` — a minimal Hono app that returns a health check:
   ```typescript
   import { Hono } from 'hono';

   const app = new Hono();

   app.get('/health', (c) => {
     return c.json({ status: 'ok', timestamp: new Date().toISOString() });
   });

   app.all('*', (c) => {
     return c.json({ error: 'Not found' }, 404);
   });

   export default app;
   ```

6. Create `web/public/.gitkeep` (empty file).

7. Install dependencies:
   ```bash
   cd web && npm install
   ```

8. Run typecheck to verify TypeScript config is valid:
   ```bash
   cd web && npx tsc --noEmit
   ```

9. Update root `.gitignore` to exclude `web/node_modules/` and `web/.wrangler/`:
   Add these lines to the existing `.gitignore`:
   ```
   # Cloudflare Pages project
   web/node_modules/
   web/.wrangler/
   web/dist/
   ```

**References:** plan.md:489-510 (repository layout target), plan.md:517-520 (Pages Functions, same origin), existing `.gitignore` at project root

**Acceptance criteria:**
- `web/` directory exists with the exact structure shown above
- `cd web && npm install` completes without errors
- `cd web && npx tsc --noEmit` exits 0 (no type errors)
- `cd web && npx wrangler pages dev --local` starts and `curl http://localhost:8787/api/health` returns `{"status":"ok","timestamp":"..."}`
- `curl http://localhost:8787/api/nonexistent` returns `{"error":"Not found"}` with status 404
- **Log message clarity:** The `/health` endpoint returns a JSON object with `status` and `timestamp` fields — this is the first API log message and sets the pattern for all future endpoints
- **Failure handling:** The catch-all `app.all('*')` returns a 404 JSON response for any unmatched route — no unhandled routes, no HTML error pages
- **Code quality:**
  - `tsconfig.json` has `"strict": true` — no type safety bypasses allowed
  - `"noUncheckedIndexedAccess": true` — array access requires null checks
  - `"isolatedModules": true` — each file can be transpiled independently
  - Hono app uses `c.json()` for all responses — consistent response format
  - No `any` type used anywhere
  - All configuration values use `^` version ranges, matching the project convention
- **Unit test coverage:** No unit tests in this phase — the health check endpoint is verified via `curl` in the acceptance criteria. Unit tests for API endpoints begin in Phase 3.
- **Documentation:** Todo 6 creates `docs/staging/cloudflare-setup.md`

**QA:**
- Happy: `curl http://localhost:8787/api/health` returns `{"status":"ok",...}` → pass
- Failure: `wrangler pages dev --local` fails to start → check `wrangler.toml` for correct `database_id`, check `npm install` completed, check `wrangler whoami` is still authenticated

**Commit:** Y | chore(web): scaffold Cloudflare Pages project with Hono, TypeScript, and Wrangler config

---

### Todo 6: Write documentation

**What to do:**

Create `docs/staging/cloudflare-setup.md` following the existing documentation pattern (see `docs/staging/publish-html.md` for the template). The file must include:

1. **H1 title:** `# Cloudflare Setup`
2. **Overview table** (2-column pipe table): Cloudflare Account, Wrangler CLI, D1 Database, R2 Bucket, Pages Project, Local Dev, Deploy
3. **Resources section:** D1 database (name, binding, creation command), R2 bucket (name, binding, public read access), Pages project (name, URL, Pages Functions path)
4. **Configuration section:** Table of `wrangler.toml` keys with values and notes
5. **Local Development section:** `npm install`, `wrangler pages dev --local`, `tsc --noEmit` commands
6. **Environment Variables section:** Table of all env vars needed across phases (CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, SCRAPER_SECRET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME) with purpose and phase
7. **Troubleshooting table:** 4 most common problems and solutions

**References:** `docs/staging/publish-html.md` (documentation template — overview table → architecture → how it works → schema → configuration → usage), plan.md:561-576 (environment variables)

**Acceptance criteria:**
- `docs/staging/cloudflare-setup.md` exists and follows the overview table → resources → configuration → local development → environment variables → troubleshooting pattern
- All resource names, binding names, and commands match what was created in Todos 1-5
- **Log message clarity:** Documentation includes exact commands for verification so anyone can confirm the setup is correct
- **Failure handling:** Troubleshooting table covers: (1) not logged in, (2) database not listed, (3) pages dev fails to start, (4) npm install fails
- **Code quality:** Documentation matches the style and structure of existing `docs/staging/*.md` files — ATX headings, pipe tables, fenced code blocks with language tags
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Open `docs/staging/cloudflare-setup.md` — all sections present, all resource names match actual resources → pass
- Failure: Resource name in docs doesn't match `wrangler d1 list` output → fix the documentation

**Commit:** Y | docs: add Cloudflare setup documentation

---

### Todo 7: Final verification

**What to do:**

Run the complete verification checklist:

1. Verify Wrangler authentication:
   ```bash
   wrangler whoami
   ```
   **Expected:** Shows your email and account ID.

2. Verify D1 database:
   ```bash
   wrangler d1 list
   ```
   **Expected:** List includes `haqita-db`.

3. Verify R2 bucket:
   ```bash
   wrangler r2 bucket list
   ```
   **Expected:** List includes `haqita-images`.

4. Verify Pages project:
   ```bash
   wrangler pages project list
   ```
   **Expected:** List includes `haqita` with production branch `main`.

5. Verify local dev server:
   ```bash
   cd web && npx wrangler pages dev --local &
   sleep 5
   curl -s http://localhost:8787/api/health
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/api/nonexistent
   kill %1
   ```
   **Expected:** Health endpoint returns `{"status": "ok", ...}`. Nonexistent route returns `404`.

6. Verify TypeScript:
   ```bash
   cd web && npx tsc --noEmit
   ```
   **Expected:** Exits 0 with no output (no type errors).

7. Verify directory structure:
   ```bash
   find web -type f -not -path '*/node_modules/*' -not -path '*/.wrangler/*' | sort
   ```
   **Expected output:**
   ```
   web/functions/api/[[route]].ts
   web/package.json
   web/public/.gitkeep
   web/tsconfig.json
   web/wrangler.toml
   ```

**References:** All previous todos

**Acceptance criteria:**
- All 7 verification steps pass with the expected output
- **Log message clarity:** Each command's output is clear and unambiguous — a resource either exists or it doesn't
- **Failure handling:** If any step fails, go back to the corresponding todo and fix it before proceeding to Phase 2
- **Documentation:** Verification outputs confirm the documentation in Todo 6 is accurate

**QA:**
- Happy: All 7 steps pass → Phase 1 complete
- Failure: Any step fails → fix the issue in the corresponding todo, re-run verification

**Commit:** Y | test: verify Cloudflare infrastructure setup is complete

---

## Final verification wave
- [ ] F1. Plan compliance audit — all Must have items delivered, no Must NOT have items present
- [ ] F2. Code quality review — `tsc --noEmit` clean, no `any` types, strict mode enabled
- [ ] F3. Real manual QA — `wrangler pages dev --local` starts, `curl /api/health` returns 200, `curl /api/nonexistent` returns 404
- [ ] F4. Scope fidelity — no database schemas, no API routes beyond health check, no HTML files in `web/public/`

---

## Commit strategy
- One commit per todo that changes files (Todos 5, 6, 7)
- Commit messages: `chore(web):`, `docs:`, `test:`
- Infrastructure setup commands (Todos 1-4) do not produce commits — they create Cloudflare resources

---

## Success criteria
1. `wrangler whoami` shows authenticated account
2. `wrangler d1 list` shows `haqita-db`
3. `wrangler r2 bucket list` shows `haqita-images`
4. `wrangler pages project list` shows `haqita`
5. `cd web && npx tsc --noEmit` exits 0
6. `curl http://localhost:8787/api/health` returns `{"status":"ok"}`
7. `docs/staging/cloudflare-setup.md` documents all resources and commands
