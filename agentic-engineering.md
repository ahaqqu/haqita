# Agentic Engineering: Haqita Dummy Pipeline

Run the full haqita pipeline against local dummy supermarket websites in an isolated workspace. The real `database/` and `output/` directories are never modified.

## Objectives

1. **Auto self-fix end-to-end scenarios** — Run the dummy pipeline, detect failures, fix them, and rerun until the end results are valid.
2. **Auto self-update docs** — When the dummy run reveals a new failure mode or fix, update this document and the scripts under `agentic_engineering/`.
3. **Auto self-suggest agentic-engineering improvements** — After each run, propose simpler or more robust ways to run, verify, or isolate the dummy pipeline.

## One-command run

From the repo root:

```bash
agentic_engineering/dummy/run_agentic.sh
```

This creates a temp workspace, starts the dummy server, runs the full pipeline, and prints the workspace path.

## What it does

1. Copies the repo into `/tmp/haqita_dummy_<id>/` (excluding `.git`, `.venv`, `database`, `output`).
2. Creates fresh `database/` and `output/` dirs inside the temp workspace.
3. Serves dummy Lotte and Superindo promo pages from `http://localhost:18080`.
4. Runs health check, then `scripts/orchestrator.py --full --verbose`.
5. Prints stage statuses and end-result file sizes.

## Mock external APIs to avoid rate limits

Dummy runs can avoid Gemini quota issues by enabling mocks:

```bash
MOCK_OCR=1 MOCK_AI_VERIFIER=1 agentic_engineering/dummy/run_agentic.sh
```

- `MOCK_OCR=1` — Returns pre-recorded OCR fixtures instead of calling Gemini.
- `MOCK_AI_VERIFIER=1` — Returns deterministic YES for ambiguous pairs instead of calling Gemini.

Fixtures live in `agentic_engineering/dummy/mocks/ocr_fixtures/`.

## Verify end results

After the run, the workspace path is printed. Check the outputs:

```bash
WORKSPACE=/tmp/haqita_dummy_<id>
test -s $WORKSPACE/output/html/active_promo.json && echo "active_promo.json OK"
test -s $WORKSPACE/output/html/promo_catalog.json && echo "promo_catalog.json OK"
test -s $WORKSPACE/output/html/price_history.json && echo "price_history.json OK"
test -s $WORKSPACE/output/html/review_queue.json && echo "review_queue.json OK"
```

A successful run produces Stage 4 (`publish_html`) with `complete` status and non-empty files in `$WORKSPACE/output/html/`.

## Expected stage statuses

| Stage | Expected status | Notes |
|---|---|---|
| Scrape | `new_images` | Discovers 3 Lotte + 3 Superindo dummy brochures. |
| OCR | `complete` | Extracts products from all 6 dummy images. |
| Consolidation | `complete` | Builds `price_history.json` and `product_catalog.json`. |
| Publish HTML | `complete` | Generates `output/html/*.json`. |
| Sync Cloudflare | `complete` or `error` | Requires `SCRAPER_SECRET` and a configured API endpoint. Failure here does not invalidate the local end results. |
| Deploy | `complete` or `error` | Requires Cloudflare Pages setup. Failure here does not invalidate the local end results. |

## Cloudflare end-to-end verification

If you deploy the dummy run to Cloudflare, assert against the live app:

```bash
CF_BASE=https://haqita.pages.dev
curl -sf $CF_BASE/ > /dev/null && echo "Pages root OK"
curl -sf $CF_BASE/api/v1/health | grep -q '"status":"ok"' && echo "API health OK"
curl -sf $CF_BASE/api/v1/stats | grep -q "total_products_lotte" && echo "API stats OK"
curl -sf "$CF_BASE/api/v1/products?limit=1" | grep -q '"data":' && echo "API products OK"
curl -sf "$CF_BASE/api/v1/promos" | grep -q '"data":' && echo "API promos OK"
curl -sf "$CF_BASE/api/v1/brochures" | grep -q '"data":' && echo "API brochures OK"
```

Enable Cloudflare verification in the bundled script:

```bash
RUN_PIPELINE=1 CLOUDFLARE_VERIFY=1 agentic_engineering/dummy/verify.sh
```

## Isolating dummy data in Cloudflare

Never sync dummy data to the production Cloudflare database. Use one of these isolation strategies:

1. **Separate staging project** — Point `cloudflare_sync.api_url` in `config.yaml` to a staging Worker, e.g. `https://haqita-staging.pages.dev/api/v1`.
2. **Separate D1 database** — Create a `haqita-dummy` D1 database and bind it to the staging Worker.
3. **Wipe before sync** — If using a dedicated dummy D1, truncate it before each run:
   ```bash
   wrangler d1 execute haqita-dummy --file=agentic_engineering/dummy/clean_d1.sql
   ```

The local dummy workspace never touches production credentials unless you explicitly configure them.

## Self-fix loop

If any required end result is missing or invalid:

1. Inspect the orchestrator output and stage status files in `$WORKSPACE/output/stage_results/`.
2. Identify the failing stage.
3. Fix the root cause.
4. Re-run `agentic_engineering/dummy/run_agentic.sh`.
5. Repeat up to 5 times. Escalate if unresolved.

Do not modify the real `database/` or `output/` in the repo root. All fixes should target the temp workspace, the dummy server files (`agentic_engineering/dummy/`), or the pipeline scripts.

## Cleanup

Temp workspaces are deleted automatically when `run_agentic.sh` exits. To clean a specific workspace manually:

```bash
cd /tmp/haqita_dummy_<id>
.venv/bin/python agentic_engineering/dummy/clean_dummy_data.py
```

To remove all temp workspaces:

```bash
rm -rf /tmp/haqita_dummy_*
```
