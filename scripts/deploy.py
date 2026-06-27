"""
Haqita Stage 6: Deploy + Sync.

Deploys the browser UI to Cloudflare Pages (if the deployed API version is
stale), then syncs data to the deployed API. Also supports local dev server.

Usage:
    python scripts/deploy.py                           # Deploy configured targets
    python scripts/deploy.py --dry-run                 # Preview without executing
    python scripts/deploy.py --verbose                 # Show detailed output
    python scripts/deploy.py --target local            # Local dev server only
    python scripts/deploy.py --target cloudflare       # Cloudflare Pages only
    python scripts/deploy.py --target both             # Both targets
"""

import argparse
import http.server
import json
import logging
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.config import load_config
from scripts.sync_cloudflare import run_sync

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_HTML = ROOT / "output" / "html"
WEB_DIR = ROOT / "web"
PUBLIC_DIR = WEB_DIR / "public"
STAGE_RESULTS = ROOT / "output" / "stage_results"
DEPLOY_STATUS = STAGE_RESULTS / "deploy_status.json"

LOCAL_HTTP_PORT = 8080
LOCAL_WRANGLER_PORT = 8787

logger = logging.getLogger(__name__)

# Background processes started by this script; killed on exit.
_background_procs: list[subprocess.Popen] = []


def setup_logging(verbose: bool) -> logging.Logger:
    """Configure the deploy logger with console and file handlers."""
    LOG_DIR = ROOT / "output" / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"deploy_{timestamp}.log"

    deploy_logger = logging.getLogger(__name__)
    deploy_logger.setLevel(logging.DEBUG)
    deploy_logger.handlers = []

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    deploy_logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    deploy_logger.addHandler(ch)

    sync_logger = logging.getLogger("scripts.sync_cloudflare")
    sync_logger.setLevel(logging.DEBUG)
    sync_logger.handlers = []
    sync_logger.addHandler(fh)
    sync_logger.addHandler(ch)

    deploy_logger.info("Log file: %s", log_file)
    return deploy_logger


def load_json(path: Path, default=None):
    """Load a JSON file, returning ``default`` if it does not exist."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def write_status(status: str, target: str, details: dict | None = None) -> None:
    """Write deploy_status.json to output/stage_results/."""
    STAGE_RESULTS.mkdir(parents=True, exist_ok=True)
    output = {
        "stage": "deploy",
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "target": target,
    }
    if details:
        output["details"] = details
    DEPLOY_STATUS.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Wrote %s", DEPLOY_STATUS)


def _terminate_background() -> None:
    """Terminate any background processes started by this script."""
    for proc in _background_procs:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _register_cleanup() -> None:
    """Register signal handlers so background processes are cleaned up on exit."""
    def _handler(signum, frame):
        logger.info("\nReceived signal %s, shutting down deploy servers...", signum)
        _terminate_background()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _require_command(name: str, friendly: str) -> str:
    """Return the absolute path to ``name`` or print an error and exit."""
    path = shutil.which(name)
    if not path:
        logger.error("%s not found in PATH.", friendly)
        logger.error("Install it (e.g. `npm install -g %s`) and try again.", name)
        sys.exit(1)
    return path


def _copy_static_files(dry_run: bool) -> list[str]:
    """Copy root index.html and output/html/*.json into web/public/."""
    files_to_copy = [
        (ROOT / "index.html", PUBLIC_DIR / "index.html"),
        (OUTPUT_HTML / "active_promo.json", PUBLIC_DIR / "active_promo.json"),
        (OUTPUT_HTML / "price_history.json", PUBLIC_DIR / "price_history.json"),
        (OUTPUT_HTML / "promo_catalog.json", PUBLIC_DIR / "promo_catalog.json"),
        (OUTPUT_HTML / "review_queue.json", PUBLIC_DIR / "review_queue.json"),
    ]

    copied: list[str] = []
    warned: list[str] = []

    if dry_run:
        logger.info("[DRY-RUN] Would copy static files to %s/", PUBLIC_DIR.relative_to(ROOT))
    else:
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        # Remove stale files so the public dir mirrors the latest output.
        for stale in PUBLIC_DIR.iterdir():
            if stale.name in {".gitkeep"}:
                continue
            try:
                if stale.is_file() or stale.is_symlink():
                    stale.unlink()
                elif stale.is_dir():
                    shutil.rmtree(stale)
            except OSError as exc:
                logger.warning("Could not remove stale public file %s: %s", stale, exc)

    for src, dst in files_to_copy:
        if not src.exists():
            logger.warning("[WARN] Source not found: %s", src.relative_to(ROOT))
            warned.append(src.name)
            continue
        if dry_run:
            logger.info("  [WOULD COPY] %s -> %s/", src.name, PUBLIC_DIR.relative_to(ROOT))
        else:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            logger.info("  [OK] %s -> %s/", src.name, PUBLIC_DIR.relative_to(ROOT))
        copied.append(src.name)

    return copied


def _run_typecheck(dry_run: bool) -> None:
    """Run TypeScript typecheck in web/."""
    if dry_run:
        logger.info("[DRY-RUN] Would run: cd web && npm run typecheck")
        return

    _require_command("npm", "npm")
    logger.info("Running typecheck...")
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        cwd=WEB_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Typecheck failed:\n%s", result.stdout + result.stderr)
        sys.exit(1)
    logger.info("  Typecheck passed.")


def _install_deps_if_needed(dry_run: bool) -> None:
    """Install npm dependencies in web/ if node_modules is missing."""
    node_modules = WEB_DIR / "node_modules"
    if node_modules.exists():
        return

    if dry_run:
        logger.info("[DRY-RUN] Would install web/ dependencies")
        return

    _require_command("npm", "npm")
    logger.info("Installing web/ dependencies...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=WEB_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("npm install failed:\n%s", result.stdout + result.stderr)
        sys.exit(1)
    logger.info("  Dependencies installed.")


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    """Wait up to ``timeout`` seconds for a TCP port to accept connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socketserver.socket(socketserver.TCPServer.address_family, socketserver.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.5)
    return False


def deploy_local(dry_run: bool, verbose: bool) -> dict:
    """Start local wrangler dev server and static HTTP server.

    This function blocks until the user interrupts it (Ctrl+C). The background
    processes are terminated on exit.
    """
    logger.info("=== Local deploy ===")
    logger.info("Target: http://localhost:%d (static) and http://localhost:%d (API)", LOCAL_HTTP_PORT, LOCAL_WRANGLER_PORT)

    if dry_run:
        logger.info("[DRY-RUN] Would start:")
        logger.info("  cd web && npm run dev")
        logger.info("  python -m http.server %d (from project root)", LOCAL_HTTP_PORT)
        return {"status": "dry_run", "ports": [LOCAL_HTTP_PORT, LOCAL_WRANGLER_PORT]}

    _require_command("npm", "npm")
    _install_deps_if_needed(dry_run=False)
    _copy_static_files(dry_run=False)

    _register_cleanup()

    # Start wrangler pages dev in web/ on port 8787.
    logger.info("Starting wrangler pages dev --local on port %d...", LOCAL_WRANGLER_PORT)
    wrangler_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=WEB_DIR,
        stdout=subprocess.PIPE if not verbose else None,
        stderr=subprocess.PIPE if not verbose else None,
        text=True,
    )
    _background_procs.append(wrangler_proc)

    if not _wait_for_port(LOCAL_WRANGLER_PORT, timeout=60.0):
        logger.error("wrangler dev did not start on port %d in time.", LOCAL_WRANGLER_PORT)
        _terminate_background()
        return {"status": "error", "error": "wrangler_dev_timeout"}

    logger.info("  wrangler dev ready on http://localhost:%d", LOCAL_WRANGLER_PORT)

    # Start static HTTP server in project root on port 8080.
    logger.info("Starting static HTTP server on port %d...", LOCAL_HTTP_PORT)

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, format, *args):
            if verbose:
                super().log_message(format, *args)

    httpd = socketserver.TCPServer(("", LOCAL_HTTP_PORT), QuietHandler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    if not _wait_for_port(LOCAL_HTTP_PORT, timeout=10.0):
        logger.error("HTTP server did not start on port %d in time.", LOCAL_HTTP_PORT)
        httpd.shutdown()
        _terminate_background()
        return {"status": "error", "error": "http_server_timeout"}

    logger.info("  HTTP server ready on http://localhost:%d", LOCAL_HTTP_PORT)
    logger.info("")
    logger.info("Local deploy running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
            # If wrangler exits unexpectedly, stop the HTTP server too.
            if wrangler_proc.poll() is not None:
                logger.error("wrangler dev exited unexpectedly (code %d).", wrangler_proc.returncode)
                httpd.shutdown()
                return {"status": "error", "error": "wrangler_dev_exited"}
    except KeyboardInterrupt:
        logger.info("\nStopping local deploy servers...")
    finally:
        httpd.shutdown()
        _terminate_background()

    return {"status": "complete", "ports": [LOCAL_HTTP_PORT, LOCAL_WRANGLER_PORT]}


def _get_local_head_sha() -> str:
    """Return the local HEAD commit SHA via ``git rev-parse HEAD``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Could not get local HEAD SHA: %s", exc)
    return "unknown"


def _get_deployed_version(api_url: str, timeout: float = 5.0) -> str | None:
    """Call ``GET {api_url}/version`` and return the ``version`` field.

    Returns None if the endpoint is unreachable, returns a non-200 status,
    or the response is not valid JSON.
    """
    version_url = api_url.rstrip("/") + "/version"
    try:
        resp = requests.get(version_url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("version", None)
        logger.info("  Version endpoint returned status %s", resp.status_code)
    except requests.RequestException as exc:
        logger.info("  Could not reach version endpoint: %s", exc)
    except (ValueError, TypeError) as exc:
        logger.info("  Could not parse version response: %s", exc)
    return None


def _set_commit_sha_secret(sha: str, dry_run: bool) -> bool:
    """Set COMMIT_SHA as a Cloudflare Pages secret via ``wrangler pages secret put``."""
    if dry_run:
        logger.info("[DRY-RUN] Would set COMMIT_SHA=%s as Cloudflare Pages secret", sha[:12])
        return True

    _require_command("wrangler", "wrangler")
    logger.info("Setting COMMIT_SHA as Cloudflare Pages secret...")
    result = subprocess.run(
        ["wrangler", "pages", "secret", "put", "COMMIT_SHA", sha],
        cwd=WEB_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Failed to set COMMIT_SHA secret:\n%s", result.stdout + result.stderr)
        return False
    logger.info("  COMMIT_SHA secret updated to %s", sha[:12])
    return True


def _deploy_to_cloudflare(dry_run: bool, verbose: bool) -> dict:
    """Deploy static files to Cloudflare Pages (raw deploy — no version check)."""
    _require_command("npm", "npm")
    _install_deps_if_needed(dry_run)
    _copy_static_files(dry_run)
    _run_typecheck(dry_run)

    if dry_run:
        logger.info("[DRY-RUN] Would run: cd web && npm run deploy")
        return {"status": "dry_run", "url": "https://haqita.pages.dev"}

    logger.info("Deploying to Cloudflare Pages...")
    result = subprocess.run(
        ["npm", "run", "deploy"],
        cwd=WEB_DIR,
        capture_output=not verbose,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Cloudflare Pages deploy failed:\n%s", result.stdout + result.stderr)
        return {"status": "error", "error": "deploy_failed"}

    logger.info("  Deploy complete: https://haqita.pages.dev")
    return {"status": "complete", "url": "https://haqita.pages.dev"}


def deploy_cloudflare(dry_run: bool, verbose: bool) -> dict:
    """Deploy to Cloudflare Pages if the deployed API is stale, then sync data.

    Flow:
    1. Read local HEAD SHA.
    2. Call ``GET {api_url}/version`` on the deployed API.
    3. If the SHA differs or the endpoint is unreachable: set COMMIT_SHA secret,
       copy static files, typecheck, deploy.
    4. After deploy (or if SHA already matches), sync data via ``run_sync()``.
    """
    logger.info("=== Cloudflare Pages deploy + sync ===")

    if not (WEB_DIR / "package.json").exists():
        logger.error("web/package.json not found. Run setup first.")
        return {"status": "error", "error": "web_package_json_missing"}

    if not (ROOT / "index.html").exists():
        logger.error("index.html not found at project root.")
        return {"status": "error", "error": "index_html_missing"}

    # Determine API URL
    _cfg = load_config()
    cf_cfg = _cfg.get("cloudflare_sync", {})
    env_url = os.getenv("CLOUDFLARE_API_URL")
    api_url = (env_url or cf_cfg.get("api_url", "https://haqita.pages.dev/api/v1")).rstrip("/")

    # Read local SHA and check deployed version
    local_sha = _get_local_head_sha()
    logger.info("Local HEAD SHA: %s", local_sha[:12] if local_sha != "unknown" else local_sha)
    deployed_version = _get_deployed_version(api_url)
    logger.info("Deployed version: %s", deployed_version[:12] if deployed_version else "N/A")

    needs_deploy = deployed_version is None or deployed_version != local_sha

    if needs_deploy:
        if not dry_run:
            logger.info("Deployed API is stale — deploying new version...")

        deploy_result = _deploy_to_cloudflare(dry_run, verbose)
        if deploy_result.get("status") == "error":
            return deploy_result

        # Set COMMIT_SHA secret only after deploy succeeds, so version tracking
        # is consistent: the running API matches the SHA we recorded.
        if not dry_run:
            if not _set_commit_sha_secret(local_sha, dry_run=dry_run):
                logger.warning("Failed to set COMMIT_SHA secret — version tracking will be broken on the next run")
    else:
        logger.info("Deployed API is up to date (SHA matches). Skipping deploy.")
        if dry_run:
            logger.info("[DRY-RUN] Would skip deploy")

    # Sync data to the (now current) API
    logger.info("")
    logger.info("=== Syncing data to deployed API ===")
    if dry_run:
        secret = ""
    else:
        secret = os.getenv("SCRAPER_SECRET", "")
        if not secret:
            logger.error("SCRAPER_SECRET not set. Cannot sync.")
            return {"status": "error", "error": "SCRAPER_SECRET not set"}

    sync_result = run_sync(api_url, secret, dry_run=dry_run, verbose=verbose)
    if sync_result.get("status") == "error":
        logger.error("Sync after deploy failed: %s", sync_result.get("error"))
        return {"status": "error", "error": sync_result.get("error")}

    status = "dry_run" if dry_run else "complete"
    return {"status": status, "url": "https://haqita.pages.dev", "deploy_needed": needs_deploy}


def main() -> None:
    parser = argparse.ArgumentParser(description="Haqita Stage 6: Deploy")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--target",
        choices=["local", "cloudflare", "both"],
        help="Deployment target (default: from config.yaml deploy section)",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    cfg = load_config()
    deploy_cfg = cfg.get("deploy", {})

    # Determine effective target.
    if args.target:
        target = args.target
    elif deploy_cfg.get("cloudflare") and deploy_cfg.get("local"):
        target = "both"
    elif deploy_cfg.get("cloudflare"):
        target = "cloudflare"
    elif deploy_cfg.get("local"):
        target = "local"
    else:
        logger.error("No deploy target enabled. Set deploy.local or deploy.cloudflare in config.yaml.")
        write_status("error", "none", {"error": "no_target_enabled"})
        sys.exit(1)

    logger.info("Deploy target: %s", target)
    if args.dry_run:
        logger.info("[DRY-RUN] No servers will be started and no deploy will run.")
        logger.info("")

    details: dict = {"target": target}
    try:
        if target == "local":
            result = deploy_local(args.dry_run, args.verbose)
        elif target == "cloudflare":
            result = deploy_cloudflare(args.dry_run, args.verbose)
        elif target == "both":
            cf_result = deploy_cloudflare(args.dry_run, args.verbose)
            details["cloudflare"] = cf_result
            if cf_result.get("status") == "error" and not args.dry_run:
                write_status("error", target, details)
                sys.exit(1)
            result = deploy_local(args.dry_run, args.verbose)
            details["local"] = result
        else:
            raise ValueError(f"Unknown target: {target}")

        details.update(result)
        status = result.get("status", "complete")
        write_status(status, target, details)

        if status == "error":
            sys.exit(1)

    except Exception as exc:
        logger.error("Deploy failed: %s", exc)
        write_status("error", target, {"error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
