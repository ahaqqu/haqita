# Haqita Code Audit — Phase 1 & 2 Implementation

**Date:** May 16, 2026
**Auditor:** opencode (AI-assisted review)
**Scope:** implementation-v2.md + implementation-phase2.md vs actual codebase

---

## Verification of Previous Audit

The original `docs/audit.md` was reviewed for accuracy against the actual codebase:

| Previous Claim | Verdict | Notes |
|---|---|---|
| "Matcher bug at matcher.py:383-391 — idx_b out of scope" | **Partially correct** | The actual dead code is `if idx_b in matched_b_indices: pass` at `matcher.py:390-391`. `idx_b` is the last inner-loop value, not necessarily the matched index. Harmless (does nothing), but signals a design gap. The cited line numbers/code didn't match actual code. |
| "Inconsistent Product Key Generation" | **Valid** | `consolidate.py:304` uses Lotte product name only. OCR spelling differences between stores could produce different keys for the same product. |
| "Path Mismatch Between Docs and Code" | **Partially inaccurate** | Phase2 docs and code consistently use `output/consolidation/`. The v2 docs used `output/`. The real path issue is worse (see orphaned directories below). |
| "Hardcoded Fallback in Price History" | **Invalid** | `append_to_price_history(history, history_snapshots, today)` is correctly typed: `history: dict`, `products: list[dict]`. Not a bug. |
| "Missing Review Queue Visibility" | **Outdated** | `consolidate.py:572` now prints `Review queue: {len(review_data)}` in the summary. |
| "No clear feedback when OCR fails" | **Partially valid** | Errors are caught, but user gets minimal info on *why* (Ollama not running? bad image? API key missing?). |

**Previous audit accuracy: ~60%.** It catches some real issues but misses critical bugs and contains outdated/false claims.

---

## What Works Well

1. **All 100 tests pass** with zero failures
2. **Docker support complete**: Dockerfile, docker-compose.yml, requirements.txt, .dockerignore all present
3. **Feature flags for each gate** (`gate0`-`gate6`) are properly implemented, tested, and individually toggleable
4. **All 7 matching gates implemented**: unit type, brand, token Jaccard, exact match, embedding, price plausibility, AI verifier
5. **Atomic write pattern** prevents corrupt JSON if process is killed mid-write
6. **Good separation of concerns** — each matching gate is an isolated, testable function
7. **Logging** is informative and user-friendly (progress, gate results, timing)
8. **`units_value_compatible`** implementation is cleaner than the v2 docs

---

## 🔴 Critical Issues

### 1. Gate 6 AI Verifier — Indentation Bug (`matcher.py:416-430`)

The removal loop `for i in reversed(to_remove)` is **inside** the `for i, result in enumerate(ai_results)` loop instead of after it:

```python
for i, result in enumerate(ai_results):
    if result == 'NO':
        to_remove.append(i)
    elif result is None:
        review_items.append({
            'product_a': ambiguous_pairs[i],
            'product_b': ambiguous_pairs[i],  # Both point to SAME object
            'reason': 'ai_verifier_unexpected',
        })
    for i in reversed(to_remove):           # ← WRONG: runs on EVERY iteration
        removed = matched_pairs.pop(i)       # pops stale indices
```

When AI returns multiple "NO" responses, this causes index-out-of-range or removes wrong items from `matched_pairs`. Also `product_a` and `product_b` reference the same `ambiguous_pairs[i]` dict.

**Fix:** Move the `for i in reversed(to_remove)` block outside (after) the enumeration loop.

### 2. Lotte Scraper Ignores OCR Provider (`lotte.py:110`)

```python
from scripts.ocr.ollama_client import call_ollama_ocr, extract_promo_date  # Always Ollama!
...
products_raw = call_ollama_ocr(str(processed_path), self.cfg)
```

The Superindo scraper correctly uses `extract_products()` from `ocr_processor.py` which routes to the configured provider (Ollama or Gemini). But `lotte.py` **always calls Ollama directly**, even when `OCR_PROVIDER=gemini` is set.

**Impact:** A user configuring Gemini via `.env` will see Superindo OCR succeed and Lotte OCR fail with "Ollama not running".

### 3. Pipeline Double-OCR — Wastes API Quota & Time

The `haqita.bat` pipeline runs scrapers (which internally OCR images) THEN runs `run_ocr.py` (which OCRs the same images again):

```
Stage 1: Scrape
  lotte.py       → downloads + OCRs images → writes to output/ocr/  (WASTED)
  superindo.py   → downloads + OCRs images → writes to output/ocr/  (WASTED)
Stage 2: OCR
  run_ocr.py     → OCRs same images AGAIN  → writes to database/ocr/ (USED)
Stage 3: Consolidation
  consolidate.py → reads from database/ocr/
```

Each pipeline run costs **double the API quota** (~32 Gemini requests instead of ~16). Time doubles (~200s vs ~100s). `output/ocr/` files are orphaned — nothing reads them.

**Root cause:** Scrapers should only scrape (download images). OCR is a separate concern.

### 4. Orphaned Directories

- `output/ocr/` — written by scrapers, read by nothing
- `output/scrape/` — empty, unused
- `output/consolidation/` — written by consolidate, read by (missing) index.html only
- `database/ocr/<store>/` — written by run_ocr.py, read by consolidate (the canonical path)

As a user, I'd be confused about where data actually lives.

---

## 🟡 Moderate Issues

### 5. No `index.html` — Phase 3 Missing

The primary user-facing output does not exist. Without it, the only way to see results is reading raw JSON files. The tool cannot actually display price comparisons yet.

### 6. Brand Normalization Drops `.replace(' ', '')` vs v2 Docs

v2 doc: `BRAND_ALIASES.get(b, b).lower().replace(' ', '')` (strips spaces → "goldenfarm")
Implementation: `BRAND_ALIASES.get(b, b)` (preserves spaces → "golden farm" = 2 Jaccard tokens)

"Golden Farm" → "golden farm" (two tokens) vs "goldenfarm" (one token). This changes matching behavior for multi-word brands.

### 7. Brand Aliases Case Mismatch

v2 docs: `'S0sro': 'sosro'` (uppercase), `'S0s0': 'sosro'`
Code: `'s0sro': 'sosro'` (lowercase), `'s0s0': 'sosro'`

Works because `normalize_brand()` lowercases, but communicates wrong info.

### 8. `parse_valid_until` Only Handles Range Format

Works: `"7 - 20 Mei 2026"` → `"2026-05-20"`
Fails: `"s/d 20 Mei 2026"`, `"Valid until 15 May 2026"`, `"20 Mei 2026"` (single date)

Real brochures use various date formats. Many promos would have `valid_until: null` incorrectly.

### 9. Live API Key on Disk (`.env` contains `GEMINI_API_KEY`)

While `.env` is in `.gitignore`, the file contains a live Google API key on the filesystem.
**Action:** Rotate the key if this is a production or shared machine.

### 10. `OLLAMA_BASE_URL` Not Documented in `.env.example`

`matcher.py:175` and `ollama_client.py:23` honor `OLLAMA_BASE_URL` for Docker (needs `http://host.docker.internal:11434`), but `.env.example` doesn't mention it. A Docker user must discover this through code reading.

### 11. Docker Detection Fragile (`_detect_docker()`)

```python
def _detect_docker() -> bool:
    return os.path.exists('/.dockerenv')
```

`/.dockerenv` may not exist in minimal Docker images. More robust: check `os.path.exists('/proc/1/cgroup')` or environment variables.

### 12. No Health Check Script

`scripts/health_check.py` is documented in v2 §8.1 but doesn't exist. Current `haqita.bat` doesn't call it, so this is only a doc gap.

---

## ⚪ Minor Issues / Improvements

### 13. `normalizer.py` - `UNIT_TYPE_MAP` includes `'s': 'count'`

A bare `'s'` suffix matches anything ending in 's' (e.g., "products", "items"). The test at `test_normalizer.py:68` verifies `"1100's"` matches as count, but this could produce false positives for non-unit words.

### 14. `extract_products()` in `consolidate.py` Only Handles Wrapper Schema

```python
def extract_products(data: dict) -> list[dict]:
    if 'products' in data:
        return data['products']
    return []
```

Doesn't handle the scraper's `new_images[].products` nested schema. This is fine because consolidate only reads `run_ocr.py` output, but it means the scraper output format is entirely incompatible.

### 15. No `--verbose` Flag

No way to see *why* two products didn't match (which gate rejected a pair). Debugging requires adding print statements.

---

## Validation of Constraints & Edge Cases

| Constraint / Edge Case | Status | Notes |
|---|---|---|
| Empty store (0 products) | ✅ Tested | `test_empty_store` passes, shows all as singles |
| Corrupt input JSON | ✅ Handled | Atomic write replaces it |
| No internet connection | ❌ Not handled | `requests.get()` will throw unhandled exception |
| Ollama/Gemini unavailable | ⚠️ Partial | `_ollama_verify` catches exceptions → returns `[None]`; Lotte scraper crashes hard |
| 5× price difference | ✅ Handled | Sent to review_queue |
| Unicode in product names | ⚠️ Untested | No test case covers this |
| Very long product names | ⚠️ Untested | `make_product_key` slug could produce very long keys |
| Same image, different URL | ⚠️ Partial | MD5 detects same content, URL not tracked separately |
| Concurrent runs | ❌ Not handled | State file race conditions |
| Image download failure | ✅ Handled | `try/except` in `download_and_classify` |
| Zero products matched | ✅ Handled | All products become singles |
| Promo text with no known pattern | ✅ Handled | Falls back to `promo_type: single` |
| AI verifier returns garbage | ✅ Handled | `None` → review_queue |

---

## Usability Feedback (as a user)

| Aspect | Rating | Notes |
|---|---|---|
| First-time setup | ⚠️ Hard | No setup script. Must install Python 3.12+, Ollama, 2 vision models (~7.5GB total), pip deps, configure `.env` |
| Daily use | ✅ Good | `haqita.bat` menu is clear, dry-run at every stage |
| Error messages | ⚠️ Partial | "OCR failed" doesn't say *why* (timeout? wrong model? API key? network?) |
| Debugging | ❌ Hard | No `--verbose`. Can't see which gate rejected a pair without editing code |
| Output visibility | ❌ None | No `index.html` — can't see price comparisons |
| Pipeline speed | ⚠️ Slow | Double OCR wastes time. Ollama takes 30-60s/image |
| Docker experience | ⚠️ Rough | Must manually set `OLLAMA_BASE_URL`, `host.docker.internal` may not work on all Windows Docker configs |

---

## Recommendations Before Phase 3

### Must Fix (blocks Phase 3 quality):

1. **Fix Gate 6 indentation** (`matcher.py:421`) — move removal loop outside the `for i, result` enumeration
2. **Fix `lotte.py` provider routing** — use `extract_products()` from `ocr_processor.py`
3. **Separate scrape from OCR** — scrapers download only; OCR is always `run_ocr.py`

### Should Fix:

4. **Create `index.html`** — the whole point of the tool
5. **Add `--verbose` flag** to matcher showing which gate rejected each pair
6. **Clean up orphaned directories** — remove `output/ocr/`, `output/scrape/`
7. **Add `OLLAMA_BASE_URL` to `.env.example`**
8. **Rotate the exposed `GEMINI_API_KEY`** if applicable

### Nice to Have:

9. **Add more date formats** to `parse_valid_until()`
10. **Add connection checks** before making API calls (fail fast with clear message)
11. **Add Golden File Regression tests** (mentioned in v2 §9.2)
12. **Add `health_check.py`** — verify Ollama/Gemini/models before pipeline run
13. **Add `no-ocr` flag to scrapers** so they can skip the double OCR

---

## Documentation vs Implementation Gap

| Doc Section | Status | Notes |
|---|---|---|
| Docker Setup | ✅ Complete | All files present and tested |
| Matching Pipeline (7 gates) | ✅ Complete | All gates implemented + feature flags |
| Feature Flags | ✅ Complete | Config has all `gates.*` booleans |
| Test Coverage | ✅ Complete | 100 matching tests pass |
| Phase 3 HTML | ❌ Missing | `index.html` does not exist |
| Health Check | ❌ Missing | `scripts/health_check.py` does not exist |
| `.env.example` | ⚠️ Partial | Missing `OLLAMA_BASE_URL` |
| Phase 1 Scrapers | ⚠️ Partial | Lotte scraper has provider routing bug |
| Price normalization in normalizer | ⚠️ Drifted | `normalize_brand()` behavior differs from v2 spec |

---

**Bottom Line:** The core matching engine is well-tested and structurally sound. However, there are 4 critical bugs (Gate 6 indentation, Lotte provider, double-OCR pipeline, orphaned directories) that significantly impact correctness, cost, and user experience. Phase 3 (`index.html`) is the critical missing piece — without it the tool produces no usable output. 4 of 6 test categories in the previous audit's "Edge Cases Not Handled" remain unaddressed.
