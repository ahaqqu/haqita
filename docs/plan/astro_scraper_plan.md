# Astro Promo Scraper
## Implementation Plan — astronauts.id

**Stack:** Python · BeautifulSoup · JSON  
**No OCR. No images. SSR HTML parsed directly.**  
**Goal:** Extract only discounted products from active Astro promo pages.

---

## Table of Contents

1. [How the Website Works](#1-how-the-website-works)
2. [Scraper Architecture](#2-scraper-architecture)
3. [Project Files](#3-project-files)
4. [Configuration](#4-configuration)
5. [Data Schema](#5-data-schema)
6. [Implementation](#6-implementation)
7. [The locationId Problem](#7-the-locationid-problem)
8. [Integration with Main Pipeline](#8-integration-with-main-pipeline)
9. [Testing Plan](#9-testing-plan)
10. [Differences vs Lotte & Superindo](#10-differences-vs-lotte--superindo)
11. [Known Limitations & Edge Cases](#11-known-limitations--edge-cases)
12. [Future Improvements](#12-future-improvements)

---

## 1. How the Website Works

Astro's website (`astronauts.id`) is **server-side rendered**. Product names, prices, and discount percentages are baked directly into the HTML response. BeautifulSoup can parse it without a headless browser or JavaScript execution.

### 1.1 Page hierarchy

```
Homepage (astronauts.id)
  │
  ├── /promo/kombo-puas-2026        ← Product promo (scrape this)
  ├── /promo/daily-protein-af       ← Product promo (scrape this)
  ├── /promo/harvest-picks-af       ← Product promo (scrape this)
  ├── /promo/pengguna-baru          ← New user only (skip)
  ├── /promo/penggunabaru-usp       ← New user only (skip)
  └── /promo/guestmode-ff           ← Guest mode only (skip)
```

The homepage is the **source of truth** for which promo pages are currently active. Promo slugs rotate weekly — do not hardcode them.

### 1.2 Promo page HTML structure

A single promo page (e.g., `/promo/kombo-puas-2026`) mixes discounted and full-price products. The discount signal is always visible in the rendered text:

```
Discounted product:
  33%   Rp 38.000   Rp 25.600   Head & Shoulders Anti Bacterial   160ml

Full-price product (no discount):
        Rp 26.500               Sunsilk Hijab Shampoo             160ml
```

The rule is simple: **a product on discount always has a percentage badge AND two prices** (strikethrough original + discounted). Full-price products have only one price. The scraper uses this to filter promo-only products without any guessing.

### 1.3 Product URL structure

```
https://www.astronauts.id/p/{product-slug}?locationId=591&cartType=INSTANT
```

- `product-slug` is URL-normalized (lowercase, hyphens) — useful as a stable product key
- `locationId` is the hub/dark store ID — prices can differ by hub
- `cartType=INSTANT` is for 15-minute delivery

---

## 2. Scraper Architecture

```
1. Fetch homepage
       │
       ▼
2. Extract all /promo/* links
   Filter out: pengguna-baru, penggunabaru-usp, guestmode-ff, ajak-belanja
       │
       ▼ (for each promo URL, with delay)
3. Fetch promo page HTML
       │
       ▼
4. Parse product blocks
   Keep only: discount_pct present + two prices in markup
       │
       ▼
5. Deduplicate across promo pages (same product can appear in multiple pages)
       │
       ▼
6. Save → output/astro_promos_YYYYMMDD_HHMMSS.json
          output/astro_promos_latest.json (overwrite)
```

### Why this approach works without OCR

| Signal | Source | Reliability |
|---|---|---|
| Product name | `<a>` link text | High — structured HTML |
| Unit size | Link text suffix (e.g. "160ml") | High — consistent format |
| Discount % | Text prefix before prices (e.g. "33%") | High — always present when discounted |
| Original price | First `Rp` value in discounted block | High |
| Discounted price | Second `Rp` value in discounted block | High |

No OCR ambiguity. No numeral corruption. Prices are clean strings.

---

## 3. Project Files

Add the following to the existing project structure:

```
haqita/
├── scripts/
│   └── scrapers/
│       └── astro_web.py            # ← New (this plan)
│
├── data/
│   └── scrape/
│       └── astro_state.json        # Tracks previously scraped promo slugs
│
├── output/
│   ├── astro_promos_YYYYMMDD_HHMMSS.json
│   └── astro_promos_latest.json
│
└── config.yaml                     # Add astro section (see §4)
```

No new directories needed beyond `data/scrape/` which already exists.

---

## 4. Configuration

### config.yaml — add astro section

```yaml
scrapers:
  lotte:
    # ... existing config

  superindo:
    # ... existing config

  astro:
    url: https://www.astronauts.id
    location_id: 591              # Hub ID — see §7 to find yours for South Tangerang
    request_delay_seconds: 2      # Polite delay between promo page requests
    timeout_seconds: 30

    # Promo slugs that are user-specific — never contain product promos
    skip_slugs:
      - pengguna-baru
      - penggunabaru-usp
      - guestmode-ff
      - ajak-belanja

    # Minimum discount % to include (filter out 1-2% rounding promos if desired)
    min_discount_pct: 3

# Add Astro to consolidation display hints
consolidation:
  display_hints:
    stores: ["Lotte", "Superindo", "Astro"]
    store_colors:
      Lotte: "#0057A8"
      Superindo: "#E8211D"
      Astro: "#E8680C"            # Astro orange
```

---

## 5. Data Schema

### 5.1 Per-product record

```json
{
  "name": "Head & Shoulders Anti Bacterial Clean & Balanced Anti Dandruff Shampoo",
  "unit": "160ml",
  "original_price": 38000,
  "discounted_price": 25600,
  "discount_pct": 33,
  "savings": 12400,
  "product_url": "https://www.astronauts.id/p/head-shoulders-anti-bacterial-clean-balanced-anti-dandruff-shampoo-160ml?locationId=591&cartType=INSTANT",
  "product_slug": "head-shoulders-anti-bacterial-clean-balanced-anti-dandruff-shampoo-160ml",
  "promo_page": "kombo-puas-2026"
}
```

**`product_slug`** is extracted from the URL path. It is URL-normalized (lowercase, hyphens, no special chars) and serves as a stable product key for deduplication and catalog matching. This is more reliable than the OCR'd names from Lotte/Superindo.

### 5.2 Output file envelope

`output/astro_promos_YYYYMMDD_HHMMSS.json`

```json
{
  "store": "Astro",
  "scraped_at": "2026-05-14T09:00:00",
  "source_url": "https://www.astronauts.id",
  "location_id": 591,
  "promo_pages_scraped": [
    "kombo-puas-2026",
    "daily-protein-af",
    "harvest-picks-af"
  ],
  "scrape_method": "html_parse",
  "products": [
    { "...": "see §5.1" }
  ],
  "rejected": [
    {
      "reason": "no_discount_pct",
      "product_slug": "some-product-slug",
      "promo_page": "kombo-puas-2026"
    }
  ],
  "stats": {
    "promo_pages_found": 6,
    "promo_pages_scraped": 3,
    "promo_pages_skipped": 3,
    "products_with_discount": 42,
    "products_without_discount": 18,
    "duplicates_removed": 5
  }
}
```

### 5.3 State file

`data/scrape/astro_state.json` — tracks which promo slugs have been seen before, for change detection.

```json
{
  "last_run": "2026-05-14T09:00:00",
  "seen_promo_slugs": [
    "kombo-puas-2026",
    "daily-protein-af"
  ],
  "new_slugs_this_run": [
    "harvest-picks-af"
  ]
}
```

---

## 6. Implementation

### 6.1 Full script — `scripts/scrapers/astro_web.py`

```python
"""
Astro promo scraper — astronauts.id
Extracts only discounted products from active promo pages.
No OCR needed. Server-side rendered HTML parsed with BeautifulSoup.

Usage:
  python scripts/scrapers/astro_web.py
  python scripts/scrapers/astro_web.py --dry-run    # Log URLs without scraping
  python scripts/scrapers/astro_web.py --page kombo-puas-2026  # Single page
"""

import re
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.astronauts.id"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.astronauts.id/",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    import yaml
    with open(Path(__file__).parent.parent.parent / "config.yaml") as f:
        return yaml.safe_load(f)


def parse_idr_price(text: str) -> int | None:
    """
    Parse Indonesian price string to integer.
    "Rp25.600", "Rp 25.600", "25.600" → 25600
    Indonesian thousands separator is '.' — strip it before parsing.
    """
    if not text:
        return None
    s = re.sub(r'[Rr][Pp]\.?\s*', '', str(text)).strip()
    # Remove Indonesian thousands separator (dot before 3 digits)
    s = re.sub(r'\.(?=\d{3})(?!\d)', '', s)
    s = s.replace(',', '').replace(' ', '')
    try:
        val = int(float(s))
        return val if 100 <= val <= 2_000_000 else None
    except (ValueError, TypeError):
        return None


def parse_discount_pct(text: str) -> int | None:
    """Extract leading discount percentage. "33% Rp38.000 ..." → 33"""
    m = re.search(r'^(\d{1,3})%', text.strip())
    return int(m.group(1)) if m else None


def extract_unit(text: str) -> str | None:
    """
    Extract unit from product text.
    Matches: 160ml, 1.5L, 500g, 50sheets, 1pcs, 8pcs, 250sheets 2ply
    """
    m = re.search(
        r'\b(\d+(?:[.,]\d+)?\s*(?:ml|l(?:iter)?|g(?:ram)?|kg|'
        r'pcs|pack|sachet|sheets?|lembar|bks|botol|kaleng|buah)(?:\s+\d+ply)?)\b',
        text, re.IGNORECASE
    )
    return m.group(1).strip() if m else None


def clean_product_name(raw_text: str, unit: str | None) -> str:
    """
    Remove price tokens and unit from raw link text to get the product name.
    The link text often repeats the name twice (image alt + text) — deduplicate.
    """
    s = raw_text

    # Remove discount % prefix
    s = re.sub(r'^\d{1,3}%', '', s).strip()

    # Remove all price occurrences
    s = re.sub(r'Rp\s*[\d.,]+', '', s)

    # Remove unit if found
    if unit:
        s = s.replace(unit, '')

    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    # Deduplicate repeated name (image alt + text node often duplicates it)
    words = s.split()
    half = len(words) // 2
    if half > 2 and words[:half] == words[half:half * 2]:
        s = ' '.join(words[:half])

    return s.strip()


# ── Step 1: Discover active promo URLs from homepage ─────────────────────────

def get_promo_urls(cfg: dict) -> list[str]:
    """
    Scrape homepage and return all active /promo/* page URLs.
    Filters out user-specific promos (new user, referral, etc.)
    """
    skip_slugs = set(cfg['scrapers']['astro'].get('skip_slugs', []))

    try:
        resp = requests.get(BASE_URL, headers=HEADERS,
                            timeout=cfg['scrapers']['astro']['timeout_seconds'])
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch homepage: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    promo_urls = []
    seen = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if "/promo/" not in href:
            continue

        # Normalize to absolute URL
        if href.startswith("http"):
            url = href.split("?")[0]   # Strip query params
        else:
            url = BASE_URL + (href if href.startswith("/") else "/" + href)
            url = url.split("?")[0]

        slug = url.rstrip("/").split("/promo/")[-1]

        if slug in skip_slugs:
            logger.debug(f"Skipping user-specific promo: {slug}")
            continue

        if url not in seen:
            seen.add(url)
            promo_urls.append(url)
            logger.info(f"  Found promo page: /{slug}")

    logger.info(f"Discovered {len(promo_urls)} product promo pages")
    return promo_urls


# ── Step 2: Parse a single promo page ────────────────────────────────────────

def scrape_promo_page(url: str, cfg: dict) -> tuple[list[dict], list[dict]]:
    """
    Fetch one promo page and extract discounted products.
    Returns: (products_with_discount, rejected_products)
    """
    slug = url.rstrip("/").split("/promo/")[-1]
    location_id = cfg['scrapers']['astro']['location_id']
    min_discount = cfg['scrapers']['astro'].get('min_discount_pct', 3)

    try:
        resp = requests.get(url, headers=HEADERS,
                            timeout=cfg['scrapers']['astro']['timeout_seconds'])
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return [], []

    soup = BeautifulSoup(resp.text, "html.parser")
    products = []
    rejected = []

    # Find all product anchor tags — identified by the /p/ path and locationId param
    product_links = soup.find_all("a", href=re.compile(r"/p/[^?]+\?locationId="))

    # Deduplicate by product path (same product linked multiple times per block)
    seen_paths = set()
    unique_links = []
    for link in product_links:
        path = link["href"].split("?")[0]   # /p/{slug}
        if path not in seen_paths:
            seen_paths.add(path)
            unique_links.append(link)

    for link in unique_links:
        raw_text = link.get_text(separator=" ", strip=True)
        href = link.get("href", "")
        product_slug = href.split("/p/")[-1].split("?")[0]

        # ── Gate: must have a discount percentage ────────────────────────────
        discount_pct = parse_discount_pct(raw_text)
        if discount_pct is None or discount_pct < min_discount:
            rejected.append({
                "reason": "no_discount_pct" if discount_pct is None else "below_min_discount",
                "product_slug": product_slug,
                "promo_page": slug,
            })
            continue

        # ── Gate: must have two distinct prices ──────────────────────────────
        price_strings = re.findall(r'Rp\s*[\d.,]+', raw_text)
        if len(price_strings) < 2:
            rejected.append({
                "reason": "missing_second_price",
                "product_slug": product_slug,
                "promo_page": slug,
            })
            continue

        original_price = parse_idr_price(price_strings[0])
        discounted_price = parse_idr_price(price_strings[1])

        if not original_price or not discounted_price:
            rejected.append({
                "reason": "price_parse_failed",
                "product_slug": product_slug,
                "raw_prices": price_strings[:2],
                "promo_page": slug,
            })
            continue

        if discounted_price >= original_price:
            rejected.append({
                "reason": "discounted_not_lower_than_original",
                "product_slug": product_slug,
                "original": original_price,
                "discounted": discounted_price,
                "promo_page": slug,
            })
            continue

        # ── Extract unit and clean name ───────────────────────────────────────
        unit = extract_unit(raw_text)
        name = clean_product_name(raw_text, unit)

        if len(name) < 3:
            rejected.append({
                "reason": "name_too_short",
                "product_slug": product_slug,
                "raw_text": raw_text[:100],
                "promo_page": slug,
            })
            continue

        # ── Build canonical product URL with configured locationId ────────────
        product_url = f"{BASE_URL}/p/{product_slug}?locationId={location_id}&cartType=INSTANT"

        products.append({
            "name": name,
            "unit": unit,
            "original_price": original_price,
            "discounted_price": discounted_price,
            "discount_pct": discount_pct,
            "savings": original_price - discounted_price,
            "product_url": product_url,
            "product_slug": product_slug,
            "promo_page": slug,
        })

    logger.info(f"  {slug}: {len(products)} discounted, {len(rejected)} skipped")
    return products, rejected


# ── Step 3: Orchestrator ──────────────────────────────────────────────────────

def run(dry_run: bool = False, single_page: str | None = None,
        output_dir: str = "output") -> str:
    """
    Full scrape run.
    dry_run: discover URLs and log them, skip actual scraping.
    single_page: scrape only one promo slug (for testing).
    Returns path to output JSON.
    """
    cfg = load_config()
    delay = cfg['scrapers']['astro']['request_delay_seconds']
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Load state
    state_path = Path("data/scrape/astro_state.json")
    state = {"seen_promo_slugs": [], "last_run": None}
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)

    # Discover promo pages
    if single_page:
        promo_urls = [f"{BASE_URL}/promo/{single_page}"]
    else:
        promo_urls = get_promo_urls(cfg)

    if dry_run:
        logger.info("[DRY RUN] Promo URLs that would be scraped:")
        for url in promo_urls:
            slug = url.split("/promo/")[-1]
            is_new = slug not in state["seen_promo_slugs"]
            logger.info(f"  {'[NEW] ' if is_new else '       '}{url}")
        return ""

    # Scrape each promo page
    all_products = []
    all_rejected = []
    seen_product_slugs = set()
    scraped_slugs = []
    new_promo_slugs = []

    for url in promo_urls:
        slug = url.split("/promo/")[-1]
        scraped_slugs.append(slug)
        if slug not in state["seen_promo_slugs"]:
            new_promo_slugs.append(slug)

        time.sleep(delay)
        products, rejected = scrape_promo_page(url, cfg)
        all_rejected.extend(rejected)

        # Deduplicate across promo pages
        for p in products:
            if p["product_slug"] not in seen_product_slugs:
                seen_product_slugs.add(p["product_slug"])
                all_products.append(p)
            else:
                logger.debug(f"Duplicate skipped: {p['product_slug']}")

    # Build output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"astro_promos_{timestamp}.json"
    filepath = output_path / filename

    output = {
        "store": "Astro",
        "scraped_at": datetime.now().isoformat(),
        "source_url": BASE_URL,
        "location_id": cfg['scrapers']['astro']['location_id'],
        "promo_pages_scraped": scraped_slugs,
        "scrape_method": "html_parse",
        "products": all_products,
        "rejected": all_rejected,
        "stats": {
            "promo_pages_found": len(promo_urls),
            "promo_pages_scraped": len(scraped_slugs),
            "new_promo_pages": len(new_promo_slugs),
            "products_with_discount": len(all_products),
            "products_rejected": len(all_rejected),
        }
    }

    # Atomic write: temp file then rename
    import tempfile, shutil
    with tempfile.NamedTemporaryFile("w", dir=output_path, suffix=".tmp",
                                     delete=False, encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        tmp = f.name
    shutil.move(tmp, filepath)

    # Overwrite latest
    latest = output_path / "astro_promos_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Update state
    state["last_run"] = datetime.now().isoformat()
    state["seen_promo_slugs"] = list(set(state["seen_promo_slugs"]) | set(scraped_slugs))
    state["new_slugs_this_run"] = new_promo_slugs
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    logger.info(f"Saved {len(all_products)} discounted products → {filepath}")
    return str(filepath)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Astro promo scraper")
    parser.add_argument("--dry-run", action="store_true",
                        help="Discover URLs without scraping")
    parser.add_argument("--page", metavar="SLUG",
                        help="Scrape only one promo page (e.g. kombo-puas-2026)")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    run(dry_run=args.dry_run, single_page=args.page, output_dir=args.output_dir)
```

---

## 7. The locationId Problem

Every product URL on astronauts.id carries a `?locationId=591` parameter. This is Astro's hub ID — the specific dark store that fulfills orders in your area. Prices and stock availability can differ between hubs.

**Location 591** appears to be a South Jakarta/Senayan area hub. For South Tangerang, your nearest hub may have a different ID with slightly different prices.

### How to find your hub ID

1. Open `https://www.astronauts.id` in Chrome
2. Open DevTools → **Network** tab → filter by **Fetch/XHR**
3. Enter your address or allow location access on the site
4. Watch for API calls — look for requests containing `locationId` or `hubId` in the URL or response body
5. Note the number — that's your hub ID for South Tangerang

Alternatively: browse to any product page, allow location, and read the `locationId` from the URL that appears in your browser's address bar.

Once found, set it in `config.yaml`:

```yaml
scrapers:
  astro:
    location_id: 591    # Replace with your hub ID
```

### What happens if you use the wrong hub ID

The scraper still works — you get prices from a different hub. For comparison against Lotte/Superindo, the price difference is usually small (0–5%). If accuracy is critical, use the correct hub ID. If you just want a general picture, 591 is fine as a starting point.

---

## 8. Integration with Main Pipeline

### 8.1 Adding Astro to `consolidate.py`

Astro products integrate into the existing pipeline with one change: the matching key candidate is `product_slug` (URL-normalized), which is cleaner than OCR'd names from Lotte/Superindo.

```python
# In consolidate.py — load all three store files
def load_latest_store_file(store_name: str, output_dir: str) -> dict | None:
    pattern = f"{store_name.lower()}_promos_*.json"
    files = sorted(Path(output_dir).glob(pattern))
    if not files:
        logger.warning(f"No output file found for {store_name}")
        return None
    with open(files[-1]) as f:
        return json.load(f)

lotte_data = load_latest_store_file("lotte", "output")
superindo_data = load_latest_store_file("superindo", "output")
astro_data = load_latest_store_file("astro", "output")      # ← Add this
```

### 8.2 Astro-specific matching hint

When matching Astro products against Lotte/Superindo, the `product_slug` encodes the full product name in normalized form (lowercase, hyphens). You can use it as an additional exact-match signal before the embedding step:

```python
def slug_to_tokens(slug: str) -> frozenset:
    """
    Convert URL slug to token set for matching.
    "head-shoulders-anti-bacterial-160ml" → {"head", "shoulders", "anti", "bacterial"}
    Remove unit-like tokens to avoid false positives.
    """
    tokens = slug.replace("-", " ").split()
    unit_tokens = {"ml", "g", "kg", "l", "pcs", "pack", "gram", "sheets", "sachet"}
    return frozenset(
        t for t in tokens
        if len(t) > 1 and not re.match(r'^\d+$', t) and t not in unit_tokens
    )
```

Add this as a pre-check in Gate 3 (exact token-set match) of the matching pipeline:

```python
# Gate 3 addition: slug-token match for Astro products
if hasattr(product_a, 'product_slug') or hasattr(product_b, 'product_slug'):
    slug = (product_a.get('product_slug') or product_b.get('product_slug', ''))
    slug_tokens = slug_to_tokens(slug)
    name_tokens_other = canonical_tokens(product_b['name'] if product_a.get('product_slug') else product_a['name'])
    if slug_tokens and slug_tokens.issubset(name_tokens_other):
        # Strong match: all slug tokens found in the other product's name
        matched_pairs.append({..., 'match_method': 'slug_exact', 'match_confidence': 0.97})
```

### 8.3 Adding Astro to `haqita.bat`

```batch
echo  [1] Scrape Lotte Mart promos
echo  [2] Scrape Superindo promos
echo  [3] Scrape Astro promos               ← Add this
echo  [4] Dry-run Lotte
echo  [5] Dry-run Superindo
echo  [6] Dry-run Astro                     ← Add this
echo  [7] Consolidate ^& build index.html
echo  [8] Full pipeline (all 3 stores)      ← Update this

if "%choice%"=="3" python scripts/scrapers/astro_web.py
if "%choice%"=="6" python scripts/scrapers/astro_web.py --dry-run
```

Full pipeline update:

```batch
:FULL_PIPELINE
echo [1/5] Health check...
python scripts/health_check.py || goto PIPELINE_FAIL
echo [2/5] Scraping Lotte...
python scripts/scrapers/lotte_qwen.py || echo Lotte failed, continuing...
echo [3/5] Scraping Superindo...
python scripts/scrapers/superindo_qwen.py || echo Superindo failed, continuing...
echo [4/5] Scraping Astro...
python scripts/scrapers/astro_web.py || echo Astro failed, continuing...
echo [5/5] Consolidating...
python scripts/consolidate.py
```

### 8.4 Astro in `consolidated_latest.json`

Astro products have `effective_unit_price` equal to `discounted_price` (no bundle math needed for the basic case). The `promo_type` is always `"discount_pct"` for the core scraper.

```json
{
  "store": "Astro",
  "price": 38000,
  "effective_unit_price": 25600,
  "bundle_size": 1,
  "promo": "33% off",
  "promo_type": "discount_pct",
  "discount_pct": 33,
  "period": null,
  "valid_until": null
}
```

Note: Astro does not show validity dates on promo pages. `valid_until` is always null for Astro products unless scraped from a dedicated campaign page that includes dates.

---

## 9. Testing Plan

### 9.1 Unit tests

| Test | Input | Expected |
|---|---|---|
| `parse_idr_price` | `"Rp25.600"` | `25600` |
| `parse_idr_price` | `"Rp 1.250.000"` | `1250000` |
| `parse_idr_price` | `"???"` | `None` |
| `parse_idr_price` | `"Rp 50"` (below min) | `None` |
| `parse_discount_pct` | `"33% Rp38.000 Rp25.600"` | `33` |
| `parse_discount_pct` | `"Rp26.500 Sunsilk"` | `None` |
| `extract_unit` | `"Dove Shampoo 135ml"` | `"135ml"` |
| `extract_unit` | `"Soft Facial Tissue 250sheets 2ply"` | `"250sheets 2ply"` |
| `extract_unit` | `"Sabut Spons 1pcs"` | `"1pcs"` |
| `clean_product_name` | `"33% Rp38.000 Rp25.600 Dove Shampoo Dove Shampoo 135ml"` | `"Dove Shampoo"` |
| `slug_to_tokens` | `"head-shoulders-160ml"` | `{"head", "shoulders"}` |

```bash
python -m pytest tests/test_astro_parsers.py -v
```

### 9.2 Dry run test

```bash
python scripts/scrapers/astro_web.py --dry-run
```

Expected: lists all discovered promo URLs with `[NEW]` markers, no network requests beyond the homepage.

### 9.3 Single page test

```bash
python scripts/scrapers/astro_web.py --page kombo-puas-2026
```

Expected output file with only discounted products from that one page. Verify manually against the live page in browser.

### 9.4 Full run test

```bash
python scripts/scrapers/astro_web.py
```

Checks:
- Output JSON is valid
- All products have `discount_pct > 0`
- All products have `discounted_price < original_price`
- No product has `name` shorter than 3 characters
- `astro_promos_latest.json` is updated
- `data/scrape/astro_state.json` is updated with current slugs

### 9.5 Duplicate detection test

Run scraper twice in a row. Second run should produce the same product list but `new_promo_pages` in state should be empty.

### 9.6 Rejection logging test

Feed a manually crafted HTML with non-discounted products. Verify they appear in `rejected[]` with correct `reason` field.

### 9.7 Edge cases

| Scenario | Expected behaviour |
|---|---|
| Homepage returns no `/promo/` links | Log error, return empty, no crash |
| A promo page returns 403 | Log error for that page, continue to next |
| Product with 1% discount (below `min_discount_pct: 3`) | Added to `rejected[]` with `below_min_discount` |
| Product name duplicated 3× in text | `clean_product_name` handles up to 2× — add test for 3× if seen |
| Price string `"Rp 1.250.000"` (two thousands separators) | Must parse to `1250000` not `1250` |
| Promo page with no discounted products (all full price) | Returns empty list, no crash |
| `location_id` missing from config | Raise `KeyError` with clear message |

---

## 10. Differences vs Lotte & Superindo

| Aspect | Lotte / Superindo | Astro |
|---|---|---|
| **Source format** | Brochure images (JPG/PNG) | Live HTML webpage |
| **Extraction method** | OCR via Gemini | BeautifulSoup HTML parse |
| **Data freshness** | Weekly (brochure cycle) | Near real-time (can change daily) |
| **Promo detection** | Inferred from promo text field | Explicit: discount % + two prices in HTML |
| **OCR errors** | Yes — numeral corruption, unit errors | None — structured clean text |
| **Price reliability** | Medium | High |
| **Location dependency** | No (citywide brochure) | Yes — prices vary by hub ID |
| **Requires Gemini API** | Yes | No |
| **Requires internet** | Yes (image download) | Yes (web request) |
| **Valid-until date** | Usually present in brochure | Rarely present on promo pages |
| **Bundle pricing** | Common (dapat 5 pcs) | Sometimes (handled by `promo_parser`) |
| **Rate limit risk** | Low (few image downloads) | Medium (one request per promo page) |
| **Product key quality** | OCR'd name (noisy) | URL slug (clean, normalized) |

---

## 11. Known Limitations & Edge Cases

### Products visible on promo page but not actually discounted

Some Astro promo pages (especially "Kombo" and "Pilih 2" pages) include full-price items as part of a bundle mechanic — the discount only applies when you buy a specific combination. These look like non-discounted products in the HTML (single price, no %). The scraper correctly skips them. They appear in `rejected[]` with `no_discount_pct`.

**The bundle mechanic itself** ("Pilih 2, Diskon 15%") is announced as a section header in the HTML (e.g., `💆🏻‍♀️ Kombo Rambut Badai: Pilih 2 Diskon 15%`), not as a per-product attribute. Capturing this requires section-level parsing, which is a future improvement (see §12).

### No validity dates

Astro does not display promo validity dates on product listing pages. The `valid_until` field is always `null` in Astro output. This means the HTML comparison (`valid_until` sorting in the UI) will always rank Astro as "unknown expiry". Work around this by checking the site manually or scraping campaign detail pages when available.

### Hub-dependent prices

If a product is cheaper at hub 591 than your local South Tangerang hub, the scraper reports the wrong price. Find your correct hub ID (see §7) to avoid this.

### Page structure can change

Astro updates their frontend regularly. The product link selector (`href=re.compile(r"/p/[^?]+\?locationId=")`) is robust — it targets the URL pattern rather than CSS class names, which are more likely to change. If the scraper stops finding products, check: (1) if the URL pattern changed, (2) if products now load via XHR instead of SSR.

### `clean_product_name` handles 2× duplication, not 3×

The link text deduplication logic handles the most common case (name repeated twice). If Astro's markup changes to repeat the name three times, names will be truncated. Add a test case if you see this in production.

---

## 12. Future Improvements

### Section-level bundle promo parsing

The "Pilih 2, Diskon 15%" mechanic is the most common promo type on Astro's Kombo pages. Capturing it requires parsing section headers alongside product blocks:

```python
# Future: scrape section headers + their products
sections = soup.find_all("h2")  # Section headers like "💆🏻‍♀️ Kombo Rambut Badai: Pilih 2 Diskon 15%"
for header in sections:
    bundle_discount = parse_discount_pct_from_header(header.text)
    # Collect sibling product blocks under this header
```

This gives a `conditional_discount_pct` field in the output, distinguishing it from per-product discounts.

### Validity date from campaign detail pages

Some Astro campaigns have detail pages with start/end dates. These can be scraped by following links from the promo page to individual campaign metadata. Low priority since most Astro promos are short-lived anyway.

### XHR API interception (more robust long-term)

If Astro migrates to client-side rendering (React/Next.js with API calls), HTML parsing breaks. At that point, intercept the underlying API endpoints using browser DevTools → Network → XHR/Fetch. Astro's API likely returns structured JSON, which is even easier to parse than HTML. Document the discovered endpoints in `docs/astro_api_endpoints.md` when this becomes necessary.

### Run frequency

Astro promos can change daily (flash deals, expiring campaigns). Consider running the Astro scraper daily while keeping Lotte/Superindo weekly (they're brochure-based). Add to `haqita.bat`:

```batch
echo  [9] Quick refresh: Astro only (no OCR, fast)
if "%choice%"=="9" python scripts/scrapers/astro_web.py && python scripts/consolidate.py --astro-only
```

The `--astro-only` flag in consolidate.py would rebuild the output JSON using the cached Lotte/Superindo data plus the fresh Astro data, without re-running OCR.

### Price history for Astro

Astro prices can change between scrape runs. The existing `price_history.json` schema handles this — just ensure Astro products are appended the same way as Lotte/Superindo products after each consolidation run. Over 4–6 weeks this will reveal which Astro products have genuinely stable promo prices vs volatile flash deals.
