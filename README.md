# Haqita — Jakarta Grocery Price Comparison

Compare grocery prices across Jakarta supermarkets using local AI (Qwen3-VL) and web scraping.

## Quick Start

```cmd
haqita.bat
```

Launches an interactive menu with options to run the scraper, OCR processor, or dry-run.

## Tools

| Tool | What it does | Docs | Run via menu |
|---|---|---|---|
| **Lotte Scraper** | Fetches promo flyers from Lotte Mart, detects new ones, OCRs products | [`docs/lotte_scraper.md`](docs/lotte_scraper.md) | Option 1 |
| **Qwen3-VL OCR** | Reads product names, prices, brands from brochure images | [`docs/qwen_ocr.md`](docs/qwen_ocr.md) | Option 2 |
| **Dry-run** | Reports new promos without running OCR | [`docs/lotte_scraper.md`](docs/lotte_scraper.md) | Option 3 |

## Project Structure

```
haqita/
├── haqita.bat                        ← Interactive launch menu
├── .env                              ← Configuration (API keys, modes)
├── scripts/
│   ├── qwen_ocr_processor.py         ← OCR engine (Qwen3-VL via Ollama)
│   ├── run_qwen_ocr.bat              ← Batch launcher for OCR
│   ├── run_lotte_scraper.bat         ← Batch launcher for scraper
│   └── scrapers/
│       └── lotte_qwen.py             ← Lotte promo scraper
├── data/
│   ├── test/lotte/
│   │   ├── html-scape/               ← Test HTML + assets (for test mode)
│   │   └── image-brochure/           ← Test/promo images for OCR
│   └── scape/lotte/                  ← Downloaded scraper images (auto-created)
├── output/                           ← OCR results (timestamped JSON)
└── docs/
    ├── lotte_scraper.md              ← Scraper documentation
    └── qwen_ocr.md                   ← OCR documentation
```

## Requirements

- Python 3.8+
- Ollama with `qwen3-vl:2b` (auto-pulled by batch files)
- NVIDIA GPU recommended (~3.3 GiB VRAM), works on CPU
- Windows 10+

Python packages: `requests`, `beautifulsoup4`, `Pillow`
