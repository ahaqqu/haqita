# Haqita — Jakarta Grocery Price Comparison

Compare grocery prices across Jakarta supermarkets using AI OCR and web scraping.

## Supported Stores

- **Lotte Mart** — `https://www.lottemart.co.id/all-promo-mart`
- **Superindo** — `https://www.superindo.co.id/promosi/` (Katalog Super Hemat + Promo Koran)

## Architecture

```
  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │  Stage 1    │     │  Stage 2     │     │  Stage 3         │     │  Stage 4         │
  │  Scrape     │────▶│  OCR         │────▶│  Consolidation   │────▶│  Publish HTML    │
  └─────────────┘     └──────────────┘     └──────────────────┘     └──────────────────┘
        │                     │                       │                       │
        ▼                     ▼                       ▼                       ▼
  database/scrape/        database/ocr/           database/                 output/html/
                                                  (price_history,            active_promo.json
                                                   catalog, review,          price_history.json
                                                   consolidated_*)           index.html
```

Each stage runs independently. If a stage fails, select **[1] → [5] Resume** to continue from where it left off — completed stages are skipped automatically.

**Matching pipeline** (inside Stage 3): 7 gates — unit type → brand → token Jaccard → exact match → embedding → price check → AI verifier. Each gate is individually toggleable via `config.yaml`.

## Quick Start

```cmd
haqita.bat
```

Launches an interactive menu. Select **[1]** for the full pipeline, or run individual stages ([2]–[4]). Each stage has a dry-run mode.

## Viewing the HTML UI

After running the pipeline, open the browser UI:

```cmd
python -m http.server 8080
```

Then open `http://localhost:8080` in a browser. Features:
- **Search** products by name, brand, or unit
- **Filter** by store (All / Lotte / Superindo)
- **Sort** by cheapest, name, savings, or expiry
- **Expand** cards for price comparison, trend charts, and brochure links
- **Auto-refresh** every 5 minutes when tab is visible
- **Print-friendly** layout (Ctrl+P)

> Opening `index.html` directly via `file://` will fail due to CORS. An HTTP server is required.

## Run Mode

Set `RUN_MODE` in `.env`:

```env
RUN_MODE=native   # or "docker"
```

| Mode | Description |
|---|---|
| `native` (default) | Runs scripts directly on your machine |
| `docker` | Runs stages in Docker containers |

## Menu

Run `haqita.bat` to access the interactive menu. Options [2]-[5] run a **single stage only** — they do not chain to subsequent stages. Only Option [1] runs the full pipeline end-to-end.

```
 [1] Run full pipeline        → submenu: Normal, Dry-run, Verbose, Verbose+Dry-run, Resume
 [2] Stage 1: Scrape          → scrape only (submenu: All, Lotte, Superindo, Dry-run)
 [3] Stage 2: OCR             → OCR only (submenu: All, Lotte, Superindo, Specific, Dry-run)
 [4] Stage 3: Consolidation   → consolidate only (submenu: Run, Dry-run, Custom dir)
 [5] Stage 4: Publish HTML    → generate active_promo.json + copy for browser (Run, Dry-run, Verbose, Docker)
 [6] Tests                    → submenu: Integration tests, Matching tests
 [7] Health check             → pre-flight verification
 [0] Exit
```

### Resume (Option [1] → [5])

If a stage fails during a full pipeline run, fix the issue and select **[1] → [5] Resume**. The orchestrator reads stage status files and skips already-completed stages, continuing from where it left off. No need to rerun stages one by one.

## OCR Providers

| Provider | Setup | Best for |
|---|---|---|
| **Gemini** (default) | Set `GEMINI_API_KEY` in `.env` | Higher accuracy, cloud-based |
| **Ollama** | Run `ollama serve` locally | Free, offline, no API key |

Switch via `.env`: `OCR_PROVIDER=gemini` or `OCR_PROVIDER=ollama`

## Requirements

- Python 3.12+
- Ollama with `qwen3-vl:7b` (if using Ollama)
- NVIDIA GPU recommended (~3.3 GiB VRAM), works on CPU
- Windows 10+
- Docker (optional, only when `RUN_MODE=docker`)

## Testing

Via `haqita.bat` → Option [5]:

| Choice | Action |
|---|---|
| **1** | Integration tests (OCR on real images) |
| **2** | Matching pipeline tests (124 unit tests) |

## Documentation

| Doc | Description |
|---|---|
| [staging/scrape.md](docs/staging/scrape.md) | Stage 1: Scrape — inputs, outputs, state, configuration |
| [staging/ocr.md](docs/staging/ocr.md) | Stage 2: OCR — provider config, output schema, validation |
| [staging/consolidation.md](docs/staging/consolidation.md) | Stage 3: Consolidation — matching pipeline, schemas, gate details |
| [staging/publish-html.md](docs/staging/publish-html.md) | Stage 4: Publish HTML — active_promo.json generation, HTML UI |
| [staging/orchestrator.md](docs/staging/orchestrator.md) | Pipeline orchestrator — stage communication, logging, smart OCR skipping |

## Project Structure

```
haqita/
├── haqita.bat                        ← Interactive launch menu
├── index.html                        ← Stage 4: Browser UI (search, filter, sort, charts)
├── config.yaml                       ← All tunable settings
├── .env                              ← Configuration (API keys, provider toggles)
├── docker/                           ← Docker configuration
├── scripts/
│   ├── scrapers/                     ← Stage 1: Web scrapers
│   ├── ocr/                          ← Stage 2: OCR processors
│   ├── consolidate.py                ← Stage 3: Merge + match, write to database/
│   ├── publish_html.py               ← Stage 4: Generate active_promo.json + copy
│   ├── orchestrator.py               ← Pipeline orchestrator
│   ├── health_check.py               ← Pre-flight verification
│   └── matching/                     ← Matching pipeline (7 gates)
├── database/                         ← Generated, maintained (source of truth)
│   ├── price_history.json            ← Append-only price snapshots
│   ├── product_catalog.json          ← Auto-built product registry
│   ├── review_queue.json             ← Flagged matches for review
│   └── consolidated_*.json           ← Timestamped consolidation archives
├── output/
│   └── html/                         ← Stage 4 output (safe to delete)
│       ├── active_promo.json         ← Generated from database/
│       └── price_history.json        ← Copy from database/
├── tests/                            ← Unit and integration tests
└── docs/                             ← Documentation
```
