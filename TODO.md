# Haqita — TODO / Backlog

Items to address after Phase 2 is complete.

## Phase 1 Refactoring

### [x] Scrapers share duplicated code (state, download, etc.)
- **Status**: DONE — Extracted `scripts/scrapers/base_scraper.py` with `BaseScraper` class.
- Both `lotte.py` and `superindo.py` now inherit from `BaseScraper`.
- Shared code: `md5_hash`, `load_state`, `save_state`, `filename_from_url`, `download_image`, `fetch_html`, `download_and_classify`, `run_ocr_loop`.

### [x] `lotte.py` uses old `ollama_ocr_processor.py`
- **Status**: DONE — Now uses `scripts/ocr/ollama_client.py` with proven two-step OCR strategy.
- Legacy `ollama_ocr_processor.py` removed.

### [x] Lotte scraper output schema differs from Superindo
- **Status**: DONE — Both scrapers now produce the same standard product schema:
  - `lotte.py`: `_normalize_lotte_products()` adds missing fields
  - `superindo.py`: `validate_product()` adds missing fields
  - Final output: `{"name", "brand", "unit", "price", "promo", "period", "image_source", "ocr_raw_price", "ocr_confidence"}`

### [x] `data/scape` typo
- **Status**: DONE — Fixed in `lotte.py`, `docs/implementation.md`, `docs/lotte_scraper.md`.

## Future Improvements

### [ ] Dockerize scrapers
- Currently only consolidation runs in Docker. Consider Dockerizing scrapers too for consistency.

### [ ] Ollama model upgrade
- `lotte_qwen.py` still references `qwen3-vl:2b` while config uses `qwen3-vl:7b`. Align.

### [ ] Add Superindo "Promo Koran" scraping
- Currently only "Katalog Super Hemat" is implemented.
