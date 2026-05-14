# Haqita — Grocery Price Comparison Tool
## Full Implementation Plan

**Stack:** Python scripts · JSON files · Single HTML output  
**No server. No database. No deployment.**  
**End goal:** `index.html` that shows scraped promo data with accurate cross-store price comparison.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Configuration](#3-configuration)
4. [Data Schemas](#4-data-schemas)
5. [Phase 1 — Superindo Scraper](#5-phase-1--superindo-scraper)
6. [Phase 2 — Consolidation & Product Matching](#6-phase-2--consolidation--product-matching)
7. [Phase 3 — HTML Display](#7-phase-3--html-display)
8. [Phase 4 — Integration & Menu](#8-phase-4--integration--menu)
9. [Testing Strategy](#9-testing-strategy)
10. [Future Improvements](#10-future-improvements)

---

## 1. Architecture Overview

```
  Lotte Mart website          Superindo website
        │                           │
        ▼                           ▼
 lotte_qwen.py              superindo_qwen.py
        │                           │
        ▼                           ▼
lotte_promos_DATE.json   superindo_promos_DATE.json
        │                           │
        └──────────┬────────────────┘
                   ▼
            consolidate.py
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
consolidated_  consolidated_  price_
DATE.json      latest.json    history.json
                   │
                   ▼
              index.html
          (reads JSON at open)
```

### Design Principles

1. **Simple over clever** — no abstractions that don't earn their complexity at this scale
2. **Fail gracefully** — partial results beat no results; log everything that fails
3. **Pre-compute for the HTML** — all math (unit prices, savings %) done in Python, not JS
4. **Accuracy first** — matching a wrong product across stores is worse than showing no match

---

## 2. Project Structure

```
haqita/
├── haqita.bat                          # Main menu (Windows)
├── config.yaml                         # All tunable settings
├── .env                                # Secrets and provider toggles (never committed)
├── .env.example                        # Template for .env
│
├── scripts/
│   ├── scrapers/
│   │   ├── lotte_qwen.py               # Lotte Mart scraper (existing)
│   │   └── superindo_qwen.py           # Superindo scraper (Phase 1)
│   ├── consolidate.py                  # Merge + match + output JSON (Phase 2)
│   ├── ocr/
│   │   ├── ocr_processor.py            # Shared OCR interface (Ollama or Gemini)
│   │   └── image_preprocess.py         # Image prep before OCR
│   ├── matching/
│   │   ├── normalizer.py               # Name/unit/brand normalization
│   │   ├── matcher.py                  # Multi-tier matching pipeline
│   │   └── promo_parser.py             # Indonesian promo text parser
│   └── health_check.py                 # Pre-run environment validation
│
├── data/
│   └── scrape/
│       ├── lotte/                      # Downloaded brochure images (Lotte)
│       ├── superindo/                  # Downloaded brochure images (Superindo)
│       ├── lotte_state.json            # MD5 hashes of processed Lotte images
│       └── superindo_state.json        # MD5 hashes of processed Superindo images
│
├── output/
│   ├── lotte_promos_YYYYMMDD_HHMMSS.json
│   ├── superindo_promos_YYYYMMDD_HHMMSS.json
│   ├── consolidated_YYYYMMDD_HHMMSS.json
│   ├── consolidated_latest.json        # Always the latest run — HTML reads this
│   ├── price_history.json              # Accumulated snapshots across runs
│   ├── price_history.json.backup       # Auto-backup before every write
│   ├── product_catalog.json            # Auto-built product registry
│   └── review_queue.json               # Low-confidence matches for inspection
│
├── index.html                          # The deliverable — opens in any browser
│
├── test_data/
│   ├── lotte/
│   │   ├── sample_html/
│   │   ├── sample_images/
│   │   └── golden_outputs/
│   ├── superindo/
│   │   ├── sample_html/
│   │   ├── sample_images/
│   │   └── golden_outputs/
│   └── consolidate/
│       ├── sample_lotte_promos.json
│       ├── sample_superindo_promos.json
│       ├── edge_cases/
│       └── golden_outputs/
│
└── docs/
    ├── lotte_scraper.md
    ├── superindo_scraper.md
    └── matching_decisions.md           # Log of threshold decisions and why
```

---

## 3. Configuration

### config.yaml

```yaml
scrapers:
  lotte:
    url: https://www.lottemart.co.id/all-promo-mart
    min_image_size_kb: 50
    request_delay_seconds: 2

  superindo:
    url: https://www.superindo.co.id/promosi/katalog-super-hemat/
    region_filter: jabodetabek-palembang
    min_image_size_kb: 50
    request_delay_seconds: 2

ocr:
  provider: ollama                    # "ollama" or "gemini" — override in .env
  model_ollama: qwen3-vl:7b           # Use 7b for accuracy; 2b as fallback if RAM limited
  model_gemini: gemini-2.0-flash      # Used when OCR_PROVIDER=gemini in .env
  timeout_seconds: 120
  max_retries: 2
  temperature: 0                      # Always 0 for OCR — deterministic output
  image_min_width_px: 1400            # Scale up smaller images before OCR
  image_contrast_enhance: 1.4
  image_sharpness_enhance: 1.2

consolidation:
  # Matching pipeline thresholds
  token_jaccard_min: 0.30             # Below this: skip pair before embedding
  embedding_model: paraphrase-multilingual-MiniLM-L12-v2
  embedding_auto_match: 0.85          # Embedding score >= this: auto-match
  embedding_ambiguous_low: 0.55       # Below this: no match
                                      # Between 0.55-0.85: send to AI verifier
  unit_tolerance_pct: 15              # UnitParser: allow ±15% for OCR unit noise
  price_ratio_max: 3.0                # Per-unit price ratio > this: flag match

  # AI verifier (only for ambiguous embedding pairs)
  ai_model: qwen3:4b
  ai_batch_size: 20

validation:
  min_price: 100
  max_price: 1_000_000
  min_product_name_length: 3
  ocr_confidence_flag_threshold: 0.7  # Flag for review (don't reject)

monitoring:
  review_queue_max: 100
  metrics_enabled: true
```

### .env.example

```dotenv
# Copy to .env and fill in values. Never commit .env to git.

# OCR provider override: "ollama" (default, local) or "gemini" (cloud, free tier)
# OCR_PROVIDER=ollama

# Required only when OCR_PROVIDER=gemini
# Get your free key at: https://aistudio.google.com/apikey
# GEMINI_API_KEY=your_key_here
```

### Loading config in scripts

```python
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv  # pip install python-dotenv

load_dotenv()  # Reads .env if present, silently skips if missing

def load_config() -> dict:
    with open(Path(__file__).parent.parent / 'config.yaml') as f:
        cfg = yaml.safe_load(f)
    # .env can override OCR provider without editing config.yaml
    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg['ocr']['gemini_api_key'] = env_key
    return cfg
```

---

## 4. Data Schemas

### 4.1 OCR output (per store, per run)

`lotte_promos_YYYYMMDD_HHMMSS.json` / `superindo_promos_YYYYMMDD_HHMMSS.json`

```json
{
  "store": "Lotte",
  "scraped_at": "2026-05-14T07:39:37",
  "source_url": "https://www.lottemart.co.id/all-promo-mart",
  "images_processed": 6,
  "ocr_provider": "ollama",
  "ocr_model": "qwen3-vl:7b",
  "products": [
    {
      "name": "Indomie Goreng Ayam Geprek",
      "brand": "Indomie",
      "unit": "85 g",
      "price": 15500,
      "promo": "DAPAT 5 pcs",
      "period": "7 - 20 Mei 2026",
      "image_source": "promo_lotte_abc123.jpg",
      "ocr_raw_price": "Rp 15.500",
      "ocr_confidence": 0.91
    }
  ],
  "rejected": [
    {
      "raw": {"name": "X", "price": "Rp ???"},
      "reason": "price_unparseable",
      "image_source": "promo_lotte_def456.jpg"
    }
  ],
  "stats": {
    "products_extracted": 42,
    "products_rejected": 2,
    "images_failed_ocr": 1
  }
}
```

### 4.2 Consolidated output (read by index.html)

`consolidated_latest.json`

```json
{
  "generated_at": "2026-05-14T08:20:00",
  "scrape_dates": {
    "Lotte": "2026-05-14T07:39:37",
    "Superindo": "2026-05-14T08:15:00"
  },
  "source_files": [
    "lotte_promos_20260514_073937.json",
    "superindo_promos_20260514_081500.json"
  ],
  "display_hints": {
    "stores": ["Lotte", "Superindo"],
    "store_colors": { "Lotte": "#0057A8", "Superindo": "#E8211D" },
    "currency": "IDR",
    "locale": "id-ID"
  },
  "products": [
    {
      "key": "indomie-goreng-ayam-geprek--indomie--85g",
      "name": "Indomie Goreng Ayam Geprek",
      "brand": "Indomie",
      "unit": "85 g",
      "unit_type": "weight",
      "unit_value_g": 85,
      "stores": [
        {
          "store": "Lotte",
          "price": 15500,
          "effective_unit_price": 3100,
          "bundle_size": 5,
          "promo": "DAPAT 5 pcs",
          "promo_type": "bundle_buy",
          "period": "7 - 20 Mei 2026",
          "valid_until": "2026-05-20"
        },
        {
          "store": "Superindo",
          "price": 3500,
          "effective_unit_price": 3500,
          "bundle_size": 1,
          "promo": null,
          "promo_type": "single",
          "period": "12 - 25 Mei 2026",
          "valid_until": "2026-05-25"
        }
      ],
      "price_min": 3100,
      "price_max": 3500,
      "cheapest_store": "Lotte",
      "price_gap": 400,
      "savings_pct": 11.4,
      "has_promo": true,
      "promo_summary": "Dapat 5 pcs di Lotte",
      "valid_until": "2026-05-20",
      "match_method": "exact",
      "match_confidence": 1.0
    }
  ],
  "singles": [
    {
      "key": "abc-kecap-manis--abc--600ml",
      "name": "ABC Kecap Manis",
      "brand": "ABC",
      "unit": "600 ml",
      "store": "Lotte",
      "price": 18900,
      "effective_unit_price": 18900,
      "promo": null,
      "period": "7 - 20 Mei 2026",
      "valid_until": "2026-05-20"
    }
  ],
  "stats": {
    "total_products_lotte": 42,
    "total_products_superindo": 38,
    "matched_across_stores": 15,
    "lotte_only": 27,
    "superindo_only": 23,
    "match_methods": { "exact": 10, "embedding": 4, "ai": 1 },
    "flagged_for_review": 2,
    "validation_rejected": 3
  }
}
```

**Key difference from original plan:** `singles` (store-specific products) is a separate list from `products` (cross-store matches). This makes the HTML logic much simpler — matched products always have `stores[]`, singles always have one store.

### 4.3 Price history

`price_history.json`

```json
{
  "snapshots": [
    {
      "product_key": "indomie-goreng-ayam-geprek--indomie--85g",
      "name": "Indomie Goreng Ayam Geprek",
      "brand": "Indomie",
      "unit": "85 g",
      "date": "2026-05-14",
      "store": "Lotte",
      "price": 15500,
      "effective_unit_price": 3100,
      "promo": "DAPAT 5 pcs"
    }
  ],
  "metadata": {
    "last_updated": "2026-05-14T08:20:00",
    "total_runs": 1,
    "schema_version": "1.1"
  }
}
```

### 4.4 Product catalog (auto-built, used for matching)

`output/product_catalog.json`

```json
{
  "catalog": {
    "indomie-goreng-ayam-geprek--indomie--85g": {
      "canonical_key": "indomie-goreng-ayam-geprek--indomie--85g",
      "display_name": "Indomie Goreng Ayam Geprek",
      "brand": "Indomie",
      "unit": "85 g",
      "unit_type": "weight",
      "unit_value_g": 85,
      "first_seen": "2026-05-14",
      "last_seen": "2026-05-14",
      "appearance_count": 1,
      "stores_found": ["Lotte"],
      "name_variants": [
        {"name": "Indomie Goreng Ayam Geprek", "count": 1, "store": "Lotte"}
      ],
      "confidence": 0.4,
      "manually_verified": false
    }
  },
  "metadata": {
    "total_entries": 42,
    "last_updated": "2026-05-14T08:20:00",
    "schema_version": "1.1"
  }
}
```

---

## 5. Phase 1 — Superindo Scraper

**Deliverable:** `scripts/scrapers/superindo_qwen.py`  
**Effort:** ~250 lines (reuses OCR infrastructure from Lotte scraper)

### 5.1 Superindo page structure

Superindo has two promo pages:

| Page | URL | Content |
|---|---|---|
| Katalog Super Hemat | `/promosi/katalog-super-hemat/` | Regional brochure images in swiper slider |
| Promo Koran | `/promosi/promo-koran/` | Single newspaper promo image |

Start with Katalog Super Hemat. Add Promo Koran in a later iteration.

### 5.2 HTML structure to parse

```html
<div class="swiper-slide">
  <a class="fancybox"
     data-fancybox="jabodetabek-palembang"
     href="https://www.superindo.co.id/images/katalog/6a04...DKI.jpg">
    <img src="https://www.superindo.co.id/images/katalog/6a04...DKI.jpg">
  </a>
</div>
```

The `data-fancybox` value is the region name. Filter for `jabodetabek-palembang` only.

### 5.3 Scraper flow

```
1.  Fetch GET https://www.superindo.co.id/promosi/katalog-super-hemat/
2.  Parse HTML with BeautifulSoup
3.  Find all .swiper-slide elements → filter data-fancybox="jabodetabek-palembang"
4.  Extract image URLs from href attributes
5.  Load data/scrape/superindo_state.json (create empty if not exists)
6.  For each image URL:
    a. Compute MD5 of URL string
    b. If MD5 already in state.json → SKIP (already processed)
    c. Download image to data/scrape/superindo/<md5>_<filename>
    d. Validate: size > 50 KB, dimensions > 300×300 px
    e. If --dry-run flag: log URL, skip OCR
    f. Preprocess image (contrast + scale)
    g. Run OCR → extract products
    h. Validate + clean each product
    i. Append to results list
7.  Save results to output/superindo_promos_YYYYMMDD_HHMMSS.json
8.  Update superindo_state.json with newly processed MD5s
```

### 5.4 Shared OCR interface

Create `scripts/ocr/ocr_processor.py` as a unified OCR interface. Both scrapers import from here.

```python
import json
import re
import os
import requests
from pathlib import Path

# OCR_PROMPT shared by both scrapers
OCR_PROMPT = """Extract all product promotions from this Indonesian supermarket brochure image.

Return ONLY a valid JSON array. No explanation. No markdown code fences. Start with [ and end with ].

Each item must follow this exact structure:
{
  "name": "full product name as shown",
  "brand": "brand name if visible, else null",
  "unit": "size as shown (e.g. '85 g', '1.5 L', '6 x 45 ml'), else null",
  "price": <integer in IDR, numbers only, no dots or Rp symbol>,
  "promo": "promo text if any (e.g. 'DAPAT 5 pcs', 'Beli 2 Gratis 1'), else null",
  "period": "validity dates if shown (e.g. '7 - 20 Mei 2026'), else null"
}

Rules:
- price MUST be an integer (3500 not "Rp 3.500"). Indonesian thousands separator is '.' — ignore it.
- If you are not confident about a price, omit that product entirely.
- Extract EVERY product visible, including small-text items.
- Ignore store logos, decorative banners, and page numbers."""


def call_ollama_ocr(image_path: str, cfg: dict) -> list[dict]:
    """Call local Ollama with qwen3-vl model."""
    import base64
    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": cfg['ocr']['model_ollama'],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": OCR_PROMPT}
            ]
        }],
        "stream": False,
        "options": {
            "temperature": cfg['ocr']['temperature'],
            "num_ctx": 8192,
            "seed": 42
        }
    }
    resp = requests.post("http://localhost:11434/api/chat", json=payload,
                         timeout=cfg['ocr']['timeout_seconds'])
    resp.raise_for_status()
    raw_text = resp.json()['message']['content']
    return _parse_ocr_json(raw_text)


def call_gemini_ocr(image_path: str, cfg: dict) -> list[dict]:
    """Call Gemini 2.0 Flash API (free tier). Requires GEMINI_API_KEY in .env."""
    import base64
    import google.generativeai as genai  # pip install google-generativeai

    api_key = cfg['ocr'].get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(cfg['ocr']['model_gemini'])

    with open(image_path, 'rb') as f:
        img_bytes = f.read()

    response = model.generate_content([
        {"mime_type": "image/jpeg", "data": img_bytes},
        OCR_PROMPT
    ])
    return _parse_ocr_json(response.text)


def extract_products(image_path: str, cfg: dict) -> list[dict]:
    """
    Main entry point. Routes to Ollama or Gemini based on config/env.
    Retries once on JSON parse failure.
    """
    provider = cfg['ocr'].get('provider', 'ollama')

    for attempt in range(cfg['ocr']['max_retries']):
        try:
            if provider == 'gemini':
                return call_gemini_ocr(image_path, cfg)
            else:
                return call_ollama_ocr(image_path, cfg)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == cfg['ocr']['max_retries'] - 1:
                raise
            # Give explicit retry instruction on second attempt
            # (handled inside individual call functions)
    return []


def _parse_ocr_json(raw_text: str) -> list[dict]:
    """Strip markdown fences and parse JSON array from OCR response."""
    # Remove ```json ... ``` or ``` ... ``` wrappers
    clean = re.sub(r'^```[a-z]*\s*|\s*```$', '', raw_text.strip(), flags=re.MULTILINE)
    # Find the JSON array (starts with [ ends with ])
    match = re.search(r'\[.*\]', clean, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in OCR response: {clean[:200]}")
    return json.loads(match.group(0))
```

### 5.5 Image preprocessing

Create `scripts/ocr/image_preprocess.py`:

```python
from PIL import Image, ImageEnhance
from pathlib import Path

def preprocess_for_ocr(img_path: str, cfg: dict) -> str:
    """
    Enhance image before OCR. Saves to a temp file.
    Returns path to the processed image.
    """
    img = Image.open(img_path).convert('RGB')

    # Scale up if too small — VL models work better on larger images
    min_w = cfg['ocr']['image_min_width_px']
    if img.width < min_w:
        scale = min_w / img.width
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    # Enhance contrast and sharpness
    img = ImageEnhance.Contrast(img).enhance(cfg['ocr']['image_contrast_enhance'])
    img = ImageEnhance.Sharpness(img).enhance(cfg['ocr']['image_sharpness_enhance'])

    # Save processed version alongside original
    processed_path = str(img_path).replace('.jpg', '_proc.jpg').replace('.jpeg', '_proc.jpg')
    img.save(processed_path, 'JPEG', quality=92)
    return processed_path


def split_image_halves(img_path: str) -> tuple[str, str]:
    """
    Split a tall brochure page into top and bottom halves.
    Use when OCR returns fewer than 3 products on a page with dense content.
    """
    img = Image.open(img_path).convert('RGB')
    w, h = img.size
    top_path = img_path.replace('.jpg', '_top.jpg')
    bot_path = img_path.replace('.jpg', '_bot.jpg')
    img.crop((0, 0, w, h // 2)).save(top_path, 'JPEG', quality=92)
    img.crop((0, h // 2, w, h)).save(bot_path, 'JPEG', quality=92)
    return top_path, bot_path
```

### 5.6 OCR output validation

Validate every product extracted by OCR before saving. This is done inline in each scraper.

```python
import re

# Indonesian price string: "Rp 8.500", "8.500", "8,500" → integer 8500
def clean_price(raw) -> int | None:
    if raw is None:
        return None
    s = re.sub(r'[Rr][Pp]\.?\s*', '', str(raw)).strip()
    # Remove Indonesian thousands separator (dot before 3 digits, not decimal)
    s = re.sub(r'(\d)\.(\d{3})(?!\d)', r'\1\2', s)
    s = s.replace(',', '').replace(' ', '').replace('.', '')
    try:
        val = int(float(s))
        return val if 100 <= val <= 1_000_000 else None
    except (ValueError, TypeError):
        return None

# Fix common numeral OCR corruptions in unit strings
_UNIT_CORRECTIONS = [
    (r'\bSg\b', '5g'), (r'\bBg\b', '8g'),
    (r'\bIOO\b', '100'), (r'\bI00\b', '100'),
    (r'\bS00\b', '500'), (r'\bSOO\b', '500'),
    (r'\bl\b', '1'),   # lowercase L as digit 1 in unit context
]
def clean_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    for pattern, replacement in _UNIT_CORRECTIONS:
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
    return s if s else None

def validate_product(raw: dict, image_source: str) -> tuple[dict | None, str | None]:
    """
    Returns (cleaned_product, None) on success.
    Returns (None, reason_string) on failure.
    """
    name = str(raw.get('name', '')).strip()
    if len(name) < 3:
        return None, 'name_too_short'

    price = clean_price(raw.get('price'))
    if price is None:
        return None, f'price_invalid: {raw.get("price")}'

    return {
        'name': name,
        'brand': str(raw['brand']).strip() if raw.get('brand') else None,
        'unit': clean_unit(raw.get('unit')),
        'price': price,
        'promo': str(raw['promo']).strip() if raw.get('promo') else None,
        'period': str(raw['period']).strip() if raw.get('period') else None,
        'image_source': image_source,
        'ocr_raw_price': str(raw.get('price', '')),
        'ocr_confidence': float(raw.get('ocr_confidence', 1.0)),
    }, None
```

### 5.7 Testing plan — Phase 1

| Test | How | Edge cases |
|---|---|---|
| HTML parsing | Save local copy of Superindo page, run BeautifulSoup in isolation | Missing elements, different region names |
| Image download | `--dry-run` flag: log URLs without downloading | Broken URLs, 404s, redirects |
| OCR single image | Download one image manually, run `extract_products()` on it | Blank page, ads-only, corrupted file |
| Duplicate detection | Run scraper twice — second run should skip all images | Same image at different URL |
| Price parsing | Unit test `clean_price()` with: "Rp 8.500", "8,500", "8 500", "Rp8500", "???" | All formats seen in the wild |
| Split image fallback | Feed a dense 12-product page, verify split produces more products | Single-product page (no need to split) |
| OCR validation | Feed malformed products (no price, 1-char name) | Verify rejection + logging |
| State persistence | Verify `superindo_state.json` written correctly after run | First run (no state file), corrupted state file |

---

## 6. Phase 2 — Consolidation & Product Matching

**Deliverable:** `scripts/consolidate.py`, `scripts/matching/`  
**Effort:** ~500 lines total

### 6.1 Matching pipeline overview

The pipeline processes each pair of products (one from Lotte, one from Superindo) through ordered gates. A pair exits as MATCH, NO MATCH, or REVIEW. The gates are ordered cheapest-first.

```
For each (Lotte product A, Superindo product B) candidate pair:

Gate 0 — Unit type pre-filter
  → Incompatible types (weight vs count): SKIP PAIR immediately

Gate 1 — Brand pre-filter
  → Normalized brands known and different: SKIP PAIR immediately

Gate 2 — Token Jaccard pre-filter
  → token_overlap(A.name, B.name) < 0.30: SKIP PAIR (not similar enough)

Gate 3 — Exact token-set match
  → canonical_tokens(A) == canonical_tokens(B) AND units compatible:
     → MATCH (confidence: 1.0, method: "exact")

Gate 4 — Embedding similarity
  → Load paraphrase-multilingual-MiniLM-L12-v2 (once at startup)
  → Score >= 0.85 AND units compatible: MATCH (confidence: score, method: "embedding")
  → Score 0.55–0.85: candidate for Gate 5
  → Score < 0.55: NO MATCH

Gate 5 — Price plausibility check
  → Per-unit price ratio > 3×: FLAG → review_queue, not matched

Gate 6 — AI verification (qwen3:4b)
  → Only for pairs that survived Gates 0-5 with ambiguous scores
  → Batched (up to 20 pairs per Ollama call)
  → YES: MATCH (confidence: 0.75, method: "ai")
  → NO: NO MATCH
  → Unexpected: review_queue
```

### 6.2 Normalizer (`scripts/matching/normalizer.py`)

```python
import re
from functools import lru_cache

# ── Brand normalization ────────────────────────────────────────────────────────
# Populated empirically: run for 2–3 weeks, review review_queue.json,
# add OCR corruptions you see. Common patterns: l↔I, 0↔O, rn↔m, S↔5.
BRAND_ALIASES: dict[str, str] = {
    'lndomie': 'indomie',
    'lndomi': 'indomie',
    'S0sro': 'sosro',
    'S0s0': 'sosro',
    'Ult rajaya': 'ultrajaya',
    'UItra jaya': 'ultrajaya',
    'Ultrqjaya': 'ultrajaya',
    # Add more as encountered
}

def normalize_brand(brand: str | None) -> str:
    if not brand:
        return ''
    b = brand.strip()
    return BRAND_ALIASES.get(b, b).lower().replace(' ', '')

# ── Unit type ─────────────────────────────────────────────────────────────────
UNIT_TYPE_MAP: dict[str, str] = {
    'g': 'weight', 'gram': 'weight', 'gr': 'weight', 'kg': 'weight',
    'ml': 'volume', 'l': 'volume', 'liter': 'volume', 'lt': 'volume',
    'pcs': 'count', 'pack': 'count', 'sachet': 'count',
    'bks': 'count', 'bungkus': 'count', 'botol': 'count', 'kaleng': 'count',
}

def unit_type(unit: str | None) -> str | None:
    if not unit:
        return None
    token = re.split(r'[\s\d×x]', unit.lower().strip())[-1].strip()
    return UNIT_TYPE_MAP.get(token)

def units_type_compatible(u1: str | None, u2: str | None) -> bool:
    """True if types match OR either unit is unknown."""
    t1, t2 = unit_type(u1), unit_type(u2)
    if t1 is None or t2 is None:
        return True
    return t1 == t2

# ── Unit value normalization ───────────────────────────────────────────────────
def parse_unit_to_base(unit: str | None) -> tuple[float, str] | None:
    """
    Returns (normalized_value, unit_type) or None.
    Examples: "85 g" → (85.0, "weight"), "1.5 L" → (1500.0, "volume"),
              "6 x 45 ml" → (270.0, "volume"), "3 pcs" → (3.0, "count")
    """
    if not unit:
        return None
    s = unit.lower().replace(',', '.')

    # Multi-pack: "6 x 45 ml" or "6x45g"
    m = re.search(r'(\d+(?:\.\d+)?)\s*[×x]\s*(\d+(?:\.\d+)?)\s*(g|kg|ml|l)', s)
    if m:
        qty = float(m.group(1)) * float(m.group(2))
        u = m.group(3)
        base = qty * 1000 if u == 'kg' else qty * 1000 if u == 'l' else qty
        utype = 'weight' if u in ('g', 'kg') else 'volume'
        return (base, utype)

    # Single unit
    m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|gram|l|liter|ml|pcs|pack|sachet|bks|botol)', s)
    if m:
        val = float(m.group(1))
        u = m.group(2)
        conversions = {'kg': 1000, 'l': 1000, 'liter': 1000}
        base = val * conversions.get(u, 1)
        utype = UNIT_TYPE_MAP.get(u, 'count')
        return (base, utype)

    return None

def units_value_compatible(u1: str | None, u2: str | None, tolerance: float = 0.15) -> bool:
    """True if unit values are within tolerance (default ±15% for OCR noise)."""
    p1, p2 = parse_unit_to_base(u1), parse_unit_to_base(u2)
    if not p1 or not p2:
        return u1 == u2 if u1 and u2 else True
    if p1[1] != p2[1]:
        return False
    ratio = max(p1[0], p2[0]) / max(min(p1[0], p2[0]), 0.001)
    return ratio <= (1 + tolerance)

# ── Name normalization ─────────────────────────────────────────────────────────
_UNIT_PATTERN = r'\b\d+(?:[.,]\d+)?\s*(?:[×x]\s*\d+(?:[.,]\d+)?\s*)?(kg|g|gram|ml|l|liter|pcs|pack|sachet|bks)\b'

@lru_cache(maxsize=2048)
def normalize_name(name: str) -> str:
    """
    Lowercase, strip units, strip punctuation, collapse whitespace.
    Cached — same name always produces same result.
    """
    s = name.lower()
    s = re.sub(_UNIT_PATTERN, '', s)          # Remove unit suffixes
    s = re.sub(r'[^a-z0-9\s]', ' ', s)        # Non-alphanum → space
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def canonical_tokens(name: str) -> frozenset:
    """Order-independent token set for exact matching."""
    tokens = normalize_name(name).split()
    return frozenset(t for t in tokens if len(t) > 1)  # Drop single-char noise

def token_overlap(name_a: str, name_b: str) -> float:
    """Jaccard similarity on token sets. Pre-filter before embedding."""
    ta, tb = canonical_tokens(name_a), canonical_tokens(name_b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
```

### 6.3 Promo parser (`scripts/matching/promo_parser.py`)

```python
import re
from dataclasses import dataclass

@dataclass
class PromoResult:
    promo_type: str         # bundle_buy | get_free | discount_pct | discount_fixed | single
    display: str            # Original promo text
    unit_count: int         # Effective units received
    effective_unit_price: int

_PATTERNS = [
    # "DAPAT 5 pcs" / "dapat 3 buah"
    (r'dapat\s+(\d+)\s*(?:pcs|buah|pack)?', 'bundle_buy'),
    # "Beli 2 Gratis 1" / "Beli 3 Gratis 1"
    (r'beli\s+(\d+)\s*gratis\s+(\d+)', 'get_free'),
    # "2/Rp 10.000" or "3 pcs / Rp15.000"
    (r'(\d+)\s*(?:pcs|buah)?\s*/\s*(?:Rp\.?\s*)?([\d.,]+)', 'multi_price'),
    # "Diskon 20%"
    (r'diskon\s+(\d+)\s*%', 'discount_pct'),
    # "Hemat Rp 5.000"
    (r'hemat\s+(?:Rp\.?\s*)?([\d.,]+)', 'discount_fixed'),
]

def parse_promo(promo_text: str | None, base_price: int) -> PromoResult:
    """
    Returns a PromoResult. Falls back to single-unit if no pattern matches.
    base_price: the price field from OCR (may be total bundle price).
    """
    if not promo_text:
        return PromoResult('single', '', 1, base_price)

    text = promo_text.lower().strip()

    for pattern, ptype in _PATTERNS:
        m = re.search(pattern, text)
        if m:
            if ptype == 'bundle_buy':
                count = int(m.group(1))
                return PromoResult(ptype, promo_text, count, round(base_price / count))
            elif ptype == 'get_free':
                buy, free = int(m.group(1)), int(m.group(2))
                total = buy + free
                return PromoResult(ptype, promo_text, total, round(base_price / total))
            elif ptype == 'multi_price':
                count = int(m.group(1))
                total_str = re.sub(r'\.(?=\d{3})', '', m.group(2)).replace(',', '')
                try:
                    total = int(float(total_str))
                    return PromoResult(ptype, promo_text, count, round(total / count))
                except ValueError:
                    pass
            elif ptype == 'discount_pct':
                pct = int(m.group(1))
                unit_price = round(base_price * (1 - pct / 100))
                return PromoResult(ptype, promo_text, 1, unit_price)
            elif ptype == 'discount_fixed':
                discount_str = re.sub(r'\.(?=\d{3})', '', m.group(1))
                try:
                    discount = int(float(discount_str))
                    return PromoResult(ptype, promo_text, 1, max(base_price - discount, 1))
                except ValueError:
                    pass

    return PromoResult('single', promo_text, 1, base_price)


def parse_valid_until(period: str | None) -> str | None:
    """
    Extract the end date from period string.
    "7 - 20 Mei 2026" → "2026-05-20"
    """
    if not period:
        return None
    MONTHS = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'mei': '05', 'jun': '06', 'jul': '07', 'agu': '08',
        'sep': '09', 'okt': '10', 'nov': '11', 'des': '12',
        'may': '05', 'aug': '08', 'oct': '10', 'dec': '12'
    }
    # Find last date in string: "20 Mei 2026"
    m = re.findall(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})', period)
    if m:
        day, month_str, year = m[-1]
        month = MONTHS.get(month_str[:3].lower())
        if month:
            return f"{year}-{month}-{int(day):02d}"
    return None
```

### 6.4 Matcher (`scripts/matching/matcher.py`)

```python
from .normalizer import (
    normalize_brand, units_type_compatible, units_value_compatible,
    canonical_tokens, token_overlap, normalize_name
)
import requests
import json
import logging

logger = logging.getLogger(__name__)


def load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {model_name} ...")
    model = SentenceTransformer(model_name)
    logger.info("Embedding model ready.")
    return model


def compute_similarity_matrix(names_a: list[str], names_b: list[str], model) -> list[list[float]]:
    """Returns similarity[i][j] for names_a[i] vs names_b[j]."""
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    all_names = names_a + names_b
    embs = model.encode(all_names, convert_to_numpy=True)
    embs_a = embs[:len(names_a)]
    embs_b = embs[len(names_a):]
    matrix = cosine_similarity(embs_a, embs_b)
    return matrix.tolist()


def price_plausibility_ok(price_a: int, unit_a: str | None,
                           price_b: int, unit_b: str | None,
                           max_ratio: float = 3.0) -> bool:
    """Returns False if per-unit prices are suspiciously different."""
    from .normalizer import parse_unit_to_base
    p_a = parse_unit_to_base(unit_a)
    p_b = parse_unit_to_base(unit_b)
    if not p_a or not p_b or p_a[0] == 0 or p_b[0] == 0:
        return True
    pu_a = price_a / p_a[0]
    pu_b = price_b / p_b[0]
    ratio = max(pu_a, pu_b) / min(pu_a, pu_b)
    return ratio <= max_ratio


AI_PROMPT_TEMPLATE = """You are comparing grocery products from two Indonesian supermarket brochures.
Decide if these two listings refer to the SAME physical product.

Product A ({store_a}): "{name_a}" — {unit_a} — Rp {price_a:,}
Product B ({store_b}): "{name_b}" — {unit_b} — Rp {price_b:,}

Rules:
- SAME: same brand, same variant, same (or very close) size
- DIFFERENT: different brand, different variant, OR clearly different size (e.g. 85g vs 250g)
- OCR spelling typos do NOT make products different
- Different pack sizes are DIFFERENT even if per-unit price is similar

Reply with exactly one word: YES or NO"""


def verify_with_ai(pairs: list[dict], cfg: dict) -> list[dict | None]:
    """
    Send ambiguous pairs to qwen3:4b for binary yes/no.
    Returns list of match dicts or None for each input pair.
    """
    results = []
    batch_prompt = "\n\n---\n\n".join([
        AI_PROMPT_TEMPLATE.format(
            store_a=p['product_a']['store'], name_a=p['product_a']['name'],
            unit_a=p['product_a'].get('unit', 'unknown'),
            price_a=p['product_a']['effective_unit_price'],
            store_b=p['product_b']['store'], name_b=p['product_b']['name'],
            unit_b=p['product_b'].get('unit', 'unknown'),
            price_b=p['product_b']['effective_unit_price'],
        )
        for p in pairs
    ])
    batch_prompt += f"\n\nAnswer for each pair above, one per line (YES or NO only):"

    try:
        resp = requests.post("http://localhost:11434/api/generate", json={
            "model": cfg['consolidation']['ai_model'],
            "prompt": batch_prompt,
            "stream": False,
            "options": {"temperature": 0, "seed": 42}
        }, timeout=60)
        resp.raise_for_status()
        lines = resp.json()['response'].strip().splitlines()

        for i, (pair, line) in enumerate(zip(pairs, lines)):
            answer = line.strip().lower()
            if answer in ('yes', 'ya', 'y', 'match', 'sama'):
                results.append({**pair, 'match_method': 'ai', 'match_confidence': 0.75})
            elif answer in ('no', 'tidak', 'n', 'beda'):
                results.append(None)
            else:
                logger.warning(f"Unexpected AI response for pair {i}: {line!r}")
                results.append({'__review': True, **pair, 'reason': f'ai_uncertain: {line}'})
    except Exception as e:
        logger.error(f"AI verification failed: {e}")
        results = [None] * len(pairs)

    return results


def match_products(lotte_products: list[dict], superindo_products: list[dict],
                   cfg: dict, embedding_model=None) -> tuple[list, list, list, list]:
    """
    Run full matching pipeline.
    Returns: (matched_pairs, lotte_only, superindo_only, review_items)
    """
    emb_auto = cfg['consolidation']['embedding_auto_match']
    emb_low = cfg['consolidation']['embedding_ambiguous_low']
    jaccard_min = cfg['consolidation']['token_jaccard_min']
    unit_tol = cfg['consolidation']['unit_tolerance_pct'] / 100

    matched_lotte_idx = set()
    matched_superindo_idx = set()
    matched_pairs = []
    ambiguous_pairs = []
    review_items = []

    # ── Gates 0–3: rule-based (cheap) ────────────────────────────────────────
    for i, a in enumerate(lotte_products):
        for j, b in enumerate(superindo_products):
            if j in matched_superindo_idx:
                continue

            # Gate 0: unit type
            if not units_type_compatible(a.get('unit'), b.get('unit')):
                continue

            # Gate 1: brand
            ba, bb = normalize_brand(a.get('brand')), normalize_brand(b.get('brand'))
            if ba and bb and ba != bb:
                continue

            # Gate 2: token Jaccard pre-filter
            overlap = token_overlap(a['name'], b['name'])
            if overlap < jaccard_min:
                continue

            # Gate 3: exact token match
            if canonical_tokens(a['name']) == canonical_tokens(b['name']) and \
               units_value_compatible(a.get('unit'), b.get('unit'), unit_tol):
                matched_pairs.append({
                    'product_a': {**a, 'store': 'Lotte'},
                    'product_b': {**b, 'store': 'Superindo'},
                    'match_method': 'exact',
                    'match_confidence': 1.0,
                    '_idx_a': i, '_idx_b': j
                })
                matched_lotte_idx.add(i)
                matched_superindo_idx.add(j)
                break

    # ── Gate 4: embedding similarity (remaining candidates) ───────────────────
    remaining_lotte = [(i, p) for i, p in enumerate(lotte_products) if i not in matched_lotte_idx]
    remaining_superindo = [(j, p) for j, p in enumerate(superindo_products) if j not in matched_superindo_idx]

    if remaining_lotte and remaining_superindo and embedding_model:
        names_a = [normalize_name(p['name']) for _, p in remaining_lotte]
        names_b = [normalize_name(p['name']) for _, p in remaining_superindo]
        sim_matrix = compute_similarity_matrix(names_a, names_b, embedding_model)

        for ri, (i, a) in enumerate(remaining_lotte):
            best_rj = max(range(len(remaining_superindo)), key=lambda x: sim_matrix[ri][x])
            best_score = sim_matrix[ri][best_rj]
            rj, b = remaining_superindo[best_rj]

            if rj in matched_superindo_idx:
                continue
            if not units_type_compatible(a.get('unit'), b.get('unit')):
                continue

            pair = {
                'product_a': {**a, 'store': 'Lotte'},
                'product_b': {**b, 'store': 'Superindo'},
                '_idx_a': i, '_idx_b': rj,
                '_score': best_score
            }

            if best_score >= emb_auto and units_value_compatible(a.get('unit'), b.get('unit'), unit_tol):
                matched_pairs.append({
                    **pair, 'match_method': 'embedding', 'match_confidence': round(best_score, 3)
                })
                matched_lotte_idx.add(i)
                matched_superindo_idx.add(rj)
            elif best_score >= emb_low:
                # Gate 5: price plausibility before escalating to AI
                if not price_plausibility_ok(
                    a.get('effective_unit_price', a['price']),
                    a.get('unit'),
                    b.get('effective_unit_price', b['price']),
                    b.get('unit'),
                    cfg['consolidation']['price_ratio_max']
                ):
                    review_items.append({**pair, 'reason': 'price_ratio_too_high'})
                else:
                    ambiguous_pairs.append(pair)

    # ── Gate 6: AI verification for ambiguous pairs ───────────────────────────
    if ambiguous_pairs:
        ai_results = verify_with_ai(ambiguous_pairs, cfg)
        for pair, result in zip(ambiguous_pairs, ai_results):
            if result is None:
                continue
            if result.get('__review'):
                review_items.append(result)
            else:
                matched_pairs.append(result)
                matched_lotte_idx.add(pair['_idx_a'])
                matched_superindo_idx.add(pair['_idx_b'])

    lotte_only = [p for i, p in enumerate(lotte_products) if i not in matched_lotte_idx]
    superindo_only = [p for j, p in enumerate(superindo_products) if j not in matched_superindo_idx]

    return matched_pairs, lotte_only, superindo_only, review_items
```

### 6.5 Consolidation script (`scripts/consolidate.py`) — flow

```
1.  Health check — abort early if critical issues
2.  Load latest lotte_promos_*.json  (glob, pick newest by timestamp)
3.  Load latest superindo_promos_*.json
4.  Backup price_history.json → price_history.json.backup
5.  For every product in both stores:
    a. Run parse_promo() to get effective_unit_price
    b. Run parse_valid_until() to get valid_until date
6.  Load embedding model (once)
7.  Run match_products() → matched_pairs, lotte_only, superindo_only, review_items
8.  Build consolidated "products" list from matched_pairs
9.  Build "singles" list from lotte_only + superindo_only
10. Compute display fields: price_min, price_max, cheapest_store, savings_pct, etc.
11. Update product_catalog.json
12. Append to price_history.json
13. Write consolidated_YYYYMMDD_HHMMSS.json
14. Overwrite consolidated_latest.json (atomic: write to temp, then rename)
15. Append to review_queue.json (if any)
16. Print summary to console
```

**Atomic write pattern** (prevents corrupt `consolidated_latest.json` if the process is killed mid-write):

```python
import tempfile, shutil, os

def atomic_write_json(data: dict, path: str) -> None:
    dir_ = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', dir=dir_, suffix='.tmp',
                                     delete=False, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path = f.name
    shutil.move(tmp_path, path)  # Atomic on same filesystem
```

### 6.6 Catalog update logic

After matching, update `product_catalog.json` with new entries and variant tracking. The catalog improves matching accuracy over time — products seen multiple times across stores get higher confidence scores and serve as anchor points for future fuzzy matching.

```python
def update_catalog(catalog: dict, all_products: list[dict], today: str) -> dict:
    for product in all_products:
        key = product['key']
        if key not in catalog:
            catalog[key] = {
                'canonical_key': key,
                'display_name': product['name'],
                'brand': product.get('brand'),
                'unit': product.get('unit'),
                'unit_type': product.get('unit_type'),
                'unit_value_g': product.get('unit_value_g'),
                'first_seen': today,
                'last_seen': today,
                'appearance_count': 1,
                'stores_found': [product['store']],
                'name_variants': [{'name': product['name'], 'count': 1, 'store': product['store']}],
                'confidence': 0.3,
                'manually_verified': False
            }
        else:
            entry = catalog[key]
            entry['last_seen'] = today
            entry['appearance_count'] += 1
            if product['store'] not in entry['stores_found']:
                entry['stores_found'].append(product['store'])
            # Track OCR name variants
            for v in entry['name_variants']:
                if v['name'] == product['name']:
                    v['count'] += 1
                    break
            else:
                entry['name_variants'].append({'name': product['name'], 'count': 1, 'store': product['store']})
            # Confidence grows with evidence
            entry['confidence'] = _score_confidence(entry)
    return catalog

def _score_confidence(entry: dict) -> float:
    score = 0.0
    if entry['appearance_count'] >= 3: score += 0.3
    elif entry['appearance_count'] >= 2: score += 0.15
    if len(entry['stores_found']) >= 2: score += 0.3
    else: score += 0.1
    if len(entry['name_variants']) == 1: score += 0.2
    elif len(entry['name_variants']) <= 3: score += 0.1
    if entry.get('unit') and entry['unit'] != 'unknown': score += 0.1
    if entry.get('brand') and entry['brand'] != 'unknown': score += 0.1
    return round(min(score, 1.0), 2)
```

### 6.7 Testing plan — Phase 2

| Test | How | Edge cases |
|---|---|---|
| Unit-type pre-filter | Pair "Indomie 85g" vs "Indomie 5 pcs" | Ensure they are never matched |
| Brand filter | "ABC Kecap" (Lotte) vs "XYZ Kecap" (Superindo) | Different brands → no match |
| Token Jaccard | Compute overlap for known similar and dissimilar pairs | Single-word names, all-brand names |
| Exact match | "Indomie Goreng Ayam Geprek" vs "Goreng Indomie Ayam Geprek" (word order swap) | Verify match via canonical_tokens |
| Unit value tolerance | "85 g" vs "86 g" (within 15%): match. "85 g" vs "100 g": no match | Boundary values |
| Price plausibility | Pair with identical name but 5× unit price difference | Sent to review, not matched |
| AI parser | Mock AI response with: "YES", "NO", "maybe", random text | All handled without crash |
| promo_parser | "DAPAT 5 pcs" at 15500 → unit_price 3100 | "Beli 2 Gratis 1", "Diskon 20%", "Hemat Rp 5.000" |
| parse_valid_until | "7 - 20 Mei 2026" → "2026-05-20" | Single-date strings, null input |
| Atomic write | Kill process mid-write, verify no corrupt JSON | Verify backup was created first |
| Empty store | One store has zero products | No crash, other store shown as singles |
| price_history append | Run consolidate twice, verify two entries per product | Exact dedup: same product+date+store not added twice |
| clean_price | "Rp 8.500" → 8500, "8,500" → 8500, "Rp 1.250.000" → 1250000, "???" → None | All Indonesian separator variants |

---

## 7. Phase 3 — HTML Display

**Deliverable:** `index.html` (single self-contained file)  
**Effort:** ~400 lines (HTML + CSS + vanilla JS)

### 7.1 Data flow

```
User opens index.html in browser
   │
   ▼
fetch("output/consolidated_latest.json")   ← relative path, works locally
fetch("output/price_history.json")
   │
   ▼
Render product list from JSON
   │
   ├── "products" array → Matched cards (show both stores + savings)
   └── "singles" array → Single-store cards (show one store)
```

> **Note:** `fetch()` with file:// protocol is blocked in Chrome by default. Open with a local server  
> (`python -m http.server 8000`) or use Firefox, which allows local file fetch.  
> Add a one-liner to `haqita.bat` that starts a local server and opens the browser.

### 7.2 UI sections

**Header:**
- Haqita logo/wordmark
- "Data per: 14 Mei 2026" — from `generated_at`
- Store filter buttons: All · Lotte · Superindo
- Sort controls: Nama · Termurah · Hemat · Berakhir

**Product cards (matched — best use for user):**
```
┌──────────────────────────────────────────────────┐
│  🔵 Lotte   🔴 Superindo                         │
│                                                  │
│  Indomie Goreng Ayam Geprek  ·  85 g             │
│                                                  │
│  Rp 3.100  ◄ Lotte (Dapat 5 pcs)                │
│  Rp 3.500     Superindo                          │
│                                                  │
│  Hemat Rp 400 (11%) di Lotte  ·  s/d 20 Mei     │
└──────────────────────────────────────────────────┘
```

**Product cards (single store):**
```
┌──────────────────────────────────────────────────┐
│  🔵 Lotte only                                   │
│                                                  │
│  ABC Kecap Manis  ·  600 ml                      │
│  Rp 18.900  ·  s/d 20 Mei                        │
└──────────────────────────────────────────────────┘
```

**Expandable detail panel (click on a card):**
- Price-per-unit table with breakdown
- Mini price trend chart (Canvas 2D, visible when ≥2 history entries)
- Promo expiry countdown
- Match confidence badge (shown only when `match_confidence < 0.80`)

**Footer:**
- Last scraped: per store
- Product counts
- "⚠ N produk perlu ditinjau" link to review summary (if review_queue has items)

### 7.3 Key JS logic (index.html)

```javascript
// Load data
async function loadData() {
  const [consolidated, history] = await Promise.all([
    fetch('output/consolidated_latest.json').then(r => r.json()),
    fetch('output/price_history.json')
      .then(r => r.json())
      .catch(() => ({ snapshots: [] }))  // History optional
  ]);
  return { consolidated, history };
}

// Format IDR price: 3100 → "Rp 3.100"
function formatIDR(n) {
  return 'Rp ' + n.toLocaleString('id-ID');
}

// Format date: "2026-05-20" → "20 Mei 2026"
const MONTHS_ID = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
function formatDateID(isoDate) {
  if (!isoDate) return '';
  const [y, m, d] = isoDate.split('-');
  return `${parseInt(d)} ${MONTHS_ID[parseInt(m) - 1]} ${y}`;
}

// Build product card HTML
function buildMatchedCard(product, storeFilter) {
  // All price values come pre-computed from JSON — no math in JS
  const cheapestEntry = product.stores.find(s => s.store === product.cheapest_store);
  const otherEntry = product.stores.find(s => s.store !== product.cheapest_store);

  const savingsText = product.price_gap > 0
    ? `Hemat ${formatIDR(product.price_gap)} (${product.savings_pct}%) di ${product.cheapest_store}`
    : 'Harga sama';

  const lowConfidenceBadge = product.match_confidence < 0.80
    ? `<span class="badge badge-warning" title="Match tidak terverifikasi (${(product.match_confidence * 100).toFixed(0)}%)">⚠ Perkiraan</span>`
    : '';

  return `
    <div class="card card-matched" data-key="${product.key}">
      <div class="card-stores">
        ${product.stores.map(s => `<span class="store-badge store-${s.store.toLowerCase()}">${s.store}</span>`).join('')}
        ${lowConfidenceBadge}
      </div>
      <div class="card-name">${product.name}</div>
      <div class="card-unit">${product.unit || ''}</div>
      <div class="card-prices">
        <div class="price-row price-cheapest">
          <span class="price-value">${formatIDR(cheapestEntry.effective_unit_price)}</span>
          <span class="price-store">${cheapestEntry.store}</span>
          ${cheapestEntry.promo ? `<span class="promo-tag">${cheapestEntry.promo}</span>` : ''}
        </div>
        ${otherEntry ? `
        <div class="price-row">
          <span class="price-value dimmed">${formatIDR(otherEntry.effective_unit_price)}</span>
          <span class="price-store dimmed">${otherEntry.store}</span>
        </div>` : ''}
      </div>
      <div class="card-footer">
        <span class="savings-text">${savingsText}</span>
        ${product.valid_until ? `<span class="expiry">s/d ${formatDateID(product.valid_until)}</span>` : ''}
      </div>
    </div>`;
}

// Price trend chart (Canvas 2D — no library needed)
function drawPriceChart(canvas, productKey, stores, history) {
  const snapshots = history.snapshots.filter(s => s.product_key === productKey);
  if (snapshots.length < 2) return;  // Not enough data

  // Group by store and date, sort by date
  const storeData = {};
  for (const snap of snapshots) {
    if (!storeData[snap.store]) storeData[snap.store] = [];
    storeData[snap.store].push({ date: snap.date, price: snap.effective_unit_price });
  }
  for (const s in storeData) storeData[s].sort((a, b) => a.date.localeCompare(b.date));

  // Draw — simple polyline chart, one color per store
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const PAD = 30;
  const storeColors = { Lotte: '#0057A8', Superindo: '#E8211D' };

  // Compute scale
  const allPrices = Object.values(storeData).flat().map(p => p.price);
  const minP = Math.min(...allPrices) * 0.9;
  const maxP = Math.max(...allPrices) * 1.1;
  const allDates = [...new Set(Object.values(storeData).flat().map(p => p.date))].sort();

  const xScale = d => PAD + (allDates.indexOf(d) / (allDates.length - 1)) * (W - 2 * PAD);
  const yScale = p => H - PAD - ((p - minP) / (maxP - minP)) * (H - 2 * PAD);

  ctx.clearRect(0, 0, W, H);
  for (const [store, points] of Object.entries(storeData)) {
    ctx.strokeStyle = storeColors[store] || '#888';
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((pt, i) => {
      const x = xScale(pt.date), y = yScale(pt.price);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      // Dot
      ctx.fillStyle = storeColors[store] || '#888';
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.stroke();
  }
}
```

### 7.4 Testing plan — Phase 3

| Test | Method | Edge cases |
|---|---|---|
| JSON load | Open in browser with valid JSON | network error, malformed JSON |
| Empty data | No JSON files present | Show "Belum ada data" state |
| Large dataset | Load 500+ products | Render time, scroll performance |
| Store filter | Click Lotte/Superindo/All buttons | Single-store products hidden by wrong filter |
| Trend chart | After 2+ runs, verify chart renders | 1 data point (chart hidden), missing dates |
| Price formatting | Verify IDR format (dots as thousands sep) | Prices like 100, 1000000 |
| Date formatting | "2026-05-20" → "20 Mei 2026" | Null dates, edge months |
| Low confidence badge | Set match_confidence=0.5 in test JSON | Verify badge shown |
| Mobile | Resize to 375px width | No horizontal scroll, readable text |
| Local server | `python -m http.server 8000` then open | fetch() blocked on file:// in Chrome |

---

## 8. Phase 4 — Integration & Menu

**Deliverable:** updated `haqita.bat`

```batch
@echo off
:MENU
cls
echo ========================================
echo        Haqita - Grocery Price Tool
echo ========================================
echo.
echo  [1] Scrape Lotte Mart promos
echo  [2] Scrape Superindo promos
echo  [3] Dry-run Lotte  (no OCR, just check for new images)
echo  [4] Dry-run Superindo
echo  [5] Consolidate ^& build index.html
echo  [6] Full pipeline  (Lotte + Superindo + Consolidate)
echo  [7] Open index.html in browser
echo  [8] Health check
echo  [0] Exit
echo.
set /p choice="Your choice: "

if "%choice%"=="1" python scripts/scrapers/lotte_qwen.py
if "%choice%"=="2" python scripts/scrapers/superindo_qwen.py
if "%choice%"=="3" python scripts/scrapers/lotte_qwen.py --dry-run
if "%choice%"=="4" python scripts/scrapers/superindo_qwen.py --dry-run
if "%choice%"=="5" python scripts/consolidate.py
if "%choice%"=="6" call :FULL_PIPELINE
if "%choice%"=="7" call :OPEN_HTML
if "%choice%"=="8" python scripts/health_check.py
if "%choice%"=="0" exit /b

goto MENU

:FULL_PIPELINE
echo [1/4] Health check...
python scripts/health_check.py || goto PIPELINE_FAIL
echo [2/4] Scraping Lotte...
python scripts/scrapers/lotte_qwen.py || echo Lotte scrape failed, continuing...
echo [3/4] Scraping Superindo...
python scripts/scrapers/superindo_qwen.py || echo Superindo scrape failed, continuing...
echo [4/4] Consolidating...
python scripts/consolidate.py
echo.
echo Pipeline complete. Opening browser...
call :OPEN_HTML
goto :EOF

:OPEN_HTML
REM Start local server and open browser (avoids fetch() file:// restriction in Chrome)
start /B python -m http.server 8000 --directory .
timeout /t 1 /nobreak >nul
start http://localhost:8000/index.html
goto :EOF

:PIPELINE_FAIL
echo Health check failed. Aborting pipeline.
pause
goto MENU
```

### 8.1 Health check (`scripts/health_check.py`)

Runs before the full pipeline. Checks:
- Ollama service responding (`GET http://localhost:11434/api/tags`)
- Required models installed (`qwen3-vl:7b`, `qwen3:4b`)
- `output/` directory writable
- Disk space > 1 GB free
- Internet connectivity (HEAD request to lottemart.co.id)

If `OCR_PROVIDER=gemini` in `.env`:
- Checks `GEMINI_API_KEY` is set
- Skips Ollama checks

Prints pass/warn/fail per check. Returns exit code 1 if any FAIL.

---

## 9. Testing Strategy

### 9.1 Module tests (run before each phase)

```bash
# Phase 1 — OCR and scraping
python -m pytest tests/test_price_parser.py          # clean_price() variations
python -m pytest tests/test_unit_parser.py           # parse_unit_to_base(), units_value_compatible()
python -m pytest tests/test_promo_parser.py          # all promo patterns
python -m pytest tests/test_image_preprocess.py      # contrast, scale

# Phase 2 — Matching
python -m pytest tests/test_normalizer.py            # normalize_name(), canonical_tokens(), etc.
python -m pytest tests/test_matcher.py               # all 6 gates with fixture data
python -m pytest tests/test_catalog.py               # update_catalog(), _score_confidence()
python -m pytest tests/test_consolidate.py           # end-to-end with sample JSONs
```

### 9.2 Golden file regression tests

For each store, maintain a set of reference images with known expected outputs. Run after any change to the OCR prompt or image preprocessing:

```bash
python tests/test_ocr_golden.py --store lotte
python tests/test_ocr_golden.py --store superindo
```

These fail if extracted products differ from `golden_outputs/`. Update golden files intentionally, never automatically.

### 9.3 End-to-end smoke test

```bash
# Run with test fixture data (not live scrape)
python scripts/consolidate.py \
  --lotte-file test_data/consolidate/sample_lotte_promos.json \
  --superindo-file test_data/consolidate/sample_superindo_promos.json \
  --output-dir test_data/consolidate/output/

# Verify output matches expected
python tests/test_golden_consolidate.py
```

---

## 10. Future Improvements

These are explicitly out of scope for v1. Revisit after 4–6 weeks of real operation when you have empirical data about what breaks.

### OCR provider switch via `.env`

The codebase already supports this via `OCR_PROVIDER` in `.env`. To activate Gemini:

```dotenv
# .env
OCR_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Gemini 2.0 Flash free tier: 1,500 requests/day, 15 req/min. A full weekly run uses ~16 requests — comfortably within the free tier.

Benefits over local qwen3-vl: faster (~3–5s/image vs 30–60s), better accuracy on Indonesian mixed-font brochures, no Ollama dependency for the OCR step.

No code changes needed — the OCR provider abstraction in `ocr_processor.py` handles the routing.

### Add a third store (Alfamart, Indomaret)

1. Create `scripts/scrapers/alfamart_qwen.py` following the same pattern
2. Add `alfamart` entry to `config.yaml → scrapers`
3. Add `{"Alfamart": "#E40521"}` to `display_hints.store_colors` in consolidate.py
4. The matching pipeline handles N stores — no structural changes needed

Transitive closure (NetworkX) only becomes useful when all 3 stores are live. Add it then.

### FAISS for scale

The current `numpy` + `cosine_similarity` approach handles 10,000 products in ~200ms — fast enough for any foreseeable scale of this tool. Add FAISS only if the catalog grows beyond ~50,000 entries.

### Active learning for ambiguous matches

After 4–6 weeks, `review_queue.json` will have accumulated enough human-reviewed edge cases to build a simple labeled dataset. Use this to:
1. Tune embedding thresholds empirically (plot precision/recall curves)
2. Fine-tune the embedding model on Indonesian grocery names (requires ~500 labeled pairs)

### Probabilistic record linkage (Fellegi-Sunter)

A statistical framework for entity resolution that outperforms threshold-based approaches. Worth exploring once you have 6+ months of labeled match/no-match data. Not useful before that.

### Scheduled runs

Currently manual. Future: Windows Task Scheduler to run the full pipeline every Monday morning before weekly shopping.

```batch
REM Task Scheduler command
cmd /c "cd /d C:\haqita && python scripts/scrapers/lotte_qwen.py && python scripts/scrapers/superindo_qwen.py && python scripts/consolidate.py"
```

---

## Appendix: Dependencies

```txt
# requirements.txt
requests>=2.31
beautifulsoup4>=4.12
Pillow>=10.0
pyyaml>=6.0
python-dotenv>=1.0
sentence-transformers>=2.7   # For embedding-based matching
scikit-learn>=1.4            # cosine_similarity
numpy>=1.26
rapidfuzz>=3.6               # Faster fuzzy string matching (optional, fallback to difflib)

# Optional — only when OCR_PROVIDER=gemini
google-generativeai>=0.8
```

Ollama and the models (`qwen3-vl:7b`, `qwen3:4b`) are installed separately:
```bash
ollama pull qwen3-vl:7b
ollama pull qwen3:4b
```
