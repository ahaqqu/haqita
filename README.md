# Haqita — Jakarta Grocery Price Comparison

Compare grocery prices across Jakarta supermarkets using AI OCR and web scraping.

## Pipeline

Each stage runs independently. If something fails, rerun from that stage onward.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Haqita — Price Comparison                        │
└─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
  │  Stage 1    │     │  Stage 2     │     │  Stage 3         │
  │  Scrape     │────▶│  OCR         │────▶│  Consolidation   │
  └─────────────┘     └──────────────┘     └──────────────────┘
        │                     │                       │
        ▼                     ▼                       ▼
  database/scrape/        database/ocr/           output/consolidation/
  └─ lotte/               └─ lotte/               ├─ consolidated_latest.json
  │  └─ state.json          │  └─ state.json      └─ consolidated_YYYYMMDD_*.json
  │  └─ 20260516/           │  └─ lotte_promos_*.json
  └─ superindo/             └─ superindo/
     └─ state.json              └─ state.json
     └─ 20260516/               └─ superindo_promos_*.json
                                                (debuggable, can be deleted)
                                                       │
                                                       ▼
                                                  database/
                                                  ├─ price_history.json
                                                  ├─ product_catalog.json
                                                  └─ review_queue.json
                                                (maintained, do not delete)

  Dry-run behavior:
    Stage 1 dry-run  → report new images without downloading
    Stage 2 dry-run  → print products without saving JSON
    Stage 3 dry-run  → write to output/consolidation/dry_run_*.json, skip database

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Matching Pipeline (inside Stage 3)                                 │
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
  │  Future (Phase 3)                                                   │
  │                                                                     │
  │  consolidated_latest.json ──────▶ index.html (browser display)      │
  └─────────────────────────────────────────────────────────────────────┘
```

### Stage 1: Scrape

Downloads current promo brochure images from supermarket websites.

| | |
|---|---|
| **Input** | Superindo / Lotte Mart website URLs (from `config.yaml`) |
| **Output** | Brochure images in `database/scrape/<store>/<YYYYMMDD>/` (JPG/PNG) |
| **State** | `database/scrape/<store>/state.json` — MD5 tracking to skip already-seen images |
| **Dry-run** | Reports new images without downloading |

### Stage 2: OCR

Extracts product data from brochure images using Gemini or Ollama vision models.

| | |
|---|---|
| **Input** | Brochure images in `database/scrape/<store>/<YYYYMMDD>/` |
| **Output** | `database/ocr/<store>/<store>_promos_YYYYMMDD_HHMMSS.json` |
| **State** | `database/ocr/<store>/state.json` — tracks OCR'd images to avoid re-processing (saves API quota) |
| **Schema** | See below |
| **Dry-run** | Prints extracted products without saving JSON |

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

### Stage 3: Consolidation

Merges OCR results from both stores, matches same products across stores, computes unit prices and savings.

| | |
|---|---|
| **Input** | Latest `output/ocr/lotte_promos_*.json` and `output/ocr/superindo_promos_*.json` |
| **Output** | `output/consolidation/consolidated_latest.json` (always overwritten — HTML reads this) |
| | `output/consolidation/consolidated_YYYYMMDD_HHMMSS.json` (timestamped archive, can be deleted) |
| **Database** | `database/price_history.json` — accumulated price snapshots across runs |
| | `database/product_catalog.json` — auto-built product registry |
| | `database/review_queue.json` — low-confidence matches for inspection |
| **Dry-run** | Writes to `output/consolidation/dry_run_*.json`, skips database update |

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
        { "store": "Lotte", "price": 15500, "effective_unit_price": 3100, "bundle_size": 5, "promo": "DAPAT 5 pcs", "image_path": "database/scrape/lotte/20260516/promo_abc123.jpg" },
        { "store": "Superindo", "price": 3500, "effective_unit_price": 3500, "bundle_size": 1, "image_path": "database/scrape/superindo/20260516/promo_def456.jpg" }
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

Launches an interactive menu organized by stages. Each stage can be run independently — if something fails, you can rerun from that stage onward.

## Menu

| Key | Action | Description |
|---|---|---|
| **1** | Full pipeline | Scrape → OCR → Consolidate (end-to-end) |
| **2** | Stage 1: Scrape | Download brochure images (Lotte, Superindo, All, or dry-run) |
| **3** | Stage 2: OCR | Extract products from scraped images (all, specific, or dry-run) |
| **4** | Stage 3: Consolidation | Match products across stores (run or dry-run) |
| **5** | Tests | Integration tests or matching pipeline tests |

Each stage has a **dry-run** mode:
- **Scrape dry-run**: Reports new images without downloading
- **OCR dry-run**: Prints extracted products without saving JSON
- **Consolidation dry-run**: Runs full pipeline but outputs to `output/consolidation/dry_run_*.json` instead of updating `database/`

The **full pipeline** option ([1]) chains all 3 stages automatically with no dry-run — it scrapes, OCRs, and consolidates to the database in one go.

## Project Structure

```
haqita/
├── haqita.bat                        ← Interactive launch menu
├── config.yaml                       ← All tunable settings
├── .env                              ← Configuration (API keys, provider toggles)
├── docker/                           ← Docker configuration
│   ├── Dockerfile                    ← Python 3.12 + all deps
│   ├── docker-compose.yml            ← Full pipeline in container
│   └── .dockerignore                 ← Files excluded from build context
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
├── database/                         ← Generated, maintained (do not delete)
│   ├── scrape/
│   │   ├── lotte/
│   │   │   ├── state.json            ← MD5 tracking for already-seen images
│   │   │   └── 20260516/             ← Images from today's scrape (date-based)
│   │   └── superindo/
│   │       ├── state.json
│   │       └── 20260516/
│   ├── ocr/
│   │   ├── lotte/
│   │   │   ├── state.json            ← Tracks OCR'd images (saves quota)
│   │   │   └── lotte_promos_*.json   ← OCR results with image_path
│   │   └── superindo/
│   │       ├── state.json
│   │       └── superindo_promos_*.json
│   ├── price_history.json            ← Accumulated price snapshots
│   ├── product_catalog.json          ← Auto-built product registry
│   └── review_queue.json             ← Low-confidence matches
├── output/                           ← Generated, can be deleted (debugging)
│   └── consolidation/
│       ├── consolidated_latest.json  ← Always latest — HTML reads this
│       ├── consolidated_YYYYMMDD_HHMMSS.json  ← Timestamped archives
│       └── dry_run_*.json            ← Dry-run output
│   └── consolidation/
│       ├── consolidated_latest.json  ← Always latest — HTML reads this
│       ├── consolidated_YYYYMMDD_HHMMSS.json  ← Timestamped archives
│       └── dry_run_*.json            ← Dry-run output
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
