"""
Scrape all stores — Docker entry point.
Runs Lotte and Superindo scrapers sequentially.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.scrapers.lotte import main as lotte_main
from scripts.scrapers.superindo import main as superindo_main

if __name__ == "__main__":
    print("=" * 60)
    print("  Scrape All Stores (Docker)")
    print("=" * 60)
    print()

    print("--- Lotte Mart ---")
    lotte_main()
    print()

    print("--- Superindo ---")
    superindo_main()
    print()

    print("Scrape complete.")
