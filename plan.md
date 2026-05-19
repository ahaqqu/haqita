# Plan: Propagate `promo` from array to UI & database

## Problem

Gemini prompt (`gemini.py:9`) specifies `promo` as a JSON array, e.g. `["DISKON 20%", "MAX 1"]`. But `validate_product()` (`ocr_processor.py:80`) calls `str()` on it, producing `"['DISKON 20%', 'MAX 1']"` — a corrupted Python list literal — which is stored in the database and displayed ugly in the UI.

## Goal

`promo` is stored as a JSON array everywhere (`list[str] | null`), and displayed cleanly in the UI.

---

## Changes (8 files)

### 1. `scripts/ocr/ocr_processor.py` — Entry normalizer

Add a helper and use it in `validate_product()`.

```python
def _normalize_promo(promo) -> list[str] | None:
    if not promo:
        return None
    if isinstance(promo, list):
        return [str(p).strip() for p in promo if str(p).strip()]
    return [str(promo).strip()]
```

Replace line 80:
```python
# old
'promo': str(raw['promo']).strip() if raw.get('promo') else None,
# new
'promo': _normalize_promo(raw.get('promo')),
```

---

### 2. `scripts/matching/promo_parser.py` — Accept list input

**Signature change:**
```python
# old
def parse_promo(promo_text: str | None, base_price: int) -> PromoResult:
# new
def parse_promo(promo_text: str | list[str] | None, base_price: int) -> PromoResult:
```

**Logic changes:**
- Normalize input to `list[str]`
- Iterate each promo string, try all regex patterns
- Pick the result with the **lowest `effective_unit_price`** (best deal for customer)
- Join all promo texts with `"; "` for the `display` field
- If no pattern matches any item, fallback to `promo_type='single'` with joined display

---

### 3. `scripts/matching/consolidation.py` — List-aware aggregation

- `build_store_entry()`: change `promo: str = None` → `promo: list[str] = None`
- `build_single_product()`: change `promo: str = None` → `promo: list[str] = None`
- `build_promo_summary()` line 59-61: change to join list items:

```python
# old
has_promo = any(s["promo"] for s in store_entries)
promo_parts = [f"{s['promo']} di {s['store']}" for s in store_entries if s["promo"]]
# new
has_promo = any(s["promo"] for s in store_entries)
promo_parts = [
    f"{'; '.join(s['promo'])} di {s['store']}"
    for s in store_entries if s["promo"]
]
```

- `generate_consolidated_from_history()`: normalize promo when reading from `price_history.json` (old data may be string). Add helper:

```python
def _normalize_promo(v):
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    # Handle old stringified Python list: "['A', 'B']" or plain string
    s = str(v).strip()
    if s.startswith('[') and s.endswith(']'):
        import ast
        try:
            items = ast.literal_eval(s)
            return [str(x).strip() for x in items if str(x).strip()]
        except:
            pass
    return [s]
```

Call it on each `snap.get("promo")` at lines 211 and 242.

---

### 4. `scripts/consolidate.py` — Pass-through (no logic change needed)

- All `p.get('promo')` references (lines 260, 342, 353, 391, 413, 471, 486) now naturally return a list from the normalized OCR data
- `build_store_entry()` / `build_single_product()` accept `list[str]`
- History snapshots (lines 471, 486) serialize to JSON array automatically via `json.dump`

No code changes needed here (assuming the type changes in consolidation.py are compatible).

---

### 5. `scripts/ocr/ollama_client.py` — Prompt consistency

Update the Ollama `PROMPT_CONVERT` example (line 45-46) and instruction (line 54):

```python
# old
'{"brand": "AICE", "name": "Sandwich Cookies Panda", "price": 39900, "unit": "6 x 45 ml", "promo": "BUY 1 GET 1"}'
"- promo: Promo text (e.g., ...). Set to null if none."

# new
'{"brand": "AICE", "name": "Sandwich Cookies Panda", "price": 39900, "unit": "6 x 45 ml", "promo": ["BUY 1 GET 1"]}'
"- promo: Array of promo texts. Set to null if none."
```

Also update `RETRY_CORRECTION` line 59.

---

### 6. `index.html` — UI rendering

**`buildStoreRows()` (~line 785):**
```javascript
// old
const promoText = s.promo ? ` (${s.promo})` : "";
// new
const promoText = s.promo && s.promo.length ? ` (${s.promo.join(', ')})` : "";
```

**`buildSingleCard()` (~line 839):**
```javascript
// old
const promoLabel = hasPromo && s.promo ? s.promo : (product.promo_label || "");
const promoColorClass = promoLabel.toLowerCase().includes("diskon") ? "promo-red" : "promo-green";
// new
const promoText = hasPromo && s.promo && s.promo.length ? s.promo.join(', ') : (product.promo_label || "");
const promoColorClass = promoText.toLowerCase().includes("diskon") ? "promo-red" : "promo-green";
```

Also adjust the variable used in the template literal (line 842):
```javascript
// old
const promoBadge = promoLabel ? ... : "";
// new
const promoBadge = promoText ? ... : "";
```

---

### 7. `scripts/ocr/prompts/gemini.py` — No change

Already specifies `promo` as an array (line 9). No action needed.

---

### 8. `scripts/publish_html.py` — No change

Passes data through unchanged. No action needed.

---

### 9. `tests/ocr/test_ocr_validation.py` — Update test data

- `test_promo_preserved` (line 68, 71):
  ```python
  # old
  raw = {"name": "Item", "promo": "DAPAT 2 pcs", "price": 10000}
  assert result["promo"] == "DAPAT 2 pcs"
  # new
  raw = {"name": "Item", "promo": ["DAPAT 2 pcs"], "price": 10000}
  assert result["promo"] == ["DAPAT 2 pcs"]
  ```

- `test_valid_product` (line 16): change `"promo": "DAPAT 5 pcs"` → `"promo": ["DAPAT 5 pcs"]`

---

## Data Migration (existing `price_history.json`)

The database has mixed formats:
- `"DISKON 20%"` (plain string)
- `"['DISKON 20%', 'MAX 1']"` (stringified Python list)

Read-time normalization in `generate_consolidated_from_history()` (item 3 above) handles both. **One-time migration script is optional** but recommended for cleanliness:

```python
# scripts/migrate_promo_to_array.py
# Reads price_history.json, converts all promo values to arrays, writes back.
```

---

# Issue 2: Stop OCR on daily quota exhausted (don't retry)

## Problem

When Gemini daily quota is hit (429 RESOURCE_EXHAUSTED with quotaId `GenerateRequestsPerDayPerProjectPerModel-FreeTier`), `call_gemini_ocr()` retries 3 times with delays (55s, 60s, 59s) before failing. Then `run_ocr.py` catches the error and moves to the next image — which will also fail 3 times. All remaining images waste ~3 minutes each failing.

## Goal

Detect daily quota errors immediately, log once, stop OCR for all remaining images. Already OCR'd images continue to next stage.

---

## Changes (3 files)

### 1. `scripts/ocr/gemini_client.py` — Detect quota vs rate limit, add custom exception

Add a custom exception at the top:

```python
class QuotaExhaustedError(Exception):
    """Daily quota exhausted — stop all OCR processing."""
```

In `call_gemini_ocr()` (~line 60), differentiate between **rate limit** (transient, retry) and **daily quota** (permanent until reset):

```python
# old
if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate limit" in err_str.lower():
    parsed_delay = parse_retry_delay(err_str)
    wait_time = parsed_delay if parsed_delay else 60
    ...retry logic...

# new
if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate limit" in err_str.lower():
    # Check for daily quota vs rate limit
    if "quota" in err_str.lower() and ("per day" in err_str.lower() or "daily" in err_str.lower() or "PerDay" in err_str):
        raise QuotaExhaustedError(f"Daily quota exhausted: {err_str[:200]}")
    parsed_delay = parse_retry_delay(err_str)
    wait_time = parsed_delay if parsed_delay else 60
    ...existing retry logic...
```

**Heuristic**: If the error mentions both "quota" and daily-related keywords, it's a daily quota (not worth retrying). Otherwise treat as rate limit (retry with backoff).

---

### 2. `scripts/ocr/ocr_processor.py` — Let `QuotaExhaustedError` propagate

In `extract_products()` (~line 19-25), the `except` clause currently catches `(json.JSONDecodeError, ValueError)`. `QuotaExhaustedError` is neither, so it will propagate automatically. **No change needed** unless there's a generic `Exception` catch — there isn't. Verified: only catches specific exceptions.

---

### 3. `scripts/ocr/run_ocr.py` — Catch quota error and break

In `run_ocr()` (~line 152), import `QuotaExhaustedError`. Add a specific catch before the generic `Exception` handler:

```python
# old
try:
    products_raw = extract_products(processed, cfg)
    ...
except Exception as e:
    print(f"    [ERR] OCR failed: {e}")
    continue

# new
try:
    products_raw = extract_products(processed, cfg)
    ...
except QuotaExhaustedError as e:
    print(f"    [ERR] Gemini daily quota exhausted. Stopping OCR for remaining images.")
    print(f"    {e}")
    all_rejected.append({
        "raw": {"image": img_path.name, "error": str(e)},
        "reason": "daily_quota_exhausted",
    })
    break
except Exception as e:
    print(f"    [ERR] OCR failed: {e}")
    continue
```

Also add the import at the top of `run_ocr.py`:

```python
from scripts.ocr.gemini_client import QuotaExhaustedError
```

**Behavior:**
- Quota hit on image N → log error, mark that image as rejected with reason `daily_quota_exhausted`
- `break` out of the processing loop — remaining N+1...M images are skipped
- Already-processed images (1..N-1) are in `all_products` and `processed_filenames` → saved to output file and state → continue to next stage normally
- Output file and state are still saved, so next run will skip already-OCR'd images

---

## Summary (Issue 2)

| File | Action |
|------|--------|
| `gemini_client.py` | Add `QuotaExhaustedError`, detect daily quota vs rate limit |
| `ocr_processor.py` | No change (exception propagates automatically) |
| `run_ocr.py` | Catch `QuotaExhaustedError`, break processing loop |

---

## Combined Summary (All Issues)

| File | Issue 1 (promo array) | Issue 2 (quota stop) |
|------|-----------------------|----------------------|
| `ocr_processor.py` | Add `_normalize_promo()`, apply in `validate_product()` | No change |
| `promo_parser.py` | Accept `str\|list\|None`, iterate for best match | — |
| `consolidation.py` | Update type hints, fix `build_promo_summary`, add read-time normalization | — |
| `consolidate.py` | Pass-through (no change) | — |
| `ollama_client.py` | Update prompt to request array | — |
| `index.html` | Join array for inline/badge display | — |
| `gemini.py` | No change | — |
| `publish_html.py` | No change | — |
| `test_ocr_validation.py` | Update fixtures to use arrays | — |
| `gemini_client.py` | — | Add `QuotaExhaustedError`, detect daily quota vs rate limit |
| `run_ocr.py` | — | Catch `QuotaExhaustedError`, break processing loop |
