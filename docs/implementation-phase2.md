# Haqita — Phase 2: Consolidation & Product Matching

## Implementation Guide

**Branch:** `feature/phase-2-consolidation`  
**Stack:** Python scripts, JSON files, Docker container  
**Goal:** Merge OCR results from Lotte & Superindo, match same products across stores, output consolidated JSON for HTML display.

---

## Table of Contents

0. [Rules & Principles](#0-rules--principles)
1. [Architecture](#1-architecture)
2. [Project Structure](#2-project-structure)
3. [Configuration](#3-configuration)
4. [Data Schemas](#4-data-schemas)
5. [Matching Pipeline](#5-matching-pipeline)
6. [Normalizer](#6-normalizer)
7. [Promo Parser](#7-promo-parser)
8. [Matcher](#8-matcher)
9. [Consolidate Script](#9-consolidate-script)
10. [Docker Setup](#10-docker-setup)
11. [Testing Strategy](#11-testing-strategy)
12. [Implementation Order](#12-implementation-order)
13. [Logging & User Output](#13-logging--user-output)
14. [Bat Files](#14-bat-files)

---

## 0. Rules & Principles

### Cross-Phase Awareness
- **Phase 1 issues must be flagged**: Even when working on Phase 2, any problem or optimization candidate found in Phase 1 (scrapers, OCR) must be spoken out loud.
- **Goal is smooth end-to-end flow**: Don't workaround Phase 2 problems caused by bad Phase 1 output. Always find the best solution, even if it means refactoring Phase 1.
- **Confirm before refactoring**: Any refactor (Phase 1 or otherwise) must be confirmed with the user before implementation. Never silently change existing code.

### Implementation Workflow
- **Step-by-step**: Follow the Implementation Order (Section 12) strictly, one step at a time.
- **Review gate**: After each step is done, ask the user to review. Wait for confirmation before proceeding to the next step.
- **Commit discipline**: User commits and pushes after review. Never commit without explicit request.
- **Branch rule**: Only commit to `feature/phase-2-consolidation`. Never commit to other branches.

### Code Quality
- **Clean code**: Add appropriate comments, especially for complex/technical logic in the matching pipeline.
- **Isolated gates**: Each matching gate must be a clean, standalone function with clear input/output.
- **Feature flags**: Every gate must be individually enable/disable-able via `config.yaml`.
- **Logging**: Use appropriate log levels. Print important events and any operation that takes noticeable time — user must always understand what the system is doing.

### Testing
- **Unit vs Integration**: Pure functions → unit tests. External services or full pipeline → integration tests.
- **All test items covered**: Every test item from implementation-v2.md §6.7 must have a corresponding test.
- **Use real OCR data**: Integration tests use `data/test/*/ocr-result/*.json` files as input.

---

## 1. Architecture

```
  Lotte OCR JSON (output/lotte_*.json)    Superindo OCR JSON (output/superindo_*.json)
                    │                                      │
                    └──────────────────┬───────────────────┘
                                       ▼
                              consolidate.py
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
          consolidated_*.json   consolidated_     price_history.json
                                latest.json       product_catalog.json
                                review_queue.json
                                       │
                                       ▼
                                  index.html
                              (reads JSON at open)
```

### Design Principles

1. **Simple over clever** — no abstractions that don't earn their complexity
2. **Fail gracefully** — partial results beat no results; log everything that fails
3. **Pre-compute for the HTML** — all math (unit prices, savings %) done in Python, not JS
4. **Accuracy first** — matching a wrong product across stores is worse than showing no match

### Key Constraints

- Ollama runs on Windows host via `ollama serve`, NOT inside Docker
- Docker connects to Ollama at `http://host.docker.internal:11434`
- Gemini API calls go out directly from container (no proxy needed)
- OCR provider is Gemini (more accurate); AI verifier defaults to Ollama (free)

---

## 2. Project Structure

```
haqita/
├── haqita.bat                          # Main menu (Windows) — UPDATED
├── config.yaml                         # All tunable settings — UPDATED
├── .env                                # Secrets and provider toggles (never committed)
├── .env.example                        # Template for .env — UPDATED
├── Dockerfile                          # NEW — Python 3.12 + all deps
├── docker-compose.yml                  # NEW — Full pipeline in container
├── .dockerignore                       # NEW
│
├── scripts/
│   ├── scrapers/
│   │   ├── base_scraper.py               # Shared scraper infrastructure (BaseScraper class)
│   │   ├── lotte.py                      # Lotte Mart scraper (store-specific)
│   │   └── superindo.py                  # Superindo scraper (store-specific)
│   ├── consolidate.py                  # NEW — Merge + match + output JSON
│   ├── run_consolidate.bat             # NEW — Windows launcher for consolidation
│   ├── ocr/
│   │   ├── ocr_processor.py            # Shared OCR interface (existing)
│   │   ├── gemini_client.py            # Gemini OCR client (existing)
│   │   ├── ollama_client.py            # Ollama OCR client (existing)
│   │   ├── image_preprocess.py         # Image prep before OCR (existing)
│   │   └── prompts/                    # OCR prompts (existing)
│   └── matching/
│       ├── __init__.py                 # Package marker (existing, empty)
│       ├── normalizer.py               # NEW — Name/unit/brand normalization
│       ├── matcher.py                  # NEW — Multi-tier matching pipeline
│       └── promo_parser.py             # NEW — Indonesian promo text parser
│
├── data/
│   └── scrape/
│       ├── lotte/                      # Downloaded brochure images (Lotte)
│       └── superindo/                  # Downloaded brochure images (Superindo)
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
├── tests/
│   ├── matching/                       # NEW
│   │   ├── __init__.py
│   │   ├── test_normalizer.py          # Unit tests for normalizer
│   │   ├── test_promo_parser.py        # Unit tests for promo parser
│   │   ├── test_matcher.py             # Unit tests for matcher gates
│   │   └── test_consolidate.py         # Integration tests for full pipeline
│   └── integration/
│       ├── run_integration_tests.bat   # UPDATED — Add matching test option
│       ├── test_lotte_ocr.py           # Existing
│       └── test_superindo_ocr.py       # Existing
│
├── index.html                          # The deliverable — opens in any browser (Phase 3)
│
└── docs/
    ├── implementation-v2.md            # Original full plan (read-only reference)
    └── implementation-phase2.md        # THIS FILE — Phase 2 implementation guide
```

---

## 3. Configuration

### config.yaml (updated)

```yaml
scrapers:
  lotte:
    url: https://www.lottemart.co.id/all-promo-mart
    min_image_size_kb: 50
    request_delay_seconds: 2

  superindo:
    urls:
      - https://www.superindo.co.id/promosi/katalog-super-hemat/
      - https://www.superindo.co.id/promosi/promo-koran/
    region_filter: jabodetabek-palembang
    min_image_size_kb: 50
    request_delay_seconds: 2

ocr:
  provider: gemini

  ollama:
    model: qwen3-vl:7b
    num_ctx: 8192
    timeout_seconds: 300
    max_retries: 2
    temperature: 0
    image_min_width_px: 1400
    image_contrast_enhance: 1.4
    image_sharpness_enhance: 1.2

  gemini:
    model: gemini-3-flash-preview
    timeout_seconds: 60
    max_retries: 2

consolidation:
  # Matching pipeline thresholds
  token_jaccard_min: 0.30             # Below this: skip pair before embedding
  embedding_model: paraphrase-multilingual-MiniLM-L12-v2
  embedding_auto_match: 0.85          # Embedding score >= this: auto-match
  embedding_ambiguous_low: 0.55       # Below this: no match
                                       # Between 0.55-0.85: send to AI verifier
  unit_tolerance_pct: 15              # UnitParser: allow ±15% for OCR unit noise
  price_ratio_max: 3.0                # Per-unit price ratio > this: flag match

  # Feature flags for each gate (enable/disable individually)
  gates:
    gate0_unit_type: true
    gate1_brand: true
    gate2_token_jaccard: true
    gate3_exact_match: true
    gate4_embedding: true
    gate5_price_plausibility: true
    gate6_ai_verifier: true

  # AI verifier (for ambiguous pairs)
  ai_verifier:
    provider: ollama                  # "ollama" or "gemini"
    ai_model: qwen3:4b                # Ollama model
    gemini_model: gemini-3-flash-preview  # Gemini model (if provider=gemini)
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

### .env.example (updated)

```dotenv
# Copy to .env and fill in values. Never commit .env to git.

# OCR provider: "ollama" (local) or "gemini" (cloud, free tier)
# OCR_PROVIDER=gemini

# Required only when OCR_PROVIDER=gemini
# Get your free key at: https://aistudio.google.com/apikey
# GEMINI_API_KEY=your_key_here

# AI verifier provider: "ollama" (free, default) or "gemini"
# AI_VERIFIER_PROVIDER=ollama
```

### Loading config in scripts

```python
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def load_config() -> dict:
    with open(Path(__file__).parent.parent / 'config.yaml') as f:
        cfg = yaml.safe_load(f)
    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg['ocr']['provider'] = env_provider
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg['ocr']['gemini']['api_key'] = env_key
    env_ai = os.getenv('AI_VERIFIER_PROVIDER')
    if env_ai:
        cfg['consolidation']['ai_verifier']['provider'] = env_ai
    return cfg
```

---

## 4. Data Schemas

### 4.1 OCR output (per store, per run)

This is the schema produced by the scrapers and read by `consolidate.py`.

```json
{
  "store": "Lotte",
  "scraped_at": "2026-05-14T07:39:37",
  "source_url": "https://www.lottemart.co.id/all-promo-mart",
  "images_processed": 6,
  "ocr_provider": "gemini",
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

**Test JSON schema** (from `data/test/*/ocr-result/*.json`):
```json
{
  "image": "ht1.jpeg",
  "provider": "gemini",
  "ocr_time_s": 21.8,
  "products_count": 6,
  "rejected_count": 1,
  "products": [
    {
      "name": "GOLDEN FARM French Fries Shoestring",
      "brand": "GOLDEN FARM",
      "unit": "1 kg",
      "price": 32000,
      "promo": "LOTTE MART Point SPECIAL PRICE, Max 1",
      "period": "7 - 20 Mei 2026",
      "image_source": "ht1.jpeg",
      "ocr_raw_price": "32000",
      "ocr_confidence": 1.0
    }
  ],
  "rejected": [
    {
      "raw": {"name": "Gula Pasir", "brand": "CHOICE L / SUS", "price": 0},
      "reason": "price_invalid: 0"
    }
  ]
}
```

`consolidate.py` must accept **both** schemas — detect store from filename (`lotte_*` → Lotte, `superindo_*` → Superindo) and extract `products[]` regardless of wrapper schema.

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

**Key rule:** `products` = cross-store matches (always have `stores[]`), `singles` = store-specific (always have one `store`).

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

### 4.4 Product catalog

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

## 5. Matching Pipeline

The pipeline processes each pair of products (one from Lotte, one from Superindo) through ordered gates. A pair exits as MATCH, NO MATCH, or REVIEW. Gates are ordered cheapest-first. Each gate is isolated and feature-flagged.

```
For each (Lotte product A, Superindo product B) candidate pair:

Gate 0 — Unit type pre-filter
  → Incompatible types (weight vs count): SKIP PAIR immediately
  → Config: consolidation.gates.gate0_unit_type

Gate 1 — Brand pre-filter
  → Normalized brands known and different: SKIP PAIR immediately
  → Config: consolidation.gates.gate1_brand

Gate 2 — Token Jaccard pre-filter
  → token_overlap(A.name, B.name) < 0.30: SKIP PAIR (not similar enough)
  → Config: consolidation.gates.gate2_token_jaccard

Gate 3 — Exact token-set match
  → canonical_tokens(A) == canonical_tokens(B) AND units compatible:
     → MATCH (confidence: 1.0, method: "exact")
  → Config: consolidation.gates.gate3_exact_match

Gate 4 — Embedding similarity
  → Load paraphrase-multilingual-MiniLM-L12-v2 (once at startup)
  → Score >= 0.85 AND units compatible: MATCH (confidence: score, method: "embedding")
  → Score 0.55–0.85: candidate for Gate 5
  → Score < 0.55: NO MATCH
  → Config: consolidation.gates.gate4_embedding

Gate 5 — Price plausibility check
  → Per-unit price ratio > 3×: FLAG → review_queue, not matched
  → Config: consolidation.gates.gate5_price_plausibility

Gate 6 — AI verification (qwen3:4b or Gemini)
  → Only for pairs that survived Gates 0-5 with ambiguous scores
  → Batched (up to 20 pairs per call)
  → YES: MATCH (confidence: 0.75, method: "ai")
  → NO: NO MATCH
  → Unexpected: review_queue
  → Config: consolidation.gates.gate6_ai_verifier
```

### GateResult enum

```python
class GateResult(Enum):
    SKIP = "skip"           # Pair eliminated, no further processing
    PASS = "pass"           # Pair continues to next gate
    MATCH = "match"         # Pair matched, stop processing
    NO_MATCH = "no_match"   # Pair rejected, stop processing
    AMBIGUOUS = "ambiguous" # Needs further verification (Gate 5/6)
    REVIEW = "review"       # Flag for human review
```

---

## 6. Normalizer

**File:** `scripts/matching/normalizer.py`

### Brand normalization

```python
BRAND_ALIASES: dict[str, str] = {
    'lndomie': 'indomie',
    'lndomi': 'indomie',
    'S0sro': 'sosro',
    'S0s0': 'sosro',
    'Ult rajaya': 'ultrajaya',
    'UItra jaya': 'ultrajaya',
    'Ultrqjaya': 'ultrajaya',
}

def normalize_brand(brand: str | None) -> str:
    """Returns lowercase, space-stripped brand. Maps aliases."""
```

### Unit type detection

```python
UNIT_TYPE_MAP: dict[str, str] = {
    'g': 'weight', 'gram': 'weight', 'gr': 'weight', 'kg': 'weight',
    'ml': 'volume', 'l': 'volume', 'liter': 'volume', 'lt': 'volume',
    'pcs': 'count', 'pack': 'count', 'sachet': 'count',
    'bks': 'count', 'bungkus': 'count', 'botol': 'count', 'kaleng': 'count',
    'pck': 'count', 'pch': 'count', 'tub': 'count', 'box': 'count',
    'bag': 'count', 'set': 'count', 's': 'count',
}

def unit_type(unit: str | None) -> str | None:
    """Returns 'weight', 'volume', 'count', or None."""

def units_type_compatible(u1: str | None, u2: str | None) -> bool:
    """True if types match OR either unit is unknown."""
```

### Unit value normalization

```python
def parse_unit_to_base(unit: str | None) -> tuple[float, str] | None:
    """
    Returns (normalized_value, unit_type) or None.
    Examples: "85 g" → (85.0, "weight"), "1.5 L" → (1500.0, "volume"),
              "6 x 45 ml" → (270.0, "volume"), "3 pcs" → (3.0, "count")
    """

def units_value_compatible(u1: str | None, u2: str | None, tolerance: float = 0.15) -> bool:
    """True if unit values are within tolerance (default ±15% for OCR noise)."""
```

### Name normalization

```python
_UNIT_PATTERN = r'\b\d+(?:[.,]\d+)?\s*(?:[×x]\s*\d+(?:[.,]\d+)?\s*)?(kg|g|gram|ml|l|liter|pcs|pack|sachet|bks)\b'

@lru_cache(maxsize=2048)
def normalize_name(name: str) -> str:
    """Lowercase, strip units, strip punctuation, collapse whitespace. Cached."""

def canonical_tokens(name: str) -> frozenset:
    """Order-independent token set for exact matching."""

def token_overlap(name_a: str, name_b: str) -> float:
    """Jaccard similarity on token sets. Pre-filter before embedding."""
```

---

## 7. Promo Parser

**File:** `scripts/matching/promo_parser.py`

### PromoResult dataclass

```python
@dataclass
class PromoResult:
    promo_type: str         # bundle_buy | get_free | discount_pct | discount_fixed | multi_price | single
    display: str            # Original promo text
    unit_count: int         # Effective units received
    effective_unit_price: int
```

### Supported patterns

```python
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
```

### parse_promo

```python
def parse_promo(promo_text: str | None, base_price: int) -> PromoResult:
    """
    Returns a PromoResult. Falls back to single-unit if no pattern matches.
    base_price: the price field from OCR (may be total bundle price).
    """
```

### parse_valid_until

```python
def parse_valid_until(period: str | None) -> str | None:
    """
    Extract the end date from period string.
    "7 - 20 Mei 2026" → "2026-05-20"
    """
    MONTHS = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'mei': '05', 'jun': '06', 'jul': '07', 'agu': '08',
        'sep': '09', 'okt': '10', 'nov': '11', 'des': '12',
        'may': '05', 'aug': '08', 'oct': '10', 'dec': '12'
    }
```

---

## 8. Matcher

**File:** `scripts/matching/matcher.py`

### Gate functions (isolated, feature-flagged)

Each gate is a standalone function. The orchestrator checks config before calling.

```python
def gate0_unit_type(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 0: Skip if unit types are incompatible (weight vs count)."""

def gate1_brand(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 1: Skip if normalized brands are known and different."""

def gate2_token_jaccard(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 2: Skip if token Jaccard overlap < threshold."""

def gate3_exact_match(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 3: Match if canonical tokens are equal AND units compatible."""

def gate4_embedding(a: dict, b: dict, cfg: dict, model) -> GateResult:
    """Gate 4: Embedding similarity. Returns MATCH/AMBIGUOUS/NO_MATCH."""

def gate5_price_plausibility(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 5: Flag for review if per-unit price ratio > max."""

def gate6_ai_verifier(pairs: list[dict], cfg: dict) -> list[dict | None]:
    """Gate 6: Send ambiguous pairs to AI (Ollama or Gemini) for binary yes/no."""
```

### AI verifier

```python
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
```

### Embedding model

```python
def load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)

def compute_similarity_matrix(names_a: list[str], names_b: list[str], model) -> list[list[float]]:
    """Returns similarity[i][j] for names_a[i] vs names_b[j]."""
```

### Main orchestrator

```python
def match_products(lotte_products: list[dict], superindo_products: list[dict],
                   cfg: dict, embedding_model=None) -> tuple[list, list, list, list]:
    """
    Run full matching pipeline.
    Returns: (matched_pairs, lotte_only, superindo_only, review_items)
    """
```

---

## 9. Consolidate Script

**File:** `scripts/consolidate.py`

### CLI interface

```
python scripts/consolidate.py [options]

Options:
  --input-dir DIR          Auto-detect store from filename, pick latest per store
  --lotte-dir DIR          Explicit Lotte input directory
  --superindo-dir DIR      Explicit Superindo input directory
  --output-dir DIR         Output directory (default: output/)
  --no-docker              Run natively (not in Docker)
```

**Default behavior** (no args): reads from `output/` directory.

### Flow

```
1.  Load config
2.  Discover input files (CLI args or auto-detect from output/)
3.  Load latest Lotte JSON → extract products[]
4.  Load latest Superindo JSON → extract products[]
5.  If either store has zero products: log warning, continue with singles only
6.  Backup price_history.json → price_history.json.backup
7.  For every product in both stores:
    a. Run parse_promo() to get effective_unit_price, promo_type, bundle_size
    b. Run parse_valid_until() to get valid_until date
8.  Load embedding model (once, if Gate 4 enabled)
9.  Run match_products() → matched_pairs, lotte_only, superindo_only, review_items
10. Build consolidated "products" list from matched_pairs:
    - Compute key, unit_type, unit_value_g
    - Compute price_min, price_max, cheapest_store, price_gap, savings_pct
    - Build promo_summary
11. Build "singles" list from lotte_only + superindo_only
12. Update product_catalog.json
13. Append to price_history.json (dedup: same product+date+store not added twice)
14. Write consolidated_YYYYMMDD_HHMMSS.json
15. Overwrite consolidated_latest.json (atomic: write to temp, then rename)
16. Append to review_queue.json (if any, cap at review_queue_max)
17. Print summary to console
```

### Atomic write pattern

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

### Catalog update logic

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
            for v in entry['name_variants']:
                if v['name'] == product['name']:
                    v['count'] += 1
                    break
            else:
                entry['name_variants'].append({'name': product['name'], 'count': 1, 'store': product['store']})
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

### Product key generation

```python
def make_product_key(name: str, brand: str | None, unit: str | None) -> str:
    """
    Generate a stable, URL-safe key for a product.
    "Indomie Goreng" + "Indomie" + "85 g" → "indomie-goreng--indomie--85g"
    """
    name_slug = re.sub(r'[^a-z0-9]+', '-', name.lower().strip()).strip('-')
    brand_slug = re.sub(r'[^a-z0-9]+', '-', (brand or '').lower().strip()).strip('-')
    unit_slug = re.sub(r'[^a-z0-9]+', '-', (unit or '').lower().strip()).strip('-')
    return f"{name_slug}--{brand_slug}--{unit_slug}"
```

---

## 10. Docker Setup

### Dockerfile

```dockerfile
FROM python:3.12-slim

# System deps for sentence-transformers build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Default command
CMD ["python", "scripts/consolidate.py"]
```

### requirements.txt

```
requests
beautifulsoup4
Pillow
pyyaml
python-dotenv
google-genai
sentence-transformers
numpy
scikit-learn
pytest
```

### docker-compose.yml

```yaml
services:
  haqita:
    build: .
    volumes:
      - .:/app
    env_file: .env
    extra_hosts:
      - "host.docker.internal:host-gateway"
    command: python scripts/consolidate.py
```

### .dockerignore

```
.git/
__pycache__/
*.pyc
.pytest_cache/
.vscode/
output/
work/
data/scrape/
*.egg-info/
dist/
build/
.env
```

### Ollama connection

Ollama runs on Windows host via `ollama serve`. Docker connects to it at `http://host.docker.internal:11434`. The AI verifier code must detect when running inside Docker and use `host.docker.internal` instead of `localhost`.

```python
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
# In Docker, set OLLAMA_BASE_URL=http://host.docker.internal:11434 in .env
```

---

## 11. Testing Strategy

### Test classification

| Test | Type | Rationale | File |
|---|---|---|---|
| Unit-type pre-filter | **Unit** | Pure function, no external deps | `test_normalizer.py` |
| Brand filter | **Unit** | Pure function, no external deps | `test_normalizer.py` |
| Token Jaccard | **Unit** | Pure function, no external deps | `test_normalizer.py` |
| Exact match (word order swap) | **Unit** | Pure function, no external deps | `test_normalizer.py` |
| Unit value tolerance (boundary) | **Unit** | Pure function, no external deps | `test_normalizer.py` |
| Price plausibility (5× ratio) | **Unit** | Pure function, no external deps | `test_matcher.py` |
| AI parser (mock YES/NO/garbage) | **Unit** | Mock HTTP, no real Ollama needed | `test_matcher.py` |
| promo_parser: "DAPAT 5 pcs" | **Unit** | Pure function, no external deps | `test_promo_parser.py` |
| promo_parser: "Beli 2 Gratis 1" | **Unit** | Pure function, no external deps | `test_promo_parser.py` |
| promo_parser: "Diskon 20%" | **Unit** | Pure function, no external deps | `test_promo_parser.py` |
| promo_parser: "Hemat Rp 5.000" | **Unit** | Pure function, no external deps | `test_promo_parser.py` |
| promo_parser: "N/Rp X" | **Unit** | Pure function, no external deps | `test_promo_parser.py` |
| parse_valid_until | **Unit** | Pure function, no external deps | `test_promo_parser.py` |
| Atomic write (corrupt JSON) | **Unit** | Filesystem only, no external deps | `test_consolidate.py` |
| Empty store (zero products) | **Integration** | Needs full pipeline orchestration | `test_consolidate.py` |
| price_history append + dedup | **Integration** | Needs full pipeline + file I/O | `test_consolidate.py` |
| clean_price (all formats) | **Unit** | Pure function | `test_ocr_processor.py` |
| Full end-to-end pipeline | **Integration** | Uses real `data/test/*/ocr-result/*.json` files | `test_consolidate.py` |
| Embedding model matching | **Integration** | Requires sentence-transformers model download | `test_matcher.py` (marked `@pytest.mark.slow`) |

### Test data

Use `data/test/lotte/ocr-result/gemini/ht1.json`, `data/test/lotte/ocr-result/gemini/ht5.json`, and `data/test/superindo/ocr-result/gemini/sample_katalog_1.json` as input for integration tests.

### Running tests

```bash
# All tests
pytest tests/matching/ -v

# Unit tests only (fast, no model download)
pytest tests/matching/ -v -m "not slow"

# Integration tests (requires model download)
pytest tests/matching/test_consolidate.py -v

# Slow tests (embedding model)
pytest tests/matching/ -v -m slow
```

---

## 12. Implementation Order

| Step | Action | Files |
|---|---|---|
| 1 | Create branch `feature/phase-2-consolidation` | git |
| 2 | Docker setup | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `requirements.txt` |
| 3 | Update config.yaml with gate feature flags | `config.yaml` |
| 4 | Normalizer + unit tests | `scripts/matching/normalizer.py`, `tests/matching/test_normalizer.py` |
| 5 | Promo parser + unit tests | `scripts/matching/promo_parser.py`, `tests/matching/test_promo_parser.py` |
| 6 | Matcher + unit tests | `scripts/matching/matcher.py`, `tests/matching/test_matcher.py` |
| 7 | Consolidate script + integration tests | `scripts/consolidate.py`, `tests/matching/test_consolidate.py` |
| 8 | Update bat files | `haqita.bat`, `tests/integration/run_integration_tests.bat`, `scripts/run_consolidate.bat` |
| 9 | Update .env.example | `.env.example` |
| 10 | Run all tests, fix issues | pytest |
| 11 | Commit & push | git |

---

## 13. Logging & User Output

### Logging levels

```python
import logging
logger = logging.getLogger(__name__)

# INFO: user-facing progress (always shown)
logger.info("Loading %d Lotte products from %s", len(products), filepath)
logger.info("Loading embedding model (first run downloads ~90MB)...")
logger.info("Gate 3: %d exact matches found", count)
logger.info("Gate 4: running embedding similarity on %d candidate pairs...", count)
logger.info("Gate 6: sending %d ambiguous pairs to AI verifier...", count)

# DEBUG: technical details (verbose mode)
logger.debug("Pair: '%s' vs '%s' → Jaccard=%.2f", name_a, name_b, score)

# WARNING: issues that don't stop processing
logger.warning("Price ratio %.1fx for '%s' vs '%s' — sent to review", ratio, name_a, name_b)

# ERROR: failures that stop processing
logger.error("AI verification failed: %s", e)
```

### Console output (print) for long operations

These operations take noticeable time — print status so user knows what's happening:

```
[*] Loading Lotte products from output/lotte_promos_20260514_073937.json ... 6 products
[*] Loading Superindo products from output/superindo_promos_20260514_081500.json ... 21 products
[*] Parsing promo text and computing effective unit prices ...
[*] Loading embedding model (first run downloads ~90MB) ...
[*] Running matching pipeline ...
    Gate 0 (unit type): 12 pairs skipped
    Gate 1 (brand): 8 pairs skipped
    Gate 2 (token jaccard): 45 pairs skipped
    Gate 3 (exact match): 3 matches found
    Gate 4 (embedding): 12 pairs evaluated, 2 auto-matched, 5 ambiguous
    Gate 5 (price plausibility): 1 sent to review
    Gate 6 (AI verifier): sending 5 pairs to Ollama ... (may take 30s)
[*] Building consolidated output ...
[*] Writing consolidated_20260514_082000.json
[*] Writing consolidated_latest.json (atomic)
[*] Updating product_catalog.json: 24 entries
[*] Appending to price_history.json: 24 snapshots
[*] Review queue: 1 items

========================================
  Consolidation Summary
========================================
  Lotte products:     6
  Superindo products: 21
  Matched:            5
  Lotte only:         1
  Superindo only:     16
  Review queue:       1
========================================
```

---

## 14. Bat Files

### haqita.bat (updated)

Add menu items:
```
[6] Consolidate prices (Docker)
[7] Run matching tests
```

### tests/integration/run_integration_tests.bat (updated)

Add option:
```
[5] Matching pipeline tests
```

### scripts/run_consolidate.bat (new)

```bat
@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Haqita — Consolidation Pipeline
echo ========================================
echo.

echo  [1] Run consolidation (Docker)
echo  [2] Run consolidation (native Python)
echo  [3] Run with custom input directory
echo  [0] Back
echo.

set /p choice="Your choice: "

if "%choice%"=="1" goto RUN_DOCKER
if "%choice%"=="2" goto RUN_NATIVE
if "%choice%"=="3" goto RUN_CUSTOM
if "%choice%"=="0" exit /b 0

:RUN_DOCKER
echo Running in Docker...
docker compose up --build
goto END

:RUN_NATIVE
echo Running natively...
python scripts/consolidate.py
goto END

:RUN_CUSTOM
set /p dir="Input directory: "
if "%dir%"=="" set dir=output
python scripts/consolidate.py --input-dir "%dir%"
goto END

:END
echo.
pause
```

---

## Appendix: OCR Data Observations

From the test JSON files in `data/test/*/ocr-result/*.json`:

### Lotte HT1 (6 products)
- Packaged/frozen goods with brands
- Promo: "LOTTE MART Point SPECIAL PRICE, Max 1"
- Units: "1 kg", "1000 ml", "1100's", "335 ml", "2 x 800 ml", "set"

### Lotte HT5 (5 products)
- Fresh produce/meat, mostly no brand
- Promo: "BUY 1 GET 1", "Satu Harga"
- Units: "100 g", "500 g", "100 g / 120 g"

### Superindo (21 products)
- Mixed categories
- Promo diversity: "Diskon 15%", "Beli 1 Gratis 1", "maks. 4 pch", "Harga Spesial"
- Units: "100 g", "pck", "950 g", "946 ml", "140 g", "4 x 200's", "bag", "box", "tub", "35 ml", "1500 ml", "1600 ml", "1 kg"

### Cross-store match candidates (from visual inspection)
- "GOLDEN FARM French Fries" (Lotte) vs "365 French Fries" (Superindo) — different brands, should NOT match
- "Daging Semur / Rendang / Rawon" (Lotte) vs "Dada Ayam Tanpa Tulang" (Superindo) — different cuts, should NOT match
- "Ikan Bawal Hitam" (Superindo) — no Lotte equivalent, becomes single
- "Boneless Dada / Paha Tanpa Kulit" (Lotte) vs "Dada Ayam Tanpa Tulang, Paha Ayam Boneless" (Superindo) — similar, may match via embedding
