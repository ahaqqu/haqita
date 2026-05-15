# Haqita — Jakarta Grocery Price Comparison

Compare grocery prices across Jakarta supermarkets using AI OCR and web scraping.

## Quick Start

```cmd
haqita.bat
```

Launches an interactive menu with options to run scrapers, OCR processor, or dry-run.

## Tools

| Tool | What it does | Docs | Run via menu |
|---|---|---|---|
| **Lotte Scraper** | Fetches promo flyers from Lotte Mart, detects new ones, OCRs products | [`docs/lotte_scraper.md`](docs/lotte_scraper.md) | Option 1 |
| **Superindo Scraper** | Fetches promo flyers from Superindo, detects new ones, OCRs products | — | Option 2 |
| **Dry-run** | Reports new promos without running OCR | [`docs/lotte_scraper.md`](docs/lotte_scraper.md) | Option 3/4 |
| **Integration Tests** | Runs OCR on real brochure images | — | Option 5 |

## Project Structure

```
haqita/
├── haqita.bat                        ← Interactive launch menu
├── config.yaml                       ← All tunable settings
├── .env                              ← Configuration (API keys, provider toggles)
├── Dockerfile                        ← Docker image for consolidation pipeline
├── docker-compose.yml                ← Docker service definition
├── scripts/
│   ├── scrapers/
│   │   ├── base_scraper.py           ← Shared scraper infrastructure
│   │   ├── lotte.py                  ← Lotte Mart scraper (store-specific)
│   │   └── superindo.py              ← Superindo scraper (store-specific)
│   ├── ocr/
│   │   ├── ocr_processor.py          ← Unified OCR interface (routes to Gemini or Ollama)
│   │   ├── gemini_client.py          ← Gemini OCR client
│   │   ├── ollama_client.py          ← Ollama OCR client
│   │   ├── image_preprocess.py       ← Image preprocessing
│   │   └── prompts/                  ← Store-specific OCR prompts
│   └── matching/                     ← Phase 2: Product matching pipeline
│       ├── normalizer.py             ← Name/unit/brand normalization
│       ├── promo_parser.py           ← Indonesian promo text parser
│       └── matcher.py                ← Multi-tier matching pipeline
├── data/
│   └── scrape/
│       ├── lotte/                    ← Downloaded Lotte promo images
│       └── superindo/                ← Downloaded Superindo promo images
├── output/                           ← OCR results + consolidated output
├── tests/
│   ├── integration/                  ← OCR integration tests
│   └── matching/                     ← Matching pipeline tests
└── docs/
    ├── lotte_scraper.md              ← Lotte scraper documentation
    └── implementation-phase2.md      ← Phase 2 implementation guide
```

## Requirements

- Python 3.8+
- Ollama with `qwen3-vl:7b` (configurable in config.yaml)
- NVIDIA GPU recommended (~3.3 GiB VRAM), works on CPU
- Windows 10+
- Docker (for consolidation pipeline)

Python packages: `requests`, `beautifulsoup4`, `Pillow`, `pyyaml`, `python-dotenv`, `google-genai`

## OCR Providers

Haqita supports two OCR providers, configured in `config.yaml`:

| Provider | Setup | Best for |
|---|---|---|
| **Gemini** (default) | Set `GEMINI_API_KEY` in `.env` | Higher accuracy, cloud-based |
| **Ollama** | Run `ollama serve` locally | Free, offline, no API key needed |

Switch via `.env`:
```env
OCR_PROVIDER=gemini   # or "ollama"
```
