"""
Haqita Stage 5: Sync to Cloudflare.

Reads the latest pipeline output and pushes data to the Cloudflare API.
Uploads new/changed brochure images to R2. Records R2 URLs in D1 via the API.
Does NOT modify any local files in database/ or output/.

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
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common.http_client import retry_call
from scripts.config import load_config

import requests

try:
    import boto3
    from botocore.config import Config
except ImportError:  # pragma: no cover
    boto3 = None
    Config = None

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = ROOT / "database"
OUTPUT_DIR = ROOT / "output" / "html"
SCRAPE_DIR = DATABASE_DIR / "scrape"
SYNC_STATE_FILE = DATABASE_DIR / "sync_state.json"

# Default API URL — overridden by --api-url or config.yaml cloudflare_sync.api_url
DEFAULT_API_URL = "https://haqita.pages.dev/api/v1"


def load_json(path: Path, default: Any = None) -> Any:
    """Load a JSON file, returning ``default`` if it does not exist or is empty."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def load_sync_state() -> dict:
    """Load sync state from ``database/sync_state.json``.

    Returns a dict with ``uploaded_images`` and ``last_sync`` keys. If the state
    file is missing or corrupt, a fresh empty state is returned so the sync can
    proceed from scratch.
    """
    try:
        return load_json(
            SYNC_STATE_FILE,
            {"uploaded_images": {}, "last_sync": None, "last_sync_run_id": None},
        )
    except json.JSONDecodeError as exc:
        logger.warning("Sync state file is corrupt (%s). Starting fresh.", exc)
        return {"uploaded_images": {}, "last_sync": None, "last_sync_run_id": None}


def save_sync_state(state: dict) -> None:
    """Persist sync state to ``database/sync_state.json`` atomically.

    Writes to a temporary file in the same directory and then renames it into
    place so a crash mid-write cannot leave a partially written state file.
    """
    state["last_sync"] = datetime.now().isoformat()
    temp_fd, temp_path = tempfile.mkstemp(
        dir=SYNC_STATE_FILE.parent, prefix=".sync_state_", suffix=".tmp"
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(temp_path, SYNC_STATE_FILE)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def update_sync_state(
    state: dict, uploaded_images: list[dict], sync_run_id: str
) -> None:
    """Update sync state after a successful sync.

    Args:
        state: Current sync state dict (mutated in place).
        uploaded_images: List of ``{"local_path": str, "hash": str}`` entries for
            images that were uploaded in this run.
        sync_run_id: The ``sync_run_id`` from the batch payload.
    """
    if "uploaded_images" not in state:
        state["uploaded_images"] = {}

    for img in uploaded_images:
        state["uploaded_images"][img["local_path"]] = img["hash"]

    state["last_sync_run_id"] = sync_run_id
    save_sync_state(state)


def get_api_url(args: argparse.Namespace, cfg: dict) -> str:
    """Determine API URL from ``--api-url``, env var, or config fallback."""
    if args.api_url:
        return args.api_url.rstrip("/")
    env_url = os.getenv("CLOUDFLARE_API_URL")
    if env_url:
        return env_url.rstrip("/")
    cf_cfg = cfg.get("cloudflare_sync", {})
    return cf_cfg.get("api_url", DEFAULT_API_URL).rstrip("/")


def get_scraper_secret() -> str:
    """Get the Bearer token from the ``SCRAPER_SECRET`` environment variable."""
    secret = os.getenv("SCRAPER_SECRET")
    if not secret:
        logger.error("SCRAPER_SECRET environment variable is not set.")
        logger.error("Set it in .env or export SCRAPER_SECRET=your_secret")
        sys.exit(1)
    return secret


def setup_logging(verbose: bool) -> None:
    """Configure the root logger level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", force=True)


def build_sync_batch(
    history: dict, catalog: dict, promo_catalog_data: list, display_hints: dict
) -> dict:
    """Build the sync batch payload from local JSON data.

    Reads:
      - ``history``: ``database/price_history.json`` (snapshots with all fields)
      - ``catalog``: ``database/product_catalog.json`` catalog entries
      - ``promo_catalog_data``: ``output/html/promo_catalog.json``
      - ``display_hints``: ``output/html/active_promo.json`` ``display_hints``

    Returns a dict matching the ``POST /api/v1/sync/batch`` schema:
      - ``source``: ``"haqita-pipeline-v1"``
      - ``sync_run_id``: timestamp-based ID
      - ``stores``: extracted from snapshots plus display_hints colors
      - ``products``: from catalog entries
      - ``prices``: from snapshots (promo and standardized_promo passed as-is)
      - ``promos``: from promo_catalog_data
    """
    sync_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    store_names = sorted(
        {s["store"] for s in history.get("snapshots", []) if s.get("store")}
    )
    store_colors = display_hints.get("store_colors", {})
    stores = [{"name": name, "color": store_colors.get(name)} for name in store_names]

    products = []
    for key, entry in catalog.items():
        products.append(
            {
                "key": entry.get("canonical_key") or key,
                "name": entry.get("display_name", ""),
                "brand": entry.get("brand"),
                "category": None,  # Not currently present in the catalog
                "unit": entry.get("unit", ""),
                "unit_type": entry.get("unit_type"),
                "unit_value_g": entry.get("unit_value_g"),
            }
        )

    prices = []
    for snap in history.get("snapshots", []):
        prices.append(
            {
                "product_key": snap["product_key"],
                "store": snap["store"],
                "price": snap["price"],
                "effective_unit_price": snap["effective_unit_price"],
                "bundle_size": snap.get("bundle_size", 1),
                "promo": snap.get("promo"),
                "promo_type": snap.get("promo_type"),
                "valid_from": snap.get("valid_from"),
                "valid_until": snap.get("valid_until"),
                "image_path": snap.get("image_path"),
                "scrape_time": snap.get("scrape_time", ""),
                "date": snap["date"],
                "match_method": snap.get("match_method"),
                "match_confidence": snap.get("match_confidence"),
                "standardized_promo": snap.get("standardized_promo"),
            }
        )

    promos = []
    for p in promo_catalog_data:
        promos.append(
            {
                "key": p["key"],
                "display": p["display"],
                "type": p.get("type"),
                "discount_pct": p.get("discount_pct"),
                "product_count": p.get("product_count", 0),
                "stores": p.get("stores", {}),
                "example_products": p.get("example_products", []),
            }
        )

    return {
        "source": "haqita-pipeline-v1",
        "sync_run_id": sync_run_id,
        "dummy_data": os.getenv("DUMMY_DATA") == "1",
        "stores": stores,
        "products": products,
        "prices": prices,
        "promos": promos,
    }


def send_batch_sync(api_url: str, secret: str, batch: dict, dry_run: bool) -> dict:
    """Send the batch payload to ``POST /api/v1/sync/batch``.

    Uses ``retry_call`` from ``scripts.common.http_client`` for transient HTTP
    errors. Returns the API response dict on success, or an error dict when a
    non-retryable error (401/400) occurs.
    """
    if dry_run:
        dummy_flag = batch.get("dummy_data", False)
        logger.info(
            "  [DRY-RUN] Would sync: %d stores, %d products, %d prices, %d promos (dummy_data=%s)",
            len(batch["stores"]),
            len(batch["products"]),
            len(batch["prices"]),
            len(batch["promos"]),
            dummy_flag,
        )
        return {
            "dry_run": True,
            "stores": len(batch["stores"]),
            "products": len(batch["products"]),
            "prices": len(batch["prices"]),
            "promos": len(batch["promos"]),
        }

    url = f"{api_url}/sync/batch"
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}

    def do_post() -> dict:
        resp = requests.post(url, json=batch, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError("Authentication failed (401). Check SCRAPER_SECRET.")
        if resp.status_code == 400:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"message": resp.text}
            raise ValueError(
                f"Validation error (400): {error_data.get('message', resp.text)}"
            )
        if resp.status_code not in (200, 207):
            raise RuntimeError(f"API error ({resp.status_code}): {resp.text[:200]}")
        return resp.json()

    try:
        result = retry_call(do_post, max_retries=3, context="sync_batch")
        logger.info("  Batch sync response:")
        logger.info("    stores:   %s", result.get("stores", {}))
        logger.info("    products: %s", result.get("products", {}))
        logger.info("    prices:   %s", result.get("prices", {}))
        logger.info("    promos:   %s", result.get("promos", {}))
        if result.get("errors"):
            logger.warning("    errors:   %d rows failed", len(result["errors"]))
            for err in result["errors"][:5]:
                logger.warning(
                    "      %s/%s: %s",
                    err.get("table", "?"),
                    err.get("key", "?"),
                    err.get("error", "unknown"),
                )
        return result
    except (ValueError, RuntimeError) as exc:
        logger.error("  Batch sync failed: %s", exc)
        return {"error": str(exc)}
    except Exception as exc:
        logger.error("  Batch sync failed (unexpected): %s", exc)
        return {"error": str(exc)}


def get_r2_client(cfg: dict) -> boto3.client:  # type: ignore[name-defined]
    """Create an S3-compatible boto3 client for Cloudflare R2.

    Reads credentials from environment variables:
      - ``R2_ACCESS_KEY_ID``
      - ``R2_SECRET_ACCESS_KEY``
      - ``R2_ENDPOINT`` (e.g., ``https://<account_id>.r2.cloudflarestorage.com``)

    Returns a boto3 S3 client configured with signature version ``s3v4`` and
    region ``auto``.
    """
    if boto3 is None or Config is None:
        logger.error("boto3 is not installed. Run: pip install boto3>=1.34.0")
        sys.exit(1)

    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    endpoint = os.getenv("R2_ENDPOINT")

    if not all([access_key, secret_key, endpoint]):
        logger.error(
            "R2 credentials not set. Need R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, and R2_ENDPOINT in .env"
        )
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def compute_file_hash(path: Path) -> str:
    """Compute the MD5 hex digest of a file for change detection."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_images_to_upload(history: dict, sync_state: dict) -> list[dict]:
    """Determine which brochure images need uploading to R2.

    For each unique ``image_path`` found in the price history snapshots:
      - Skip paths that do not exist locally (with a warning).
      - Skip files whose MD5 hash matches the recorded hash in ``sync_state``.
      - Include everything else, converting the local path to an R2 key by
        stripping the ``database/scrape/`` prefix.

    Returns a list of dicts with keys ``local_path``, ``r2_key``, ``hash``,
    and ``abs_path``.
    """
    image_paths = {
        s["image_path"] for s in history.get("snapshots", []) if s.get("image_path")
    }
    uploaded_images = sync_state.get("uploaded_images", {})
    to_upload = []

    for local_path_str in sorted(image_paths):
        local_path = ROOT / local_path_str
        if not local_path.exists():
            logger.warning("  Image not found locally: %s", local_path_str)
            continue

        file_hash = compute_file_hash(local_path)

        if (
            local_path_str in uploaded_images
            and uploaded_images[local_path_str] == file_hash
        ):
            continue

        r2_key = local_path_str.replace("database/scrape/", "", 1)
        # Prefix with dummy/ when DUMMY_DATA is set
        if os.getenv("DUMMY_DATA") == "1":
            r2_key = f"dummy/{r2_key}"
        to_upload.append(
            {
                "local_path": local_path_str,
                "r2_key": r2_key,
                "hash": file_hash,
                "abs_path": local_path,
            }
        )

    return to_upload


def upload_images_to_r2(
    images: list[dict],
    r2_client: boto3.client,
    bucket_name: str,
    dry_run: bool,  # type: ignore[name-defined]
) -> dict:
    """Upload images to R2 and return a mapping of local path to public R2 URL.

    Each image is uploaded using its pre-computed ``r2_key``. Failures for a
    single image are logged but do not abort the rest of the upload queue.
    """
    results = {}
    for img in images:
        if dry_run:
            logger.info(
                "  [DRY-RUN] Would upload: %s -> r2://%s/%s",
                img["local_path"],
                bucket_name,
                img["r2_key"],
            )
            results[img["local_path"]] = f"https://pub-hash.r2.dev/{img['r2_key']}"
            continue

        try:
            r2_client.upload_file(
                str(img["abs_path"]),
                bucket_name,
                img["r2_key"],
            )
            r2_public_url = os.getenv("R2_PUBLIC_URL", "https://pub-hash.r2.dev")
            r2_public_url = r2_public_url.rstrip("/")
            r2_url = f"{r2_public_url}/{img['r2_key']}"
            results[img["local_path"]] = r2_url
            logger.info("  Uploaded: %s -> %s", img["local_path"], r2_url)
        except Exception as exc:
            logger.error("  Upload failed: %s: %s", img["local_path"], exc)

    return results


def send_images_sync(api_url: str, secret: str, manifest: dict, dry_run: bool) -> dict:
    """Send the image manifest to ``POST /api/v1/sync/images``."""
    if dry_run:
        logger.info(
            "  [DRY-RUN] Would record %d image URL(s)", len(manifest.get("images", []))
        )
        return {"dry_run": True}

    url = f"{api_url}/sync/images"
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}

    def do_post() -> dict:
        resp = requests.post(url, json=manifest, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError("Authentication failed (401). Check SCRAPER_SECRET.")
        if resp.status_code == 400:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"message": resp.text}
            raise ValueError(
                f"Validation error (400): {error_data.get('message', resp.text)}"
            )
        if resp.status_code not in (200, 207):
            raise RuntimeError(f"API error ({resp.status_code}): {resp.text[:200]}")
        return resp.json()

    try:
        result = retry_call(do_post, max_retries=3, context="sync_images")
        logger.info(
            "  Images: %d updated, %d skipped",
            result.get("updated", 0),
            result.get("skipped", 0),
        )
        return result
    except Exception as exc:
        logger.error("  Image URL recording failed: %s", exc)
        return {"error": str(exc)}


def main() -> None:
    """Parse CLI flags and run the Stage 5 Cloudflare sync."""
    parser = argparse.ArgumentParser(description="Haqita Stage 5: Sync to Cloudflare")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without uploading"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed sync report"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="Override API URL (default: https://haqita.pages.dev/api/v1)",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    cfg = load_config()

    if args.dry_run:
        logger.info("[DRY-RUN] No data will be sent to the API or R2.")
        logger.info("")

    api_url = get_api_url(args, cfg)
    logger.info("API URL: %s", api_url)

    if args.dry_run:
        secret = ""
    else:
        secret = get_scraper_secret()

    # Load source data
    history = load_json(
        DATABASE_DIR / "price_history.json", {"snapshots": [], "metadata": {}}
    )
    catalog_raw = load_json(DATABASE_DIR / "product_catalog.json", {"catalog": {}})
    catalog = catalog_raw.get("catalog", {})
    promo_catalog_data = load_json(OUTPUT_DIR / "promo_catalog.json", [])
    active_promo = load_json(OUTPUT_DIR / "active_promo.json", {})
    display_hints = active_promo.get("display_hints", {})

    # Build and send batch
    logger.info("Building sync batch...")
    batch = build_sync_batch(history, catalog, promo_catalog_data, display_hints)
    logger.info(
        "  Stores: %d, Products: %d, Prices: %d, Promos: %d",
        len(batch["stores"]),
        len(batch["products"]),
        len(batch["prices"]),
        len(batch["promos"]),
    )
    logger.info("")

    logger.info("Syncing batch to API...")
    batch_result = send_batch_sync(api_url, secret, batch, args.dry_run)
    if "error" in batch_result:
        logger.error("Batch sync failed. See error above.")
        if not args.dry_run:
            sys.exit(1)
    logger.info("")

    # R2 image upload
    logger.info("Checking images for R2 upload...")
    sync_state = load_sync_state()
    images_to_upload = get_images_to_upload(history, sync_state)

    uploaded: dict = {}
    if images_to_upload:
        logger.info("  %d image(s) to upload", len(images_to_upload))
        if not args.dry_run:
            r2_client = get_r2_client(cfg)
            bucket_name = os.getenv("R2_BUCKET_NAME", "haqita-images")
            uploaded = upload_images_to_r2(
                images_to_upload, r2_client, bucket_name, args.dry_run
            )
        else:
            uploaded = upload_images_to_r2(
                images_to_upload, None, "haqita-images", args.dry_run
            )

        if uploaded and not args.dry_run:
            logger.info("Recording R2 URLs in API...")
            image_manifest = {
                "images": [
                    {
                        "local_path": local_path,
                        "r2_key": uploaded[local_path].split("/", 3)[-1],
                        "r2_url": uploaded[local_path],
                    }
                    for local_path in uploaded
                ]
            }
            send_images_sync(api_url, secret, image_manifest, args.dry_run)
    else:
        logger.info("  No new or changed images to upload.")

    logger.info("")

    # Update sync state after successful operations
    if not args.dry_run and "error" not in batch_result:
        if images_to_upload:
            uploaded_hashes = [
                {"local_path": img["local_path"], "hash": img["hash"]}
                for img in images_to_upload
                if img["local_path"] in uploaded
            ]
            update_sync_state(sync_state, uploaded_hashes, batch["sync_run_id"])
        else:
            sync_state["last_sync_run_id"] = batch["sync_run_id"]
            save_sync_state(sync_state)
        logger.info("  Sync state saved to %s", SYNC_STATE_FILE)

    logger.info("")
    logger.info("Sync complete.")


if __name__ == "__main__":
    main()
