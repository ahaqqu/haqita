# Stage 3: Consolidation

Merges OCR results from both stores, matches same products across stores, computes unit prices and savings.

## Overview

| | |
|---|---|
| **Input** | Latest `database/ocr/<store>/<store>_promos_*.json` |
| **Output** | `database/consolidated_YYYYMMDD_HHMMSS.json` (timestamped archive in database) |
| **Database** | `database/price_history.json` — accumulated price snapshots |
| | `database/product_catalog.json` — auto-built product registry |
| | `database/review_queue.json` — low-confidence matches for inspection |
| **Dry-run** | Writes to `output/consolidation/dry_run_*.json`, skips database update |

## Consolidated Output Schema

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

## Matching Pipeline

Each product pair passes through 7 gates. Each gate is individually toggleable via `config.yaml`.

```
lotte_products ──┐
                 ├──▶ Gate 0: Unit Type ──▶ Gate 1: Brand
superindo_       │       │                      │
products   ──────┘       ▼                      ▼
                   Gate 2: Jaccard ──▶ Gate 3: Exact Match
                          │                      │
                          ▼                      ▼
                   Gate 4: Embedding ──▶ Gate 5: Price Check
                          │                      │
                          ▼                      ▼
                   Gate 6: AI Verifier ──▶ MATCH / NO / REVIEW
```

### Gate Details

| Gate | Name | Purpose | Result |
|---|---|---|---|
| 0 | Unit Type | Skip if incompatible (weight vs volume) | SKIP / PASS |
| 1 | Brand | Skip if different known brands | SKIP / PASS |
| 2 | Token Jaccard | Skip if name similarity below threshold | SKIP / PASS |
| 3 | Exact Match | Immediate match if normalized names identical | MATCH / PASS |
| 4 | Embedding | Semantic similarity via sentence-transformers | MATCH / AMBIGUOUS / PASS |
| 5 | Price Check | Flag if per-unit price ratio too high | REVIEW / PASS |
| 6 | AI Verifier | LLM binary YES/NO for ambiguous pairs | MATCH / NO / REVIEW |

### Configuration

```yaml
consolidation:
  token_jaccard_min: 0.30
  embedding_model: paraphrase-multilingual-MiniLM-L12-v2
  embedding_auto_match: 0.85
  embedding_ambiguous_low: 0.55
  unit_tolerance_pct: 15
  price_ratio_max: 3.0

  gates:
    gate0_unit_type: true
    gate1_brand: true
    gate2_token_jaccard: true
    gate3_exact_match: true
    gate4_embedding: true
    gate5_price_plausibility: true
    gate6_ai_verifier: true

  ai_verifier:
    provider: ollama
    ai_model: qwen3:4b
    gemini_model: gemini-3-flash-preview
    ai_batch_size: 20
```

## Promo Parsing

Promo text is parsed to compute effective unit price:

| Pattern | Example | Result |
|---|---|---|
| `DAPAT N pcs` | "DAPAT 5 pcs" | bundle_buy, unit_count=5 |
| `Beli N Gratis M` | "Beli 2 Gratis 1" | get_free, unit_count=3 |
| `N / Rp X` | "3 / Rp 10.000" | multi_price, unit_count=3 |
| `Diskon N%` | "Diskon 20%" | discount_pct |
| `Hemat Rp X` | "Hemat Rp 5.000" | discount_fixed |

## Date Parsing

Promo periods are parsed to extract end date (`valid_until`):

| Input | Output |
|---|---|
| `"7 - 20 Mei 2026"` | `"2026-05-20"` |
| `"Berlaku 1-15 Mei 2026"` | `"2026-05-15"` |
| `"s/d 20 Mei 2026"` | `"2026-05-20"` |
| `"Valid until 15 May 2026"` | `"2026-05-15"` |
| `"20 Mei 2026"` | `"2026-05-20"` |

## Usage

Via `haqita.bat` → Option [4] → Consolidation submenu:

| Choice | Action |
|---|---|
| **1** | Run consolidation |
| **2** | Dry-run (no database update) |

## Verbose Logging

Run with `--verbose` flag to get detailed match results in `database/logs/consolidate_<timestamp>.log`:

- All matched pairs with match method and confidence
- All lotte-only and superindo-only products
- All review queue items with rejection reason
- All gate rejections with which gate filtered the pair and why

## Database Files

### price_history.json

Accumulated price snapshots across runs. Each entry tracks:

```json
{
  "2026-05-16": [
    {
      "key": "indomie-goreng--indomie--85g",
      "name": "Indomie Goreng",
      "store": "Lotte",
      "price": 3500,
      "effective_unit_price": 3100
    }
  ]
}
```

### product_catalog.json

Auto-built product registry with all known products and their attributes.

### review_queue.json

Low-confidence matches flagged for manual inspection.
