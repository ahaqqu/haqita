## Overview
Build a Jakarta grocery price comparison web app with:
- Python scraping scripts
- CSV file for data storage
- Static HTML frontend with JavaScript to read CSV
- Multi-category grocery item model

## Scope
- Scraping: Python scripts for Alfamart, Superindo, Indomaret, and Lotte, outputting to a shared CSV file.
- Data: CSV file with product prices, stores, categories.
- Frontend: Static HTML page that loads CSV data via JavaScript and displays comparisons.
- Features:
  - Search products across all stores.
  - Compare prices from Lotte, Superindo, Indomart, and Alfamart.
  - Support items belonging to multiple categories.
  - Show best deal highlights and store rankings.

## Architecture
1. `scrapers/`
   - Python scripts for each supermarket (alfamart.py, superindo.py, etc.).
   - Output scraped data to a shared `data/products.csv` file.

2. `data/products.csv`
   - Columns: id, name, category, store, price, unit, location, updatedAt
   - Supports multiple categories per item.

3. `index.html`
   - Static HTML with JavaScript to load CSV, search/filter, and display comparisons.
   - No server needed; open locally in browser.

## Data Model
CSV file `data/products.csv` with columns:
- `id`: Unique identifier
- `name`: Product name
- `category`: Primary category (can have multiple separated by comma)
- `store`: Store name (Lotte, Superindo, Indomaret, Alfamart)
- `price`: Price as string (e.g., "Rp 3.200")
- `unit`: Unit (e.g., "85g", "1L")
- `location`: Store branch or location
- `updatedAt`: Timestamp of last update

Search logic will match user queries against `name` and `category`.

## Frontend
- Static HTML with JavaScript to load CSV data.
- Core features:
  - Load and parse CSV using PapaParse library.
  - Search bar to filter products by name.
  - Category chips to filter by category.
  - Display product comparison cards with store prices.
  - Highlight cheapest store and price differences.
- Use the existing `haqita-ux.html` mockup as the UI reference.

## Implementation Steps
See `docs/implementation-plan.md` for detailed phased implementation, starting with Lotte scraper.

## Verification
1. Run Python scrapers to generate `data/products.csv`.
2. Open `index.html` in a browser.
3. Search for products and verify comparisons across all four supermarkets.
4. Confirm UI matches the mockup and highlights best deals.

## Notes
- Use the existing `haqita-ux.html` mockup as the UI reference for the static HTML design.
- Keep the CSV model flexible for multiple categories and product metadata.
- Prefer a clean, modern web experience for Jakarta grocery shoppers.

## Deliverables
- `docs/plan.md`
- `docs/scraping.md`
- `docs/implementation-plan.md`
- `scrapers/` Python scripts
- `data/products.csv`
- `index.html` static frontend
- README with local run instructions
