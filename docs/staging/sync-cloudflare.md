# Sync to Cloudflare

## Overview

Reads the latest pipeline output and pushes data to the Cloudflare API. It is the bridge between the proven local pipeline and the new Cloudflare backend.

Sync is now part of Stage 5 (Deploy + Sync) — `deploy.py` imports and calls the `run_sync()` function after deploying. It can also be run standalone via `scripts/sync_cloudflare.py`.

**Script:** `scripts/sync_cloudflare.py` (also callable as `run_sync()` from `scripts/deploy.py`)

## What It Does

1. **Batch Sync**: Reads `database/price_history.json`, `database/product_catalog.json`, and `output/html/promo_catalog.json`, builds a batch payload, and sends it to `POST /api/v1/sync/batch`. If the API returns errors for **every** row (e.g. remote D1 has no tables), the sync aborts with `status=error` and `error=all_rows_failed` instead of reporting success.
2. **R2 Image Upload**: Checks for new or changed brochure images (by MD5 hash against `sync_state.json`), uploads them to Cloudflare R2 via the S3-compatible API, and records the R2 URLs via `POST /api/v1/sync/images`.
3. **R2 Verification** (`--verify-r2`): Lists the R2 bucket via paginated `list_objects_v2`, re-uploads referenced images that are missing from R2 or whose hash is untracked in `sync_state`, and prunes stale `sync_state` entries no longer referenced by `price_history.json`.
4. **State Tracking**: Maintains `database/sync_state.json` with image file hashes and last sync timestamp to avoid re-uploading unchanged images.

## Usage

```bash
# Basic sync (to production)
python scripts/sync_cloudflare.py

# Preview without sending
python scripts/sync_cloudflare.py --dry-run

# Detailed output
python scripts/sync_cloudflare.py --verbose

# Sync to local API
python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1

# Sync with all options
python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1 --verbose --dry-run

# Reconcile R2 bucket against sync_state
python scripts/sync_cloudflare.py --verify-r2
```

## CLI Arguments

| Flag        | Description                                                   |
| ----------- | ------------------------------------------------------------- |
| `--dry-run`   | Preview what would happen without making any changes          |
| `--verbose`   | Show detailed per-table sync reports                          |
| `--api-url`   | Override API URL (default: `https://haqita.pages.dev/api/v1`) |
| `--verify-r2` | List R2 bucket, re-upload missing referenced images, prune stale sync_state entries |

## Environment Variables

| Variable               | Required | Description                                                                                                                  |
| ---------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `SCRAPER_SECRET`       | Yes      | Bearer token for API auth                                                                                                    |
| `R2_ACCESS_KEY_ID`     | Yes      | R2 S3-compatible access key                                                                                                  |
| `R2_SECRET_ACCESS_KEY` | Yes      | R2 S3-compatible secret key                                                                                                  |
| `R2_ENDPOINT`          | Yes      | R2 endpoint URL                                                                                                              |
| `R2_BUCKET_NAME`       | No       | R2 bucket name (default: `haqita-images`)                                                                                    |
| `R2_PUBLIC_URL`        | No       | Public R2 URL for constructing image URLs                                                                                    |
| `DUMMY_DATA`           | No       | When `1`, prefixes R2 image keys with `dummy/` and sets `dummy_data=true` in the sync batch for production-safe dummy writes |

## Data Flow

```
Pipeline Output                 sync_cloudflare.py              Cloudflare
────────────────              ──────────────────              ──────────
database/                       1. Build batch ─────POST────▶  /api/v1/sync/batch
  price_history.json                                      ◀───  200 OK
  product_catalog.json
                                2. Check images
output/html/                       │
  promo_catalog.json               ├─ New/changed? ─PUT──▶  R2 bucket
                                   │                    ◀─── 200 OK
                                   └─ Record URLs ──POST──▶  /api/v1/sync/images
                                                      ◀───  200 OK
                                3. [--verify-r2] List bucket ──GET──▶  R2 (list_objects_v2)
                                   │                    ◀───  key set
                                   ├─ Missing/untracked? ─PUT──▶  R2 bucket
                                   │                        ◀───  200 OK
                                   └─ Prune stale sync_state (local)
                                4. Save sync_state.json (local)
```

## Sync State

The sync state file at `database/sync_state.json` tracks:

```json
{
  "uploaded_images": {
    "database/scrape/superindo/20260613/promo.jpg": "abc123def...",
    "database/scrape/lotte/20260613/promo.jpg": "456ghi..."
  },
  "last_sync": "2026-06-21T12:00:00",
  "last_sync_run_id": "20260621_120000"
}
```

- Image hashes use MD5 (fast, sufficient for change detection)
- Only images whose hash has changed since the last sync are re-uploaded
- Sync state is only updated after a successful sync (not on --dry-run)

## Failure Handling

- API returns 401 → Authentication failed. Check `SCRAPER_SECRET`.
- API returns 400 → Validation error. Check the batch payload structure.
- API returns 500 → Retryable. `retry_call` retries 3 times with exponential backoff.
- All rows errored (207 with `errors.length === total_rows`) → Sync aborts with `status=error` and `error=all_rows_failed`. This usually means the remote D1 schema is missing.
- R2 upload fails for one image → Other images continue uploading. The failed image will be retried on the next sync.
- Local image file missing → Warning logged, image skipped.
- R2 listing fails (`--verify-r2`) → Warning logged, reconciliation skipped; sync_state is trusted as-is.
- API unreachable → Error logged, script exits 1. Local files are NOT modified.

## Menu Integration

- `haqita.sh` / `haqita.bat`: `[6] Sync to Cloudflare` (standalone; sync also runs as part of `[7] Deploy + Sync`)
- `orchestrator.py`: `--stage deploy` or `--full` (sync runs as part of deploy). The old `--stage cloudflare-sync` flag is kept for backward compatibility but delegates to deploy with a deprecation warning.
