# Haqita — Jakarta Grocery Price Comparison

Compare grocery prices across Jakarta supermarkets using AI OCR and web scraping.

## Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Haqita — Price Comparison                        │
└─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
  │  Step 1     │     │  Step 2      │     │  Step 3          │
  │  Scrape     │────▶│  OCR         │────▶│  Consolidation   │
  └─────────────┘     └──────────────┘     └──────────────────┘
        │                     │                       │
        ▼                     ▼                       ▼
  output/scrape/        output/ocr/             output/consolidation/
  └─ lotte/             ├─ lotte_promos_*.json  ├─ consolidated_latest.json
  └─ superindo/         └─ superindo_promos_*.json └─ consolidated_YYYYMMDD_*.json
                                                (debuggable, can be deleted)
                                                       │
                                                       ▼
                                                  database/
                                                  ├─ price_history.json
                                                  ├─ product_catalog.json
                                                  └─ review_queue.json
                                                (maintained, do not delete)

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Matching Pipeline (inside Step 3)                                  │
  │                                                                     │
  │  lotte_products ──┐                                                 │
  │                   ├──▶ Gate 0: Unit Type ──▶ Gate 1: Brand          │
  │  superindo_       │       │                      │                  │
  │  products   ──────┘       ▼                      ▼                  │
  │                     Gate 2: Jaccard ──▶ Gate 3: Exact Match         │
  │                            │                      │                  │
  │                            ▼                      ▼                  │
  │                     Gate 4: Embedding ──▶ Gate 5: Price Check       │
  │                            │                      │                  │
  │                            ▼                      ▼                  │
  │                     Gate 6: AI Verifier ──▶ MATCH / NO / REVIEW      │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Output (Phase 3)                                                   │
  │                                                                     │
  │  consolidated_latest.json ──────▶ index.html (browser display)      │
  └─────────────────────────────────────────────────────────────────────┘
```

### Step 1: Scrape

Downloads current promo brochure images from supermarket websites.

| | |
|---|---|
| **Input** | Superindo / Lotte Mart website URLs (from `config.yaml`) |
| **Output** | Brochure images in `output/scrape/<store>/` (JPG/PNG) |
| **State** | `output/scrape/<store>/state.json` — tracks already-seen images to avoid re-downloading |
| **Run** | `haqita.bat` → Option 1 (Lotte) or 2 (Superindo), or dry-run Option 3/4 |

### Step 2: OCR

Extracts product data from brochure images using Gemini or Ollama vision models.

| | |
|---|---|
| **Input** | Brochure images in `output/scrape/<store>/` |
| **Output** | `output/ocr/<store>_promos_YYYYMMDD_HHMMSS.json` |
| **Schema** | See below |
| **Run** | Automatically triggered after scrape, or via integration tests (Option 5) |

**OCR output schema:**
```json
{
  "store": "Lotte",
  "scraped_at": "2026-05-14T07:39:37",
  "source_url": "https://www.lottemart.co.id/all-promo-mart",
  "images_processed": 6,
  "ocr_provider": "gemini",
  "products": [
    {
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "price": 3500,
      "promo": "DAPAT 5 pcs",
      "period": "7 - 20 Mei 2026",
      "image_source": "promo_lotte_abc123.jpg",
      "ocr_raw_price": "Rp 3.500",
      "ocr_confidence": 0.91
    }
  ],
  "rejected": [
    { "raw": { "...": "..." }, "reason": "price_invalid: 0", "image_source": "..." }
  ],
  "stats": {
    "products_extracted": 42,
    "products_rejected": 2,
    "images_failed_ocr": 1
  }
}
```

### Step 3: Consolidation

Merges OCR results from both stores, matches same products across stores, computes unit prices and savings.

| | |
|---|---|
| **Input** | Latest `output/ocr/lotte_promos_*.json` and `output/ocr/superindo_promos_*.json` |
| **Output** | `output/consolidation/consolidated_latest.json` (always overwritten — HTML reads this) |
| | `output/consolidation/consolidated_YYYYMMDD_HHMMSS.json` (timestamped archive, can be deleted) |
| **Database** | `database/price_history.json` — accumulated price snapshots across runs |
| | `database/product_catalog.json` — auto-built product registry |
| | `database/review_queue.json` — low-confidence matches for inspection |
| **Run** | `haqita.bat` → Option 6 (Docker), or `scripts\run_consolidate.bat` |

**Consolidated output schema:**
```json
{
  "generated_at": "2026-05-14T08:20:00",
  "products": [
    {
      "key": "indomie-goreng--indomie--85g",
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "unit_type": "weight",
      "stores": [
        { "store": "Lotte", "price": 15500, "effective_unit_price": 3100, "bundle_size": 5, "promo": "DAPAT 5 pcs" },
        { "store": "Superindo", "price": 3500, "effective_unit_price": 3500, "bundle_size": 1 }
      ],
      "price_min": 3100,
      "price_max": 3500,
      "cheapest_store": "Lotte",
      "savings_pct": 11.4,
      "match_method": "exact",
      "match_confidence": 1.0
    }
  ],
  "singles": [
    { "key": "...", "name": "...", "store": "Lotte", "price": 18900 }
  ],
  "stats": {
    "total_products_lotte": 42,
    "total_products_superindo": 38,
    "matched_across_stores": 15,
    "lotte_only": 27,
    "superindo_only": 23
  }
}
```

**Matching pipeline:** Each product pair passes through 7 gates (unit type → brand → token Jaccard → exact match → embedding → price plausibility → AI verifier). Each gate is individually toggleable via `config.yaml`.

## Quick Start

```cmd
haqita.bat
```

Launches an interactive menu with options to run scrapers, consolidation, or tests.

## Tools

| Tool | What it does | Docs | Run via menu |
|---|---|---|---|
| **Lotte Scraper** | Fetches promo flyers from Lotte Mart | [`docs/lotte_scraper.md`](docs/lotte_scraper.md) | Option 1 |
| **Superindo Scraper** | Fetches promo flyers from Superindo | — | Option 2 |
| **Dry-run** | Reports new promos without running OCR | [`docs/lotte_scraper.md`](docs/lotte_scraper.md) | Option 3/4 |
| **Integration Tests** | Runs OCR on real brochure images | — | Option 5 |
| **Consolidate** | Merges & matches across stores | [`docs/implementation-phase2.md`](docs/implementation-phase2.md) | Option 6 |
| **Matching Tests** | Unit tests for matching pipeline | — | Option 7 |

## Project Structure

```
haqita/
├── haqita.bat                        ← Interactive launch menu
├── config.yaml                       ← All tunable settings
├── .env                              ← Configuration (API keys, provider toggles)
├── Dockerfile                        ← Docker image for consolidation pipeline
├── docker-compose.yml                ← Docker service definition
├── scripts/
│   ├── scrapers/
│   │   ├── base_scraper.py           ← Shared scraper infrastructure
│   │   ├── lotte.py                  ← Lotte Mart scraper (store-specific)
│   │   └── superindo.py              ← Superindo scraper (store-specific)
│   ├── ocr/
│   │   ├── ocr_processor.py          ← Unified OCR interface (routes to Gemini or Ollama)
│   │   ├── gemini_client.py          ← Gemini OCR client
│   │   ├── ollama_client.py          ← Ollama OCR client
│   │   ├── image_preprocess.py       ← Image preprocessing
│   │   └── prompts/                  ← Store-specific OCR prompts
│   ├── consolidate.py                ← Phase 2: Merge + match + output JSON
│   ├── run_consolidate.bat           ← Windows launcher for consolidation
│   └── matching/                     ← Phase 2: Product matching pipeline
│       ├── normalizer.py             ← Name/unit/brand normalization
│       ├── promo_parser.py           ← Indonesian promo text parser
│       └── matcher.py                ← Multi-tier matching pipeline (7 gates)
├── data/                             ← Committed to git (static reference data)
│   └── test/                         ← Test images and expected assert files
├── output/                             ← Generated, can be deleted (debugging)
│   ├── scrape/
│   │   ├── lotte/                    ← Downloaded brochure images
│   │   └── superindo/
│   ├── ocr/
│   │   ├── lotte_promos_*.json       ← Per-store OCR output
│   │   └── superindo_promos_*.json
│   └── consolidation/
│       ├── consolidated_latest.json  ← Always latest — HTML reads this
│       └── consolidated_YYYYMMDD_HHMMSS.json  ← Timestamped archives
├── database/                         ← Generated, maintained (do not delete)
│   ├── price_history.json            ← Accumulated price snapshots
│   ├── product_catalog.json          ← Auto-built product registry
│   └── review_queue.json             ← Low-confidence matches
├── work/                             ← Generated, temporary (test output, processing)
│   └── tests/                        ← Integration test results
└── docs/
    ├── lotte_scraper.md              ← Lotte scraper documentation
    └── implementation-phase2.md      ← Phase 2 implementation guide
```

## Requirements

- Python 3.8+
- Ollama with `qwen3-vl:7b` (configurable in config.yaml)
- NVIDIA GPU recommended (~3.3 GiB VRAM), works on CPU
- Windows 10+
- Docker (for consolidation pipeline)

Python packages: `requests`, `beautifulsoup4`, `Pillow`, `pyyaml`, `python-dotenv`, `google-genai`, `sentence-transformers`, `numpy`, `scikit-learn`, `pytest`

## OCR Providers

Haqita supports two OCR providers, configured in `config.yaml`:

| Provider | Setup | Best for |
|---|---|---|
| **Gemini** (default) | Set `GEMINI_API_KEY` in `.env` | Higher accuracy, cloud-based |
| **Ollama** | Run `ollama serve` locally | Free, offline, no API key needed |

Switch via `.env`:
```env
OCR_PROVIDER=gemini   # or "ollama"
```

## Testing

```cmd
# All matching tests (unit + integration)
python -m pytest tests/matching/ -v

# Unit tests only (fast, no model download)
python -m pytest tests/matching/ -v -m "not slow"

# Integration tests (OCR on real images)
haqita.bat → Option 5
```
