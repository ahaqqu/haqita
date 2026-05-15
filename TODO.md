# Haqita — TODO / Backlog

Items to address after Phase 2 is complete.

## Phase 1 Refactoring

### [x] Scrapers share duplicated code (state, download, etc.)
- **Status**: DONE — Extracted `scripts/scrapers/base_scraper.py` with `BaseScraper` class.
- Both `lotte.py` and `superindo.py` now inherit from `BaseScraper`.
- Shared code: `md5_hash`, `load_state`, `save_state`, `filename_from_url`, `download_image`, `fetch_html`, `download_and_classify`, `run_ocr_loop`.

### [ ] `lotte.py` uses old `ollama_ocr_processor.py`
- **Status**: PARTIAL — Refactored to use `BaseScraper`, but still imports from legacy `ollama_ocr_processor.py` instead of `scripts/ocr/` module.
- **Impact**: Duplicated OCR logic, inconsistent product schema.
- **Fix**: Switch to `scripts/ocr/ocr_processor.py` + `validate_product()` like Superindo scraper does.

### [ ] Lotte scraper output schema differs from Superindo
- **Status**: DONE — `_normalize_lotte_products()` in `lotte.py` converts raw OCR output to standard schema.
- **Remaining**: Full refactor to use `scripts/ocr/` module (see item above).

### [x] `data/scape` typo
- **Status**: DONE — Fixed in `lotte.py`, `docs/implementation.md`, `docs/lotte_scraper.md`.

## Future Improvements

### [ ] Dockerize scrapers
- Currently only consolidation runs in Docker. Consider Dockerizing scrapers too for consistency.

### [ ] Ollama model upgrade
- `lotte_qwen.py` still references `qwen3-vl:2b` while config uses `qwen3-vl:7b`. Align.

### [ ] Add Superindo "Promo Koran" scraping
- Currently only "Katalog Super Hemat" is implemented.
