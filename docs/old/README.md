# Haqita - Jakarta Grocery Price Comparison

A simple web app to compare grocery prices across Lotte, Superindo, Indomaret, and Alfamart.

The Lotte scraper extracts promo images directly from HTML (no browser automation) and uses OCR to read product names and prices from the images.

## Running the Scraper

### Docker (recommended)
1. Build the Docker image:
   - `docker build -t haqita-scraper .`
2. Run the scraper using the batch file:
   - `run_scraper.bat` (loads .env automatically and runs Docker)
3. Check the results in `data/products.csv` and `scraper.log`

### Setup
Copy `.env.example` to `.env` and edit it with your values:
```
cp .env.example .env
```

Then update the file with your configuration:
```
LOTTE_OCR_ENGINE=paddle
GOOGLE_API_KEY=your_google_api_key_here
LOTTE_MAX_IMAGES=3
LOTTE_TEST_MODE=false```

The batch file automatically:
- Loads environment variables from `.env`
- Runs Docker with proper configuration
- Saves output to `scraper.log`

### Environment Variables
- `LOTTE_OCR_ENGINE`: Which OCR engine to use (`paddle` or `gemini`) — default is `paddle`
- `GOOGLE_API_KEY`: Your Google Vision API key (required only for `gemini`)
- `LOTTE_MAX_IMAGES`: Limit images processed (optional, default: all images)
- `LOTTE_TEST_MODE`: Use local HTML file instead of web scraping (optional, default: false)

### Capturing Docker Output to Files
- `docker run --rm -v ${PWD}:/app -e LOTTE_TEST_MODE=true haqita-scraper`

## Output and Logging

The scraper generates several types of output for debugging and analysis:

### Data Files
- **`data/products.csv`**: Final scraped product data with columns: id, name, category, store, price, unit, location, updatedAt
- **`data/images/lotte/`**: Downloaded promo images (saved for inspection and debugging)

### API Logs (Gemini Vision OCR)
When using Gemini Vision OCR, the scraper logs all API interactions:
- **`data/logs/gemini_request_YYYYMMDD_HHMMSS.json`**: Full API request payload sent to Google Vision API
- **`data/logs/gemini_response_YYYYMMDD_HHMMSS.json`**: Complete API response from Google Vision API

### Console Output
The scraper provides detailed console logging including:
- Image discovery and filtering progress
- OCR processing status and extracted text samples
- Product parsing results
- File save locations and timestamps

## Using Proxies for Anonymity
To hide your IP address and avoid detection, you can use proxies. The scraper supports proxy configuration via environment variables.

### Setting Up Proxies
1. **Get a Proxy Service**: Use paid proxy services like Bright Data, Oxylabs, or Smart Proxy for reliable residential proxies. Free proxies are often unreliable and may be blocked.

2. **Environment Variables**:
   - For HTTP/HTTPS requests (Requests library):
     - `HTTP_PROXY=http://proxy-server:port`
     - `HTTPS_PROXY=http://proxy-server:port`
   - For Playwright (browser-based scraping):
     - `PLAYWRIGHT_PROXY_SERVER=http://proxy-server:port`
     - `PLAYWRIGHT_PROXY_USERNAME=username` (if required)
     - `PLAYWRIGHT_PROXY_PASSWORD=password` (if required)

3. **Running with Proxies**:
   - Local: Set environment variables before running `python scrapers/lotte.py`
   - Docker: Pass env vars with `-e` flag:
     ```
     docker run --rm -v ${PWD}:/app -e HTTP_PROXY=http://your-proxy:port -e PLAYWRIGHT_PROXY_SERVER=http://your-proxy:port haqita-scraper
     ```

4. **Gemini Vision OCR**:
   - Set `GOOGLE_API_KEY` to a valid Google API key with Vision API enabled.
   - If this key is present, the scraper will call the Gemini Vision OCR endpoint instead of local Tesseract.

5. **Running with Gemini Vision OCR**:
   - Docker: `docker run --rm -v ${PWD}:/app -e GOOGLE_API_KEY=your_key haqita-scraper`

**Note**: Always respect website terms of service and local laws regarding web scraping. Use proxies responsibly.

## Test Mode for Debugging
The scraper includes a test mode that uses local HTML files instead of fetching from the web. This is useful for debugging and development.

### Setting Up Test Mode
1. Place the Lotte promo page HTML in `data/examples/lotte/All Promo Mart.html`
2. Place associated images in `data/examples/lotte/All Promo Mart_files/`
3. Set the environment variable: `LOTTE_TEST_MODE=true`

### Running in Test Mode
- **Local Python**: `LOTTE_TEST_MODE=true python scrapers/lotte.py`
- **Docker**: `docker run --rm -v ${PWD}:/app -e LOTTE_TEST_MODE=true haqita-scraper`

This mode helps debug OCR and parsing without making web requests.

## Project Structure
- `scrapers/`: Python scripts for scraping supermarket data.
- `data/products.csv`: CSV file with scraped product data.
- `data/images/lotte/`: Saved promo images from Lotte scraping (for debugging).
- `index.html`: Static HTML frontend.
- `docs/`: Documentation and plans.
