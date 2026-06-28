"""
Haqita Pipeline Orchestrator.

Chains scrape -> OCR -> consolidation -> publish HTML -> deploy+sync
stages with JSON-based inter-stage communication. Each stage writes its status to
output/stage_results/ for the next stage to consume and for resume support.

The old cloudflare-sync stage has been merged into the deploy stage: deploy
now deploys to Cloudflare Pages and then syncs data to the deployed API.
The separate ``--stage cloudflare-sync`` flag is kept for backward compatibility
but emits a deprecation warning and delegates to deploy.

Usage:
    python scripts/orchestrator.py --full
    python scripts/orchestrator.py --stage scrape
    python scripts/orchestrator.py --stage ocr --stores lotte
    python scripts/orchestrator.py --stage consolidate
    python scripts/orchestrator.py --stage publish-html
    python scripts/orchestrator.py --stage deploy
    python scripts/orchestrator.py --full --dry-run
    python scripts/orchestrator.py --full --verbose
"""

import argparse
import http.server
import json
import logging
import os
import socketserver
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
STAGE_RESULTS = ROOT / "output" / "stage_results"
LOG_DIR = ROOT / "output" / "logs"

ALL_STORES = ["lotte", "superindo"]


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging to file and optionally to console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"orchestrator_{timestamp}.log"

    logger = logging.getLogger("orchestrator")
    logger.setLevel(logging.DEBUG)

    # File handler — always verbose
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    # Console handler — INFO normally, DEBUG if verbose
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    logger.info("Log file: %s", log_file)
    return logger


def write_stage_status(stage: str, data: dict, logger: logging.Logger):
    """Write stage result JSON to database/stage_results/."""
    STAGE_RESULTS.mkdir(parents=True, exist_ok=True)
    status_file = STAGE_RESULTS / f"{stage}_status.json"
    output = {
        "stage": stage,
        "timestamp": datetime.now().isoformat(),
        **data,
    }
    status_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Wrote %s", status_file)


def read_stage_status(stage: str) -> dict | None:
    """Read stage result JSON. Returns None if not found."""
    status_file = STAGE_RESULTS / f"{stage}_status.json"
    if not status_file.exists():
        return None
    return json.loads(status_file.read_text(encoding="utf-8"))


def run_scrape(stores: list[str], dry_run: bool, logger: logging.Logger) -> dict:
    """Run scrape stage for specified stores. Returns status dict."""
    logger.info("=== Stage 1: Scrape ===")
    store_results = {}
    total_new = 0

    for store in stores:
        logger.info("Scraping %s...", store)
        scraper_script = SCRIPTS / "scrapers" / f"{store}.py"

        if not scraper_script.exists():
            logger.error("Scraper not found: %s", scraper_script)
            store_results[store] = {"status": "error", "error": "scraper_not_found"}
            continue

        cmd = [sys.executable, str(scraper_script)]
        if dry_run:
            cmd.append("--dry-run")

        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

        if result.returncode != 0:
            logger.error("Scraper %s failed (exit %d): %s", store, result.returncode, result.stderr.strip())
            store_results[store] = {"status": "error", "error": result.stderr.strip()[:200]}
            continue

        # Parse stdout for new image count
        new_count = 0
        for line in result.stdout.splitlines():
            if "Summary:" in line:
                # e.g., "[*] Summary: 3 new, 0 already processed"
                try:
                    parts = line.split("Summary:")[1].strip()
                    new_count = int(parts.split(" new")[0])
                except (ValueError, IndexError):
                    pass

        if dry_run:
            store_results[store] = {"status": "dry_run", "new_count": 0}
            logger.info("  %s: dry-run complete", store)
        elif new_count > 0:
            store_results[store] = {"status": "new_images", "new_count": new_count}
            total_new += new_count
            logger.info("  %s: %d new image(s)", store, new_count)
        else:
            store_results[store] = {"status": "no_new", "new_count": 0}
            logger.info("  %s: no new images", store)

        # Print scraper output to console
        if result.stdout.strip():
            for line in result.stdout.splitlines():
                print(f"  {line}")

    write_stage_status("scrape", {"stores": store_results, "total_new": total_new}, logger)
    return {"stores": store_results, "total_new": total_new}


def run_ocr(stores: list[str], dry_run: bool, logger: logging.Logger) -> dict:
    """Run OCR stage for all requested stores. Returns status dict.

    Per-image dedup is handled by OCR's own state file
    (database/ocr/<store>/state.json).
    """
    logger.info("=== Stage 2: OCR ===")
    store_results = {}
    total_products = 0

    if not stores:
        logger.info("No stores requested. Skipping OCR.")
        write_stage_status("ocr", {"stores": {}, "total_products": 0}, logger)
        return {"stores": {}, "total_products": 0}

    for store in stores:
        logger.info("Running OCR for %s...", store)
        ocr_script = SCRIPTS / "ocr" / "run_ocr.py"

        if not ocr_script.exists():
            logger.error("OCR script not found: %s", ocr_script)
            store_results[store] = {"status": "error", "error": "ocr_script_not_found"}
            continue

        cmd = [sys.executable, "-u", str(ocr_script), "--store", store]
        if dry_run:
            cmd.append("--dry-run")

        logger.debug("Running: %s", " ".join(cmd))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=ROOT,
        )
        stdout_lines = []
        for line in proc.stdout:
            line = line.rstrip()
            print(f"  {line}", flush=True)
            stdout_lines.append(line)
        proc.wait()
        stderr_output = proc.stderr.read()

        if proc.returncode != 0:
            logger.error("OCR %s failed (exit %d): %s", store, proc.returncode, stderr_output.strip())
            store_results[store] = {"status": "error", "error": stderr_output.strip()[:200]}
            continue

        # Parse stdout for product count
        products_extracted = 0
        for line in stdout_lines:
            if "products extracted" in line.lower() or "total products" in line.lower():
                try:
                    # e.g., "Total products extracted: 45"
                    products_extracted = int(line.split(":")[-1].strip())
                except (ValueError, IndexError):
                    pass

        if dry_run:
            store_results[store] = {"status": "dry_run", "products_extracted": 0}
            logger.info("  %s: dry-run complete", store)
        else:
            store_results[store] = {"status": "complete", "products_extracted": products_extracted}
            total_products += products_extracted
            logger.info("  %s: %d product(s) extracted", store, products_extracted)

    # Mark stores that were skipped (no new images)
    for store in stores:
        if store not in store_results:
            store_results[store] = {"status": "skipped", "reason": "no_new_images"}

    write_stage_status("ocr", {"stores": store_results, "total_products": total_products}, logger)
    return {"stores": store_results, "total_products": total_products}


def run_consolidate(dry_run: bool, logger: logging.Logger) -> dict:
    """Run consolidation stage. Returns status dict."""
    logger.info("=== Stage 3: Consolidation ===")
    consolidate_script = SCRIPTS / "consolidate.py"

    if not consolidate_script.exists():
        logger.error("Consolidate script not found: %s", consolidate_script)
        return {"status": "error", "error": "consolidate_script_not_found"}

    cmd = [sys.executable, str(consolidate_script)]
    if dry_run:
        cmd.append("--dry-run")

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

    if result.returncode != 0:
        logger.error("Consolidation failed (exit %d): %s", result.returncode, result.stderr.strip())
        return {"status": "error", "error": result.stderr.strip()[:200]}

    # Print consolidation output to console
    if result.stdout.strip():
        for line in result.stdout.splitlines():
            print(f"  {line}")

    status = {"status": "complete"}
    if dry_run:
        status["status"] = "dry_run"

    write_stage_status("consolidate", status, logger)
    return status


def run_publish_html(dry_run: bool, logger: logging.Logger) -> dict:
    """Run publish HTML stage. Returns status dict."""
    logger.info("=== Stage 4: Publish HTML ===")
    publish_script = SCRIPTS / "publish_html.py"

    if not publish_script.exists():
        logger.error("Publish HTML script not found: %s", publish_script)
        return {"status": "error", "error": "publish_html_script_not_found"}

    cmd = [sys.executable, str(publish_script)]
    if dry_run:
        cmd.append("--dry-run")

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

    if result.returncode != 0:
        logger.error("Publish HTML failed (exit %d): %s", result.returncode, result.stderr.strip())
        return {"status": "error", "error": result.stderr.strip()[:200]}

    if result.stdout.strip():
        for line in result.stdout.splitlines():
            print(f"  {line}")

    status = {"status": "complete"}
    if dry_run:
        status["status"] = "dry_run"

    write_stage_status("publish_html", status, logger)
    return status


def run_deploy(dry_run: bool, logger: logging.Logger) -> dict:
    """Run Stage 5: Deploy + Sync."""
    logger.info("=== Stage 5: Deploy + Sync ===")
    deploy_script = SCRIPTS / "deploy.py"

    if not deploy_script.exists():
        logger.error("deploy.py not found at %s", deploy_script)
        return {"status": "error", "error": "deploy script not found"}

    cmd = [sys.executable, str(deploy_script)]
    if dry_run:
        cmd.append("--dry-run")

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

    if result.stdout.strip():
        for line in result.stdout.splitlines():
            print(f"  {line}")

    if result.returncode != 0:
        logger.error("Stage 5 (deploy+sync) failed: %s", result.stderr.strip()[:200])
        return {"status": "error", "error": result.stderr.strip()[:200]}

    status = {"status": "complete"}
    if dry_run:
        status["status"] = "dry_run"

    write_stage_status("deploy", status, logger)
    return status


def commit_database(logger: logging.Logger) -> None:
    """Auto-commit pipeline data to haqita-database repo.

    Runs git add + commit + push on the database repo linked via
    the database/ symlink. Only commits if there are changes.
    Fails gracefully (logs warning) if the repo is not set up.
    """
    db_path = (ROOT / "database").resolve()
    git_dir = db_path / ".git"

    if not git_dir.exists():
        logger.warning("haqita-database repo not found at %s. Skipping auto-commit.", db_path)
        return

    try:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

        subprocess.run(
            ["git", "-C", str(db_path), "add", "-A"],
            check=True, capture_output=True, text=True, env=env,
        )

        result = subprocess.run(
            ["git", "-C", str(db_path), "diff", "--staged", "--quiet"],
            capture_output=True, env=env,
        )
        if result.returncode == 0:
            logger.info("No changes to commit to haqita-database.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subprocess.run(
            ["git", "-C", str(db_path), "commit", "-m", f"pipeline run {timestamp}"],
            check=True, capture_output=True, text=True, env=env,
        )
        logger.info("Committed pipeline data to haqita-database.")

        push_result = subprocess.run(
            ["git", "-C", str(db_path), "push"],
            capture_output=True, text=True, env=env,
        )
        if push_result.returncode != 0:
            logger.warning("Failed to push haqita-database: %s", push_result.stderr.strip())
        else:
            logger.info("Pushed haqita-database.")
    except subprocess.CalledProcessError as e:
        logger.warning("Auto-commit to haqita-database failed: %s", e.stderr.strip()[:200])


def main():
    parser = argparse.ArgumentParser(description="Haqita Pipeline Orchestrator")
    parser.add_argument("--full", action="store_true", help="Run all stages: scrape, OCR, consolidate, publish-html, deploy (sync runs as part of deploy)")
    parser.add_argument("--stage", choices=["scrape", "ocr", "consolidate", "publish-html", "cloudflare-sync", "deploy"], help="Run a single stage")
    parser.add_argument("--stores", default="lotte,superindo", help="Comma-separated store names (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would run without making changes")
    parser.add_argument("--verbose", action="store_true", help="Detailed logging to file")
    parser.add_argument("--resume", action="store_true", help="Resume from last failed stage")
    parser.add_argument("--serve", action="store_true", help="[DEPRECATED] Stage 5 deploy now handles local serving; this flag is kept for compatibility")
    parser.add_argument("--port", type=int, default=8080, help="HTTP server port when using --serve (default: 8080)")
    args = parser.parse_args()

    if not args.full and not args.stage:
        parser.error("Specify --full or --stage")

    logger = setup_logging(args.verbose)
    stores = [s.strip().lower() for s in args.stores.split(",")]
    invalid = [s for s in stores if s not in ALL_STORES]
    if invalid:
        logger.error("Unknown stores: %s (valid: %s)", ", ".join(invalid), ", ".join(ALL_STORES))
        sys.exit(1)

    print("=" * 60)
    print("  Haqita Pipeline Orchestrator")
    print(f"  Stores: {', '.join(stores)}")
    if args.dry_run:
        print("  Dry-run: YES")
    if args.verbose:
        print("  Verbose logging: YES")
    if args.resume:
        print("  Mode: Resume from last failed stage")
    print("=" * 60)
    print()

    t_start = time.time()

    if args.full and args.resume:
        # Check which stages are already complete
        scrape_status = read_stage_status("scrape")
        ocr_status = read_stage_status("ocr")
        cons_status = read_stage_status("consolidate")
        publish_status = read_stage_status("publish_html")
        deploy_status = read_stage_status("deploy")

        scrape_done = scrape_status and scrape_status.get("stores") and all(
            info.get("status") in ("new_images", "no_new", "dry_run")
            for info in scrape_status.get("stores", {}).values()
        )
        ocr_done = ocr_status and ocr_status.get("stores") and all(
            info.get("status") in ("complete", "skipped", "dry_run")
            for info in ocr_status.get("stores", {}).values()
        )
        cons_done = cons_status and cons_status.get("status") in ("complete", "dry_run")
        publish_done = publish_status and publish_status.get("status") in ("complete", "dry_run")
        # Stage 5 (cloudflare-sync) is merged into deploy now; resume uses deploy status
        deploy_done = deploy_status and deploy_status.get("status") in ("complete", "dry_run")

        if scrape_done:
            logger.info("Scrape already complete, skipping")
            print("  [SKIP] Scrape — already complete")
        else:
            print("  [RUN] Scrape")
            run_scrape(stores, args.dry_run, logger)

        print()

        if ocr_done:
            logger.info("OCR already complete, skipping")
            print("  [SKIP] OCR — already complete")
        else:
            print("  [RUN] OCR")
            ocr_result = run_ocr(stores, args.dry_run, logger)

        print()

        if cons_done:
            logger.info("Consolidation already complete, skipping")
            print("  [SKIP] Consolidation — already complete")
        else:
            print("  [RUN] Consolidation")
            cons_result = run_consolidate(args.dry_run, logger)
            if not args.dry_run and cons_result.get("status") != "error":
                commit_database(logger)

        print()

        if publish_done:
            logger.info("Publish HTML already complete, skipping")
            print("  [SKIP] Publish HTML — already complete")
        else:
            print("  [RUN] Publish HTML")
            publish_result = run_publish_html(args.dry_run, logger)

        print()

        if deploy_done:
            logger.info("Deploy already complete, skipping")
            print("  [SKIP] Deploy — already complete")
        else:
            print("  [RUN] Deploy")
            deploy_result = run_deploy(args.dry_run, logger)

        print()

    elif args.full:
        # Stage 1: Scrape all stores
        run_scrape(stores, args.dry_run, logger)
        print()

        # Stage 2: OCR all stores
        ocr_result = run_ocr(stores, args.dry_run, logger)
        print()

        # Stage 3: Consolidation (always runs)
        cons_result = run_consolidate(args.dry_run, logger)
        if not args.dry_run and cons_result.get("status") != "error":
            commit_database(logger)
        print()

        # Stage 4: Publish HTML (always runs)
        publish_result = run_publish_html(args.dry_run, logger)
        print()

        # Stage 5: Deploy + Sync (formerly two separate stages)
        deploy_result = run_deploy(args.dry_run, logger)
        if deploy_result.get("status") == "error":
            logger.error("Stage 5 (deploy+sync) failed. Use --resume to continue from here.")
            sys.exit(1)
        print()

    elif args.stage == "scrape":
        run_scrape(stores, args.dry_run, logger)

    elif args.stage == "ocr":
        ocr_result = run_ocr(stores, args.dry_run, logger)

    elif args.stage == "consolidate":
        cons_result = run_consolidate(args.dry_run, logger)

    elif args.stage == "publish-html":
        publish_result = run_publish_html(args.dry_run, logger)

    elif args.stage == "cloudflare-sync":
        logger.warning("[DEPRECATED] --stage cloudflare-sync is deprecated. Sync now runs as part of --stage deploy. Delegating to deploy...")
        deploy_result = run_deploy(args.dry_run, logger)

    elif args.stage == "deploy":
        deploy_result = run_deploy(args.dry_run, logger)

    elapsed = time.time() - t_start

    # Final summary
    print()
    print("=" * 60)
    print("  Pipeline Complete")
    print(f"  Time: {elapsed:.1f}s")
    print("=" * 60)

    # --serve is deprecated: Stage 5 deploy now handles local serving.
    # Keep the flag accepted so existing commands do not break.
    if args.serve:
        logger.warning("--serve is deprecated. Stage 5 deploy starts the local HTTP server when deploy.local is true.")
        if not args.full:
            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass

            try:
                print(f"\n[*] Starting HTTP server on http://localhost:{args.port}")
                print(f"[*] Open http://localhost:{args.port}/index.html to view results")
                print("[*] Press Ctrl+C to stop\n")
                with socketserver.TCPServer(("", args.port), QuietHandler) as httpd:
                    httpd.serve_forever()
            except Exception as e:
                logger.error("Failed to start HTTP server: %s", e)


if __name__ == "__main__":
    main()
