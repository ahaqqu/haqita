# Lotte Promo Scraper

Fetches promo flyers from the Lotte Mart website, detects new/updated promos, and extracts product data using Qwen3-VL OCR.

## How It Works

```
1. Fetch HTML     → GET https://www.lottemart.co.id/all-promo-mart
2. Parse images   → BeautifulSoup → filter by keywords (promo, flyer, ht)
3. Download       → Save to data/scape/lotte/<filename>
4. Filter         → Skip logos/icons (size < 50KB, dimensions < 300px)
5. Deduplicate    → MD5 hash comparison against state history
6. Skip old       → Already-processed hashes skipped
7. OCR new        → Qwen3-VL extracts products + promo period
8. Save results   → output/lotte_promos_YYYYMMDD_HHMMSS.json
9. Update state   → data/scape/lotte_state.json
```

## Usage

### Quick start
```cmd
run_lotte_scraper.bat
```

### Dry run (see what's new without OCR)
```cmd
run_lotte_scraper.bat --dry-run
```

### Direct Python
```cmd
python scrapers/lotte_qwen.py --dry-run
python scrapers/lotte_qwen.py
```

## New Promo Detection

Detection uses **MD5 content hashing** — not filenames or URLs:

| Scenario | Detection | Action |
|---|---|---|
| Brand new promo | New MD5 hash | OCR |
| Same promo, next week | MD5 matches history | Skipped |
| Same image, different URL | Same MD5 | Skipped (same-batch dedup) |
| Updated promo, same filename | Different MD5 | OCR (new content) |
| Logo/icon | Too small (< 50KB or < 300px) | Skipped |

Files are saved with an MD5 prefix: `ht1_588fe87e.jpeg`. This prevents overwrites — next week's `ht1.jpeg` with different content becomes `ht1_abc12345.jpeg`.

## Output

### `output/lotte_promos_YYYYMMDD_HHMMSS.json`
```json
{
  "scrape_date": "2026-05-14T07:30:00",
  "source": "https://www.lottemart.co.id/all-promo-mart",
  "mode": "live",
  "new_images": [
    {
      "filename": "ht2_b9ace8ca.jpeg",
      "md5": "b9ace8ca6873...",
      "products": [
        {"brand": "AICE", "product": "Sandwich Cookies Panda", "price": "39.900", ...}
      ],
      "product_count": 5,
      "promo_period": "7 - 20 Mei 2026",
      "ocr_time_s": 71.3
    }
  ],
  "total_new": 1,
  "total_skipped": 5,
  "status": "complete"
}
```

Results are saved **incrementally** after each image — if the scraper crashes on image 4, images 1-3 are preserved.

### `data/scape/lotte_state.json`
```json
{
  "last_run": "2026-05-14T07:30:00",
  "processed": [
    {"filename": "ht2_b9ace8ca.jpeg", "md5": "b9ace8ca6873...", "image_url": "...", ...}
  ]
}
```

## File Structure

| Path | Purpose |
|---|---|
| `scrapers/lotte_qwen.py` | Scraper script |
| `run_lotte_scraper.bat` | Batch launcher (auto-starts Ollama) |
| `data/scape/lotte/` | Downloaded promo images |
| `data/scape/lotte_state.json` | Processed image tracking |
| `output/lotte_promos_*.json` | OCR extraction results |

## Test Mode

Set `LOTTE_TEST_MODE=true` in `.env` to use saved local HTML instead of fetching the live website:

```env
LOTTE_TEST_MODE=true
```

Uses `data/examples/lotte/All Promo Mart.html` and images from its `All Promo Mart_files/` directory. Useful for debugging without hitting the live site.

## Requirements

- Python 3.8+
- `requests`, `beautifulsoup4`, `Pillow` (`pip install requests beautifulsoup4 Pillow`)
- Ollama with `qwen3-vl:2b` model (auto-pulled by the batch file)
- Internet connection for live scraping

## Configuration

Environment variables (set in `.env`):

| Variable | Default | Description |
|---|---|---|
| `LOTTE_TEST_MODE` | `false` | Use local HTML instead of live website |
| `HTTP_PROXY` | — | HTTP proxy for requests |
| `HTTPS_PROXY` | — | HTTPS proxy for requests |
