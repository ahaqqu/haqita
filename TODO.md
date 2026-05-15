# Haqita — TODO / Backlog

Items to address after Phase 2 is complete.

## Phase 1 Refactoring

### [ ] `lotte_qwen.py` uses old `qwen_ocr_processor.py`
- **Location**: `scripts/scrapers/lotte_qwen.py:17`
- **Issue**: Imports from legacy `qwen_ocr_processor.py` (root-level) instead of the newer `scripts/ocr/` module used by `superindo_qwen.py`.
- **Impact**: Duplicated OCR logic, inconsistent product schema (uses `product` key vs `name` key), harder to maintain.
- **Fix**: Refactor to use `scripts/ocr/ocr_processor.py` + `validate_product()` like Superindo scraper does.

### [ ] Lotte scraper output schema differs from Superindo
- **Lotte output**: `{scrape_date, source, new_images: [{filename, md5, products: [{brand, product, price, unit, promo}], product_count, promo_period}]}`
- **Superindo output**: `{scrape_date, source, mode, new_images: [{filename, md5, products: [{name, brand, unit, price, promo, period, image_source, ...}], rejected, product_count}]}`
- **Impact**: `consolidate.py` must handle both schemas. Better to unify.
- **Fix**: Standardize both scrapers to output the same schema (see `docs/implementation-phase2.md` §4.1).

### [ ] `data/scape` typo already fixed
- **Status**: DONE — Fixed in `lotte_qwen.py`, `docs/implementation.md`, `docs/lotte_scraper.md`.

## Future Improvements

### [ ] Dockerize scrapers
- Currently only consolidation runs in Docker. Consider Dockerizing scrapers too for consistency.

### [ ] Ollama model upgrade
- `lotte_qwen.py` still references `qwen3-vl:2b` while config uses `qwen3-vl:7b`. Align.

### [ ] Add Superindo "Promo Koran" scraping
- Currently only "Katalog Super Hemat" is implemented.
