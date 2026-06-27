import json
import logging
import re

logger = logging.getLogger(__name__)


def extract_products(image_path: str, cfg: dict) -> list[dict]:
    retries = cfg['ocr'].get('gemini', {}).get('max_retries', 2)

    from .gemini_client import call_gemini_ocr

    for attempt in range(retries):
        try:
            return call_gemini_ocr(image_path, cfg)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == retries - 1:
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

# Extracts the first unit-like token from a product name as a fallback when
# the OCR model returns null for the dedicated unit field.
_UNIT_EXTRACT_RE = re.compile(
    r'\b(\d+(?:[.,]\d+)?(?:\s*[×xX]\s*\d+(?:[.,]\d+)?)?)\s*'
    r'(kg|g|gram|ml|l|liter|lt|pcs|pack|sachet|bks|bungkus|botol|kaleng|'
    r'pck|pch|tub|box|bag|set|s)\b',
    re.IGNORECASE,
)


def _extract_unit_from_name(name: str | None) -> str | None:
    """Return the first unit-like token found in the product name, or None."""
    if not name:
        return None
    m = _UNIT_EXTRACT_RE.search(name)
    if not m:
        return None
    qty = m.group(1).replace('×', 'x').lower()
    unit = m.group(2).lower()
    # Normalise "liter" variants to "l" for consistency with parse_unit_to_base
    if unit in ('liter', 'lt'):
        unit = 'l'
    return f"{qty} {unit}".strip()


def clean_unit(raw: str | None, name: str | None = None) -> str | None:
    if raw:
        s = raw.strip()
        for pattern, replacement in _UNIT_CORRECTIONS:
            s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
        return s if s else None
    # Fallback: many brochures put the size inside the product name.
    return _extract_unit_from_name(name)


def _normalize_promo(promo) -> list[str] | None:
    """Normalize promo to a list of strings or None."""
    if not promo:
        return None
    if isinstance(promo, list):
        result = [str(p).strip() for p in promo if p and str(p).strip()]
        return result if result else None
    return [str(promo).strip()]


def validate_product(raw: dict, image_source: str) -> tuple[dict | None, str | None]:
    name = str(raw.get('name', '')).strip()
    if len(name) < 3:
        return None, 'name_too_short'

    price = clean_price(raw.get('price'))
    if price is None:
        return None, f'price_invalid: {raw.get("price")}'

    unit = clean_unit(raw.get('unit'), name)
    if not unit:
        return None, 'unit_missing'

    return {
        'name': name,
        'brand': str(raw['brand']).strip() if raw.get('brand') else None,
        'unit': unit,
        'price': price,
        'promo': _normalize_promo(raw.get('promo')),
        'period': str(raw['period']).strip() if raw.get('period') else None,
        'image_source': image_source,
        'ocr_raw_price': str(raw.get('price', '')),
        'ocr_confidence': float(raw.get('ocr_confidence', 1.0)),
    }, None
