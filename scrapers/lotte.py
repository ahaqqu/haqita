import csv
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import base64
import requests
from bs4 import BeautifulSoup
from PIL import Image
import json
import numpy as np

DATA_DIR = Path('data')
IMAGES_DIR = DATA_DIR / 'images' / 'lotte'
LOGS_DIR = DATA_DIR / 'logs'
CSV_PATH = DATA_DIR / 'products.csv'
URL = 'https://www.lottemart.co.id/all-promo-mart'
PRICE_PATTERN = re.compile(r'Rp\s*[\d\.,]+', re.I)

# OCR configuration
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
LOTTE_OCR_ENGINE = os.getenv('LOTTE_OCR_ENGINE', 'paddle').lower()
OCR_ENGINE = None
GEMINI_VISION_ENDPOINT = 'https://vision.googleapis.com/v1/images:annotate'

# Limit number of images to process (for development/debugging)
MAX_IMAGES = int(os.getenv('LOTTE_MAX_IMAGES', '0'))  # 0 = no limit

# Test mode - use local HTML file instead of fetching from web
LOCAL_HTML_PATH = DATA_DIR / 'examples' / 'lotte' / 'All Promo Mart.html'

# Headers to simulate real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Proxy configuration (set via environment variables)
PROXY_CONFIG = {}
if os.getenv('HTTP_PROXY'):
    PROXY_CONFIG['http'] = os.getenv('HTTP_PROXY')
if os.getenv('HTTPS_PROXY'):
    PROXY_CONFIG['https'] = os.getenv('HTTPS_PROXY')


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_paddle_ocr():
    global OCR_ENGINE
    if OCR_ENGINE is None:
        import paddle
        print(f"Paddle version: {paddle.__version__}")
        # Skip run_check() as it can hang during initialization
        # paddle.utils.run_check()
        import paddleocr
        print(f"PaddleOCR version: {paddleocr.__version__}")
        
        from paddleocr import PaddleOCR
        print('Initializing PaddleOCR with CPU-only mode...')
        OCR_ENGINE = PaddleOCR(
            lang="id",
            ocr_version="PP-OCRv4",  # Use more stable v4 instead of v5
            use_gpu=False,  # Explicitly disable GPU to avoid CUDA/MKLDNN conflicts
            enable_mkldnn=False,  # Disable MKLDNN to prevent PIR crash
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            det_model_dir=None,  # Use default models
            rec_model_dir=None,
        )
        print('PaddleOCR initialized successfully')
    return OCR_ENGINE


def paddle_ocr_text(image_bytes: bytes) -> str:
    image = Image.open(BytesIO(image_bytes)).convert('RGB')
    print('Initializing paddle...')
    ocr = get_paddle_ocr()
    print('Starting predict...')
    result = ocr.predict(np.asarray(image))
    print('Completed predict')
    lines = []
    for page in result:
        print(f'Result for page: {page}')
        page.print()  
        page.save_to_img("output")  
        page.save_to_json("output")  
        for item in page:
            lines.append(item[1][0])
    return '\n'.join(lines)


def download_image(url: str) -> bytes:
    if url.startswith('//'):
        url = 'https:' + url
    if url.startswith('/'):  # relative path
        url = 'https://www.lottemart.co.id' + url
    response = requests.get(url, headers=HEADERS, proxies=PROXY_CONFIG)
    response.raise_for_status()
    image_bytes = response.content
    # Save image to images directory
    filename = url.split('/')[-1].split('?')[0]  # Extract filename from URL
    if not filename:
        filename = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    image_path = IMAGES_DIR / filename
    image_path.write_bytes(image_bytes)
    print(f'Image saved to: {image_path}')
    return image_bytes


def gemini_vision_text(image_bytes: bytes) -> str:
    if not GOOGLE_API_KEY:
        raise RuntimeError('GOOGLE_API_KEY environment variable is required for OCR processing')

    print('Using Gemini Vision OCR via Google Vision API...')
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    payload = {
        'requests': [
            {
                'image': {'content': encoded_image},
                'features': [{'type': 'TEXT_DETECTION', 'maxResults': 1}]
            }
        ]
    }
    
    # Log the request
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    request_log_path = LOGS_DIR / f'gemini_request_{timestamp}.json'
    with request_log_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f'Gemini request logged to: {request_log_path}')
    
    response = requests.post(
        f'{GEMINI_VISION_ENDPOINT}?key={GOOGLE_API_KEY}',
        json=payload,
        headers={'Content-Type': 'application/json'},
        proxies=PROXY_CONFIG or None,
        timeout=120,
    )
    
    # Log the response (even if it fails)
    response_log_path = LOGS_DIR / f'gemini_response_{timestamp}.json'
    try:
        response_data = response.json()
    except:
        response_data = {'error': 'Failed to parse JSON response', 'text': response.text}
    
    with response_log_path.open('w', encoding='utf-8') as f:
        json.dump({
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'data': response_data
        }, f, indent=2, ensure_ascii=False)
    print(f'Gemini response logged to: {response_log_path}')
    
    response.raise_for_status()
    
    if not response_data.get('responses'):
        return ''
    annotation = response_data['responses'][0].get('fullTextAnnotation') or {}
    return annotation.get('text', '')


def image_to_text(image_bytes: bytes) -> str:
    print(f'Using OCR engine: {LOTTE_OCR_ENGINE}')
    if LOTTE_OCR_ENGINE == 'paddle':
        return paddle_ocr_text(image_bytes)
    if LOTTE_OCR_ENGINE == 'gemini':
        return gemini_vision_text(image_bytes)
    raise RuntimeError(
        f'Unsupported OCR engine: {LOTTE_OCR_ENGINE}. Use LOTTE_OCR_ENGINE=paddle or LOTTE_OCR_ENGINE=gemini.'
    )


def parse_ocr_text(text: str) -> list:
    print(f'OCR extracted text length: {len(text)} characters')
    print(f'First 500 characters of OCR text: {text[:500]}...')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    print(f'Found {len(lines)} non-empty lines after splitting')
    products = []
    previous_line = None
    for i, line in enumerate(lines):
        match = PRICE_PATTERN.search(line)
        if match:
            price = match.group(0).replace(' ', '')
            name = previous_line if previous_line and 'Rp' not in previous_line else 'Lotte promo'
            product = {
                'id': str(uuid.uuid4()),
                'name': name,
                'category': 'General',
                'store': 'Lotte',
                'price': price,
                'unit': '',
                'location': 'Nasional',
                'updatedAt': datetime.now().isoformat()
            }
            products.append(product)
            print(f'Product found on line {i}: {name} - {price}')
        previous_line = line
    print(f'Total products parsed: {len(products)}')
    return products


def find_promo_images(html: str) -> list:
    soup = BeautifulSoup(html, 'html.parser')
    urls = set()
    print('Searching for promo images in HTML...')
    
    # Find img tags - only process images, not PDFs
    img_count = 0
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src')
        if src:
            img_count += 1
            print(f'Found img src: {src}')
            if any(token in src.lower() for token in ['promo', 'flyer', 'catalog', 'katalog', 'jpg', 'png', 'jpeg']):
                urls.add(src)
                print(f'  -> Matched promo keyword: {src}')
    
    print(f'Total images found: {img_count}')
    print(f'Promo image URLs collected: {len(urls)}')
    for url in urls:
        print(f'  - {url}')
    
    return list(urls)


def write_products(products: list):
    ensure_data_dir()
    write_header = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0
    with CSV_PATH.open('a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'name', 'category', 'store', 'price', 'unit', 'location', 'updatedAt']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for product in products:
            writer.writerow(product)


def scrape_lotte():
    ensure_data_dir()
    products = []

    # Check for test mode
    test_mode = os.getenv('LOTTE_TEST_MODE', 'false').lower() == 'true'

    if test_mode:
        print('TEST MODE: Using local HTML file for debugging')
        if not LOCAL_HTML_PATH.exists():
            print(f'Local HTML file not found: {LOCAL_HTML_PATH}')
            return
        html_content = LOCAL_HTML_PATH.read_text(encoding='utf-8')
        print('Loaded local HTML, searching for promo images...')
        promo_urls = find_promo_images(html_content)
        
        # Apply image limit if set
        if MAX_IMAGES > 0:
            promo_urls = promo_urls[:MAX_IMAGES]
            print(f'Limited to first {MAX_IMAGES} images for processing')
        
        # For test mode, also try to load the local images
        for url in promo_urls:
            try:
                # Convert relative URLs to local file paths
                if url.startswith('./All Promo Mart_files/'):
                    local_image_path = LOCAL_HTML_PATH.parent / 'All Promo Mart_files' / url.split('/')[-1]
                    if local_image_path.exists():
                        print(f'Loading local image: {local_image_path}')
                        image_bytes = local_image_path.read_bytes()
                        if len(image_bytes) > 750000:
                            print(f"Byte is greater than 750000: {len(image_bytes)}")
                            text = image_to_text(image_bytes)
                            print('OCR completed for local image.')
                            products.extend(parse_ocr_text(text))
                        else:
                            print(f"Byte is not greater than 750000: {len(image_bytes)}")
                    else:
                        print(f'Local image not found: {local_image_path}')
                else:
                    print(f'Skipping non-local URL: {url}')
            except Exception as exc:
                print('Failed to process local image:', url, exc)
    else:
        # HTML extraction mode only - no Playwright
        print('Extracting promo images from HTML...')
        response = requests.get(URL, headers=HEADERS, proxies=PROXY_CONFIG)
        response.raise_for_status()
        image_urls = find_promo_images(response.text)
        print(f'Found {len(image_urls)} potential promo image URLs')
        
        # Apply image limit if set
        if MAX_IMAGES > 0:
            image_urls = image_urls[:MAX_IMAGES]
            print(f'Limited to first {MAX_IMAGES} images for processing')
        
        for image_url in image_urls:
            try:
                print('Processing image:', image_url)
                image_bytes = download_image(image_url)
                print(f'Downloaded image, size: {len(image_bytes)} bytes')
                text = image_to_text(image_bytes)
                print('OCR completed for image.')
                products.extend(parse_ocr_text(text))
            except Exception as exc:
                print('Failed to process image:', image_url, exc)

    if not products:
        print('No products found. OCR results may need refinement.')
        return

    print(f'Writing {len(products)} products to CSV...')
    write_products(products)
    print(f'Scraped {len(products)} products from Lotte.')


if __name__ == '__main__':
    scrape_lotte()
