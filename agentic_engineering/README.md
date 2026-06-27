# Dummy Supermarket Server

This directory contains a lightweight, self-contained HTTP server that serves static fixtures for the Lotte Mart and Superindo scrapers. It lets the scraper pipeline run against controlled local data instead of the real supermarket websites.

## Start the server

From the repository root:

```bash
python agentic_engineering/dummy_server.py
```

The server binds to `0.0.0.0:18080` and prints:

```text
Dummy supermarket server running at http://localhost:18080
```

## Quick verification

Run the included verification script to confirm the server and scraper URL overrides work:

```bash
bash agentic_engineering/verify.sh
```

This starts the server, runs both scrapers in dry-run mode, and asserts that Lotte and Superindo each discover the expected brochure images.

## Use with the scrapers

Set the environment variables before running the scrapers so they point at the dummy server:

```bash
export LOTTE_URL=http://localhost:18080/lotte/all-promo-mart
export SUPERINDO_KATALOG_URL=http://localhost:18080/superindo/promosi/katalog-super-hemat/
export SUPERINDO_KORAN_URL=http://localhost:18080/superindo/promosi/promo-koran/

python scripts/scrapers/lotte.py --dry-run
python scripts/scrapers/superindo.py --dry-run
```

## Image fixtures

All brochure images are copied into `agentic_engineering/images/` so the dummy server is completely self-contained. Deleting `database/scrape/` does not break the dummy sites.

```
agentic_engineering/images/
├── lotte/
│   ├── HD-1_a23cff43.jpeg
│   ├── HD-2_7bbd2862.jpeg
│   └── HD-3_9b977567.jpeg
└── superindo/
    ├── 6a3265e518c31HEMAT_E_25_(8)_DKI_1edfc525.jpg
    ├── 6a3265e510171HEMAT_E_25_(1)_DKI_6d2d6244.jpg
    └── ajhttd1921jun975WS-REV_5e2d6aba.jpg
```

## Clean up dummy state for idempotent runs

After a pipeline run, reset all generated state so the next run starts fresh:

```bash
.venv/bin/python agentic_engineering/clean_dummy_data.py
```

This removes local stage results, scraper/OCR state, OCR outputs, `database/*.json`, and `output/html/*`. To also clean a local wrangler D1 SQLite file:

```bash
.venv/bin/python agentic_engineering/clean_dummy_data.py --d1-local
```

To clean a remote D1 database:

```bash
.venv/bin/python agentic_engineering/clean_dummy_data.py --d1-db-name haqita-db
```

## Served URLs

| URL                                           | Content                                                               |
| --------------------------------------------- | --------------------------------------------------------------------- |
| `GET /lotte/all-promo-mart`                   | Dummy Lotte promo page                                                |
| `GET /superindo/promosi/katalog-super-hemat/` | Dummy Superindo katalog page                                          |
| `GET /superindo/promosi/promo-koran/`         | Dummy Superindo promo koran page                                      |
| `GET /lotte/promo/<filename>`                 | Lotte brochure image from `agentic_engineering/images/lotte/`         |
| `GET /superindo/promo/<filename>`             | Superindo brochure image from `agentic_engineering/images/superindo/` |

All responses include permissive CORS headers (`Access-Control-Allow-Origin: *`).
