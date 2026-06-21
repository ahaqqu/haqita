# Stage 5: Sync to Cloudflare

## Overview

Stage 5 reads the latest pipeline output and pushes data to the Cloudflare API. It is the bridge between the proven local pipeline and the new Cloudflare backend.

**Script:** `scripts/sync_cloudflare.py`

## What It Does

1. **Batch Sync**: Reads `database/price_history.json`, `database/product_catalog.json`, and `output/html/promo_catalog.json`, builds a batch payload, and sends it to `POST /api/v1/sync/batch`.
2. **R2 Image Upload**: Checks for new or changed brochure images, uploads them to Cloudflare R2 via the S3-compatible API, and records the R2 URLs via `POST /api/v1/sync/images`.
3. **State Tracking**: Maintains `database/sync_state.json` with image file hashes and last sync timestamp to avoid re-uploading unchanged images.

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
```

## CLI Arguments

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview what would happen without making any changes |
| `--verbose` | Show detailed per-table sync reports |
| `--api-url` | Override API URL (default: `https://haqita.pages.dev/api/v1`) |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SCRAPER_SECRET` | Yes | Bearer token for API auth |
| `R2_ACCESS_KEY_ID` | Yes | R2 S3-compatible access key |
| `R2_SECRET_ACCESS_KEY` | Yes | R2 S3-compatible secret key |
| `R2_ENDPOINT` | Yes | R2 endpoint URL |
| `R2_BUCKET_NAME` | No | R2 bucket name (default: `haqita-images`) |
| `R2_PUBLIC_URL` | No | Public R2 URL for constructing image URLs |

## Data Flow

```
Pipeline Output                 sync_cloudflare.py              Cloudflare
─────────────────              ──────────────────              ──────────
database/                       1. Build batch ─────POST────▶  /api/v1/sync/batch
  price_history.json                                      ◀───  200 OK
  product_catalog.json
                                2. Check images
output/html/                       │
  promo_catalog.json               ├─ New/changed? ─PUT──▶  R2 bucket
                                   │                    ◀─── 200 OK
                                   └─ Record URLs ──POST──▶  /api/v1/sync/images
                                                      ◀───  200 OK
                                3. Save sync_state.json (local)
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
- R2 upload fails for one image → Other images continue uploading. The failed image will be retried on the next sync.
- Local image file missing → Warning logged, image skipped.
- API unreachable → Error logged, script exits 1. Local files are NOT modified.

## Menu Integration

The sync script is available from the main menu:

- `haqita.sh`: `[6] Stage 5: Sync to Cloudflare`
- `haqita.bat`: `[6] Stage 5: Sync to Cloudflare`
- `orchestrator.py`: `--stage cloudflare-sync` or `--full` (runs after Stage 4)
