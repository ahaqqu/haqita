# Scraping Techniques for Jakarta Supermarkets

This document outlines detailed scraping techniques for collecting price data from Lotte, Superindo, Indomaret, and Alfamart. These methods focus on reliability, legal compliance, and efficiency. Always respect robots.txt, rate-limit requests, and avoid overloading servers.

## General Best Practices
- **Prefer APIs over HTML**: Look for JSON endpoints in browser devtools network tab.
- **Use headless browsers**: For dynamic content, use Playwright or Puppeteer.
- **Normalize data**: Standardize product names, categories, and prices across stores.
- **Handle rate limits**: Implement delays (e.g., 1-2 seconds between requests).
- **Cache results**: Store scraped data in your database to avoid re-scraping.
- **Legal note**: Scraping may violate terms of service; consider partnerships or official APIs first.

## Alfamart Scraping
### Target Pages
- Main promo listing: `https://www.alfamart.co.id/promo/jsm`
- Other promo categories: `/promo/psm`, `/promo/tebus-murah`, `/promo/member-only`, `/promo/house-brand`
- Promo detail pages: `/promo-detail/{slug}` (e.g., `/promo-detail/body-care-fair-1`)

### What to Scrape
- Product name (e.g., "Indomie Goreng 85g")
- Promo price (e.g., "Rp 3.200")
- Original price (e.g., "Rp 3.500")
- Discount percentage or savings
- Promo period (e.g., "s/d 4 Mei 2025")
- Store/branch info if available
- Product category (e.g., "Sembako", "Minuman")

### Recommended Approach
1. **Inspect for APIs**: Open `/promo/jsm` in browser devtools. Check Network tab for XHR requests returning JSON data (e.g., product lists). If found, use that endpoint directly.
2. **HTML Scraping**: If no API, parse the HTML for product cards. Use selectors like `.promo-item` or similar. Extract text from elements containing name, price, and details.
3. **Headless Browser**: For dynamic content, use Playwright to load the page and extract rendered elements.
4. **Pagination**: Promo pages may have multiple pages; scrape all by following "next" links or API pagination.
5. **Data Extraction**: Use libraries like Cheerio (Node.js) or BeautifulSoup (Python) for HTML parsing. For JS-heavy sites, Selenium or Playwright.

### Example Code Snippet (Node.js with Cheerio)
```javascript
const axios = require('axios');
const cheerio = require('cheerio');

async function scrapeAlfamartPromo(url) {
  const { data } = await axios.get(url);
  const $ = cheerio.load(data);
  const products = [];
  $('.promo-item').each((i, el) => {
    const name = $(el).find('.product-name').text().trim();
    const promoPrice = $(el).find('.promo-price').text().trim();
    const originalPrice = $(el).find('.original-price').text().trim();
    products.push({ name, promoPrice, originalPrice });
  });
  return products;
}
```

## Superindo Scraping
### Target Pages
- Promo catalog: `https://www.superindo.co.id/promosi/katalog-super-hemat`
- Other promos: `/promosi/promo-partner`, `/promosi/promo-koran`
- Detail pages: `/home/hit/{id}` (e.g., `/home/hit/2344`)

### What to Scrape
- Product name (e.g., "Indomie Mi Goreng Jumbo")
- Price (e.g., "Rp 12.570")
- Discount details (e.g., "Beli 3 Lebih Hemat")
- Category or promo type (e.g., "Super Hemat")
- Store branch if specified

### Recommended Approach
1. **API Inspection**: Check for JSON endpoints in Network tab when loading promo pages.
2. **HTML Parsing**: Scrape product cards from catalog pages. Look for classes like `.promo-card` or `.product-item`.
3. **Dynamic Content**: Use headless browser if content loads via JS.
4. **Pagination**: Handle multiple promo sections or pages.
5. **Data Extraction**: Similar to Alfamart, use Cheerio or BeautifulSoup.

### Example Code Snippet (Python with BeautifulSoup)
```python
import requests
from bs4 import BeautifulSoup

def scrape_superindo_promo(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    products = []
    for item in soup.find_all('div', class_='promo-card'):
        name = item.find('h3').text.strip()
        price = item.find('span', class_='price').text.strip()
        products.append({'name': name, 'price': price})
    return products
```

## Indomaret Scraping
### Target Pages
- Corporate site: `https://www.indomaret.co.id/` (limited price data)
- Shopping app/site: `klikindomaret.com` or KlikIndomaret app
- Brochure PDFs: Download from promo sections and OCR

### What to Scrape
- Product listings from search/results
- Promo prices from brochures or app
- Product name, price, category
- Promo details (e.g., "Diskon 20%")

### Recommended Approach
1. **App/API Reverse Engineering**: Use tools like Charles Proxy or mitmproxy to intercept KlikIndomaret app traffic. Find search/product APIs returning JSON.
2. **Web Scraping**: If web version exists, scrape product pages.
3. **OCR for Brochures**: Download promo PDFs/images from Indomaret site. Use Tesseract or Google Vision API to extract text (product names, prices).
4. **Data Extraction**: For APIs, parse JSON directly. For images, preprocess (crop, enhance) before OCR.

### Example Code Snippet (Python with Tesseract for OCR)
```python
import pytesseract
from PIL import Image
import requests

def scrape_indomaret_brochure(image_url):
    response = requests.get(image_url)
    img = Image.open(BytesIO(response.content))
    text = pytesseract.image_to_string(img)
    # Parse text for product names and prices
    # (Custom logic needed based on brochure layout)
    return extracted_data
```

## Lotte Scraping
### Target Pages
- Main site: `https://www.lottemart.co.id/`
- Promo listings: `/all-promo-mart`, `/all-promo-grosir`
- Online order: `https://order.lottemart.co.id/`

### What to Scrape
- Product name (e.g., "Choice L Pembersih Lantai")
- Price (e.g., "Rp 34.500")
- Store type (Lotte Mart or Lotte Grosir)
- Promo details and branch info

### Why OCR
Lotte promo pages often render offers as flyer images or image-based catalogs instead of plain text. Use OCR to extract text from screenshots or flyer images.

### Recommended Approach
1. **Headless Browser**: Use Playwright to render the page and capture the visible promo content.
2. **Screenshot or download images**: Save the rendered promo visuals for OCR.
3. **OCR**: Use Tesseract via `pytesseract` to extract text from the image.
4. **Parse OCR text**: Extract product names and `Rp` price patterns from the OCR output.
5. **Save results**: Write the structured products to a CSV file.

### Example Code Snippet (Python with Playwright + Tesseract)
```python
import re
from PIL import Image
import pytesseract
from playwright.sync_api import sync_playwright

PRICE_PATTERN = re.compile(r'Rp\s*[\d\.,]+', re.I)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://www.lottemart.co.id/all-promo-mart', wait_until='networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='data/lotte_screenshot.png', full_page=True)
    browser.close()

text = pytesseract.image_to_string(Image.open('data/lotte_screenshot.png'))
lines = [line.strip() for line in text.splitlines() if line.strip()]
products = []
previous_line = None
for line in lines:
    match = PRICE_PATTERN.search(line)
    if match:
        products.append({'name': previous_line or 'Lotte promo', 'price': match.group(0)})
    previous_line = line
```

### Notes
- If Playwright is unavailable, attempt to find flyer or promo image URLs with BeautifulSoup and OCR those images directly.
- OCR text will often need manual cleanup or more precise parsing logic based on the flyer layout.

## Implementation in Spring Boot Backend
- Create a `@Scheduled` service to run scrapers periodically (e.g., daily).
- Store scraped data in PostgreSQL tables (products, prices, stores).
- Use JPA entities to map data.
- Handle errors and retries in scraping logic.
- Expose scraped data via REST APIs for the Flutter frontend.

## Next Steps
- Test scrapers on a single page first.
- Implement rate limiting and error handling.
- Integrate into the Spring Boot app as a data ingestion service.