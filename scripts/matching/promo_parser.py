"""
Indonesian promo text parser.

Detects promo type and computes effective unit price / unit count.
"""

import re
from dataclasses import dataclass


@dataclass
class PromoResult:
    promo_type: str         # bundle_buy | get_free | discount_pct | discount_fixed | multi_price | single
    display: str            # Original promo text
    unit_count: int         # Effective units received
    effective_unit_price: int


# Ordered patterns — first match wins.
_PATTERNS = [
    # "Beli 2 Gratis 1" / "Beli 3 Gratis 1"
    (r'beli\s+(\d+)\s*(?:gratis|free)\s+(\d+)', 'get_free'),
    # "DAPAT 5 pcs" / "dapat 3 buah" / "2 Pack"
    (r'(?:dapat|get)\s+(\d+)\s*(?:pcs|buah|pack)?', 'bundle_buy'),
    # "2/Rp 10.000" or "3 pcs / Rp15.000"
    (r'(\d+)\s*(?:pcs|buah)?\s*/\s*(?:Rp\.?\s*)?([\d.,]+)', 'multi_price'),
    # "Diskon 20%"
    (r'diskon\s+(\d+)\s*%', 'discount_pct'),
    # "Hemat Rp 5.000"
    (r'hemat\s+(?:Rp\.?\s*)?([\d.,]+)', 'discount_fixed'),
]


def _parse_price(raw: str) -> int:
    """Convert '15.000' or '15,000' to 15000."""
    return int(raw.replace('.', '').replace(',', ''))


def parse_promo(promo_text: str | None, base_price: int) -> PromoResult:
    """
    Returns a PromoResult. Falls back to single-unit if no pattern matches.
    base_price: the price field from OCR (may be total bundle price).
    """
    if not promo_text:
        return PromoResult(
            promo_type='single',
            display='',
            unit_count=1,
            effective_unit_price=base_price,
        )

    for pattern, ptype in _PATTERNS:
        m = re.search(pattern, promo_text, re.IGNORECASE)
        if m:
            if ptype == 'get_free':
                pay = int(m.group(1))
                free = int(m.group(2))
                total = pay + free
                return PromoResult(
                    promo_type='get_free',
                    display=promo_text,
                    unit_count=total,
                    effective_unit_price=max(1, base_price // total),
                )
            elif ptype == 'bundle_buy':
                count = int(m.group(1))
                return PromoResult(
                    promo_type='bundle_buy',
                    display=promo_text,
                    unit_count=count,
                    effective_unit_price=max(1, base_price // count),
                )
            elif ptype == 'multi_price':
                count = int(m.group(1))
                price = _parse_price(m.group(2))
                return PromoResult(
                    promo_type='multi_price',
                    display=promo_text,
                    unit_count=count,
                    effective_unit_price=max(1, price // count),
                )
            elif ptype == 'discount_pct':
                pct = int(m.group(1))
                discounted = max(1, base_price * (100 - pct) // 100)
                return PromoResult(
                    promo_type='discount_pct',
                    display=promo_text,
                    unit_count=1,
                    effective_unit_price=discounted,
                )
            elif ptype == 'discount_fixed':
                saved = _parse_price(m.group(1))
                discounted = max(1, base_price - saved)
                return PromoResult(
                    promo_type='discount_fixed',
                    display=promo_text,
                    unit_count=1,
                    effective_unit_price=discounted,
                )

    return PromoResult(
        promo_type='single',
        display=promo_text,
        unit_count=1,
        effective_unit_price=base_price,
    )


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_MONTHS = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'mei': '05', 'jun': '06', 'jul': '07', 'agu': '08',
    'sep': '09', 'okt': '10', 'nov': '11', 'des': '12',
    'may': '05', 'aug': '08', 'oct': '10', 'dec': '12',
}


def parse_valid_until(period: str | None) -> str | None:
    """
    Extract the end date from a period string.

    Supported formats:
        "7 - 20 Mei 2026"       → "2026-05-20"
        "14-17 Mei 2026"        → "2026-05-17"
        "Berlaku 1-15 Mei 2026" → "2026-05-15"
        "s/d 20 Mei 2026"       → "2026-05-20"
        "Valid until 15 May 2026" → "2026-05-15"
        "20 Mei 2026"           → "2026-05-20"
    """
    if not period:
        return None

    # Range: "7 - 20 Mei 2026", "14-17 Mei 2026", "Berlaku 1-15 Mei 2026"
    m = re.search(
        r'(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(\w+)\s+(\d{4})',
        period,
    )
    if m:
        day = int(m.group(2))
        month_str = m.group(3).lower()[:3]
        year = m.group(4)
        month = _MONTHS.get(month_str)
        if month:
            return f"{year}-{month}-{day:02d}"

    # Single end date: "s/d 20 Mei 2026", "sd. 20 Mei 2026", "sampai 20 Mei 2026"
    m = re.search(
        r'(?:s[/\.]?d|sampai|until)\s+(\d{1,2})\s+(\w+)\s+(\d{4})',
        period,
        re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()[:3]
        year = m.group(3)
        month = _MONTHS.get(month_str)
        if month:
            return f"{year}-{month}-{day:02d}"

    # Bare single date: "20 Mei 2026"
    m = re.search(
        r'(\d{1,2})\s+(\w+)\s+(\d{4})',
        period,
    )
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()[:3]
        year = m.group(3)
        month = _MONTHS.get(month_str)
        if month:
            return f"{year}-{month}-{day:02d}"

    return None
