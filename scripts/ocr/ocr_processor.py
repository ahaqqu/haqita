import base64
import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

OCR_PROMPT = """Extract all product promotions from this Indonesian supermarket brochure image.

Return ONLY a valid JSON array. No explanation. No markdown code fences. Start with [ and end with ].

Each item must follow this exact structure:
{
  "name": "full product name as shown",
  "brand": "brand name if visible, else null",
  "unit": "size as shown (e.g. '85 g', '1.5 L', '6 x 45 ml'), else null",
  "price": <integer in IDR, numbers only, no dots or Rp symbol>,
  "promo": "promo text if any (e.g. 'DAPAT 5 pcs', 'Beli 2 Gratis 1'), else null",
  "period": "validity dates if shown (e.g. '7 - 20 Mei 2026'), else null"
}

Rules:
- price MUST be an integer (3500 not "Rp 3.500"). Indonesian thousands separator is '.' — ignore it.
- If you are not confident about a price, omit that product entirely.
- Extract EVERY product visible, including small-text items.
- Ignore store logos, decorative banners, and page numbers."""


def call_ollama_ocr(image_path: str, cfg: dict) -> list[dict]:
    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": cfg['ocr']['model_ollama'],
        "prompt": OCR_PROMPT,
        "images": [img_b64],
        "stream": False,
        "options": {
            "temperature": cfg['ocr']['temperature'],
            "num_ctx": 8192,
            "seed": 42
        }
    }
    resp = requests.post("http://localhost:11434/api/generate", json=payload,
                         timeout=cfg['ocr']['timeout_seconds'])
    resp.raise_for_status()
    raw_text = resp.json()['response']
    return _parse_ocr_json(raw_text)


def call_gemini_ocr(image_path: str, cfg: dict) -> list[dict]:
    import google.generativeai as genai

    api_key = cfg['ocr'].get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(cfg['ocr']['model_gemini'])

    with open(image_path, 'rb') as f:
        img_bytes = f.read()

    response = model.generate_content([
        {"mime_type": "image/jpeg", "data": img_bytes},
        OCR_PROMPT
    ])
    return _parse_ocr_json(response.text)


def extract_products(image_path: str, cfg: dict) -> list[dict]:
    provider = cfg['ocr'].get('provider', 'ollama')

    for attempt in range(cfg['ocr']['max_retries']):
        try:
            if provider == 'gemini':
                return call_gemini_ocr(image_path, cfg)
            else:
                return call_ollama_ocr(image_path, cfg)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == cfg['ocr']['max_retries'] - 1:
                raise
    return []


def _parse_ocr_json(raw_text: str) -> list[dict]:
    clean = re.sub(r'^```[a-z]*\s*|\s*```$', '', raw_text.strip(), flags=re.MULTILINE)
    match = re.search(r'\[.*\]', clean, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in OCR response: {clean[:200]}")
    return json.loads(match.group(0))


def clean_price(raw) -> int | None:
    if raw is None:
        return None
    s = re.sub(r'[Rr][Pp]\.?\s*', '', str(raw)).strip()
    s = re.sub(r'(\d)\.(\d{3})(?!\d)', r'\1\2', s)
    s = s.replace(',', '').replace(' ', '').replace('.', '')
    try:
        val = int(float(s))
        return val if 100 <= val <= 1_000_000 else None
    except (ValueError, TypeError):
        return None


_UNIT_CORRECTIONS = [
    (r'\bSg\b', '5g'), (r'\bBg\b', '8g'),
    (r'\bIOO\b', '100'), (r'\bI00\b', '100'),
    (r'\bS00\b', '500'), (r'\bSOO\b', '500'),
    (r'\bl\b', '1'),
]


def clean_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    for pattern, replacement in _UNIT_CORRECTIONS:
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
    return s if s else None


def validate_product(raw: dict, image_source: str) -> tuple[dict | None, str | None]:
    name = str(raw.get('name', '')).strip()
    if len(name) < 3:
        return None, 'name_too_short'

    price = clean_price(raw.get('price'))
    if price is None:
        return None, f'price_invalid: {raw.get("price")}'

    return {
        'name': name,
        'brand': str(raw['brand']).strip() if raw.get('brand') else None,
        'unit': clean_unit(raw.get('unit')),
        'price': price,
        'promo': str(raw['promo']).strip() if raw.get('promo') else None,
        'period': str(raw['period']).strip() if raw.get('period') else None,
        'image_source': image_source,
        'ocr_raw_price': str(raw.get('price', '')),
        'ocr_confidence': float(raw.get('ocr_confidence', 1.0)),
    }, None
