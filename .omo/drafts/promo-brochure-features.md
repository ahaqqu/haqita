---
slug: promo-brochure-features
status: approved
intent: clear
pending-action: write .omo/plans/promo-brochure-features.md
approach: Three parallel streams: (A) promo standardization in consolidation pipeline, (B) promo listing UI tab, (C) brochure gallery UI tab
---

# Draft: promo-brochure-features

## Components (topology ledger)
| id | outcome | status | evidence path |
|----|---------|--------|---------------|
| A | Promo standardization backend — normalize promo strings into structured format in price_history.json via consolidation | active | database/price_history.json:raw promo, scripts/matching/promo_parser.py:existing parser, scripts/matching/consolidation.py:build pipeline |
| B | Promo listing UI tab — tab showing all promos grouped by type with product counts | active | index.html:current single-page app pattern, admin.html:522 lines existing admin page |
| C | Brochure gallery UI tab — tab showing brochure thumbnails, click reveals product cards | active | database/scrape/superindo/20260613/:12 images, price_history.json:image_path links products to brochures |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
|------------|----------------|-----------|-------------|
| Promo normalization runs during generate_consolidated_from_history() | Yes — it's the central rebuild function used by both Stage 3 and Stage 4 | Avoids duplicating logic; single source of truth | Yes — output in active_promo.json is regenerated each run |
| Standardized promo data stored as new field in price_history.json snapshots | New field `standardized_promo` alongside existing `promo` array | Preserves backward compatibility with existing UI code | Yes |
| Promo types categorization | percentage_discount, fixed_discount, bogo, bundle, member_price, promo_price, freebie, quantity_limit, special | Covers all 110 observed promo strings | Yes — easy to add new types |

## Findings (cited - path:lines)
1. Raw promo data: 110 unique strings, 158 combos, severe casing/typo inconsistency — database/price_history.json, direct analysis via python
2. Existing promo parser: scripts/matching/promo_parser.py — handles get_free, discount_pct, bundle_buy, multi_price, discount_fixed; also has parse_period() for dates
3. Basic normalization already exists: _normalize_promo() in consolidation.py line 20 — handles list conversion and legacy stringified lists
4. Brochure image structure: 12 images in database/scrape/superindo/20260613/, each product via image_path — confirmed via python analysis
5. Current UI does NOT have a "View Brochure" button in the product card itself (only in the expanded detail panel) — index.html:877
6. No existing promo listing or brochure gallery views — index.html only has product grid

## Decisions (with rationale)
| decision | choice | rationale |
|----------|--------|-----------|
| Standardization scope | Database-level rewrite (in price_history.json via consolidation) | User chose this over publish-only. Ensures structured promo data is available to all downstream consumers. |
| UI navigation | Tab navigation (Products | Promos | Brochures) | User chose this. Keeps everything in one page, consistent with current single-page app pattern. |
| Standardized schema | New `standardized_promo` field alongside existing `promo` | Non-breaking. Existing UI code that reads `promo` continues to work unchanged. |
| Backend changes | Enhance promo_parser.py, wire into consolidation.py, add promo_catalog for promo-level metadata | Separates concerns: parser handles one promo string, consolidation builds the structured output |

## Scope IN
1. Enhance promo_parser.py with comprehensive normalization (casing, splitting, typos, categorizing)
2. Wire promo normalization into consolidation.py's generate_consolidated_from_history()
3. Add standardized_promo field to price_history.json snapshots (during consolidation)
4. Add a promo_catalog section to active_promo.json listing all unique promos with metadata
5. Refactor index.html with tab navigation (Products | Promos | Brochures)
6. Promo listing tab: grouped by type, product counts, filterable by store
7. Brochure gallery tab: thumbnails grouped by store/date, click shows products
8. Update admin.html if needed for consistency

## Scope OUT (Must NOT have)
1. No changes to the data pipeline (scraping, OCR) — only consolidation and publish stages
2. No changes to the matching engine (7 gates)
3. No CSS framework changes — stay with existing CSS variables
4. No backend server — stay as static HTML/JSON served via HTTP server
5. No authentication or user management
6. No image processing — use existing brochure images as-is
7. No changes to the 3rd party integrations (Gemini OCR)

## Open questions
<!-- None — all resolved via exploration + user decisions -->

## Approval gate
status: approved
<!-- Approved by user on 2026-06-21. User selected: database-level rewrite + tab navigation. -->
