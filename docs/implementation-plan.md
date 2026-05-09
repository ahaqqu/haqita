# Implementation Plan for HaQita MVP

## Overview
This plan outlines phased implementation of the simplified HaQita grocery price comparison MVP. Focus is on getting prices for **Lotte** supermarket first, then expanding. Each phase is small for easy review and iteration.

## Phase 1: Project Setup and Lotte Scraper (1-2 days)
### Goal
Set up basic project structure and implement a working scraper for Lotte to populate initial CSV data.

### Tasks
1. **Create Project Structure**
   - `scrapers/` folder for Python scripts.
   - `data/` folder for `products.csv`.
   - `index.html` placeholder.
   - `docs/` for documentation.

2. **Implement Lotte Scraper (`scrapers/lotte.py`)**
   - Target: `https://www.lottemart.co.id/all-promo-mart`
   - Scrape product name, price, category, store ("Lotte"), unit, location.
   - Output to `data/products.csv` (create if not exists, append mode).
   - Handle basic HTML parsing with BeautifulSoup.
   - Add error handling and rate limiting.

3. **CSV Schema**
   - Headers: id,name,category,store,price,unit,location,updatedAt
   - Use UUID for id, current timestamp for updatedAt.

4. **Test Scraper**
   - Run `python scrapers/lotte.py`
   - Verify CSV output with sample Lotte products.
   - Check for duplicates and data quality.

### Deliverables
- Working Lotte scraper.
- `data/products.csv` with Lotte data.
- Basic README with run instructions.

### Review Checkpoint
- CSV has 10-20 Lotte products.
- Scraper runs without errors.

## Phase 2: Expand to All Supermarkets (2-3 days)
### Goal
Add scrapers for Alfamart, Superindo, and Indomaret, combining all data into one CSV.

### Tasks
1. **Implement Alfamart Scraper (`scrapers/alfamart.py`)**
   - Target: `https://www.alfamart.co.id/promo/jsm`
   - Similar structure to Lotte scraper.

2. **Implement Superindo Scraper (`scrapers/superindo.py`)**
   - Target: `https://www.superindo.co.id/promosi/katalog-super-hemat`
   - Handle dynamic content if needed (use requests-html or Selenium).

3. **Implement Indomaret Scraper (`scrapers/indomaret.py`)**
   - Target: KlikIndomaret app API or brochure PDFs.
   - If API, reverse-engineer; else, OCR PDFs.

4. **Master Scraper Script (`scrapers/run_all.py`)**
   - Run all scrapers sequentially.
   - Append to CSV without overwriting.

5. **Data Normalization**
   - Standardize category names across stores.
   - Handle multiple categories per item.

### Deliverables
- All four scrapers working.
- `data/products.csv` with data from all supermarkets.
- Updated README.

### Review Checkpoint
- CSV has products from all four stores.
- No major data inconsistencies.

## Phase 3: Static HTML Frontend (2-3 days)
### Goal
Build static HTML to read CSV and display comparisons, inspired by `haqita-ux.html`.

### Tasks
1. **Set Up `index.html`**
   - Include PapaParse for CSV parsing.
   - Basic structure: header, search bar, category chips, product list.

2. **JavaScript Logic**
   - Load CSV on page load.
   - Implement search by name.
   - Filter by category.
   - Display product cards with store prices.
   - Highlight cheapest store and price differences.

3. **Styling**
   - Copy CSS from `haqita-ux.html` for mobile-first design.
   - Make responsive for local viewing.

4. **Features**
   - Sort by price.
   - Show best deal card.

### Deliverables
- Functional `index.html` that displays CSV data.
- Search and filter working.

### Review Checkpoint
- Open `index.html` locally and see product comparisons.
- UI resembles mockup.

## Phase 4: Testing, Refinements, and Polish (1-2 days)
### Goal
Test end-to-end, fix issues, and add final touches.

### Tasks
1. **End-to-End Testing**
   - Run all scrapers, then open HTML.
   - Verify search, filters, and comparisons.

2. **Error Handling**
   - Handle missing CSV or parsing errors in JS.
   - Add loading indicators.

3. **Data Quality**
   - Clean CSV for duplicates.
   - Add sample data if scrapers fail.

4. **Documentation**
   - Update README with full setup.
   - Add troubleshooting notes.

### Deliverables
- Complete MVP ready for local use.
- Final docs.

### Review Checkpoint
- MVP works smoothly for price comparisons.

## General Notes
- **Tools**: Python 3.8+, BeautifulSoup, requests, PapaParse (CDN).
- **Dependencies**: `pip install requests beautifulsoup4`
- **Version Control**: Commit after each phase.
- **Risks**: Websites may change; have fallbacks like sample data.
- **Timeline**: Total 6-10 days for MVP.

## Next Steps
Start with Phase 1. Ready to implement? Let me know!