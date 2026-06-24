#!/usr/bin/env python3
"""Tab-content assertions and screenshot capture for agentic verification.

Loads output/html/active_promo.json, validates Products/Promos/Brochures
tabs, opens headless Chromium on the live page with show_dummy=true, and
captures screenshots.

Usage:
    python agentic_engineering/verify_tabs.py
    python agentic_engineering/verify_tabs.py --active-promo /path/to/active_promo.json
    python agentic_engineering/verify_tabs.py --active-promo ... --output-dir /path/to/evidence
"""

import argparse
import json
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("verify_tabs")

CHROME_PATHS = [
    os.path.expanduser("~/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"),
    os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell"),
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def load_active_promo(path: str) -> dict:
    if not os.path.isfile(path):
        log.error(f"active_promo.json not found at {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def validate_products_tab(data: dict):
    products = data.get("products", [])
    singles = data.get("singles", [])
    if not products and not singles:
        log.error("[FAIL] Products tab: no products or singles found")
        return False
    log.info(f"[PASS] Products tab: {len(products)} products, {len(singles)} singles")
    return True


def validate_promos_tab(data: dict):
    catalog = data.get("promo_catalog", [])
    if not catalog:
        log.error("[FAIL] Promos tab: no promo_catalog found")
        return False
    log.info(f"[PASS] Promos tab: {len(catalog)} promos in catalog")
    return True


def validate_brochures_tab(data: dict):
    products = data.get("products", [])
    singles = data.get("singles", [])
    all_items = products + singles
    image_paths = []
    for item in all_items:
        stores = item.get("stores", [])
        if not stores and item.get("image_path"):
            image_paths.append(item["image_path"])
        for s in stores:
            if s.get("image_path"):
                image_paths.append(s["image_path"])
    if not image_paths:
        log.error("[FAIL] Brochures tab: no image_path found in products/singles")
        return False
    log.info(f"[PASS] Brochures tab: {len(image_paths)} brochure images found")
    return True


def capture_screenshots(output_dir: str, chrome_path: str):
    """Open the live page with show_dummy=true using Selenium and capture screenshots per tab."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    opts = Options()
    opts.binary_location = chrome_path
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")

    driver = webdriver.Chrome(options=opts)
    try:
        url = "https://haqita.pages.dev/?show_dummy=true"
        log.info(f"Opening {url}")
        driver.get(url)

        # Wait for the page to load
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".tab-bar"))
        )
        time.sleep(3)

        # Verify dummy data is shown (dummy badge should be visible)
        try:
            badge = driver.find_element(By.ID, "dummy-badge")
            if badge.is_displayed():
                log.info("[PASS] Dummy data badge is visible")
            else:
                log.warning("[WARN] Dummy badge element found but not visible")
        except Exception:
            log.warning("[WARN] Dummy badge element not found on page")

        tabs = {
            "tab-products": "products",
            "tab-promos": "promos",
            "tab-brochures": "brochures",
        }

        for screenshot_name, tab_name in tabs.items():
            try:
                tab = driver.find_element(By.CSS_SELECTOR, f'[data-tab="{tab_name}"]')
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                screenshot_path = os.path.join(output_dir, f"{screenshot_name}.png")
                driver.save_screenshot(screenshot_path)
                log.info(f"[PASS] Screenshot saved: {screenshot_path}")
            except Exception as e:
                log.error(f"[FAIL] Could not capture {screenshot_name}: {e}")
                return False

        return True
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Verify Cloudflare tab contents and capture screenshots")
    parser.add_argument("--active-promo", default="output/html/active_promo.json",
                        help="Path to active_promo.json")
    parser.add_argument("--output-dir", default=".omo/evidence",
                        help="Directory to save screenshots and evidence")
    parser.add_argument("--no-screenshots", action="store_true",
                        help="Skip browser screenshots")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    data = load_active_promo(args.active_promo)

    all_pass = True

    json_result = {
        "products": validate_products_tab(data),
        "promos": validate_promos_tab(data),
        "brochures": validate_brochures_tab(data),
    }

    for check, passed in json_result.items():
        if not passed:
            all_pass = False

    if all_pass:
        log.info("[PASS] All JSON assertions passed")
    else:
        log.error("[FAIL] Some JSON assertions failed")
        sys.exit(1)

    # Save JSON validation result
    summary_path = os.path.join(args.output_dir, "verify_tabs_summary.json")
    with open(summary_path, "w") as f:
        json.dump(json_result, f, indent=2)
    log.info(f"Summary written to {summary_path}")

    # Screenshots
    if not args.no_screenshots:
        chrome_path = find_chrome()
        if chrome_path:
            log.info(f"Using Chrome: {chrome_path}")
            screenshots_ok = capture_screenshots(args.output_dir, chrome_path)
            if not screenshots_ok:
                log.error("[FAIL] Screenshot capture failed")
                sys.exit(1)
        else:
            log.warning("[WARN] No Chrome/Chromium binary found; skipping screenshots")
            log.info("  Install chromium-browser or point to a chrome binary")
            # Write a note to the evidence dir
            note_path = os.path.join(args.output_dir, "screenshots_skipped.txt")
            with open(note_path, "w") as f:
                f.write("Screenshots skipped: no Chrome/Chromium binary available\n")
    else:
        log.info("Screenshots skipped (--no-screenshots)")

    log.info("[PASS] All verifications passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
