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
                                                   consolidated_*)           promo_catalog.json
                                                                                 review_queue.json
                                                                                 index.html
                                                                             │
                                                                             ▼
                                                                       ┌──────────────────┐
                                                                       │  Stage 5         │
                                                                       │  Deploy + Sync   │
                                                                       └──────────────────┘
```

Each stage runs independently. If a stage fails, select **[1] → [4] Resume** to continue from where it left off — completed stages are skipped automatically.

**Matching pipeline** (inside Stage 3): 7 gates — unit type → brand → token Jaccard → exact match → embedding → price check → AI verifier. Each gate is individually toggleable via `config.yaml`.

## Quick Start

### Windows

```cmd
haqita.bat
```

### Ubuntu / WSL

```bash
./haqita.sh
```

On the first run, `haqita.sh` automatically creates a Python virtual environment (`.venv`) and installs all required packages from `requirements.txt`. If you ever need to reinstall dependencies, run:

```bash
./haqita.sh --setup
```

Launches an interactive menu. Select **[1]** for the full pipeline, or run individual stages ([2]–[7]). Each stage has a dry-run mode.

## Viewing the HTML UI

After a full pipeline run, the local UI is served automatically by **Stage 5: Deploy + Sync** at `http://localhost:8080` (when `deploy.local: true` in `config.yaml`). You can also start the server manually:

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

## Menu

Run `haqita.bat` (Windows) or `./haqita.sh` (Ubuntu/WSL) to access the interactive menu. Options [2]-[7] run a **single stage only** — they do not chain to subsequent stages. Only Option [1] runs the full pipeline end-to-end.

```
 [1] Run full pipeline        → submenu: Normal, Dry-run, Verbose, Verbose+Dry-run, Resume
 [2] Stage 1: Scrape          → scrape only (submenu: All, Lotte, Superindo, Dry-run)
 [3] Stage 2: OCR             → OCR only (submenu: All, Lotte, Superindo, Specific, Dry-run)
 [4] Stage 3: Consolidation   → consolidate only (submenu: Run, Dry-run, Custom dir)
 [5] Stage 4: Publish HTML    → generate active_promo.json + copy for browser (Run, Dry-run, Verbose)
 [6] Sync to Cloudflare       → sync data to Cloudflare API (standalone; sync also runs as part of deploy)
 [7] Deploy + Sync            → deploy to Cloudflare Pages + sync, or local dev server (Run, Dry-run, Verbose)
 [8] Start HTTP server        → start python -m http.server 8080
 [9] Tests                    → submenu: Integration tests, Matching tests
 [10] Health check            → pre-flight verification
 [0] Exit
```

### Resume (Option [1] → [4])

If a stage fails during a full pipeline run, fix the issue and select **[1] → [4] Resume**. The orchestrator reads stage status files and skips already-completed stages, continuing from where it left off. No need to rerun stages one by one.

## OCR Provider

Gemini (cloud) is the only OCR provider. Set `GEMINI_API_KEY` in `.env` (free tier at https://aistudio.google.com/apikey).

## Requirements

- Python 3.12+ (3.12 or 3.13 recommended; 3.14+ may not have wheels for all ML packages yet)
- Gemini API key (free tier)
- Windows 10+ (for `haqita.bat`) or Linux/WSL with bash (for `haqita.sh`)

On a fresh Ubuntu/WSL system, `haqita.sh` handles Python package installation automatically. You only need Python 3.12+ installed:

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

## Testing

Via `haqita.bat`/`./haqita.sh` → Option [9]:

| Choice | Action                                   |
| ------ | ---------------------------------------- |
| **1**  | Integration tests (OCR on real images)   |
| **2**  | Matching pipeline tests (124 unit tests) |

### Agentic-engineering verification

Dedicated scripts for isolated, production-safe dummy runs:

```bash
bash agentic_engineering/prepare.sh          # install deps, verify .env, gate on unit tests
./haqita.sh              # interactive pipeline
HAQITA_BATCH=1 ./haqita.sh  # non-interactive batch mode
bash agentic_engineering/verify.sh           # end-to-end verification in temp workspace
```

See [agentic_engineering/agentic-engineering.md](agentic_engineering/agentic-engineering.md) for details.

For end-to-end verification after a full pipeline run:

- Local UI: `curl -s http://localhost:8080/` returns the HTML page
- Local API: `curl -s http://localhost:8787/api/v1/health` returns `{"status":"ok",...}`
- Production UI: `curl -s https://haqita.pages.dev/` returns the HTML page (when `deploy.cloudflare: true`)
- Production API: `curl -s https://haqita.pages.dev/api/v1/health` returns `{"status":"ok",...}`

## Documentation

| Doc                                                                         | Description                                                              |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| [staging/scrape.md](docs/staging/scrape.md)                                 | Stage 1: Scrape — inputs, outputs, state, configuration                  |
| [staging/ocr.md](docs/staging/ocr.md)                                       | Stage 2: OCR — provider config, output schema, validation                |
| [staging/consolidation.md](docs/staging/consolidation.md)                   | Stage 3: Consolidation — matching pipeline, schemas, gate details        |
| [staging/publish-html.md](docs/staging/publish-html.md)                     | Stage 4: Publish HTML — active_promo.json generation, HTML UI            |
| [staging/sync-cloudflare.md](docs/staging/sync-cloudflare.md)               | Sync to Cloudflare — API batch sync, R2 image upload (standalone or via deploy) |
| [staging/deploy-pages.md](docs/staging/deploy-pages.md)                     | Stage 5: Deploy + Sync — version-aware Cloudflare Pages deploy + sync    |
| [staging/orchestrator.md](docs/staging/orchestrator.md)                     | Pipeline orchestrator — stage communication, logging, smart OCR skipping |
| [agentic_engineering/agentic-engineering.md](agentic_engineering/agentic-engineering.md)                            | Agentic pipeline verification with dummy data isolation                  |
| [staging/api-sync-endpoints.md](docs/staging/api-sync-endpoints.md)         | Cloudflare API sync endpoints and schemas                                |
| [staging/security-configuration.md](docs/staging/security-configuration.md) | Security headers, secrets, and WAF configuration                         |
| [database/price_history.md](docs/database/price_history.md)                 | `price_history.json` — append-only price snapshots (schema v1.2)         |
| [database/product_catalog.md](docs/database/product_catalog.md)             | `product_catalog.json` — auto-built product registry                     |
| [database/review_queue.md](docs/database/review_queue.md)                   | `review_queue.json` — flagged matches for manual review                  |

## Project Structure

```
haqita/
├── haqita.bat                        ← Interactive launch menu (Windows)
├── haqita.sh                         ← Interactive launch menu (Ubuntu/WSL)
├── agentic_engineering/
│   ├── prepare.sh                        ← Dependency installer + unit-test gate for agentic runs
│   ├── verify.sh                         ← End-to-end dummy pipeline verification in temp workspace
│   └── agentic-engineering.md            ← Guide for isolated dummy pipeline runs
├── requirements.txt                  ← Python dependencies
├── index.html                        ← Main UI: product browser (search, filter, sort, charts)
├── admin.html                        ← Admin UI: review queue management
├── config.yaml                       ← All tunable settings
├── .env                              ← Configuration (API keys, provider toggles)
├── scripts/
│   ├── scrapers/                     ← Stage 1: Web scrapers
│   ├── ocr/                          ← Stage 2: OCR processors
│   ├── consolidate.py                ← Stage 3: Merge + match, write to database/
│   ├── publish_html.py               ← Stage 4: Generate active_promo.json + copy
│   ├── sync_cloudflare.py            ← Sync data to Cloudflare API/R2 (standalone or called by deploy.py)
│   ├── deploy.py                     ← Stage 5: Version-aware Cloudflare Pages deploy + sync, local dev server
│   ├── orchestrator.py               ← Pipeline orchestrator
│   ├── health_check.py               ← Pre-flight verification
│   └── matching/                     ← Matching pipeline (7 gates)
├── database/ ──symlink──▶ ../haqita-database/   ← Pipeline data (separate repo)
├── output/
│   └── html/                         ← Stage 4 output (safe to delete)
│       ├── active_promo.json         ← Generated from database/
│       └── price_history.json        ← Copy from database/
├── tests/                            ← Unit and integration tests
└── docs/                             ← Documentation
```

## Setup

### Database repo

Pipeline data lives in a separate repository: [ahaqqu/haqita-database](https://github.com/ahaqqu/haqita-database).

Clone it as a sibling of the main repo and the setup script will create the symlink:

```bash
# Clone the database repo (as a sibling directory)
git clone git@github.com:ahaqqu/haqita-database.git ../haqita-database

# Or use the setup script (does the same thing):
bash scripts/setup_database_repo.sh
```

The symlink at `database/` points to `../haqita-database/`. All pipeline scripts write through the symlink transparently. The database repo is auto-committed after each pipeline run.
