"""
Haqita Stage 5: Deploy + Sync.

Deploys the browser UI to Cloudflare Pages (if the deployed API version is
stale), then syncs data to the deployed API. Also supports local dev server.

Usage:
    python scripts/deploy.py                           # Deploy configured targets
    python scripts/deploy.py --target local            # Local dev server only
    python scripts/deploy.py --target cloudflare       # Cloudflare Pages only
    python scripts/deploy.py --target both             # Both targets
    python scripts/deploy.py --skip-d1-schema          # Skip remote D1 schema apply
    python scripts/deploy.py --verify-r2               # Reconcile R2 vs sync_state
"""

import argparse
import http.server
import json
import logging
import os
import re
import shutil
import signal
import socket
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
LOCAL_PID_FILE = STAGE_RESULTS / "local_dev_pids.json"

logger = logging.getLogger(__name__)

# Background processes started by this script; killed on exit.
_background_procs: list[subprocess.Popen] = []


def setup_logging() -> logging.Logger:
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
    ch.setLevel(logging.DEBUG)
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


def _copy_static_files() -> list[str]:
    """Stage output/html/*.json into web/public/output/html/ for static fallback.

    The HTML UI files (index.html, admin.html) already live in web/public/ as
    the single source of truth for both local dev and Cloudflare Pages. This
    function only stages the JSON data files the UI fetches via the relative
    path ``output/html/<name>.json`` so the static fallback works when the API
    is unreachable. The Cloudflare Pages deploy serves web/public/ verbatim, so
    the staged JSONs are deployed alongside the HTML.
    """
    # Destination mirrors the client's relative fetch path: output/html/<name>.
    PUBLIC_HTML_DIR = PUBLIC_DIR / "output" / "html"

    files_to_copy = [
        (OUTPUT_HTML / "active_promo.json", PUBLIC_HTML_DIR / "active_promo.json"),
        (OUTPUT_HTML / "price_history.json", PUBLIC_HTML_DIR / "price_history.json"),
        (OUTPUT_HTML / "promo_catalog.json", PUBLIC_HTML_DIR / "promo_catalog.json"),
        (OUTPUT_HTML / "review_queue.json", PUBLIC_HTML_DIR / "review_queue.json"),
    ]

    copied: list[str] = []
    warned: list[str] = []

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    # Only remove the generated JSON staging dir; the HTML files in web/public/
    # are the source of truth and must not be wiped.
    if PUBLIC_HTML_DIR.exists():
        shutil.rmtree(PUBLIC_HTML_DIR)
    PUBLIC_HTML_DIR.mkdir(parents=True, exist_ok=True)

    # One-time cleanup: remove legacy top-level JSONs staged by the previous
    # deploy layout (they now live under web/public/output/html/).
    for legacy in PUBLIC_DIR.iterdir():
        if legacy.name in {".gitkeep", "index.html", "admin.html", "output"}:
            continue
        if legacy.is_file() and legacy.suffix == ".json":
            try:
                legacy.unlink()
                logger.info("  [CLEAN] removed legacy %s", legacy.relative_to(ROOT))
            except OSError as exc:
                logger.warning("Could not remove legacy %s: %s", legacy, exc)

    for src, dst in files_to_copy:
        if not src.exists():
            logger.warning("[WARN] Source not found: %s", src.relative_to(ROOT))
            warned.append(src.name)
            continue
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        logger.info("  [OK] %s -> %s/", src.name, PUBLIC_HTML_DIR.relative_to(ROOT))
        copied.append(src.name)

    return copied


def _run_typecheck() -> None:
    """Run TypeScript typecheck in web/."""
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


def _install_deps_if_needed() -> None:
    """Install npm dependencies in web/ if node_modules is missing."""
    node_modules = WEB_DIR / "node_modules"
    if node_modules.exists():
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
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.5)
    return False


def _detect_wrangler_port(
    proc: subprocess.Popen,
    expected_port: int,
    timeout: float = 60.0,
) -> int | None:
    """Read wrangler's stdout/stderr to find the port it bound to.

    Returns the detected port, or ``None`` on timeout.
    """
    port_pattern = re.compile(r"Ready on http://localhost:(\d+)")
    deadline = time.time() + timeout

    def _read_stream(stream: subprocess.PIPE, results: list) -> None:
        for line in iter(stream.readline, ""):
            results.append(line)

    out_lines: list[str] = []
    err_lines: list[str] = []
    out_thread = threading.Thread(target=_read_stream, args=(proc.stdout, out_lines), daemon=True)
    err_thread = threading.Thread(target=_read_stream, args=(proc.stderr, err_lines), daemon=True)
    out_thread.start()
    err_thread.start()

    while time.time() < deadline:
        for line in out_lines + err_lines:
            m = port_pattern.search(line)
            if m:
                return int(m.group(1))
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    # Fall back to expected port if wrangler already bound to it
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.connect(("127.0.0.1", expected_port))
        return expected_port
    except OSError:
        pass

    return None


def _detect_wrangler_port_from_log(
    log_file: Path,
    expected_port: int,
    timeout: float = 60.0,
) -> int | None:
    """Poll a wrangler log file to find the port it bound to.

    Used in detached mode where stdout/stderr are redirected to a file
    instead of a pipe. Returns the detected port, or ``None`` on timeout.
    """
    port_pattern = re.compile(r"Ready on http://localhost:(\d+)")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                m = port_pattern.search(content)
                if m:
                    return int(m.group(1))
            except OSError:
                pass
        time.sleep(0.2)

    # Fall back to expected port if wrangler already bound to it
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.connect(("127.0.0.1", expected_port))
        return expected_port
    except OSError:
        pass

    # Fall back to stored port from PID file if it exists
    try:
        if LOCAL_PID_FILE.exists():
            data = json.loads(LOCAL_PID_FILE.read_text(encoding="utf-8"))
            ports = data.get("ports", [])
            if len(ports) >= 2:
                stored_port = ports[1]
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect(("127.0.0.1", stored_port))
                return stored_port
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        pass

    return None


def _kill_proc_group(proc: subprocess.Popen) -> None:
    """Terminate a detached process and its entire process group."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def deploy_local() -> dict:
    """Start local wrangler dev server and static HTTP server.

    This function blocks until the user interrupts it (Ctrl+C). The background
    processes are terminated on exit.
    """
    logger.info("=== Local deploy ===")
    logger.info("Target: http://localhost:%d (static) and http://localhost:%d (API)", LOCAL_HTTP_PORT, LOCAL_WRANGLER_PORT)

    _require_command("npm", "npm")
    _install_deps_if_needed()
    _copy_static_files()

    _register_cleanup()

    # Start wrangler pages dev in web/ and detect the actual port.
    logger.info("Starting wrangler pages dev --local...")
    wrangler_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=WEB_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _background_procs.append(wrangler_proc)

    detected_port = _detect_wrangler_port(wrangler_proc, LOCAL_WRANGLER_PORT, timeout=60.0)
    if detected_port is None:
        logger.error("wrangler dev did not start in time.")
        _terminate_background()
        return {"status": "error", "error": "wrangler_dev_timeout"}

    if detected_port != LOCAL_WRANGLER_PORT:
        logger.warning(
            "wrangler dev started on port %d instead of %d.",
            detected_port,
            LOCAL_WRANGLER_PORT,
        )

    wrangler_port = detected_port
    logger.info("  wrangler dev ready on http://localhost:%d", wrangler_port)

    # Start static HTTP server serving web/public/ (same dir Cloudflare Pages
    # deploys) on port 8080. The HTML files live there as the single source of
    # truth, and the JSON static fallback is staged at web/public/output/html/.
    logger.info("Starting static HTTP server on port %d...", LOCAL_HTTP_PORT)

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

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

    return {"status": "complete", "ports": [LOCAL_HTTP_PORT, wrangler_port]}


def _deploy_local_detached() -> dict:
    """Start local dev servers in the background (non-blocking).

    Starts wrangler pages dev and a static HTTP server as detached
    background processes, verifies both are ready, saves PIDs for
    later cleanup, and returns immediately. The servers keep running
    after the script exits.

    Use ``--stop-local`` to shut them down.
    """
    logger.info("=== Local deploy (detached) ===")
    logger.info(
        "Target: http://localhost:%d (static) and http://localhost:%d (API)",
        LOCAL_HTTP_PORT,
        LOCAL_WRANGLER_PORT,
    )

    # Check if servers are already running on expected or stored ports
    http_up = _wait_for_port(LOCAL_HTTP_PORT, timeout=1.0)
    wrangler_up = _wait_for_port(LOCAL_WRANGLER_PORT, timeout=1.0)
    actual_http_port = LOCAL_HTTP_PORT if http_up else None
    actual_wrangler_port = LOCAL_WRANGLER_PORT if wrangler_up else None

    pid_data = load_json(LOCAL_PID_FILE)
    if pid_data and "ports" in pid_data:
        stored = pid_data["ports"]
        if not http_up and len(stored) >= 1:
            http_up = _wait_for_port(stored[0], timeout=1.0)
            if http_up:
                actual_http_port = stored[0]
        if not wrangler_up and len(stored) >= 2:
            wrangler_up = _wait_for_port(stored[1], timeout=1.0)
            if wrangler_up:
                actual_wrangler_port = stored[1]

    if http_up and wrangler_up:
        logger.info("Local dev servers already running. Skipping.")
        return {"status": "complete", "ports": [actual_http_port, actual_wrangler_port]}
    if http_up or wrangler_up:
        logger.warning(
            "One server is already running but the other is not. Stopping the old servers first, then redeploying."
        )
        stop_local()

    _require_command("npm", "npm")
    _install_deps_if_needed()
    _copy_static_files()

    # Start wrangler pages dev detached, logging to a file.
    logger.info("Starting wrangler pages dev (background)...")
    log_dir = ROOT / "output" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    wrangler_log = log_dir / "wrangler_dev.log"

    wrangler_fh = open(wrangler_log, "w")
    try:
        wrangler_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=WEB_DIR,
            stdout=wrangler_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        wrangler_fh.close()

    http_proc = None
    try:
        detected_port = _detect_wrangler_port_from_log(
            wrangler_log, LOCAL_WRANGLER_PORT, timeout=60.0
        )
        if detected_port is None:
            logger.error("wrangler dev did not start in time. Check %s", wrangler_log)
            _kill_proc_group(wrangler_proc)
            return {"status": "error", "error": "wrangler_dev_timeout"}

        logger.info("  wrangler dev ready on http://localhost:%d", detected_port)

        # Start static HTTP server as a detached subprocess serving web/public/.
        logger.info("Starting static HTTP server on port %d (background)...", LOCAL_HTTP_PORT)
        http_proc = subprocess.Popen(
            [
                sys.executable, "-m", "http.server",
                str(LOCAL_HTTP_PORT), "--directory", str(PUBLIC_DIR),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        if not _wait_for_port(LOCAL_HTTP_PORT, timeout=10.0):
            logger.error("HTTP server did not start on port %d in time.", LOCAL_HTTP_PORT)
            _kill_proc_group(wrangler_proc)
            _kill_proc_group(http_proc)
            return {"status": "error", "error": "http_server_timeout"}

        logger.info("  HTTP server ready on http://localhost:%d", LOCAL_HTTP_PORT)

        # Save PIDs for later cleanup.
        STAGE_RESULTS.mkdir(parents=True, exist_ok=True)
        pid_data = {
            "pids": [wrangler_proc.pid, http_proc.pid],
            "ports": [LOCAL_HTTP_PORT, detected_port],
            "started_at": datetime.now().isoformat(),
        }
        LOCAL_PID_FILE.write_text(json.dumps(pid_data, indent=2), encoding="utf-8")

        logger.info("")
        logger.info("Local dev servers running in background:")
        logger.info("  Static:  http://localhost:%d", LOCAL_HTTP_PORT)
        logger.info("  API:     http://localhost:%d", detected_port)
        logger.info("  Stop with: python scripts/deploy.py --stop-local")

        return {"status": "complete", "ports": [LOCAL_HTTP_PORT, detected_port]}
    except BaseException:
        _kill_proc_group(wrangler_proc)
        if http_proc is not None:
            _kill_proc_group(http_proc)
        raise


def stop_local() -> dict:
    """Stop previously started detached local dev servers."""
    pid_data = load_json(LOCAL_PID_FILE)
    if not pid_data or not pid_data.get("pids"):
        logger.info("No local dev servers to stop (no PID file found).")
        return {"status": "complete", "stopped": 0}

    stopped = 0
    for pid in pid_data.get("pids", []):
        try:
            os.killpg(pid, signal.SIGTERM)
            stopped += 1
            logger.info("  Sent SIGTERM to process group %d", pid)
        except ProcessLookupError:
            logger.info("  PID %d already gone", pid)
        except OSError as exc:
            logger.warning("  Could not signal PID %d: %s", pid, exc)

    time.sleep(2)

    # Force kill any still alive
    for pid in pid_data.get("pids", []):
        try:
            os.killpg(pid, signal.SIGKILL)
            logger.info("  Force killed process group %d", pid)
        except (ProcessLookupError, OSError):
            pass

    LOCAL_PID_FILE.unlink(missing_ok=True)
    logger.info("Stopped %d local dev server(s).", stopped)
    return {"status": "complete", "stopped": stopped}


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


def _set_commit_sha_secret(sha: str) -> bool:
    """Set COMMIT_SHA as a Cloudflare Pages secret via ``wrangler pages secret put``."""
    _require_command("wrangler", "wrangler")
    logger.info("Setting COMMIT_SHA as Cloudflare Pages secret...")
    result = subprocess.run(
        ["wrangler", "pages", "secret", "put", "COMMIT_SHA"],
        cwd=WEB_DIR,
        input=sha,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Failed to set COMMIT_SHA secret:\n%s", result.stdout + result.stderr)
        return False
    logger.info("  COMMIT_SHA secret updated to %s", sha[:12])
    return True


def _apply_d1_schema_remote() -> bool:
    """Apply ``web/schema.sql`` to the remote (production) D1 database.

    The schema uses ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT
    EXISTS``, so running it every deploy is idempotent and safe. This is what
    actually provisions the tables the sync endpoints write into — the Pages
    static deploy itself does NOT create D1 tables, and without this step a
    fresh or reset remote D1 has no schema, so every batch sync row fails with
    ``no such table … SQLITE_ERROR``.

    Returns True on success, False on failure.
    """
    schema_file = WEB_DIR / "schema.sql"
    if not schema_file.exists():
        logger.error("D1 schema file not found: %s", schema_file)
        return False

    # wrangler is launched with cwd=WEB_DIR, so use an absolute path so the
    # --file argument resolves regardless of the caller's cwd. Wrangler's docs
    # show `--file=./web/schema.sql` run from the project root, but here we run
    # from web/, so absolute is the robust choice.
    schema_arg = f"--file={schema_file.resolve()}"

    wrangler = _require_command("wrangler", "wrangler")
    logger.info("Applying D1 schema to remote database (idempotent)...")
    result = subprocess.run(
        [
            wrangler, "d1", "execute", "haqita-db",
            "--remote", schema_arg,
        ],
        cwd=WEB_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(
            "D1 schema apply failed (rc=%d):\n%s",
            result.returncode,
            (result.stdout or "") + (result.stderr or ""),
        )
        return False
    logger.info("  D1 schema applied (CREATE TABLE/INDEX IF NOT EXISTS).")
    return True


def _deploy_to_cloudflare() -> dict:
    """Deploy static files to Cloudflare Pages (raw deploy — no version check)."""
    _require_command("npm", "npm")
    _install_deps_if_needed()
    _copy_static_files()
    _run_typecheck()

    logger.info("Deploying to Cloudflare Pages...")
    result = subprocess.run(
        ["npm", "run", "deploy"],
        cwd=WEB_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Cloudflare Pages deploy failed:\n%s", result.stdout + result.stderr)
        return {"status": "error", "error": "deploy_failed"}

    logger.info("  Deploy complete: https://haqita.pages.dev")
    return {"status": "complete", "url": "https://haqita.pages.dev"}


def deploy_cloudflare(
    skip_d1_schema: bool = False,
    verify_r2: bool = False,
) -> dict:
    """Deploy to Cloudflare Pages if the deployed API is stale, then sync data.

    Flow:
    1. Read local HEAD SHA.
    2. Call ``GET {api_url}/version`` on the deployed API.
    3. If the SHA differs or the endpoint is unreachable: set COMMIT_SHA secret,
       copy static files, typecheck, deploy.
    4. Apply ``web/schema.sql`` to the remote D1 (idempotent) so the sync
       endpoints have their tables. Without this a fresh/reset remote D1 has no
       schema and every batch row fails with ``no such table``. Skipped when
       ``--skip-d1-schema`` is passed or ``deploy.apply_d1_schema`` is false
       in config.
    5. Sync data via ``run_sync()`` (optionally with R2 verification when
       ``verify_r2`` is true).
    """
    logger.info("=== Cloudflare Pages deploy + sync ===")

    if not (WEB_DIR / "package.json").exists():
        logger.error("web/package.json not found. Run setup first.")
        return {"status": "error", "error": "web_package_json_missing"}

    if not (PUBLIC_DIR / "index.html").exists():
        logger.error("index.html not found in web/public/.")
        return {"status": "error", "error": "index_html_missing"}

    # Determine API URL
    _cfg = load_config()
    cf_cfg = _cfg.get("cloudflare_sync", {})
    env_url = os.getenv("CLOUDFLARE_API_URL")
    api_url = (env_url or cf_cfg.get("api_url", "https://haqita.pages.dev/api/v1")).rstrip("/")

    # Config flag: deploy.apply_d1_schema (default true). CLI --skip-d1-schema wins.
    deploy_cfg = _cfg.get("deploy", {})
    apply_schema = deploy_cfg.get("apply_d1_schema", True)
    if skip_d1_schema:
        apply_schema = False

    # Read local SHA and check deployed version
    local_sha = _get_local_head_sha()
    logger.info("Local HEAD SHA: %s", local_sha[:12] if local_sha != "unknown" else local_sha)
    deployed_version = _get_deployed_version(api_url)
    logger.info("Deployed version: %s", deployed_version[:12] if deployed_version else "N/A")

    needs_deploy = deployed_version is None or deployed_version != local_sha

    if needs_deploy:
        logger.info("Deployed API is stale — deploying new version...")
        deploy_result = _deploy_to_cloudflare()
        if deploy_result.get("status") == "error":
            return deploy_result

        # Set COMMIT_SHA secret only after deploy succeeds, so version tracking
        # is consistent: the running API matches the SHA we recorded.
        if not _set_commit_sha_secret(local_sha):
            logger.warning("Failed to set COMMIT_SHA secret — version tracking will be broken on the next run")
    else:
        logger.info("Deployed API is up to date (SHA matches). Skipping deploy.")

    # Apply D1 schema to remote (idempotent) before syncing, so the batch
    # endpoints always have their tables. The Pages static deploy alone does
    # not provision D1 tables.
    schema_applied = True
    if apply_schema:
        logger.info("")
        logger.info("=== Applying D1 schema to remote database ===")
        schema_applied = _apply_d1_schema_remote()
        if not schema_applied:
            logger.error(
                "Remote D1 schema apply failed. Aborting sync to avoid a "
                "100%% 'no such table' failure. Run `wrangler d1 execute "
                "haqita-db --remote --file=$(pwd)/web/schema.sql` from the "
                "project root manually, or use --skip-d1-schema to bypass."
            )
            return {"status": "error", "error": "d1_schema_apply_failed"}
    else:
        logger.info("")
        logger.info("[SKIP] D1 schema apply disabled ('--skip-d1-schema' or deploy.apply_d1_schema=false).")

    # Sync data to the (now current) API
    logger.info("")
    logger.info("=== Syncing data to deployed API ===")
    secret = os.getenv("SCRAPER_SECRET", "")
    if not secret:
        logger.error("SCRAPER_SECRET not set. Cannot sync.")
        return {"status": "error", "error": "SCRAPER_SECRET not set"}

    sync_result = run_sync(api_url, secret, verify_r2=verify_r2)
    if sync_result.get("status") == "error":
        logger.error("Sync after deploy failed: %s", sync_result.get("error"))
        return {"status": "error", "error": sync_result.get("error")}

    return {
        "status": "complete",
        "url": "https://haqita.pages.dev",
        "deploy_needed": needs_deploy,
        "d1_schema_applied": schema_applied if apply_schema else "skipped",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Haqita Stage 5: Deploy + Sync")
    parser.add_argument(
        "--target",
        choices=["local", "cloudflare", "both"],
        help="Deployment target (default: from config.yaml deploy section)",
    )
    parser.add_argument(
        "--skip-d1-schema",
        action="store_true",
        help="Do not apply web/schema.sql to remote D1 before sync (overrides deploy.apply_d1_schema=true)",
    )
    parser.add_argument(
        "--verify-r2",
        action="store_true",
        help="Reconcile R2 bucket vs sync_state: list R2, re-upload missing referenced images",
    )
    parser.add_argument(
        "--detached",
        action="store_true",
        help="Start local dev servers in background (non-blocking) instead of foreground",
    )
    parser.add_argument(
        "--stop-local",
        action="store_true",
        help="Stop previously started detached local dev servers",
    )
    args = parser.parse_args()

    setup_logging()

    # --stop-local is a standalone action: kill servers and exit.
    if args.stop_local:
        stop_local()
        return

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

    details: dict = {"target": target}
    try:
        if target == "local":
            if args.detached:
                result = _deploy_local_detached()
            else:
                result = deploy_local()
        elif target == "cloudflare":
            result = deploy_cloudflare(
                skip_d1_schema=args.skip_d1_schema,
                verify_r2=args.verify_r2,
            )
        elif target == "both":
            cf_result = deploy_cloudflare(
                skip_d1_schema=args.skip_d1_schema,
                verify_r2=args.verify_r2,
            )
            details["cloudflare"] = cf_result
            if cf_result.get("status") == "error":
                write_status("error", target, details)
                sys.exit(1)
            if args.detached:
                result = _deploy_local_detached()
            else:
                result = deploy_local()
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
