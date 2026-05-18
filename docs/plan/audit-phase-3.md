# Phase 3 Audit — Fix Plan

## Overview

This document outlines fixes for issues identified during the Phase 3 implementation audit.

---

## Issue Summary

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | Key mismatch: `product_key` vs `key` in index.html | High | Fixed |
| 2 | Missing test data files in `output/html/` | High | Fixed |
| 3 | `displayHints.stores` type mismatch (array vs object) | Medium | Fixed |
| 4 | Wrong freshness timestamp field | Medium | Fixed |
| 5 | Missing `start_period` and `end_period` fields | Medium | Plan updated |
| 6 | Match confidence logic flaw | Medium | Fixed |
| 7 | Missing schema version 1.2 default | Low | Fixed |
| 8 | Division by zero in savings_pct | Low | Already guarded |
| 9 | HTTP server warning missing | Low | Fixed |

---

## Fixes Applied

### 1. Key Mismatch (`product_key` vs `key`)
- Updated `normalizeProduct()` in `index.html` to normalize both `key` and `product_key`
- Updated `buildMatchedCard()`, `buildSingleCard()`, `buildDetailPanel()`, and `expandCard()` to use normalized key

### 2. Missing Test Data Files
- Created `data/sample/html/active_promo.json` with sample data (2 matched, 2 singles)
- Created `data/sample/html/price_history.json` with ≥1 product having ≥2 snapshots for chart testing
- Created `output/html/.gitkeep`

### 3. `displayHints.stores` Type Mismatch
- Updated `consolidate.py` to output `stores` as object: `{'Lotte': 'Lotte Mart', 'Superindo': 'Superindo'}`
- Updated `consolidation.py` to output same format

### 4. Wrong Freshness Timestamp Field
- Updated `index.html` to check `generated_at` first, fallback to `metadata.last_updated`

### 5. Missing `start_period`/`end_period` (Plan Update)
- Updated `docs/plan/implementation-phase3.md` to reflect correct schema
- Fields are `valid_from` and `valid_until`, not `start_period`/`end_period`

### 6. Match Confidence Logic Flaw
- Updated `consolidation.py` to properly handle `None` values in comparison

### 7. Missing Schema Version 1.2 Default
- Updated `consolidate.py` default schema version from `1.1` to `1.2`

### 8. HTTP Server Warning
- Updated error message in `index.html` to include HTTP server instructions

---

## Files Modified

| File | Changes |
|------|---------|
| `index.html` | Key normalization, freshness field, error message |
| `scripts/consolidate.py` | display_hints.stores object, schema version 1.2 |
| `scripts/matching/consolidation.py` | display_hints.stores object, match confidence null check |
| `data/sample/html/active_promo.json` | Created |
| `data/sample/html/price_history.json` | Created |
| `output/html/.gitkeep` | Created |
| `docs/plan/implementation-phase3.md` | Plan doc corrected |

---

## Testing Checklist

- [ ] Load `index.html` via HTTP server — data displays correctly
- [ ] Click on product card — detail panel expands with chart
- [ ] Use URL hash `#product-key` — card auto-expands on load
- [ ] Filter by store — products filter correctly
- [ ] Sort by savings — singles sort to bottom
- [ ] Freshness bar shows correct timestamp
- [ ] Store names display correctly (not "undefined")
- [ ] Price history chart renders for products with ≥2 snapshots
- [ ] Low confidence badge appears for match_confidence < 0.8

---

## Out of Scope (Not Fixed)

- Category chips
- Bottom navigation
- Brosur upload
- User accounts / avatar
- Database migration to SQL