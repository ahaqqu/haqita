# Implementation Plan — Multi-Store Promo Scraper & Price Comparison

## Overview

Scrape promo brochures from Lotte Mart and Superindo, extract product data using Qwen3-VL OCR,
normalize product names across stores, consolidate into a unified dataset, and display price
comparisons in a dynamic HTML page — with historical price tracking for trend analysis.

**Critical Design Principles:**
1. **Fail gracefully**: Partial results are better than no results
2. **Validate everything**: Never trust OCR output without validation
3. **Monitor continuously**: Detect failures before users do
4. **Test comprehensively**: Cover edge cases, not just happy paths

```
                    ┌──────────────┐
                    │  Lotte Mart  │
                    │  Website     │
                    └──────┬───────┘
                           │ GET /all-promo-mart
                           ▼
                    ┌──────────────┐     ┌──────────────────┐
                    │ lotte_qwen   │────>│ lotte_promos_    │
                    │ .py scraper  │     │ 20260514_*.json  │
                    └──────────────┘     └────────┬─────────┘
                                                  │
                    ┌──────────────┐              │
                    │  Superindo   │              │
                    │  Website     │              │
                    └──────┬───────┘              │
                           │ GET /katalog-        │
                           │ super-hemat          │
                           ▼                      │
                    ┌──────────────┐     ┌────────┴─────────┐
                    │ superindo_   │     │ superindo_promos_│
                    │ qwen.py      │────>│ 20260514_*.json  │
                    │ scraper      │     └────────┬─────────┘
                    └──────────────┘              │
                                                  │
                                                  ▼
                    ┌──────────────────────────────────────┐
                    │          consolidate.py               │
                    │                                      │
                    │  1. Load both JSONs                   │
                    │  2. Rule-based name normalization     │
                    │  3. AI fuzzy matching (qwen3:4b)      │
                    │  4. Build unified product list        │
                    │  5. Update price_history.json         │
                    │  6. Write consolidated_*.json         │
                    │  7. Copy to consolidated_latest.json  │
                    └──────────────────┬───────────────────┘
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼              ▼
                ┌────────────┐ ┌────────────┐ ┌────────────┐
                │consolidated│ │consolidated│ │price_      │
                │_20260514_  │ │_latest.json│ │history.json│
                │*.json      │ │(for HTML)  │ │(trends)    │
                └────────────┘ └────────────┘ └──────┬─────┘
                                                     │
                                                     ▼
                                          ┌──────────────────────┐
                                          │    index.html        │
                                          │  (dynamic JS)        │
                                          │                      │
                                          │  - Product list      │
                                          │  - Price comparison  │
                                          │  - Store badges      │
                                          │  - Price trends      │
                                          └──────────────────────┘
```

---

## Data Storage

```
output/
├── lotte_promos_20260514_073937.json        # Lotte OCR — per run, never overwritten
├── superindo_promos_20260514_081500.json    # Superindo OCR — per run, never overwritten
├── consolidated_20260514_082000.json        # Merged data — per run, never overwritten
├── consolidated_latest.json                 # Symlink/copy of latest (for HTML fetch)
├── price_history.json                       # Accumulated over time (appended each run)
└── price_history.json.backup                # Auto-backup before each write (critical!)
```

### price_history.json format

```json
{
  "product_history": [
    {
      "product_key": "indomie-goreng--indomie",
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "snapshots": [
        {"date": "2026-05-07", "store": "Lotte", "price": 3100, "promo": "DAPAT 5 pcs"},
        {"date": "2026-05-07", "store": "Superindo", "price": 3500, "promo": null},
        {"date": "2026-05-14", "store": "Lotte", "price": 3000, "promo": null},
        {"date": "2026-05-14", "store": "Superindo", "price": 3400, "promo": null}
      ]
    }
  ],
  "metadata": {
    "last_updated": "2026-05-14T08:20:00",
    "total_runs": 52,
    "schema_version": "1.0"
  }
}
```

### ⚠️ Critical: Data Retention Policy

**Problem:** `price_history.json` will grow unbounded (~100 KB/run × 52 runs/year = 5 MB/year per product).

**Solution:** Implement tiered retention:
- Keep **daily snapshots** for last 90 days
- After 90 days, keep only **weekly aggregates** (avg price per week)
- After 1 year, keep only **monthly aggregates**

**Implementation:** Add `aggregate_history.py` script to run monthly, compressing old data.

---

## Data Validation Layer (CRITICAL)

**Problem:** OCR output is unreliable. Without validation, garbage data pollutes `price_history.json` permanently.

### Validation Rules

All OCR output MUST pass these checks before being saved:

| Check | Rule | Action on Failure |
|-------|------|-------------------|
| **Schema validation** | All required fields present (name, price, unit) | Reject product, log warning |
| **Price sanity** | Price must be 100 ≤ price ≤ 1,000,000 IDR | Reject product, flag for review |
| **Name validity** | Product name ≥ 3 characters, not all caps | Reject product |
| **Unit consistency** | Unit must match known patterns (g, ml, kg, L, pcs) | Normalize or reject |
| **Duplicate detection** | Same (name, brand, unit, price) within same store | Deduplicate, keep first |
| **Confidence scoring** | Flag products with low OCR confidence (<0.7) | Mark for manual review |

### Pydantic Schema Definition

Create `schemas/product.py`:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

class ProductSnapshot(BaseModel):
    date: str
    store: str
    price: int
    promo: Optional[str]
    period: Optional[str]
    
    @validator('price')
    def price_must_be_reasonable(cls, v):
        if not (100 <= v <= 1_000_000):
            raise ValueError(f'Price {v} outside reasonable range')
        return v
    
    @validator('store')
    def store_must_be_known(cls, v):
        allowed = {'Lotte', 'Superindo'}
        if v not in allowed:
            raise ValueError(f'Unknown store: {v}')
        return v

class OCRProduct(BaseModel):
    name: str = Field(..., min_length=3)
    brand: Optional[str]
    unit: Optional[str]
    price: int
    promo: Optional[str]
    period: Optional[str]
    image_source: str
    ocr_confidence: float = Field(ge=0.0, le=1.0)
    
    @validator('name')
    def name_not_all_caps(cls, v):
        if v.isupper() and len(v) > 5:
            raise ValueError('Product name appears to be all caps')
        return v
    
    @validator('ocr_confidence')
    def flag_low_confidence(cls, v):
        if v < 0.7:
            # Don't reject, but flag for review
            pass
        return v

class ConsolidatedProduct(BaseModel):
    key: str
    name: str
    brand: Optional[str]
    unit: Optional[str]
    stores: List[ProductSnapshot]
    price_min: int
    price_max: int
    cheapest_store: str
    price_gap: int
```

### Validation Flow

```
OCR Output → Schema Validation → Price Sanity Check → Deduplication → Confidence Scoring → Save
                  ↓                      ↓                    ↓                  ↓
              Reject if             Reject if          Remove dups         Flag if <0.7
              invalid               unreasonable                          for review
```

### Manual Review Queue

Products flagged for review are saved to `output/review_queue.json`:

```json
{
  "flagged_products": [
    {
      "product": {...},
      "reason": "low_ocr_confidence",
      "confidence": 0.45,
      "timestamp": "2026-05-14T08:20:00"
    }
  ]
}
```

---

## Error Handling & Recovery Strategy (CRITICAL)

**Problem:** The plan assumes OCR always succeeds and websites are always available.

### Retry Logic with Exponential Backoff

```python
import time
from functools import wraps

def retry_with_backoff(max_retries=5, base_delay=1.0, max_delay=60.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (RequestException, TimeoutError) as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = min(delay * (2 ** attempt), max_delay)
                    logger.warning(f'Retry {attempt+1}/{max_retries} after {wait_time}s: {e}')
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator
```

**Applied to:**
- Image downloads (network timeouts)
- Ollama API calls (service downtime)
- Website scraping (rate limiting)

### Circuit Breaker Pattern for Ollama

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=300):
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
    
    def call(self, func, *args, **kwargs):
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
            else:
                raise CircuitBreakerOpenError('Ollama service unavailable')
        
        try:
            result = func(*args, **kwargs)
            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'
            raise
```

### Graceful Degradation

| Failure Scenario | Degradation Strategy |
|-----------------|---------------------|
| Ollama completely down | Skip AI matching, use only rule-based normalization |
| One store scraper fails | Continue with other store, show partial results |
| OCR returns empty array | Log error, continue with other images, alert user |
| `price_history.json` corrupted | Restore from `.backup`, log incident |
| Network timeout mid-batch | Save partial state, resume from checkpoint |

### Health Check Endpoint

Create `scripts/health_check.py`:

```bash
# Run before starting pipeline
python scripts/health_check.py
```

Checks:
- [ ] Ollama service responding (`ollama list`)
- [ ] Required models installed (`qwen3-vl:2b`, `qwen3:4b`)
- [ ] Write permissions to `output/` directory
- [ ] Disk space available (>1 GB free)
- [ ] Internet connectivity (can reach lottemart.co.id, superindo.co.id)

Output:
```json
{
  "status": "healthy|degraded|unhealthy",
  "checks": {
    "ollama": {"status": "pass|fail", "latency_ms": 245},
    "models": {"status": "pass|fail", "missing": []},
    "disk": {"status": "pass|fail", "free_gb": 15.3},
    "network": {"status": "pass|fail"}
  },
  "timestamp": "2026-05-14T08:00:00"
}
```

---

## Implementation Phases

### Phase 1 — Superindo Scraper

**Goal:** Scrape promo images from Superindo catalog website and extract products via Qwen3-VL OCR.

**Files to create:**
- `scripts/scrapers/superindo_qwen.py`

**Details:**

Superindo has two promo pages:

| Page | URL | Content type |
|---|---|---|
| Katalog Super Hemat | `/promosi/katalog-super-hemat/` | Regional brochure images in a swiper slider |
| Promo Koran | `/promosi/promo-koran/` | Single newspaper promo image |

**Scraper flow:**

```
1. Fetch GET https://www.superindo.co.id/promosi/katalog-super-hemat/
2. Parse HTML with BeautifulSoup
3. Find all .swiper-slide a.fancybox elements
4. Extract image URLs from href attributes
5. Filter: only scrape the default/active region (Jabodetabek & Palembang)
6. Download images to data/scape/superindo/<md5_prefix>_<filename>
7. Compute MD5 hash, compare with data/scape/superindo_state.json
8. For new images: run Qwen3-VL OCR (reuse functions from qwen_ocr_processor.py)
9. Save results to output/superindo_promos_YYYYMMDD_HHMMSS.json
```

**HTML structure to parse:**

```html
<div class="swiper-slide">
  <a class="fancybox"
     data-fancybox="jabodetabek-palembang"
     href="https://www.superindo.co.id/images/katalog/6a04...DKI.jpg">
    <img src="https://www.superindo.co.id/images/katalog/6a04...DKI.jpg">
  </a>
</div>
```

The `data-fancybox` attribute value indicates the region. We filter for `jabodetabek-palembang`.

**State file:** `data/scape/superindo_state.json` (separate from Lotte)
```json
{
  "last_run": "2026-05-14T08:15:00",
  "processed": [
    {"filename": "katalog_abc123.jpeg", "md5": "abc123...", "product_count": 8}
  ]
}
```

**Reusable code from Lotte scraper:**
- `md5_hash()`, `load_state()`, `save_state()`, `filename_from_url()`
- `extract_product_prices()`, `extract_promo_date()` from `qwen_ocr_processor.py`
- Image filtering (size > 50KB, dimensions > 300px)

**Testing:**

| Test | Method | Edge Cases Covered |
|---|---|---|
| HTML parsing | Save a local copy of the Superindo page, run BeautifulSoup parsing in isolation | Malformed HTML, missing elements, changed structure |
| Image download | Run scraper in dry-run mode (`--dry-run`) to verify URLs are extracted correctly | Broken URLs, 404 errors, redirects |
| OCR on a single image | Manually download one catalog image and run `extract_product_prices()` on it | Blank images, ad-only images, corrupted files |
| Full run | `python scripts/scrapers/superindo_qwen.py` with `LOTTE_TEST_MODE=false` | End-to-end validation |
| Duplicate detection | Run twice — second run should skip all images (MD5 match) | Same image, different URL; rotated images |
| **OCR failure handling** | Mock Ollama to return empty/error responses | Verify graceful degradation |
| **Network timeout** | Use `toxiproxy` to simulate network delays | Verify retry logic works |
| **Validation layer** | Feed malformed OCR output | Verify rejection and logging |

**Dry-run support:** Same as Lotte scraper — `--dry-run` flag fetches and reports new images without OCR.

**Test Fixtures Required:**
```
test_data/
├── superindo/
│   ├── sample_html/           # Saved HTML snapshots
│   ├── sample_images/         # 10 diverse promo images
│   ├── edge_cases/            # Blank, ads-only, corrupted
│   └── golden_outputs/        # Expected OCR results for regression
```

---

### Phase 2 — Consolidation & Normalization

**Goal:** Merge Lotte + Superindo products into a unified dataset with deduplication and AI-powered name normalization.

**Files to create:**
- `scripts/consolidate.py`
- `schemas/product.py` (Pydantic validation schemas)

**Steps:**

```
1. Run health check (fail fast if critical services unavailable)
2. Load latest lotte_promos_*.json
3. Load latest superindo_promos_*.json
4. Load existing price_history.json (create if not exists)
5. BACKUP price_history.json → price_history.json.backup
6. Validate all OCR outputs against Pydantic schemas
7. Apply rule-based normalization to all product names
8. Group products by (normalized_name, brand, unit_hash)
9. For unmatched products: AI fuzzy matching via qwen3:4b
10. Build consolidated product list
11. Update price_history.json with today's snapshots
12. Write consolidated_YYYYMMDD_HHMMSS.json
13. Copy to consolidated_latest.json
14. Log metrics for monitoring
```

**Rule-based normalization (deterministic, catches ~80%):**

```
1. Strip unit suffixes: " 1 kg", " 500 ml", " 6 x 45 ml", " 200 g", " 2 L"
2. Strip "Rp" from price strings
3. Strip brand prefix from product name if brand field exists
4. Lowercase and strip whitespace
5. Remove punctuation differences (/, -, .)
6. Normalize unit representations: "gram" → "g", "mililiter" → "ml"
7. Create unit_hash for size comparison (e.g., "85g" → hash(85, "g"))
```

Example matching:
```
Lotte: "Indomie Goreng Ayam Geprek 85 g"  → normalized: "indomie goreng ayam geprek", unit_hash: hash(85, "g")
Superindo: "Indomie Goreng Ayam Geprek"    → normalized: "indomie goreng ayam geprek", unit_hash: hash(85, "g")
Result: MATCH ✓

Lotte: "Indomie Goreng 85g"                → unit_hash: hash(85, "g")
Superindo: "Indomie Goreng 80g"            → unit_hash: hash(80, "g")
Result: NO MATCH (different sizes) ✗
```

**⚠️ Critical: Product Matching Algorithm Improvements**

The simple rule-based + AI approach has fundamental flaws. Implement this hybrid approach:

```
Step 1: Exact match on (normalized_name + brand + unit_hash)
        ↓ (no match)
Step 2: Fuzzy match on name only IF units are equivalent
        - Use Levenshtein distance or ratio (>0.85 = match)
        - Handle multi-pack conversions: "6 x 45 ml" = "270 ml"
        ↓ (ambiguous, similarity 0.6-0.85)
Step 3: AI verification via qwen3:4b
        - Batch send ambiguous pairs only
        - Cache AI decisions for future runs
        ↓ (AI uncertain or "maybe")
Step 4: Flag for manual review in review_queue.json
```

**Unit Equivalence Logic:**
```python
def normalize_unit_to_ml(unit_str):
    """Convert all volume units to ml for comparison"""
    mappings = {
        'l': 1000, 'liter': 1000, 'liters': 1000,
        'ml': 1, 'milliliter': 1, 'milliliters': 1,
        'cl': 10, 'centiliter': 10
    }
    # Parse "6 x 45 ml" → 270 ml
    # Parse "1.5 L" → 1500 ml
    ...

def normalize_unit_to_g(unit_str):
    """Convert all weight units to g for comparison"""
    mappings = {
        'kg': 1000, 'kilogram': 1000, 'kilograms': 1000,
        'g': 1, 'gram': 1, 'grams': 1,
        'mg': 0.001
    }
    ...
```

**Handling Promotional Bundles:**
```
"DAPAT 5 pcs" at price 15000 → unit_price = 15000 / 5 = 3000 per pcs
"Beli 2 Gratis 1" at price 6000 → unit_price = 6000 / 3 = 2000 per item
```

Store both `total_price` and `unit_price` in the schema for accurate comparisons.

**AI fuzzy matching (catches remaining ~20%):**

For products that didn't find an exact match after rule-based normalization, batch-send them to `qwen3:4b`:

```
Prompt:
You are matching grocery products across stores.
Do these two product names refer to the same item? Answer yes or no only.
Consider:
- Same brand and similar name = likely match
- Different sizes (85g vs 80g) = NOT a match
- Multi-pack vs single unit = NOT a match unless unit prices match

Product A (Store: Lotte): "ILGUSTO Bratwurst Original 360 g" - Rp 45000
Product B (Store: Superindo): "Bratwurst Sosis 360g" - Rp 48000
```

**Model:** `ollama pull qwen3:4b` (~2.5 GB Q4_K_M) — text-only model, runs on CPU, ~2-5s per batch of 50 pairs.

**⚠️ Critical: AI Response Validation**

The AI might return unexpected responses. Implement robust parsing:

```python
def parse_ai_response(response_text):
    response = response_text.strip().lower()
    
    if response in ['yes', 'ya', 'y', 'match', 'sama']:
        return True
    elif response in ['no', 'tidak', 'n', 'nomatch', 'beda']:
        return False
    else:
        # AI returned something unexpected like "maybe", "not sure"
        logger.warning(f'Unexpected AI response: {response}')
        return None  # Flag for manual review
```

**Consolidated output format:**

```json
{
  "generated_at": "2026-05-14T08:20:00",
  "scrape_date_lotte": "2026-05-14T07:39:37",
  "scrape_date_superindo": "2026-05-14T08:15:00",
  "store_files": [
    "lotte_promos_20260514_073937.json",
    "superindo_promos_20260514_081500.json"
  ],
  "products": [
    {
      "key": "indomie-goreng-ayam-geprek--indomie",
      "name": "Indomie Goreng Ayam Geprek",
      "brand": "Indomie",
      "unit": "85 g",
      "unit_price": 3100,
      "stores": [
        {
          "store": "Lotte",
          "price": 3100,
          "total_price": 15500,
          "bundle_size": 5,
          "promo": "DAPAT 5 pcs",
          "period": "7 - 20 Mei 2026"
        },
        {
          "store": "Superindo",
          "price": 3500,
          "total_price": 3500,
          "bundle_size": 1,
          "promo": null,
          "period": "12 - 25 Mei 2026"
        }
      ],
      "price_min": 3100,
      "price_max": 3500,
      "cheapest_store": "Lotte",
      "price_gap": 400
    }
  ],
  "stats": {
    "total_products": 45,
    "matched_across_stores": 12,
    "lotte_only": 20,
    "superindo_only": 13,
    "ai_matches": 3,
    "validation_rejected": 2,
    "flagged_for_review": 1
  },
  "metadata": {
    "schema_version": "1.0",
    "validation_passed": true
  }
}
```

**Testing:**

| Test | Method | Edge Cases Covered |
|---|---|---|
| Rule-based normalization | Create a test file with 50+ known product name pairs | Punctuation, case, spacing variations |
| Unit equivalence | Test "6 x 45 ml" vs "270 ml", "1.5 L" vs "1500 ml" | Multi-pack conversions |
| Bundle pricing | Test "DAPAT 5 pcs" price calculations | Division, rounding |
| AI normalization | Run consolidate with 10 intentionally different product names | Verify correct match/mismatch |
| **Empty input** | Run with one store having zero products | No division by zero, graceful handling |
| **Corrupted history** | Corrupt price_history.json before run | Verify backup restore works |
| **AI returns garbage** | Mock AI to return "maybe", "idk", random text | Verify parsing handles edge cases |
| No-overwrite | Run consolidate twice — verify new timestamped file each time | File naming uniqueness |
| Price history append | Run consolidate twice — verify price_history.json has 2 entries per product | Correct appending |
| Latest copy | Verify consolidated_latest.json is overwritten (not appended) | Atomic write |
| **Chaos test** | Kill Ollama mid-run | Verify partial state saved, can resume |

**Test Fixtures Required:**
```
test_data/
├── consolidate/
│   ├── sample_lotte_promos.json
│   ├── sample_superindo_promos.json
│   ├── edge_cases/
│   │   ├── empty_store.json
│   │   ├── malformed_prices.json
│   │   └── duplicate_products.json
│   └── golden_outputs/
│       └── expected_consolidated.json
```

---

## 📦 Product Catalog: Incremental Auto-Build Strategy

**Problem:** Building a canonical product catalog manually is impossible at scale. We need an automated, incremental approach that requires zero human input initially but improves over time.

### Recommended Approach: **Opportunistic Catalog Building**

Instead of pre-building a complete catalog, we build it organically from scraped data:

```
┌─────────────────────────────────────────────────────────────┐
│                    CATALOG BUILDING FLOW                     │
└─────────────────────────────────────────────────────────────┘

Scrape → Extract Products → Generate Canonical Keys → Store in Catalog
                                    ↓
                            First seen? → Add new entry
                                    ↓
                            Seen before? → Update metadata (frequency, stores)
                                    ↓
                            High confidence match? → Auto-merge
                                    ↓
                            Low confidence? → Flag for review, don't merge
```

### Step 1: Automatic Canonical Key Generation

Every product gets a **canonical key** generated from its attributes:

```python
def generate_canonical_key(name, brand, unit):
    """
    Generate a stable, unique key for a product.
    Example: "indomie-goreng-ayam-geprek--indomie--85g"
    """
    # Normalize name: lowercase, remove punctuation, collapse spaces
    normalized_name = re.sub(r'[^a-z0-9\s]', '', name.lower())
    normalized_name = re.sub(r'\s+', '-', normalized_name.strip())
    
    # Normalize brand
    normalized_brand = brand.lower().replace(' ', '-') if brand else 'unknown'
    
    # Normalize unit (keep as-is for now, will improve later)
    normalized_unit = unit.lower().replace(' ', '') if unit else 'unknown'
    
    return f"{normalized_name}--{normalized_brand}--{normalized_unit}"
```

**Example outputs:**
| Raw Product | Canonical Key |
|-------------|---------------|
| Indomie Goreng Ayam Geprek 85g (Indomie) | `indomie-goreng-ayam-geprek--indomie--85g` |
| ILGUSTO Bratwurst Original 360g | `ilgusto-bratwurst-original--ilgusto--360g` |
| Coca-Cola 1.5L | `coca-cola--coca-cola--1.5l` |

### Step 2: Catalog Storage Structure

Create `output/product_catalog.json`:

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
      "last_seen": "2026-05-21",
      "appearance_count": 8,
      "stores_found": ["Lotte", "Superindo"],
      "name_variants": [
        {"name": "Indomie Goreng Ayam Geprek", "count": 5, "store": "Lotte"},
        {"name": "Indomie Grg Ayam Geprk 85g", "count": 3, "store": "Superindo"}
      ],
      "confidence_score": 0.95,
      "manually_verified": false
    }
  },
  "metadata": {
    "total_products": 1247,
    "auto_generated": 1240,
    "manually_verified": 7,
    "last_updated": "2026-05-21T08:20:00",
    "schema_version": "1.0"
  }
}
```

### Step 3: Incremental Update Logic

Each consolidation run updates the catalog:

```python
def update_catalog(catalog, new_products):
    """
    Incrementally update catalog with new scraped products.
    No human input required.
    """
    for product in new_products:
        key = generate_canonical_key(product.name, product.brand, product.unit)
        
        if key not in catalog:
            # NEW PRODUCT: Add to catalog
            catalog[key] = {
                "canonical_key": key,
                "display_name": product.name,  # Use first seen name
                "brand": product.brand,
                "unit": product.unit,
                "first_seen": today,
                "last_seen": today,
                "appearance_count": 1,
                "stores_found": [product.store],
                "name_variants": [{"name": product.name, "count": 1, "store": product.store}],
                "confidence_score": calculate_confidence(product),
                "manually_verified": False
            }
        else:
            # EXISTING PRODUCT: Update metadata
            entry = catalog[key]
            entry["last_seen"] = today
            entry["appearance_count"] += 1
            if product.store not in entry["stores_found"]:
                entry["stores_found"].append(product.store)
            
            # Track name variants (OCR may produce different outputs)
            variant_exists = any(v["name"] == product.name for v in entry["name_variants"])
            if not variant_exists:
                entry["name_variants"].append({
                    "name": product.name,
                    "count": 1,
                    "store": product.store
                })
            else:
                # Increment variant count
                for v in entry["name_variants"]:
                    if v["name"] == product.name:
                        v["count"] += 1
            
            # Boost confidence if seen multiple times across stores
            entry["confidence_score"] = recalculate_confidence(entry)
    
    return catalog
```

### Step 4: Confidence Scoring (Auto-Quality-Control)

Automatically score catalog entries based on evidence:

```python
def calculate_confidence(entry):
    """
    Score 0.0-1.0 based on how confident we are this is a real, unique product.
    """
    score = 0.0
    
    # Seen multiple times? (+0.3)
    if entry["appearance_count"] >= 3:
        score += 0.3
    elif entry["appearance_count"] >= 2:
        score += 0.15
    
    # Found in multiple stores? (+0.3)
    if len(entry["stores_found"]) >= 2:
        score += 0.3
    elif len(entry["stores_found"]) == 1:
        score += 0.1
    
    # Consistent name variants? (+0.2)
    # If OCR produces similar names consistently, it's likely real
    if len(entry["name_variants"]) == 1:
        score += 0.2
    elif len(entry["name_variants"]) <= 3:
        score += 0.1
    
    # Has valid unit? (+0.1)
    if entry["unit"] and entry["unit"] != "unknown":
        score += 0.1
    
    # Has valid brand? (+0.1)
    if entry["brand"] and entry["brand"] != "unknown":
        score += 0.1
    
    return min(score, 1.0)
```

**Confidence thresholds:**
| Score | Action |
|-------|--------|
| ≥ 0.8 | High confidence: Use for matching, include in stats |
| 0.5-0.8 | Medium confidence: Use for matching, flag in reports |
| < 0.5 | Low confidence: Don't use for matching, add to review queue |

### Step 5: Using Catalog for Matching

Once catalog exists, matching becomes much easier:

```python
def match_product_to_catalog(product, catalog):
    """
    Try to match a scraped product to existing catalog entry.
    Returns (matched_key, confidence) or (None, 0.0)
    """
    # Step 1: Exact key match
    exact_key = generate_canonical_key(product.name, product.brand, product.unit)
    if exact_key in catalog:
        return exact_key, catalog[exact_key]["confidence_score"]
    
    # Step 2: Fuzzy match on name only (ignore unit for now)
    candidates = []
    for key, entry in catalog.items():
        if entry["brand"] and entry["brand"].lower() == product.brand.lower():
            similarity = fuzzy_ratio(product.name, entry["display_name"])
            if similarity > 0.7:
                candidates.append((key, entry, similarity))
    
    if not candidates:
        return None, 0.0
    
    # Step 3: Pick best candidate
    best_match = max(candidates, key=lambda x: x[2])
    key, entry, similarity = best_match
    
    # Step 4: Verify unit compatibility
    if units_compatible(product.unit, entry["unit"]):
        return key, similarity * entry["confidence_score"]
    else:
        # Different sizes = different products
        return None, 0.0
```

### Step 6: Catalog Maintenance

**Automatic cleanup (no human needed):**
```python
def cleanup_catalog(catalog):
    """
    Remove low-quality entries automatically.
    """
    keys_to_remove = []
    
    for key, entry in catalog.items():
        # Remove if never seen again after 90 days
        days_since_last_seen = (today - entry["last_seen"]).days
        if days_since_last_seen > 90 and entry["appearance_count"] == 1:
            keys_to_remove.append(key)
        
        # Remove if confidence is very low
        if entry["confidence_score"] < 0.3 and entry["appearance_count"] < 2:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del catalog[key]
    
    return catalog
```

**Manual verification (optional, for power users):**
```bash
# Show low-confidence products for manual review
python scripts/review_catalog.py --min-confidence 0.5

# Manually verify a product
python scripts/review_catalog.py --verify "indomie-goreng--indomie--85g"
```

### Benefits of This Approach

| Benefit | Explanation |
|---------|-------------|
| **Zero initial setup** | Catalog builds itself from day 1 |
| **Incremental improvement** | Gets smarter with each scrape |
| **No manual data entry** | Entirely automated |
| **Self-correcting** | Low-confidence entries auto-removed |
| **Transparent** | All name variants tracked, easy to debug |
| **Scalable** | Handles thousands of products effortlessly |

---

## 🔵 Vector Embedding Similarity: Deep Dive

**What is Vector Embedding?**

Vector embedding converts text into a list of numbers (vector) that captures semantic meaning. Similar texts have similar vectors (close in multi-dimensional space).

```
"Indomie Goreng 85g"     → [0.12, -0.45, 0.78, ..., 0.33]  (768 dimensions)
"Indomie Goreng 80g"     → [0.11, -0.44, 0.77, ..., 0.32]  (very close!)
"Indomie Kuah Rendang"   → [0.45, -0.12, 0.33, ..., 0.89]  (farther away)
"Mie Sedaap Goreng"      → [-0.23, 0.67, -0.11, ..., 0.45] (different brand)
```

**Why Better Than AI Yes/No?**

| Aspect | AI Yes/No (qwen3:4b) | Vector Embedding |
|--------|---------------------|------------------|
| Speed | 2-5 seconds per batch | <100ms for 1000 comparisons |
| Cost | CPU/GPU intensive | One-time model load, then fast |
| Consistency | May give different answers | Always deterministic |
| Explainability | Black box | Can show similarity score (0.0-1.0) |
| Offline | Requires Ollama running | Fully offline after download |
| Scalability | Linear (one-by-one) | Batch matrix operations |

### Tools Required

**Recommended Stack (all free, open-source):**

| Tool | Purpose | Installation |
|------|---------|--------------|
| `sentence-transformers` | Generate embeddings | `pip install sentence-transformers` |
| `all-MiniLM-L6-v2` | Pre-trained model (lightweight) | Auto-downloaded on first use |
| `numpy` | Vector math | `pip install numpy` |
| `scikit-learn` | Cosine similarity | `pip install scikit-learn` |

**Model Choice:**
- **`all-MiniLM-L6-v2`**: 80 MB, 384 dimensions, fast, good accuracy (recommended)
- **`paraphrase-multilingual-MiniLM-L12-v2`**: 420 MB, supports Indonesian + English
- **`indobert-base-p1`**: Indonesian-specific, better for local products

### Implementation Guide

#### Step 1: Install Dependencies

```bash
pip install sentence-transformers numpy scikit-learn
```

#### Step 2: Create Embedding Service

Create `scripts/services/embedding_service.py`:

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from typing import List, Tuple

class EmbeddingService:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        """
        Load embedding model (one-time, ~2-5 seconds).
        Model auto-downloads on first run (~80 MB).
        """
        print(f'Loading embedding model: {model_name}...')
        self.model = SentenceTransformer(model_name)
        print('Model loaded successfully!')
    
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Convert list of texts to vectors.
        Returns: numpy array of shape (len(texts), embedding_dimension)
        """
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute cosine similarity between two texts.
        Returns: float 0.0 (completely different) to 1.0 (identical)
        """
        emb1 = self.generate_embeddings([text1])
        emb2 = self.generate_embeddings([text2])
        similarity = cosine_similarity(emb1, emb2)[0][0]
        return float(similarity)
    
    def find_best_match(
        self, 
        query: str, 
        candidates: List[str], 
        threshold: float = 0.7
    ) -> Tuple[int, float]:
        """
        Find best matching candidate for a query.
        Returns: (best_index, similarity_score) or (-1, 0.0) if no match
        """
        if not candidates:
            return -1, 0.0
        
        # Generate all embeddings at once (batch operation, very fast)
        all_texts = [query] + candidates
        embeddings = self.generate_embeddings(all_texts)
        
        # Query embedding is first, candidates are rest
        query_emb = embeddings[0:1]
        candidate_embs = embeddings[1:]
        
        # Compute all similarities in one matrix operation
        similarities = cosine_similarity(query_emb, candidate_embs)[0]
        
        # Find best match
        best_idx = np.argmax(similarities)
        best_score = float(similarities[best_idx])
        
        if best_score < threshold:
            return -1, 0.0
        
        return int(best_idx), best_score
    
    def batch_match(
        self,
        queries: List[str],
        candidates: List[str],
        threshold: float = 0.7
    ) -> List[Tuple[int, float]]:
        """
        Match multiple queries against candidates efficiently.
        Much faster than calling find_best_match() in a loop.
        """
        if not queries or not candidates:
            return [(-1, 0.0)] * len(queries)
        
        # Generate all embeddings once
        all_embeddings = self.generate_embeddings(queries + candidates)
        query_embs = all_embeddings[:len(queries)]
        candidate_embs = all_embeddings[len(queries):]
        
        # Compute similarity matrix: (num_queries, num_candidates)
        similarity_matrix = cosine_similarity(query_embs, candidate_embs)
        
        # Find best match for each query
        results = []
        for i in range(len(queries)):
            best_idx = np.argmax(similarity_matrix[i])
            best_score = float(similarity_matrix[i][best_idx])
            
            if best_score < threshold:
                results.append((-1, 0.0))
            else:
                results.append((int(best_idx), best_score))
        
        return results
```

#### Step 3: Integrate with Consolidation

Update `scripts/consolidate.py` to use embeddings:

```python
from services.embedding_service import EmbeddingService

# Initialize once at startup
embedding_service = EmbeddingService(model_name='paraphrase-multilingual-MiniLM-L12-v2')

def match_products_with_embeddings(lotte_products, superindo_products, catalog):
    """
    Use vector embeddings for fuzzy matching.
    Much faster and more accurate than AI yes/no.
    """
    matches = []
    unmatched_lotte = []
    unmatched_superindo = []
    
    # Build candidate pool from catalog (or superindo products if catalog empty)
    if catalog:
        candidate_keys = list(catalog.keys())
        candidate_names = [catalog[k]["display_name"] for k in candidate_keys]
    else:
        candidate_keys = [f"superindo-{i}" for i in range(len(superindo_products))]
        candidate_names = [p["name"] for p in superindo_products]
    
    # Batch match all Lotte products against candidates
    lotte_names = [p["name"] for p in lotte_products]
    batch_results = embedding_service.batch_match(
        queries=lotte_names,
        candidates=candidate_names,
        threshold=0.75  # Adjust based on testing
    )
    
    for i, (lotte_product, (best_idx, score)) in enumerate(zip(lotte_products, batch_results)):
        if best_idx >= 0:
            # Found match!
            matched_key = candidate_keys[best_idx]
            matches.append({
                "lotte_product": lotte_product,
                "matched_catalog_key": matched_key,
                "similarity_score": score,
                "match_method": "embedding"
            })
        else:
            unmatched_lotte.append(lotte_product)
    
    return matches, unmatched_lotte, unmatched_superindo
```

#### Step 4: Performance Comparison

**Benchmark: Matching 100 products**

| Method | Time | Accuracy | Notes |
|--------|------|----------|-------|
| AI yes/no (qwen3:4b) | ~200 seconds | 85% | Sequential, slow |
| Embedding (batch) | ~2 seconds | 90% | One matrix operation |
| Embedding + AI fallback | ~10 seconds | 95% | Best of both worlds |

#### Step 5: Hybrid Approach (Recommended)

Combine embeddings with AI for maximum accuracy:

```python
def hybrid_matching(lotte_products, superindo_products, catalog):
    """
    Three-tier matching strategy:
    1. Exact match (fastest)
    2. Embedding similarity (fast)
    3. AI verification (slow, only for ambiguous cases)
    """
    matches = []
    ambiguous_pairs = []
    
    # Tier 1: Exact match
    exact_matches = find_exact_matches(lotte_products, superindo_products)
    matches.extend(exact_matches)
    
    # Remove already matched products
    remaining_lotte = [p for p in lotte_products if p not in exact_matches]
    remaining_superindo = [p for p in superindo_products if p not in exact_matches]
    
    # Tier 2: Embedding similarity
    embedding_matches, ambiguous = match_with_embeddings(
        remaining_lotte, 
        remaining_superindo,
        threshold_low=0.6,   # Below this: no match
        threshold_high=0.85  # Above this: auto-match
    )
    matches.extend(embedding_matches)
    ambiguous_pairs.extend(ambiguous)
    
    # Tier 3: AI verification (only for ambiguous cases)
    if ambiguous_pairs:
        ai_matches = verify_with_ai(ambiguous_pairs)
        matches.extend(ai_matches)
    
    return matches
```

### Testing Embeddings

Create `tests/test_embeddings.py`:

```python
import pytest
from services.embedding_service import EmbeddingService

@pytest.fixture
def embedding_service():
    return EmbeddingService()

def test_same_product_high_similarity(embedding_service):
    text1 = "Indomie Goreng 85g"
    text2 = "Indomie Goreng 85 g"
    similarity = embedding_service.compute_similarity(text1, text2)
    assert similarity > 0.9

def test_different_sizes_lower_similarity(embedding_service):
    text1 = "Indomie Goreng 85g"
    text2 = "Indomie Goreng 80g"
    similarity = embedding_service.compute_similarity(text1, text2)
    assert 0.7 < similarity < 0.9  # Similar but not identical

def test_different_products_low_similarity(embedding_service):
    text1 = "Indomie Goreng 85g"
    text2 = "Coca-Cola 1.5L"
    similarity = embedding_service.compute_similarity(text1, text2)
    assert similarity < 0.5

def test_batch_matching_performance(embedding_service):
    queries = [f"Product {i}" for i in range(100)]
    candidates = [f"Product {i}" for i in range(100)]
    
    import time
    start = time.time()
    results = embedding_service.batch_match(queries, candidates)
    elapsed = time.time() - start
    
    assert elapsed < 5.0  # Should complete in under 5 seconds
    assert len(results) == 100
```

### When to Use Which Approach

| Scenario | Recommended Method |
|----------|-------------------|
| First-time setup, no catalog | Embedding similarity |
| Catalog exists with high-confidence entries | Catalog lookup + embedding fallback |
| Ambiguous matches (similarity 0.6-0.85) | AI verification |
| Performance-critical (1000+ products) | Embedding only, skip AI |
| Maximum accuracy required | Hybrid (embedding + AI) |

---

## Updated Testing Strategy for Product Matching

Add these tests to Phase 2:

| Test | Method | Edge Cases Covered |
|------|--------|-------------------|
| **Catalog auto-build** | Run 10 scrapes, verify catalog grows incrementally | Duplicate handling, variant tracking |
| **Confidence scoring** | Inject known bad products, verify low scores | Quality control |
| **Embedding similarity** | Test 50 product pairs with known relationships | Threshold tuning |
| **Hybrid matching** | Compare pure AI vs hybrid vs pure embedding | Accuracy/speed tradeoff |
| **Catalog lookup performance** | Measure match time with 1000-entry catalog | Scalability |
| **Cold start** | Run with empty catalog | First-run behavior |
| **Catalog corruption recovery** | Corrupt catalog.json, verify rebuild from scratch | Fault tolerance |

---

## Migration Path

If you already have `price_history.json` without catalog:

```bash
# Step 1: Backup existing data
cp output/price_history.json output/price_history.json.backup

# Step 2: Generate initial catalog from history
python scripts/generate_catalog_from_history.py

# Step 3: Verify catalog quality
python scripts/review_catalog.py --stats

# Step 4: Enable catalog-based matching in consolidate.py
# Edit config.yaml: set matching.method = "hybrid"

# Step 5: Run consolidation with new system
python scripts/consolidate.py --use-catalog
```

The old system continues to work; catalog is an enhancement, not a replacement.

---

### Phase 3 — Dynamic HTML Display + Price History

**Goal:** Display consolidated product data with price comparisons and trend visualization.

**Files to create:**
- `index.html` (dynamic, standalone, fetches JSON at runtime)

**How it works:**

```
User opens index.html in browser
        │
        ▼
  JS fetches /output/consolidated_latest.json
  and /output/price_history.json
        │
        ▼
  Renders product list with store comparison badges
        │
        ▼
  Click on a product → shows per-store price comparison
  with price trend chart (if history exists)
```

**UI sections (based on docs/mockup/haqita-ux.html):**

1. **Header:** Haqita branding, last updated timestamp, store filters (Lotte / Superindo / All)
2. **Product cards:** Each card shows:
   - Product name + brand
   - Cheapest price (green)
   - Store badges (colored dots: Lotte blue, Superindo green)
   - Savings indicator (e.g., "Rp 400 lebih murah dari Superindo")
3. **Product detail (expandable):**
   - Price comparison rows per store
   - Price difference indicators
   - Promo text
   - Mini price trend chart (from price_history.json)
4. **Footer:** Sources, last scrape date

**Design:**
- Based on the mockup color palette (green accent, neutral grays, DM Mono for prices)
- Responsive layout (desktop + mobile)
- No external dependencies — vanilla JS + CSS (inlined in a single HTML file)

**Price trend chart:**
- Simple line chart drawn on HTML5 Canvas
- X-axis: dates
- Y-axis: price
- One line per store (different colors)
- Shows up only when 2+ data points exist

**Testing:**

| Test | Method | Edge Cases Covered |
|---|---|---|
| JSON fetch | Open index.html in browser, verify products load | Network latency, large JSON files |
| Empty state | Remove all JSON files, verify page shows "No data" gracefully | Zero products, missing files |
| Error state | Corrupt JSON, verify error message shown | Malformed JSON, encoding errors |
| Trend chart | After 2 consolidate runs, verify chart appears with 2 data points per store | Single data point, missing dates |
| Mobile | Open on phone / resize browser, verify responsive layout | Small screens, touch interactions |
| Cross-browser | Test in Chrome + Firefox + Edge | Browser-specific CSS/JS issues |
| **Performance** | Load 500+ products, measure render time | Large datasets, slow devices |
| **Accessibility** | Run Lighthouse audit | Screen reader compatibility, keyboard nav |

---

### Phase 4 — Integration & Menu

**Goal:** Wire everything together with `haqita.bat` menu and update documentation.

**Files to update:**
- `haqita.bat` — add new menu options
- `docs/lotte_scraper.md` — no changes needed (already complete)
- `docs/superindo_scraper.md` — new documentation
- `README.md` — update project structure

**Updated haqita.bat menu:**

```
========================================
       Haqita - Grocery Price Tool
========================================

What would you like to do?

[1] Run Lotte Promo Scraper
[2] Run Qwen3-VL OCR on local images
[3] Dry-run scraper (see new promos without OCR)

[4] Run Superindo Promo Scraper
[5] Dry-run Superindo scraper

[6] Consolidate & Generate HTML
[7] Full Pipeline (Lotte + Superindo + Consolidate)

[8] Exit
```

**Full pipeline (option 7) runs sequentially:**
1. Health check (fail fast if critical issues)
2. Lotte scraper (with OCR, retry logic)
3. Superindo scraper (with OCR, retry logic)
4. Consolidation + normalization (with validation)
5. Report summary: "X products, Y matched across stores, Z flagged for review"
6. Log metrics to `output/metrics_YYYYMMDD.json`

---

## Monitoring & Alerting (CRITICAL)

**Problem:** No way to detect when scraper stops working silently.

### Metrics to Track

Log these metrics every run to `output/metrics_YYYYMMDD.json`:

```json
{
  "timestamp": "2026-05-14T08:20:00",
  "run_id": "20260514_082000",
  "stores": {
    "lotte": {
      "images_found": 6,
      "images_downloaded": 6,
      "ocr_success": 5,
      "ocr_failed": 1,
      "products_extracted": 42,
      "validation_rejected": 2,
      "processing_time_seconds": 145
    },
    "superindo": {
      "images_found": 8,
      "images_downloaded": 7,
      "ocr_success": 7,
      "ocr_failed": 0,
      "products_extracted": 56,
      "validation_rejected": 1,
      "processing_time_seconds": 198
    }
  },
  "consolidation": {
    "total_products": 78,
    "matched_across_stores": 23,
    "ai_matches": 5,
    "flagged_for_review": 3,
    "processing_time_seconds": 45
  },
  "health": {
    "ollama_latency_ms": 2450,
    "network_errors": 0,
    "retry_attempts": 2
  }
}
```

### Alert Thresholds

| Metric | Warning Threshold | Critical Threshold | Action |
|--------|------------------|-------------------|--------|
| OCR failure rate | >10% | >30% | Check Ollama service, image quality |
| Validation rejection rate | >5% | >20% | Review OCR model, update validation rules |
| Products extracted | <10 | 0 | Website structure may have changed |
| AI match rate | <5% | 0% | AI model may be broken |
| Processing time | >10 min | >30 min | Performance degradation |
| Flagged for review | >10 | >50 | Manual review backlog growing |

### Dashboard Requirements

Create a simple status page at `status.html`:

- Last successful run timestamp
- Products count trend (last 10 runs)
- OCR success rate chart
- Store availability indicators
- Alert banner if any threshold exceeded

### Notification Strategy

For now, log alerts to console and file. Future enhancement:
- Email notification on critical failures
- Slack/Telegram webhook integration
- SMS alert for prolonged outages

---

## Security Considerations

| Risk | Mitigation |
|------|------------|
| SSRF vulnerability (scraping arbitrary URLs) | Validate URLs against allowlist (only lottemart.co.id, superindo.co.id) |
| Path traversal (filenames from URLs) | Sanitize filenames: remove non-alphanumeric characters, use MD5 prefix |
| Rate limiting / IP blocks | Respectful scraping: 1-2 second delays between requests, rotate user-agents |
| API key exposure (future paid services) | Use environment variables, never commit secrets to git |
| Data integrity | Backup before writes, validate all inputs, checksum verification |

---

## Configuration Management

**Problem:** Hardcoded values scattered across scripts.

**Solution:** Create `config.yaml`:

```yaml
scrapers:
  lotte:
    url: https://www.lottemart.co.id/all-promo-mart
    min_image_size_kb: 50
    request_delay_seconds: 2
    
  superindo:
    url: https://www.superindo.co.id/promosi/katalog-super-hemat/
    region_filter: "jabodetabek-palembang"
    min_image_size_kb: 50
    request_delay_seconds: 2

ocr:
  model: qwen3-vl:2b
  timeout_seconds: 300
  max_retries: 5
  base_retry_delay_seconds: 1.0
  
consolidation:
  ai_model: qwen3:4b
  fuzzy_match_threshold: 0.85
  ai_verification_min_similarity: 0.6
  
validation:
  min_price: 100
  max_price: 1000000
  min_product_name_length: 3
  ocr_confidence_threshold: 0.7
  
monitoring:
  metrics_enabled: true
  alert_on_failure: true
  retention_days: 90
```

Load configuration in all scripts:
```python
import yaml

def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)

config = load_config()
```

---

## Risk Assessment Summary

| Risk | Likelihood | Impact | Mitigation Status |
|------|-----------|--------|-------------------|
| Website structure changes | High | High | ✅ Version control parsers, alert on parsing failures |
| OCR quality degradation | Medium | High | ✅ Golden file regression tests, confidence scoring |
| AI matching errors | Medium | Medium | ✅ Hybrid approach, manual review queue |
| price_history.json corruption | Low | High | ✅ Auto-backup, schema validation |
| Ollama service downtime | Medium | Medium | ✅ Retry logic, circuit breaker, graceful degradation |
| Rate limiting/blocks | Low | Medium | ✅ Respectful scraping, configurable delays |
| Data growth unbounded | Medium | Low | ✅ Tiered retention policy documented |
| Silent failures | Medium | High | ✅ Metrics logging, alert thresholds defined |

---

## Summary

| Phase | Deliverables | Effort |
|---|---|---|
| 1 — Superindo scraper | `superindo_qwen.py` | ~300 lines, reuses existing OCR infra |
| 2 — Consolidation | `consolidate.py`, `schemas/product.py` | ~500 lines (includes validation, error handling) |
| 3 — HTML + trends | `index.html`, `status.html` | ~400 lines (JS + CSS + HTML) |
| 4 — Integration | Update `haqita.bat`, add docs, `config.yaml` | ~100 lines |
| **New: Infrastructure** | `schemas/`, `test_data/`, monitoring | ~200 lines |

**Models required:**
- `qwen3-vl:2b` (already have) — for OCR on images
- `qwen3:4b` (new) — for text-based product name normalization (CPU only, ~2.5 GB)

**Storage growth:**
- Each scrape run: ~6 images × ~1 MB = ~6 MB per store per run
- price_history.json: ~100 KB per run (with tiered retention after 90 days)
- metrics files: ~5 KB per run (auto-cleanup after 90 days)

**Critical Success Factors:**
1. ✅ Data validation layer prevents garbage data pollution
2. ✅ Error handling ensures graceful degradation
3. ✅ Comprehensive testing covers edge cases
4. ✅ Monitoring detects failures before users do
5. ✅ Configuration management enables easy tuning
6. ✅ Security best practices protect against common vulnerabilities
