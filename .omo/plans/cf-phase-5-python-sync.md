# Phase 5: Python Stage 5 Sync Script

## TL;DR (For humans)

**What you'll get:** A Python script `scripts/sync_cloudflare.py` that reads the existing pipeline output (`database/*.json` and `output/html/*.json`), pushes data to the Cloudflare API via `POST /api/v1/sync/batch`, uploads brochure images to R2, records R2 URLs via `POST /api/v1/sync/images`, and tracks sync state. The script is wired into `haqita.sh`, `haqita.bat`, and `orchestrator.py` as Stage 5. Includes `--dry-run` mode, unit tests, and documentation.

**Why this approach:** The sync script is the bridge between the proven local pipeline and the new Cloudflare backend. It follows the exact same patterns as existing pipeline scripts (`publish_html.py` template, `retry_call` for HTTP, `config.py` for config, `argparse` for CLI) so it fits seamlessly into the existing workflow.

**What it will NOT do:** Modify the existing pipeline stages (1-4), modify `index.html`, deploy to Cloudflare Pages (Phase 6), or configure security (Phase 7).

**Effort:** High (~6-8 hours: sync script, R2 upload, state tracking, menu wiring, tests, documentation)
**Risk:** Medium — R2 upload via boto3 requires correct credentials; API failures must not corrupt local data

---

## Scope

### Must have
1. `scripts/sync_cloudflare.py` with argparse (`--dry-run`, `--verbose`, `--api-url`), logging, and config loading
2. Batch sync logic: read `database/price_history.json`, `database/product_catalog.json`, `output/html/promo_catalog.json`, send to `POST /api/v1/sync/batch`
3. R2 image upload via boto3 S3-compatible API (only new/changed images)
4. R2 URL recording via `POST /api/v1/sync/images`
5. Sync state tracking in `database/sync_state.json` (image hashes, last sync timestamp)
6. Failure handling: API/R2 failures are logged and do NOT modify local files
7. Wired into `haqita.sh` (menu item [6]) and `haqita.bat` (menu item [6])
8. Wired into `scripts/orchestrator.py` (new `run_cloudflare_sync()` function, `--stage cloudflare-sync`)
9. Updated `.env.example`, `config.yaml`, `requirements.txt`
10. Unit tests at `tests/cloudflare/test_sync_cloudflare.py`
11. Documentation at `docs/staging/sync-cloudflare.md`

### Must NOT have
1. No modifications to Stages 1-4 scripts (`scrapers/`, `ocr/`, `consolidate.py`, `publish_html.py`)
2. No modifications to `index.html` or `admin.html`
3. No modifications to `database/*.json` files (sync is read-only on local data)
4. No React or frontend changes
5. No production deployment — this phase implements the script, deployment is Phase 6

---

## Verification strategy
- **Test decision:** TDD for sync logic + manual verification for R2 upload
- **Evidence:** `--dry-run` output showing counts, `--verbose` output showing per-table sync results
- **Idempotency verification:** run sync twice → second run shows 0 new images, same data counts
- **Failure handling verification:** stop local API, run sync → script logs error and exits 1, local files unchanged

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Create sync_cloudflare.py core structure | Phase 4 | 2, 3, 4, 5 | — |
| 2. Implement batch sync (stores, products, prices, promos) | 1 | 6, 7 | 3, 4, 5 |
| 3. Implement R2 image upload | 1 | 6, 7 | 2, 4, 5 |
| 4. Implement sync state tracking | 1 | 6, 7 | 2, 3, 5 |
| 5. Wire into haqita.sh, haqita.bat, orchestrator.py | 1 | 7 | 2, 3, 4 |
| 6. Write unit tests | 2, 3, 4 | 7, 8 | 5 |
| 7. Update .env.example, config.yaml, requirements.txt | 2, 3, 4, 5 | 8 | 6 |
| 8. Write documentation | 2, 3, 4, 5, 7 | 9 | 6 |
| 9. Final verification | 6, 7, 8 | — | — |

---

## Todos

### Todo 1: Create scripts/sync_cloudflare.py core structure

**What to do:**

Create `scripts/sync_cloudflare.py` following the `scripts/publish_html.py` template pattern. The script uses:
- `argparse` with `--dry-run`, `--verbose`, `--api-url` flags
- `logging.getLogger(__name__)` with `logging.basicConfig(level=logging.INFO, format='%(message)s')`
- `scripts.config.load_config()` for config loading
- `scripts.common.http_client.retry_call` for API calls with retry
- `sys.path.insert(0, ...)` for imports
- `ROOT = Path(__file__).resolve().parent.parent` for project root

```python
"""
Haqita Stage 5: Sync to Cloudflare.

Reads the latest pipeline output and pushes data to the Cloudflare API.
Uploads new/changed brochure images to R2. Records R2 URLs in D1 via the API.
Does NOT modify any local files.

Usage:
    python scripts/sync_cloudflare.py                          # Sync to default API
    python scripts/sync_cloudflare.py --dry-run                # Preview without uploading
    python scripts/sync_cloudflare.py --verbose                # Show detailed sync report
    python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1  # Sync to local API
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.config import load_config
from scripts.common.http_client import retry_call

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = ROOT / "database"
OUTPUT_DIR = ROOT / "output" / "html"
SYNC_STATE_FILE = DATABASE_DIR / "sync_state.json"

# Default API URL — overridden by --api-url or config.yaml cloudflare_sync.api_url
DEFAULT_API_URL = "https://haqita.pages.dev/api/v1"


def load_json(path: Path, default=None):
    """Load JSON file, return default if not found."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def load_sync_state() -> dict:
    """Load sync state from database/sync_state.json. Returns empty dict if not found."""
    return load_json(SYNC_STATE_FILE, {"uploaded_images": {}, "last_sync": None})


def save_sync_state(state: dict):
    """Save sync state to database/sync_state.json."""
    state["last_sync"] = datetime.now().isoformat()
    SYNC_STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_api_url(args, cfg) -> str:
    """Determine API URL from --api-url arg, config, or default."""
    if args.api_url:
        return args.api_url.rstrip("/")
    cf_cfg = cfg.get("cloudflare_sync", {})
    return cf_cfg.get("api_url", DEFAULT_API_URL).rstrip("/")


def get_scraper_secret() -> str:
    """Get SCRAPER_SECRET from environment."""
    secret = os.getenv("SCRAPER_SECRET")
    if not secret:
        logger.error("SCRAPER_SECRET environment variable is not set.")
        logger.error("Set it in .env or export SCRAPER_SECRET=your_secret")
        sys.exit(1)
    return secret


def setup_logging(verbose: bool):
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(message)s', force=True)


def main():
    parser = argparse.ArgumentParser(description="Haqita Stage 5: Sync to Cloudflare")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--verbose", action="store_true", help="Show detailed sync report")
    parser.add_argument("--api-url", type=str, help="Override API URL (default: https://haqita.pages.dev/api/v1)")
    args = parser.parse_args()

    setup_logging(args.verbose)
    cfg = load_config()

    if args.dry_run:
        logger.info("[DRY-RUN] No data will be sent to the API or R2.")
        logger.info("")

    api_url = get_api_url(args, cfg)
    logger.info(f"API URL: {api_url}")

    if not args.dry_run:
        secret = get_scraper_secret()
    else:
        secret = None  # Not needed for dry-run

    # ... batch sync, R2 upload, and state tracking are implemented in Todos 2-4
    # ... see subsequent todos for the full implementation

    logger.info("")
    logger.info("Sync complete.")


if __name__ == "__main__":
    main()
```

**References:** scripts/publish_html.py (template pattern: argparse, load_json, main()), scripts/config.py (load_config), scripts/common/http_client.py (retry_call), scripts/orchestrator.py (logging pattern), plan.md:85-105 (Stage 5 responsibilities)

**Acceptance criteria:**
- `scripts/sync_cloudflare.py` exists with the core structure shown above
- `python scripts/sync_cloudflare.py --dry-run` prints `[DRY-RUN] No data will be sent to the API or R2.` and `API URL: https://haqita.pages.dev/api/v1` and `Sync complete.`
- `python scripts/sync_cloudflare.py --help` prints usage with all three flags documented
- **Log message clarity:**
  - `[DRY-RUN]` prefix on dry-run messages (matching `publish_html.py` convention)
  - API URL is logged at start so the user knows where data is being sent
  - `Sync complete.` at the end confirms the script finished
  - Error messages include the env var name and how to set it
- **Failure handling:**
  - Missing `SCRAPER_SECRET` → log error with instructions, `sys.exit(1)` (only when not --dry-run)
  - Missing config → `load_config()` handles it (returns dict with defaults)
  - Invalid `--api-url` → URL is used as-is; API call will fail and be caught in Todo 2
- **Code quality:**
  - Follows `publish_html.py` pattern exactly: `sys.path.insert`, `ROOT`, `load_json`, argparse
  - Type hints on all function signatures
  - Docstrings on all functions
  - `retry_call` imported but not yet used (used in Todo 2)
  - No external dependencies beyond `requests` (already in `requirements.txt`) and stdlib
- **Unit test coverage:** Todo 6 tests the core functions
- **Documentation:** Todo 8 creates `docs/staging/sync-cloudflare.md`

**QA:**
- Happy: `python scripts/sync_cloudflare.py --dry-run` runs without errors → pass
- Failure: `python scripts/sync_cloudflare.py` without `SCRAPER_SECRET` → exits 1 with error message → pass

**Commit:** Y | feat(sync): add Stage 5 sync_cloudflare.py core structure

---

### Todo 2: Implement batch sync (stores, products, prices, promos)

**What to do:**

Add the batch sync logic to `scripts/sync_cloudflare.py`. This function reads the local JSON files and sends them to `POST /api/v1/sync/batch`.

Add these functions to `scripts/sync_cloudflare.py`:

```python
def build_sync_batch(history: dict, catalog: dict, promo_catalog_data: list, display_hints: dict) -> dict:
    """Build the sync batch payload from local JSON data.
    
    Reads:
      - history: database/price_history.json (snapshots with all fields)
      - catalog: database/product_catalog.json (catalog entries)
      - promo_catalog_data: output/html/promo_catalog.json (promo catalog)
      - display_hints: output/html/active_promo.json display_hints (store colors)
    
    Returns a dict matching the POST /api/v1/sync/batch schema:
      - source: "haqita-pipeline-v1"
      - sync_run_id: timestamp-based ID
      - stores: extracted from snapshots + display_hints colors
      - products: from catalog entries
      - prices: from snapshots (with JSON-encoded promo and standardized_promo)
      - promos: from promo_catalog_data
    """
    sync_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Extract unique stores from snapshots
    store_names = sorted(set(s["store"] for s in history.get("snapshots", []) if s.get("store")))
    store_colors = display_hints.get("store_colors", {})
    stores = [{"name": name, "color": store_colors.get(name)} for name in store_names]
    
    # Build products from catalog
    products = []
    for key, entry in catalog.items():
        products.append({
            "key": key,
            "name": entry.get("display_name", ""),
            "brand": entry.get("brand"),
            "category": None,  # Not in catalog
            "unit": entry.get("unit", ""),
            "unit_type": entry.get("unit_type"),
            "unit_value_g": entry.get("unit_value_g"),
        })
    
    # Build prices from snapshots
    prices = []
    for snap in history.get("snapshots", []):
        prices.append({
            "product_key": snap["product_key"],
            "store": snap["store"],
            "price": snap["price"],
            "effective_unit_price": snap["effective_unit_price"],
            "bundle_size": snap.get("bundle_size", 1),
            "promo": snap.get("promo"),  # Already an array or None in JSON
            "promo_type": snap.get("promo_type"),
            "valid_from": snap.get("valid_from"),
            "valid_until": snap.get("valid_until"),
            "image_path": snap.get("image_path"),
            "scrape_time": snap.get("scrape_time", ""),
            "date": snap["date"],
            "match_method": snap.get("match_method"),
            "match_confidence": snap.get("match_confidence"),
            "standardized_promo": snap.get("standardized_promo"),  # Already a dict or absent
        })
    
    # Build promos from promo_catalog_data
    promos = []
    for p in promo_catalog_data:
        promos.append({
            "key": p["key"],
            "display": p["display"],
            "type": p.get("type"),
            "discount_pct": p.get("discount_pct"),
            "product_count": p.get("product_count", 0),
            "stores": p.get("stores", {}),
            "example_products": p.get("example_products", []),
        })
    
    return {
        "source": "haqita-pipeline-v1",
        "sync_run_id": sync_run_id,
        "stores": stores,
        "products": products,
        "prices": prices,
        "promos": promos,
    }


def send_batch_sync(api_url: str, secret: str, batch: dict, dry_run: bool) -> dict:
    """Send the batch to POST /api/v1/sync/batch.
    
    Uses retry_call for transient HTTP errors.
    Returns the API response dict (with counts per table).
    On non-retryable error (4xx), logs the error and returns an error dict.
    """
    if dry_run:
        logger.info(f"  [DRY-RUN] Would sync: {len(batch['stores'])} stores, "
                     f"{len(batch['products'])} products, "
                     f"{len(batch['prices'])} prices, "
                     f"{len(batch['promos'])} promos")
        return {"dry_run": True, "stores": len(batch['stores']), "products": len(batch['products']),
                "prices": len(batch['prices']), "promos": len(batch['promos'])}
    
    url = f"{api_url}/sync/batch"
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    
    def do_post():
        resp = requests.post(url, json=batch, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError(f"Authentication failed (401). Check SCRAPER_SECRET.")
        if resp.status_code == 400:
            error_data = resp.json()
            raise ValueError(f"Validation error (400): {error_data.get('message', resp.text)}")
        if resp.status_code not in (200, 207):
            raise RuntimeError(f"API error ({resp.status_code}): {resp.text[:200]}")
        return resp.json()
    
    try:
        result = retry_call(do_post, max_retries=3, context="sync_batch")
        logger.info(f"  Batch sync response:")
        logger.info(f"    stores:   {result.get('stores', {})}")
        logger.info(f"    products: {result.get('products', {})}")
        logger.info(f"    prices:   {result.get('prices', {})}")
        logger.info(f"    promos:   {result.get('promos', {})}")
        if result.get("errors"):
            logger.warning(f"    errors:   {len(result['errors'])} rows failed")
            for err in result["errors"][:5]:
                logger.warning(f"      {err['table']}/{err['key']}: {err['error']}")
        return result
    except (ValueError, RuntimeError) as e:
        logger.error(f"  Batch sync failed: {e}")
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"  Batch sync failed (unexpected): {e}")
        return {"error": str(e)}
```

Update `main()` to call the batch sync:
```python
    # In main(), after getting api_url and secret:
    
    # Load source data
    history = load_json(DATABASE_DIR / "price_history.json", {"snapshots": [], "metadata": {}})
    catalog_raw = load_json(DATABASE_DIR / "product_catalog.json", {"catalog": {}})
    catalog = catalog_raw.get("catalog", {})
    promo_catalog_data = load_json(OUTPUT_DIR / "promo_catalog.json", [])
    active_promo = load_json(OUTPUT_DIR / "active_promo.json", {})
    display_hints = active_promo.get("display_hints", {})
    
    # Build and send batch
    logger.info("Building sync batch...")
    batch = build_sync_batch(history, catalog, promo_catalog_data, display_hints)
    logger.info(f"  Stores: {len(batch['stores'])}, Products: {len(batch['products'])}, "
                f"Prices: {len(batch['prices'])}, Promos: {len(batch['promos'])}")
    logger.info("")
    
    logger.info("Syncing batch to API...")
    batch_result = send_batch_sync(api_url, secret, batch, args.dry_run)
    if "error" in batch_result:
        logger.error("Batch sync failed. See error above.")
        if not args.dry_run:
            sys.exit(1)
    logger.info("")
```

**References:** plan.md:85-93 (Stage 5 responsibilities), plan.md:155-204 (sync/batch request body), scripts/common/http_client.py (retry_call pattern), database/price_history.json (snapshot schema), database/product_catalog.json (catalog schema), output/html/promo_catalog.json (promo schema)

**Acceptance criteria:**
- `python scripts/sync_cloudflare.py --dry-run --verbose` prints counts for stores, products, prices, promos without sending anything
- `python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1` (with local API running and `SCRAPER_SECRET` set) sends the batch and prints the API response with per-table counts
- `python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1` (without API running) logs error and exits 1
- Local files (`database/*.json`, `output/html/*.json`) are NOT modified by the sync
- **Log message clarity:**
  - `Building sync batch...` → `Stores: 2, Products: 589, Prices: 599, Promos: 50`
  - `Syncing batch to API...` → per-table response counts
  - Error messages include the HTTP status code and response body excerpt
  - `[DRY-RUN]` prefix on all dry-run messages
- **Failure handling:**
  - API returns 401 → `Authentication failed (401). Check SCRAPER_SECRET.` → exit 1
  - API returns 400 → `Validation error (400): <message>` → exit 1
  - API returns 500 → `retry_call` retries 3 times, then logs error → exit 1
  - API returns 207 (partial success) → logs errors but does NOT exit 1 (partial success is acceptable)
  - Network timeout → `retry_call` retries with exponential backoff
  - `database/price_history.json` missing → empty snapshots, sync sends 0 prices
- **Code quality:**
  - Follows `publish_html.py` pattern: `load_json`, `logger.info`, `sys.exit(1)` on error
  - Uses `retry_call` from `scripts/common/http_client.py` for HTTP retry logic
  - Uses `requests.post` with `timeout=30` (prevents indefinite hangs)
  - All data fields mapped from JSON source to API schema exactly
  - `standardized_promo` is passed as-is (already a dict in JSON, will be JSON-stringified by the API)
  - Type hints on all function signatures
  - Docstrings on all functions
  - No external dependencies beyond `requests` (already in requirements.txt)
- **Unit test coverage:** Todo 6 tests `build_sync_batch` with mock data and `send_batch_sync` with mocked `requests.post`
- **Documentation:** Todo 8 documents the sync flow

**QA:**
- Happy: `--dry-run --verbose` shows correct counts → pass
- Failure: API not running → error logged, exit 1, local files unchanged → pass

**Commit:** Y | feat(sync): implement batch sync for stores, products, prices, and promos

---

### Todo 3: Implement R2 image upload

**What to do:**

Add R2 image upload logic to `scripts/sync_cloudflare.py`. Uses boto3 S3-compatible API to upload images directly from the laptop to R2.

Add these functions:

```python
import boto3
from botocore.config import Config

def get_r2_client(cfg) -> boto3.client:
    """Create an S3-compatible client for R2.
    
    Reads credentials from environment:
      - R2_ACCESS_KEY_ID
      - R2_SECRET_ACCESS_KEY
      - R2_ENDPOINT (e.g., https://<account_id>.r2.cloudflarestorage.com)
    
    Returns a boto3 S3 client configured for R2.
    """
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    endpoint = os.getenv("R2_ENDPOINT")
    
    if not all([access_key, secret_key, endpoint]):
        logger.error("R2 credentials not set. Need R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT in .env")
        sys.exit(1)
    
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def compute_file_hash(path: Path) -> str:
    """Compute MD5 hash of a file for change detection."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def get_images_to_upload(history: dict, sync_state: dict) -> list[dict]:
    """Determine which images need uploading to R2.
    
    For each unique image_path in price history snapshots:
      - If the path doesn't exist locally → skip (log warning)
      - If the hash matches sync_state → skip (already uploaded)
      - Otherwise → include in upload list
    
    Returns list of: {"local_path": str, "r2_key": str, "hash": str}
    """
    # Extract unique image_paths from snapshots
    image_paths = set()
    for snap in history.get("snapshots", []):
        path = snap.get("image_path")
        if path:
            image_paths.add(path)
    
    uploaded_images = sync_state.get("uploaded_images", {})
    to_upload = []
    
    for local_path_str in sorted(image_paths):
        local_path = ROOT / local_path_str
        if not local_path.exists():
            logger.warning(f"  Image not found locally: {local_path_str}")
            continue
        
        file_hash = compute_file_hash(local_path)
        
        if local_path_str in uploaded_images and uploaded_images[local_path_str] == file_hash:
            # Already uploaded, unchanged
            continue
        
        # Convert local path to R2 key: database/scrape/superindo/20260613/abc.jpg → superindo/20260613/abc.jpg
        r2_key = local_path_str.replace("database/scrape/", "", 1)
        
        to_upload.append({
            "local_path": local_path_str,
            "r2_key": r2_key,
            "hash": file_hash,
            "abs_path": local_path,
        })
    
    return to_upload


def upload_images_to_r2(images: list[dict], r2_client, bucket_name: str, dry_run: bool) -> dict:
    """Upload images to R2. Returns dict of {local_path: r2_url} for successfully uploaded images.
    
    For each image:
      - Upload to R2 with key = r2_key
      - On success, record the public R2 URL
      - On failure, log error and continue with next image
    """
    results = {}
    for img in images:
        if dry_run:
            logger.info(f"  [DRY-RUN] Would upload: {img['local_path']} → r2://{bucket_name}/{img['r2_key']}")
            results[img["local_path"]] = f"https://pub-hash.r2.dev/{img['r2_key']}"
            continue
        
        try:
            r2_client.upload_file(
                str(img["abs_path"]),
                bucket_name,
                img["r2_key"],
            )
            # Construct public URL — the R2 public URL is configured in the dashboard
            # This URL should be read from config or env
            r2_public_url = os.getenv("R2_PUBLIC_URL", f"https://pub-hash.r2.dev")
            r2_url = f"{r2_public_url}/{img['r2_key']}"
            results[img["local_path"]] = r2_url
            logger.info(f"  Uploaded: {img['local_path']} → {r2_url}")
        except Exception as e:
            logger.error(f"  Upload failed: {img['local_path']}: {e}")
    
    return results
```

Add to `main()` after batch sync:
```python
    # R2 image upload
    logger.info("Checking images for R2 upload...")
    sync_state = load_sync_state()
    images_to_upload = get_images_to_upload(history, sync_state)
    
    if images_to_upload:
        logger.info(f"  {len(images_to_upload)} images to upload")
        if not args.dry_run:
            r2_client = get_r2_client(cfg)
            bucket_name = os.getenv("R2_BUCKET_NAME", "haqita-images")
            uploaded = upload_images_to_r2(images_to_upload, r2_client, bucket_name, args.dry_run)
        else:
            uploaded = upload_images_to_r2(images_to_upload, None, "haqita-images", args.dry_run)
        
        # Record R2 URLs via API
        if uploaded and not args.dry_run:
            logger.info("Recording R2 URLs in API...")
            image_manifest = {
                "images": [
                    {"local_path": k, "r2_key": v.split("/", 3)[-1], "r2_url": v}
                    for k, v in uploaded.items()
                ]
            }
            images_result = send_images_sync(api_url, secret, image_manifest, args.dry_run)
    else:
        logger.info("  No new or changed images to upload.")
```

Add `send_images_sync` function (similar to `send_batch_sync` but for `/sync/images`):
```python
def send_images_sync(api_url: str, secret: str, manifest: dict, dry_run: bool) -> dict:
    """Send image manifest to POST /api/v1/sync/images."""
    if dry_run:
        logger.info(f"  [DRY-RUN] Would record {len(manifest['images'])} image URLs")
        return {"dry_run": True}
    
    url = f"{api_url}/sync/images"
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    
    def do_post():
        resp = requests.post(url, json=manifest, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError("Authentication failed (401). Check SCRAPER_SECRET.")
        if resp.status_code not in (200, 207):
            raise RuntimeError(f"API error ({resp.status_code}): {resp.text[:200]}")
        return resp.json()
    
    try:
        result = retry_call(do_post, max_retries=3, context="sync_images")
        logger.info(f"  Images: {result.get('updated', 0)} updated, {result.get('skipped', 0)} skipped")
        return result
    except Exception as e:
        logger.error(f"  Image URL recording failed: {e}")
        return {"error": str(e)}
```

Add `boto3` to `requirements.txt`:
```
# Cloudflare sync
boto3>=1.34.0
```

**References:** plan.md:357-375 (Option A — R2 upload from laptop), plan.md:374 (sync_state.json for tracking), scripts/common/http_client.py (retry_call), boto3 S3 docs: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html

**Acceptance criteria:**
- `python scripts/sync_cloudflare.py --dry-run --verbose` shows which images would be uploaded (first run: all images, subsequent runs: only changed)
- `python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1` (with R2 credentials set) uploads images and records R2 URLs in D1
- Re-running sync shows `No new or changed images to upload.` (because sync_state.json tracks hashes)
- Changing an image file and re-running sync detects the change and re-uploads
- **Log message clarity:**
  - `Checking images for R2 upload...` → `N images to upload` or `No new or changed images to upload.`
  - `Uploaded: <local_path> → <r2_url>` per image
  - `Upload failed: <local_path>: <error>` on failure
  - `Recording R2 URLs in API...` → `Images: N updated, M skipped`
- **Failure handling:**
  - R2 credentials missing → log error with env var names, exit 1
  - R2 upload fails for one image → log error, continue with other images
  - API call to record R2 URLs fails → log error, but images are already in R2 (retry on next sync)
  - Local image file missing → log warning, skip that image
  - boto3 not installed → `ImportError` caught, log error with install instructions
- **Code quality:**
  - Uses `boto3.client` with S3-compatible API for R2
  - `compute_file_hash` uses MD5 for change detection (fast, sufficient for non-security use)
  - R2 key is derived from local path by stripping `database/scrape/` prefix
  - `upload_file` uses multipart upload for large files (handled by boto3)
  - `retry_call` wraps API calls for transient errors
  - Sync state is updated only after successful upload (see Todo 4)
  - Type hints on all function signatures
  - No `any` types
- **Unit test coverage:** Todo 6 tests `get_images_to_upload`, `compute_file_hash`, and `upload_images_to_r2` (with mocked boto3 client)
- **Documentation:** Todo 8 documents R2 upload process

**QA:**
- Happy: `--dry-run` shows correct image count → pass
- Failure: R2 credentials missing → error logged, exit 1 → pass
- Failure: Image file missing → warning logged, skipped → pass

**Commit:** Y | feat(sync): implement R2 image upload with change detection

---

### Todo 4: Implement sync state tracking

**What to do:**

Add sync state tracking to `scripts/sync_cloudflare.py`. The sync state file at `database/sync_state.json` records:
- `uploaded_images`: dict of `{local_path: file_hash}` — tracks which images have been uploaded and their hash at upload time
- `last_sync`: ISO datetime of the last successful sync
- `last_sync_run_id`: the sync_run_id from the last batch sync

Add this function to `scripts/sync_cloudflare.py`:

```python
def update_sync_state(state: dict, uploaded_images: dict, sync_run_id: str):
    """Update sync state after a successful sync.
    
    Args:
        state: current sync state dict
        uploaded_images: dict of {local_path: hash} for newly uploaded images
        sync_run_id: the sync_run_id from the batch
    """
    if "uploaded_images" not in state:
        state["uploaded_images"] = {}
    
    for img in uploaded_images:
        state["uploaded_images"][img["local_path"]] = img["hash"]
    
    state["last_sync_run_id"] = sync_run_id
    save_sync_state(state)
```

Update `main()` to save sync state after successful sync:

```python
    # After batch sync and image upload, update sync state
    if not args.dry_run:
        if "error" not in batch_result:
            # Update sync state with uploaded image hashes
            if images_to_upload:
                uploaded_hashes = [
                    {"local_path": img["local_path"], "hash": img["hash"]}
                    for img in images_to_upload
                ]
                update_sync_state(sync_state, uploaded_hashes, batch["sync_run_id"])
            else:
                # Still update last_sync timestamp
                sync_state["last_sync_run_id"] = batch["sync_run_id"]
                save_sync_state(sync_state)
            logger.info(f"  Sync state saved to {SYNC_STATE_FILE}")
```

**References:** plan.md:98 (sync_state.json for resume-friendly tracking), plan.md:374 (record uploaded image keys/hashes)

**Acceptance criteria:**
- After a successful sync, `database/sync_state.json` exists with `uploaded_images` dict, `last_sync` timestamp, and `last_sync_run_id`
- Re-running sync without changing images → `No new or changed images to upload.` (hashes match)
- Changing an image file and re-running sync → that image is re-uploaded and its hash is updated in sync_state
- `--dry-run` mode does NOT update sync state
- **Log message clarity:** `Sync state saved to database/sync_state.json` confirms state was persisted
- **Failure handling:**
  - Batch sync fails → sync state is NOT updated (so next run retries)
  - Image upload fails for some images → only successfully uploaded images have their hashes recorded
  - sync_state.json doesn't exist → created fresh with empty `uploaded_images`
  - sync_state.json is corrupt → caught by `load_json`, starts fresh
- **Code quality:**
  - `save_sync_state` writes atomically (write to temp, then rename — following `consolidation.py:atomic_write_json` pattern)
  - State is only updated after successful operations (no partial state)
  - `--dry-run` never modifies state (preview only)
  - Type hints on all function signatures
- **Unit test coverage:** Todo 6 tests `update_sync_state` and `load_sync_state`/`save_sync_state` round-trip
- **Documentation:** Todo 8 documents sync state file

**QA:**
- Happy: Run sync → sync_state.json created with correct hashes → pass
- Failure: Run sync with --dry-run → sync_state.json not modified → pass

**Commit:** Y | feat(sync): implement sync state tracking with image hash deduplication

---

### Todo 5: Wire into haqita.sh, haqita.bat, and orchestrator.py

**What to do:**

Wire the sync script into the existing pipeline infrastructure.

**1. Update `haqita.sh`:**

Add a new menu item. The current menu (line 211-219) has items [1]-[8] plus [0] Exit. Insert "Stage 5: Sync to Cloudflare" as item [6], shifting existing items:

Current:
```
  [1] Run full pipeline
  [2] Stage 1: Scrape
  [3] Stage 2: OCR
  [4] Stage 3: Consolidation
  [5] Stage 4: Publish HTML
  [6] Start HTTP server
  [7] Tests
  [8] Health check
  [0] Exit
```

Updated:
```
  [1] Run full pipeline
  [2] Stage 1: Scrape
  [3] Stage 2: OCR
  [4] Stage 3: Consolidation
  [5] Stage 4: Publish HTML
  [6] Stage 5: Sync to Cloudflare
  [7] Start HTTP server
  [8] Tests
  [9] Health check
  [0] Exit
```

Update the `case` statement (line 222-233) to match the new numbering:
```bash
case "$choice" in
    1) full_pipeline_menu ;;
    2) stage_scrape ;;
    3) stage_ocr ;;
    4) stage_consolidation ;;
    5) stage_publish_html ;;
    6) stage_cloudflare_sync ;;
    7) http_server ;;
    8) stage_tests ;;
    9) health_check ;;
    0) end_script ;;
    *) echo "Invalid choice. Press any key to try again..."; pause ;;
esac
```

Add the `stage_cloudflare_sync` function and its sub-functions (following the `stage_publish_html` pattern at line 622):
```bash
stage_cloudflare_sync() {
    while true; do
        clear
        echo "========================================"
        echo "  Stage 5: Sync to Cloudflare"
        echo "========================================"
        echo
        echo "  [1] Run sync"
        echo "  [2] Dry-run (preview)"
        echo "  [3] Verbose sync"
        echo "  [0] Back"
        echo
        read -rp "Your choice: " cf_choice
        case "$cf_choice" in
            1) cloudflare_sync_run; break ;;
            2) cloudflare_sync_dryrun; break ;;
            3) cloudflare_sync_verbose; break ;;
            0) break ;;
            *) echo "Invalid choice. Press any key to try again..."; pause ;;
        esac
    done
}

cloudflare_sync_run() {
    clear
    echo "========================================"
    echo "  Sync to Cloudflare"
    echo "========================================"
    echo
    $PYTHON scripts/sync_cloudflare.py
    echo
    pause
}

cloudflare_sync_dryrun() {
    clear
    echo "========================================"
    echo "  Sync to Cloudflare - Dry-run"
    echo "========================================"
    echo
    $PYTHON scripts/sync_cloudflare.py --dry-run
    echo
    pause
}

cloudflare_sync_verbose() {
    clear
    echo "========================================"
    echo "  Sync to Cloudflare - Verbose"
    echo "========================================"
    echo
    $PYTHON scripts/sync_cloudflare.py --verbose
    echo
    pause
}
```

Update `full_pipeline` function (line 262) to include Stage 5 in the echo:
```bash
echo "  Stage 1: Scrape all stores"
echo "  Stage 2: OCR all scraped images"
echo "  Stage 3: Consolidate (update database)"
echo "  Stage 4: Publish HTML"
echo "  Stage 5: Sync to Cloudflare"
```

**2. Update `haqita.bat`:**

Apply the same menu renumbering. Add `:STAGE_CLOUDFLARE_SYNC` label block following the `:STAGE_PUBLISH_HTML` pattern. Update the main menu goto table and the full pipeline echo.

**3. Update `scripts/orchestrator.py`:**

Add a `run_cloudflare_sync` function (following the `run_publish_html` pattern at lines 246-275):

```python
def run_cloudflare_sync(dry_run: bool, logger: logging.Logger) -> dict:
    """Run Stage 5: Sync to Cloudflare."""
    logger.info("=== Stage 5: Sync to Cloudflare ===")
    sync_script = SCRIPTS / "sync_cloudflare.py"
    
    if not sync_script.exists():
        logger.error("sync_cloudflare.py not found at %s", sync_script)
        return {"status": "error", "error": "sync script not found"}
    
    cmd = [sys.executable, str(sync_script)]
    if dry_run:
        cmd.append("--dry-run")
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    
    if result.returncode != 0:
        logger.error("Stage 5 failed: %s", result.stderr.strip()[:200])
        return {"status": "error", "error": result.stderr.strip()[:200]}
    
    if result.stdout.strip():
        for line in result.stdout.splitlines():
            print(f"  {line}")
    
    status = {"status": "complete"}
    if dry_run:
        status["status"] = "dry_run"
    
    write_stage_status("cloudflare_sync", status, logger)
    return status
```

Add `"cloudflare-sync"` to the `--stage` choices (line 281):
```python
parser.add_argument("--stage", choices=["scrape", "ocr", "consolidate", "publish-html", "cloudflare-sync"], ...)
```

Add the call in the `--full` branch (after `run_publish_html`):
```python
cf_sync_result = run_cloudflare_sync(args.dry_run, logger)
if cf_sync_result.get("status") == "error":
    logger.error("Stage 5 failed. Use --resume to continue from here.")
    sys.exit(1)
```

Add resume check in `--full --resume` branch:
```python
cf_sync_status = read_stage_status("cloudflare_sync")
cf_sync_done = cf_sync_status and cf_sync_status.get("status") in ("complete", "dry_run")
if not cf_sync_done:
    logger.info("Resuming at Stage 5: Sync to Cloudflare")
    cf_sync_result = run_cloudflare_sync(args.dry_run, logger)
```

**References:** haqita.sh:204-235 (menu structure), haqita.sh:622-645 (stage_publish_html pattern), scripts/orchestrator.py:246-275 (run_publish_html pattern), scripts/orchestrator.py:281 (--stage choices), scripts/orchestrator.py:314-366 (resume logic), scripts/orchestrator.py:368-383 (full pipeline), haqita.bat:18-39 (menu and goto table)

**Acceptance criteria:**
- `./haqita.sh` shows `[6] Stage 5: Sync to Cloudflare` in the menu
- Selecting [6] shows the submenu with Run, Dry-run, Verbose, Back
- Selecting [1] Run sync executes `python scripts/sync_cloudflare.py`
- Selecting [2] Dry-run executes `python scripts/sync_cloudflare.py --dry-run`
- `python scripts/orchestrator.py --stage cloudflare-sync` runs the sync
- `python scripts/orchestrator.py --full` includes Stage 5 after Stage 4
- `python scripts/orchestrator.py --full --resume` can resume from Stage 5
- **Log message clarity:** Menu items follow the existing `========` banner pattern; orchestrator logs `=== Stage 5: Sync to Cloudflare ===`
- **Failure handling:**
  - Sync script not found → orchestrator logs error, returns `{"status": "error"}`
  - Sync script exits non-zero → orchestrator logs stderr, returns error status
  - `--resume` skips Stage 5 if `cloudflare_sync_status.json` shows complete
- **Code quality:**
  - `haqita.sh` follows existing function naming: `stage_cloudflare_sync`, `cloudflare_sync_run`, etc.
  - `orchestrator.py` follows existing `run_*` function pattern exactly
  - `write_stage_status("cloudflare_sync", ...)` writes to `output/stage_results/cloudflare_sync_status.json`
  - All menu numbers shifted consistently (no gaps, no duplicates)
- **Unit test coverage:** N/A — shell script and orchestrator changes are verified manually
- **Documentation:** Todo 8 documents the menu integration

**QA:**
- Happy: `./haqita.sh` → [6] → [2] Dry-run → shows sync preview → pass
- Failure: `./haqita.sh` → [6] → [1] Run sync without SCRAPER_SECRET → error message → pass

**Commit:** Y | feat(pipeline): wire Stage 5 sync into haqita.sh, haqita.bat, and orchestrator

---

### Todo 6: Write unit tests

**What to do:**

Create `tests/cloudflare/test_sync_cloudflare.py` following the existing test pattern (class-based `Test*` with `test_*` methods, `unittest.mock.patch`, `assert`, `tmp_path`, `capsys`).

```python
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestBuildSyncBatch:
    """Tests for build_sync_batch()."""

    def test_extracts_stores_from_snapshots(self):
        """Should return unique store names from snapshots."""
        # ... create mock history with snapshots from Lotte and Superindo
        # ... call build_sync_batch(history, {}, [], {})
        # ... assert len(batch["stores"]) == 2
        # ... assert "Lotte" in [s["name"] for s in batch["stores"]]

    def test_includes_store_colors_from_display_hints(self):
        """Should include color from display_hints."""
        # ... create mock history + display_hints with store_colors
        # ... assert the store entry has the correct color

    def test_maps_catalog_fields_to_products(self):
        """Should map canonical_key->key, display_name->name, etc."""
        # ... create mock catalog with one entry
        # ... assert the product has correct field mapping

    def test_maps_snapshot_fields_to_prices(self):
        """Should map all snapshot fields to price entries."""
        # ... create mock history with one snapshot
        # ... assert the price entry has all required fields

    def test_preserves_promo_as_array_or_none(self):
        """Should pass promo as-is (array or None)."""
        # ... test with promo=["DISKON 20%"] and promo=None

    def test_preserves_standardized_promo_as_dict_or_none(self):
        """Should pass standardized_promo as-is."""
        # ... test with standardized_promo dict and without

    def test_maps_promo_catalog_fields(self):
        """Should map promo catalog entries to promos array."""
        # ... create mock promo_catalog_data
        # ... assert the promo entry has correct fields

    def test_generates_sync_run_id(self):
        """Should include a sync_run_id string."""
        # ... assert "sync_run_id" in batch and len(batch["sync_run_id"]) > 0

    def test_source_is_haqita_pipeline(self):
        """Should set source to 'haqita-pipeline-v1'."""
        # ... assert batch["source"] == "haqita-pipeline-v1"

    def test_handles_empty_history(self):
        """Should work with empty snapshots."""
        # ... create mock history with empty snapshots
        # ... assert batch["stores"] == [] and batch["prices"] == []


class TestSendBatchSync:
    """Tests for send_batch_sync()."""

    @patch('scripts.sync_cloudflare.requests.post')
    @patch('scripts.sync_cloudflare.retry_call')
    def test_sends_batch_to_api(self, mock_retry, mock_post):
        """Should POST the batch to /sync/batch with auth header."""
        # ... mock retry_call to return a success response
        # ... call send_batch_sync(url, secret, batch, dry_run=False)
        # ... assert requests.post was called with correct URL and headers

    def test_dry_run_does_not_send(self, capsys):
        """Should not send anything in dry-run mode."""
        # ... call send_batch_sync(url, secret, batch, dry_run=True)
        # ... assert [DRY-RUN] in captured output
        # ... assert requests.post was NOT called

    @patch('scripts.sync_cloudflare.requests.post')
    def test_returns_error_on_401(self, mock_post):
        """Should return error dict on 401."""
        # ... mock response with status 401
        # ... assert "error" in result

    @patch('scripts.sync_cloudflare.requests.post')
    def test_returns_error_on_400(self, mock_post):
        """Should return error dict on 400."""
        # ... mock response with status 400 and error message
        # ... assert "error" in result and "Validation" in result["error"]


class TestGetImagesToUpload:
    """Tests for get_images_to_upload()."""

    def test_returns_all_images_on_first_run(self, tmp_path):
        """Should return all images when sync_state is empty."""
        # ... create mock history with image_paths pointing to real files in tmp_path
        # ... call get_images_to_upload(history, {})
        # ... assert all images are returned

    def test_skips_already_uploaded_unchanged(self, tmp_path):
        """Should skip images whose hash matches sync_state."""
        # ... create mock history + sync_state with matching hash
        # ... assert to_upload is empty

    def test_includes_changed_images(self, tmp_path):
        """Should include images whose hash differs from sync_state."""
        # ... create mock history + sync_state with wrong hash
        # ... assert the image is in to_upload

    def test_skips_missing_local_files(self, tmp_path):
        """Should skip image_paths that don't exist locally."""
        # ... create mock history with non-existent image_path
        # ... assert to_upload is empty

    def test_converts_local_path_to_r2_key(self, tmp_path):
        """Should strip 'database/scrape/' prefix for r2_key."""
        # ... assert r2_key == "superindo/20260613/abc.jpg" for path "database/scrape/superindo/20260613/abc.jpg"


class TestComputeFileHash:
    """Tests for compute_file_hash()."""

    def test_returns_md5_hex_string(self, tmp_path):
        """Should return a 32-character hex string."""
        # ... create a file with known content
        # ... call compute_file_hash
        # ... assert len(result) == 32 and all chars are hex

    def test_same_content_same_hash(self, tmp_path):
        """Should return same hash for same content."""
        # ... create two files with same content
        # ... assert hashes are equal

    def test_different_content_different_hash(self, tmp_path):
        """Should return different hash for different content."""
        # ... create two files with different content
        # ... assert hashes differ


class TestSyncState:
    """Tests for load_sync_state() and save_sync_state()."""

    def test_load_returns_empty_state_when_file_missing(self, tmp_path, monkeypatch):
        """Should return default state when sync_state.json doesn't exist."""
        # ... monkeypatch SYNC_STATE_FILE to tmp_path / "nonexistent.json"
        # ... call load_sync_state()
        # ... assert result has empty uploaded_images

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """Should persist and restore sync state."""
        # ... monkeypatch SYNC_STATE_FILE to tmp_path / "sync_state.json"
        # ... save a state with uploaded_images
        # ... load it back
        # ... assert the state matches

    def test_save_includes_last_sync_timestamp(self, tmp_path, monkeypatch):
        """Should include last_sync timestamp in saved state."""
        # ... save state
        # ... load it
        # ... assert "last_sync" is present and is an ISO datetime


class TestUpdateSyncState:
    """Tests for update_sync_state()."""

    def test_adds_new_image_hashes(self):
        """Should add new image hashes to uploaded_images."""
        # ... call update_sync_state with existing state + new images
        # ... assert the new hashes are in state["uploaded_images"]

    def test_preserves_existing_image_hashes(self):
        """Should not remove existing hashes when adding new ones."""
        # ... call update_sync_state with existing state + new images
        # ... assert existing hashes are still present

    def test_updates_last_sync_run_id(self):
        """Should update last_sync_run_id."""
        # ... call update_sync_state with a sync_run_id
        # ... assert state["last_sync_run_id"] matches
```

**References:** tests/matching/test_publish_html.py (test pattern template), tests/matching/test_consolidate.py (mocking patterns), scripts/sync_cloudflare.py (module under test)

**Acceptance criteria:**
- `python -m pytest tests/cloudflare/test_sync_cloudflare.py -v` passes all tests
- **Log message clarity:** pytest output shows each test name and pass/fail status
- **Failure handling:**
  - Tests for empty/missing data must pass
  - Tests for API errors (401, 400) must verify error handling
  - Tests for missing local files must verify graceful skipping
- **Code quality:**
  - Follow `tests/matching/test_publish_html.py` pattern: class-based `Test*` with `test_*` methods
  - Use `unittest.mock.patch` for mocking `requests.post` and `retry_call`
  - Use `tmp_path` for temp file operations
  - Use `monkeypatch` for env/path overrides
  - `sys.path.insert(0, ...)` at top for imports
  - All assertions use plain `assert`
  - No `@pytest.mark.skip`
- **Unit test coverage:** Minimum test count:
  - TestBuildSyncBatch: 10 tests
  - TestSendBatchSync: 4 tests
  - TestGetImagesToUpload: 5 tests
  - TestComputeFileHash: 3 tests
  - TestSyncState: 3 tests
  - TestUpdateSyncState: 3 tests
  - **Total: 28 tests minimum**

**QA:**
- Happy: `python -m pytest tests/cloudflare/test_sync_cloudflare.py -v` shows 28+ passed → pass
- Failure: Any test fails → fix the sync script, not the test

**Commit:** Y | test(cloudflare): add unit tests for sync_cloudflare.py

---

### Todo 7: Update .env.example, config.yaml, requirements.txt

**What to do:**

**1. Update `.env.example`** — add Cloudflare sync env vars:
```env
# Copy to .env and fill in values. Never commit .env to git.

# Required: Gemini API key for OCR and AI verifier
# Get your free key at: https://aistudio.google.com/apikey
# GEMINI_API_KEY=your_key_here

# Cloudflare sync (Stage 5)
# Get from Cloudflare dashboard → Workers & Pages → your worker → Settings → Secrets
# SCRAPER_SECRET=your_scraper_secret_here

# R2 image upload (S3-compatible API)
# Get from Cloudflare dashboard → R2 → Manage R2 API Tokens
# R2_ACCESS_KEY_ID=your_r2_access_key
# R2_SECRET_ACCESS_KEY=your_r2_secret_key
# R2_ENDPOINT=https://your_account_id.r2.cloudflarestorage.com
# R2_BUCKET_NAME=haqita-images
# R2_PUBLIC_URL=https://pub-your-hash.r2.dev

# Optional: override default API URL
# CLOUDFLARE_API_URL=https://haqita.pages.dev/api/v1
```

**2. Update `config.yaml`** — add cloudflare_sync section:
```yaml
cloudflare_sync:
  api_url: https://haqita.pages.dev/api/v1   # Override with --api-url or CLOUDFLARE_API_URL env
```

**3. Update `requirements.txt`** — add boto3:
```
# Cloudflare sync (Stage 5)
boto3>=1.34.0
```

**References:** .env.example (existing pattern — commented out, with instructions), config.yaml (existing structure), requirements.txt (existing pattern — grouped by purpose with comments)

**Acceptance criteria:**
- `.env.example` includes all 6 new env vars with comments explaining where to get them
- `config.yaml` has `cloudflare_sync:` section with `api_url`
- `requirements.txt` has `boto3>=1.34.0` in a new `# Cloudflare sync` group
- `pip install -r requirements.txt` installs boto3 successfully
- **Log message clarity:** `.env.example` comments explain where each value comes from
- **Failure handling:** Missing env vars are detected by `sync_cloudflare.py` with clear error messages
- **Code quality:**
  - `.env.example` follows existing pattern: all values commented out, with instructions
  - `config.yaml` follows existing pattern: top-level section with scalar values
  - `requirements.txt` follows existing pattern: `>=` version pinning, grouped with comments
- **Unit test coverage:** N/A — config file updates

**QA:**
- Happy: All files updated with correct values → pass
- Failure: `pip install -r requirements.txt` fails → check boto3 version

**Commit:** Y | chore: add Cloudflare sync config to .env.example, config.yaml, and requirements.txt

---

### Todo 8: Write documentation

**What to do:**

Create `docs/staging/sync-cloudflare.md` following the existing documentation pattern (see `docs/staging/publish-html.md` for the template).

**Document structure:**
1. **H1 title:** `# Stage 5: Sync to Cloudflare`
2. **Overview table:** Input, Output, Dry-run, Verbose, Menu item
3. **Architecture section:** ASCII diagram showing data flow from pipeline output → sync script → Cloudflare API → D1/R2
4. **How It Works section:**
   - Step 1: Read local JSON files (price_history.json, product_catalog.json, promo_catalog.json, active_promo.json)
   - Step 2: Build sync batch payload (stores, products, prices, promos)
   - Step 3: POST batch to `/api/v1/sync/batch` with Bearer auth
   - Step 4: Compute MD5 hashes of brochure images, compare with sync_state.json
   - Step 5: Upload new/changed images to R2 via S3-compatible API
   - Step 6: POST image manifest to `/api/v1/sync/images` to record R2 URLs
   - Step 7: Update sync_state.json with uploaded image hashes and last_sync timestamp
5. **Sync State section:** Explain `database/sync_state.json` — uploaded_images dict, last_sync, last_sync_run_id
6. **Configuration section:** Table of env vars (SCRAPER_SECRET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET_NAME, R2_PUBLIC_URL) and config.yaml cloudflare_sync section
7. **Usage section:** Menu commands (haqita.sh [6], haqita.bat [6]), CLI commands (--dry-run, --verbose, --api-url)
8. **Failure Handling section:** Table of failure modes (API down, R2 credentials missing, image not found, partial success) and how the script handles each
9. **Idempotency section:** Explain INSERT OR REPLACE on D1, image hash deduplication, re-running sync is safe

**References:** docs/staging/publish-html.md (documentation template), plan.md:85-105 (Stage 5 design), scripts/sync_cloudflare.py (actual implementation)

**Acceptance criteria:**
- `docs/staging/sync-cloudflare.md` exists with all 9 sections
- All env vars, config keys, and CLI flags documented
- **Log message clarity:** Documentation includes example output for --dry-run and --verbose modes
- **Failure handling:** Failure modes table covers all common issues
- **Code quality:** Matches existing `docs/staging/*.md` style — ATX headings, pipe tables, fenced code blocks
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Open `docs/staging/sync-cloudflare.md` — all sections present → pass
- Failure: Missing section → add it

**Commit:** Y | docs: add Stage 5 sync to Cloudflare documentation

---

### Todo 9: Final verification

**What to do:**

Run the complete verification checklist:

1. Verify dry-run:
   ```bash
   python scripts/sync_cloudflare.py --dry-run --verbose
   ```
   **Expected:** Shows counts for stores, products, prices, promos, and images to upload. No API calls made. No files modified.

2. Verify actual sync (requires local API running):
   ```bash
   # Start local API
   cd web && npx wrangler pages dev --local &
   sleep 5
   
   # Set SCRAPER_SECRET
   export SCRAPER_SECRET=dev-secret-for-local-testing
   
   # Run sync
   python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1 --verbose
   
   # Kill API
   kill %1
   ```
   **Expected:** Batch sync succeeds with counts. R2 upload skipped if no R2 credentials. Sync state saved.

3. Verify idempotency:
   ```bash
   # Run sync again
   export SCRAPER_SECRET=dev-secret-for-local-testing
   cd web && npx wrangler pages dev --local &
   sleep 5
   python scripts/sync_cloudflare.py --api-url http://localhost:8787/api/v1 --verbose
   kill %1
   ```
   **Expected:** Same data counts. `No new or changed images to upload.`

4. Verify failure handling:
   ```bash
   # API not running
   python scripts/sync_cloudflare.py --api-url http://localhost:9999/api/v1
   ```
   **Expected:** Error logged, exit 1, local files unchanged.

5. Verify menu integration:
   ```bash
   ./haqita.sh
   # Select [6] Stage 5: Sync to Cloudflare
   # Select [2] Dry-run
   ```
   **Expected:** Shows sync dry-run output.

6. Verify orchestrator:
   ```bash
   python scripts/orchestrator.py --stage cloudflare-sync --dry-run
   ```
   **Expected:** Runs sync in dry-run mode.

7. Run unit tests:
   ```bash
   python -m pytest tests/cloudflare/ -v
   ```
   **Expected:** All tests pass (both seed_d1.py and sync_cloudflare.py tests).

**References:** All previous todos

**Acceptance criteria:**
- All 7 verification steps pass
- Idempotency confirmed — second sync shows no new data
- Failure handling confirmed — error logged, local files unchanged
- **Log message clarity:** All log messages are clear and actionable
- **Failure handling:** Script exits 1 on error, local files are never modified
- **Documentation:** Verification confirms `docs/staging/sync-cloudflare.md` is accurate

**QA:**
- Happy: All steps pass → Phase 5 complete
- Failure: Any step fails → fix the issue in the corresponding todo

**Commit:** Y | test: verify Stage 5 sync script end-to-end

---

## Final verification wave
- [ ] F1. Plan compliance audit — all Must have items delivered, no Must NOT have items present
- [ ] F2. Code quality review — `python -m pytest tests/cloudflare/ -v` all pass, follows existing script patterns, type hints, docstrings
- [ ] F3. Real manual QA — dry-run shows correct counts, actual sync populates D1, idempotency verified, failure handling verified
- [ ] F4. Scope fidelity — no changes to Stages 1-4, no index.html changes, no frontend changes

---

## Commit strategy
- One commit per todo (Todos 1-9)
- Commit messages: `feat(sync):`, `test(cloudflare):`, `chore:`, `docs:`, `test:`
- Todo 5 (menu wiring) can be split into separate commits for haqita.sh, haqita.bat, and orchestrator.py if desired

---

## Success criteria
1. `python scripts/sync_cloudflare.py --dry-run --verbose` shows correct counts for all tables and images
2. `python scripts/sync_cloudflare.py --api-url <url>` sends batch to API and uploads images to R2
3. Re-running sync is idempotent — no duplicates in D1, no re-uploads to R2
4. Sync failures log errors and exit 1 without modifying local files
5. `haqita.sh` [6] and `haqita.bat` [6] menu items work correctly
6. `orchestrator.py --stage cloudflare-sync` and `--full` include Stage 5
7. `python -m pytest tests/cloudflare/ -v` passes 28+ tests for sync script
8. `.env.example`, `config.yaml`, and `requirements.txt` updated with Cloudflare sync config
9. `docs/staging/sync-cloudflare.md` documents the sync process with all sections
