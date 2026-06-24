#!/usr/bin/env python3
"""
Reset generated pipeline state in the current workspace.

This makes agentic runs idempotent. Run it inside the workspace you want to
clean (the real repo, or a temp workspace created by run_agentic.sh).

Usage:
    .venv/bin/python tests/dummy/clean_dummy_data.py
    .venv/bin/python tests/dummy/clean_dummy_data.py --d1-local
    .venv/bin/python tests/dummy/clean_dummy_data.py --d1-db-name haqita-db
"""

import argparse
import glob
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def clean_local() -> None:
    patterns = [
        "output/stage_results/*.json",
        "database/scrape/*/state.json",
        "database/ocr/*/state.json",
        "database/ocr/*/*.json",
        "database/price_history.json",
        "database/price_history.json.backup",
        "database/product_catalog.json",
        "database/review_queue.json",
        "database/sync_state.json",
        "output/html/*",
    ]
    removed = 0
    for pattern in patterns:
        for path in glob.glob(str(ROOT / pattern)):
            p = Path(path)
            if p.is_file():
                p.unlink()
                removed += 1
            elif p.is_dir():
                for child in p.iterdir():
                    if child.is_file():
                        child.unlink()
                removed += 1
    for d in [ROOT / "output" / "stage_results", ROOT / "output" / "html"]:
        d.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Removed {removed} generated file(s) from {ROOT}")


def clean_d1_local() -> None:
    d1_dir = ROOT / ".wrangler" / "state" / "v3" / "d1"
    if not d1_dir.exists():
        print("[!] No local D1 SQLite file found")
        sys.exit(1)
    for db_file in d1_dir.rglob("*.sqlite"):
        try:
            conn = sqlite3.connect(str(db_file))
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if {"stores", "products", "prices", "promos"} <= tables:
                for table in ["prices", "promos", "products", "stores"]:
                    conn.execute(f"DELETE FROM {table}")
                conn.commit()
                conn.close()
                print(f"[OK] Truncated D1 tables in {db_file}")
                return
        except Exception:
            continue
    print("[!] No local D1 SQLite file with haqita schema found")
    sys.exit(1)


def clean_d1_remote(db_name: str) -> None:
    sql_file = ROOT / "agentic_engineering" / "dummy" / "clean_d1.sql"
    cmd = ["wrangler", "d1", "execute", db_name, "--file", str(sql_file)]
    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("[!] D1 cleanup failed")
        sys.exit(1)
    print(f"[OK] Truncated D1 tables in remote database '{db_name}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean generated pipeline state")
    parser.add_argument("--d1-local", action="store_true", help="Clean local wrangler D1 SQLite")
    parser.add_argument("--d1-db-name", help="Clean remote D1 database via wrangler")
    args = parser.parse_args()

    clean_local()
    if args.d1_local:
        clean_d1_local()
    if args.d1_db_name:
        clean_d1_remote(args.d1_db_name)

    print("[OK] Cleanup complete")


if __name__ == "__main__":
    main()
