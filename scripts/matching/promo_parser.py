"""
Indonesian promo text parser.

Detects promo type and computes effective unit price / unit count.

Effective unit price math:
- bundle_buy / get_free / multi_price: division (per-piece price from total bundle)
- discount_pct / discount_fixed: NO math. The OCR captures the post-discount
  price in the `price` field per the OCR prompt rules, so applying the
  discount again would double-discount and produce a too-low value.
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
    # "Beli 2 Gratis 1" / "Beli 3 Gratis 1" / "Buy 1 Get 1"
    (r'(?:beli|buy)\s+(\d+)\s*(?:gratis|free|get)\s+(\d+)', 'get_free'),
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


def _parse_single_promo(promo_text: str, base_price: int) -> PromoResult:
    """Parse a single promo text string and return PromoResult."""
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
                return PromoResult(
                    promo_type='discount_pct',
                    display=promo_text,
                    unit_count=1,
                    effective_unit_price=base_price,
                )
            elif ptype == 'discount_fixed':
                saved = _parse_price(m.group(1))
                return PromoResult(
                    promo_type='discount_fixed',
                    display=promo_text,
                    unit_count=1,
                    effective_unit_price=base_price,
                )

    return PromoResult(
        promo_type='single',
        display=promo_text,
        unit_count=1,
        effective_unit_price=base_price,
    )


def parse_promo(promo_text: str | list[str] | None, base_price: int) -> PromoResult:
    """
    Returns a PromoResult. Falls back to single-unit if no pattern matches.
    base_price: the price field from OCR.

    For bundle promos (get_free / bundle_buy / multi_price), base_price is the
    total bundle price from the brochure and we divide it by the unit count.

    For discount promos (discount_pct / discount_fixed), base_price is already
    the post-discount price captured by the OCR (see gemini.py prompt). We do
    not apply any further math — using the OCR price as-is is the end price.

    Accepts a single string, a list of strings, or None.
    When given a list, parses each item independently and returns the result
    with the lowest effective_unit_price (best deal for customer).
    """
    if not promo_text:
        return PromoResult(
            promo_type='single',
            display='',
            unit_count=1,
            effective_unit_price=base_price,
        )

    # Normalize to list
    if isinstance(promo_text, str):
        promo_list = [promo_text]
    else:
        promo_list = [p for p in promo_text if p and str(p).strip()]

    if not promo_list:
        return PromoResult(
            promo_type='single',
            display='',
            unit_count=1,
            effective_unit_price=base_price,
        )

    # Parse each promo string and pick the best deal
    results = [_parse_single_promo(p, base_price) for p in promo_list]

    # Filter out 'single' type (no match) if we have any real matches
    matched = [r for r in results if r.promo_type != 'single']
    if matched:
        best = min(matched, key=lambda r: r.effective_unit_price)
    else:
        best = results[0]

    # Join all promo texts for display
    display = ", ".join(promo_list)

    return PromoResult(
        promo_type=best.promo_type,
        display=display,
        unit_count=best.unit_count,
        effective_unit_price=best.effective_unit_price,
    )


# ---------------------------------------------------------------------------
# Promo normalization and categorization (for UI display)
# ---------------------------------------------------------------------------

_TITLE_CASE = {
    'diskon': 'Diskon',
    'ekstra': 'Ekstra',
    'stiker': 'Stiker',
    'gratis': 'Gratis',
    'hemat': 'Hemat',
    'lebih': 'Lebih',
    'seharga': 'Seharga',
    'harga': 'Harga',
    'spesial': 'Spesial',
    'spesial!': 'Spesial!',
    'promo': 'Promo',
    'super': 'Super',
    'mulai': 'Mulai',
    'beli': 'Beli',
    'satuan': 'Satuan',
    'anggota': 'Anggota',
    'khusus': 'Khusus',
    'member': 'Member',
    'special': 'Special',
    'price': 'Price',
    'baru': 'Baru',
    'pilihan': 'Pilihan',
    'segar': 'Segar',
    'minggu': 'Minggu',
    'ini': 'Ini',
    'fresh': 'Fresh',
    'deals': 'Deals!',
    'deals!': 'Deals!',
    'pwp': 'PWP',
    'maks': 'Maks.',
    'maks.': 'Maks.',
    'max': 'Maks.',
    'extra': 'Ekstra',
    'anti': 'Anti',
    'bocor': 'Bocor',
    'serap': 'Serap',
    'semua': 'Semua',
    'rasa': 'Rasa',
    'karton': 'Karton',
    'isi': 'Isi',
    'tpk': 'Tpk',
    'produk': 'Produk',
    'alami': 'Alami',
    'naturally': 'Naturally',
    'apel': 'Apel',
    'fuji': 'Fuji',
    'deal': 'Deal',
}

_QTY_UNITS = {
    'pch', 'pck', 'box', 'btl', 'bag', 'psg', 'bdd', 'klg',
    'krt', 'pot', 'sak', 'sct', 'tpk', 'tub',
}

def _title_case_promo(text: str) -> str:
    """Apply title casing to known promo words while preserving numbers/prices."""
    words = text.split()
    result = []
    for w in words:
        # Preserve numbers and prices
        if re.match(r'^[\d.,]+$', w):
            result.append(w)
        elif re.match(r'^\d+%$', w):
            result.append(w)
        elif re.match(r'^\d', w):
            result.append(w)
        else:
            lower = w.lower()
            if lower in _TITLE_CASE:
                result.append(_TITLE_CASE[lower])
            elif len(w) > 1 and w.isupper():
                result.append(w.capitalize())
            else:
                result.append(w)
    return ' '.join(result)


def normalize_promo_text(text: str) -> list[str]:
    """
    Normalize a promo text string into clean, title-cased segment(s).

    Returns a list of one or more normalized promo strings.
    Splits composite promos like 'DISKON 20% EKSTRA STIKER' into separate entries.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Split composite promos: "DISKON X% EKSTRA STIKER" → ["Diskon X%", "Ekstra Stiker"]
    m = re.match(r'(DISKON\s+\d+%)\s+(EKSTRA\s+STIKER)', text, re.IGNORECASE)
    if m:
        return [_title_case_promo(m.group(1)), _title_case_promo(m.group(2))]

    m = re.match(r'(HARGA\s+SPESIAL)\s+(EKSTRA\s+STIKER)', text, re.IGNORECASE)
    if m:
        return [_title_case_promo(m.group(1)), _title_case_promo(m.group(2))]

    return [_title_case_promo(text)]


def categorize_promo(text: str) -> str:
    """
    Categorize a single normalized promo string into a promo type.

    Returns one of: discount_pct, discount_fixed, bogo, bundle,
                     member_price, promo_price, freebie, quantity_limit, special
    """
    lower = text.lower().strip()

    if re.match(r'^diskon\s+\d+%', lower):
        return 'discount_pct'
    if re.match(r'^hemat\s+\d+%', lower):
        return 'discount_pct'

    if re.match(r'^\d+\s+gratis\s+\d+', lower):
        return 'bogo'
    if re.match(r'beli\s+\d+\s+gratis\s+\d+', lower):
        return 'bogo'
    if re.match(r'gratis\s+\d+\s*\(', lower):
        return 'bogo'
    if lower == 'gratis':
        return 'bogo'

    if 'khusus member' in lower:
        return 'member_price'
    if 'member special price' in lower:
        return 'member_price'
    if 'ekstra diskon member' in lower:
        return 'member_price'
    if 'pwp' == lower or lower.startswith('pwp '):
        return 'member_price'

    if lower.startswith('gratis jasa'):
        return 'freebie'
    if lower.startswith('gratis es'):
        return 'freebie'
    if lower.startswith('disertai pembelian'):
        return 'freebie'

    if re.match(r'^maks\.?\s+\d+\s+[a-z]', lower):
        return 'quantity_limit'
    if text.strip().startswith('MAX'):
        return 'quantity_limit'

    if re.match(r'^hemat\s+rp', lower):
        return 'discount_fixed'
    if re.match(r'^beli\s+\d+\s+rp', lower):
        return 'discount_fixed'
    if re.match(r'^[\d]+\s*&\s*[\d]+\s+\w+', lower):
        return 'discount_fixed'
    if lower.startswith('harga promo '):
        return 'discount_fixed'

    if 'harga spesial' in lower:
        return 'promo_price'
    if 'harga mulai' in lower:
        return 'promo_price'
    if 'super promo' in lower:
        return 'promo_price'
    if 'promo 1 hari' in lower:
        return 'promo_price'
    if 'super deal' in lower:
        return 'promo_price'
    if 'fresh deals' in lower:
        return 'promo_price'
    if 'pilihan segar' in lower:
        return 'promo_price'

    if re.match(r'^\d+\s+lebih\s+hemat', lower):
        return 'bundle'
    if re.match(r'^\d+\s+seharga', lower):
        return 'bundle'
    if re.match(r'beli\s+\d+\s+harga\s+satuan', lower):
        return 'bundle'
    if re.match(r'beli\s+\d+\s+lebih\s*!?', lower):
        return 'bundle'
    if 'beli banyak lebih hemat' in lower:
        return 'bundle'
    if 'lebih hemat' == lower or 'lebih hemat!' == lower:
        return 'bundle'
    if re.match(r'^ekstra stiker', lower):
        return 'bundle'
    if re.match(r'^extra stiker', lower):
        return 'bundle'
    if re.match(r'^extra \+?\d+\s+pcs', lower):
        return 'bundle'
    if 'ekstra serap' in lower:
        return 'bundle'
    if re.match(r'^ekstra \+?\d+\s+pcs', lower):
        return 'bundle'
    if 'karton isi' in lower:
        return 'bundle'
    if lower == 'ekstra diskon':
        return 'promo_price'

    if 'anti bocor' in lower:
        return 'special'
    if 'semua rasa' in lower:
        return 'special'
    if 'produk baru' in lower:
        return 'special'
    if lower.startswith('naturally '):
        return 'special'

    return 'special'


def standardize_promo_list(promos: list[str] | None) -> dict | None:
    """
    Standardize a list of promo strings into a structured dictionary.

    Given the raw promo strings from a snapshot, returns:
    {
      "normalized": ["Diskon 20%", "Ekstra Stiker"],
      "types": ["discount_pct", "bundle"],
      "best_type": "discount_pct",
      "discount_pct": 20,
      "max_qty": 4,
      "display_summary": "Diskon 20%"
    }

    Returns None for empty/null input.
    """
    if not promos:
        return None

    # Normalize to list
    if isinstance(promos, str):
        promo_list = [promos]
    else:
        promo_list = [p for p in promos if p and str(p).strip()]

    if not promo_list:
        return None

    all_normalized: list[str] = []
    all_types: list[str] = []
    discount_pct: int | None = None
    max_qty: int | None = None

    for raw in promo_list:
        segments = normalize_promo_text(raw)
        for seg in segments:
            all_normalized.append(seg)
            cat = categorize_promo(seg)
            all_types.append(cat)

            if cat == 'discount_pct':
                m = re.search(r'(\d+)%', seg)
                if m:
                    val = int(m.group(1))
                    if discount_pct is None or val > discount_pct:
                        discount_pct = val

            if cat == 'quantity_limit':
                m = re.search(r'maks\.?\s*(\d+)', seg.lower())
                if m:
                    val = int(m.group(1))
                    if max_qty is None or val > max_qty:
                        max_qty = val

    if not all_normalized:
        return None

    type_priority = {
        'discount_pct': 0,
        'member_price': 1,
        'bogo': 2,
        'promo_price': 3,
        'discount_fixed': 4,
        'bundle': 5,
        'freebie': 6,
        'quantity_limit': 7,
        'special': 8,
    }
    best_type = min(all_types, key=lambda t: type_priority.get(t, 99))
    display_summary = all_normalized[0]

    return {
        'normalized': all_normalized,
        'types': all_types,
        'best_type': best_type,
        'discount_pct': discount_pct,
        'max_qty': max_qty,
        'display_summary': display_summary,
    }


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_MONTHS = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'mei': '05', 'jun': '06', 'jul': '07', 'agu': '08',
    'sep': '09', 'okt': '10', 'nov': '11', 'des': '12',
    'may': '05', 'aug': '08', 'oct': '10', 'dec': '12',
}


def _to_iso(day: int, month_str: str, year: str) -> str | None:
    """Convert day/month/year to ISO date string."""
    month = _MONTHS.get(month_str.lower()[:3])
    if month:
        return f"{year}-{month}-{day:02d}"
    return None


def parse_period(period: str | None) -> tuple[str | None, str | None]:
    """
    Parse a period string into (valid_from, valid_until) as ISO strings.

    Supported formats:
        "7 - 20 Mei 2026"       → ("2026-05-07", "2026-05-20")
        "14-17 Mei 2026"        → ("2026-05-14", "2026-05-17")
        "Berlaku 1-15 Mei 2026" → ("2026-05-01", "2026-05-15")
        "s/d 20 Mei 2026"       → (None, "2026-05-20")
        "Valid until 15 May 2026" → (None, "2026-05-15")
        "20 Mei 2026"           → (None, "2026-05-20")

    Returns (None, None) if no date can be parsed.
    """
    if not period:
        return None, None

    # Range: "7 - 20 Mei 2026", "14-17 Mei 2026", "Berlaku 1-15 Mei 2026"
    m = re.search(
        r'(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(\w+)\s+(\d{4})',
        period,
    )
    if m:
        start = _to_iso(int(m.group(1)), m.group(3), m.group(4))
        end = _to_iso(int(m.group(2)), m.group(3), m.group(4))
        return start, end

    # Single end date: "s/d 20 Mei 2026", "sd. 20 Mei 2026", "sampai 20 Mei 2026"
    m = re.search(
        r'(?:s[/\.]?d|sampai|until)\s+(\d{1,2})\s+(\w+)\s+(\d{4})',
        period,
        re.IGNORECASE,
    )
    if m:
        return None, _to_iso(int(m.group(1)), m.group(2), m.group(3))

    # Bare single date: "20 Mei 2026"
    m = re.search(
        r'(\d{1,2})\s+(\w+)\s+(\d{4})',
        period,
    )
    if m:
        return None, _to_iso(int(m.group(1)), m.group(2), m.group(3))

    return None, None


# ---------------------------------------------------------------------------
# Unit tests (run via `python scripts/matching/promo_parser.py`)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # normalize_promo_text
    assert normalize_promo_text('') == []
    assert normalize_promo_text(None) == []
    assert normalize_promo_text('  ') == []
    assert normalize_promo_text('DISKON 20%') == ['Diskon 20%']
    assert normalize_promo_text('DISKON 20% EKSTRA STIKER') == ['Diskon 20%', 'Ekstra Stiker']
    assert normalize_promo_text('HARGA SPESIAL EKSTRA STIKER') == ['Harga Spesial', 'Ekstra Stiker']
    assert normalize_promo_text('HEMAT 40%') == ['Hemat 40%']
    assert normalize_promo_text('2 GRATIS 1') == ['2 Gratis 1']
    assert normalize_promo_text('GRATIS') == ['Gratis']
    assert normalize_promo_text('maks. 4 pck') == ['Maks. 4 pck']
    assert normalize_promo_text('MAX 4 box') == ['Maks. 4 box']
    assert normalize_promo_text('KHUSUS MEMBER') == ['Khusus Member']
    assert normalize_promo_text('Beli 1 Rp 16.800') == ['Beli 1 Rp 16.800']

    # categorize_promo
    assert categorize_promo('Diskon 20%') == 'discount_pct'
    assert categorize_promo('Hemat 40%') == 'discount_pct'
    assert categorize_promo('Diskon 15%') == 'discount_pct'
    assert categorize_promo('1 Gratis 1') == 'bogo'
    assert categorize_promo('2 Gratis 1') == 'bogo'
    assert categorize_promo('Gratis') == 'bogo'
    assert categorize_promo('2 Lebih Hemat') == 'bundle'
    assert categorize_promo('2 Seharga 20.980') == 'bundle'
    assert categorize_promo('Beli 2 Harga Satuan') == 'bundle'
    assert categorize_promo('Ekstra Stiker') == 'bundle'
    assert categorize_promo('Khusus Member') == 'member_price'
    assert categorize_promo('Member Special Price') == 'member_price'
    assert categorize_promo('PWP') == 'member_price'
    assert categorize_promo('Harga Spesial') == 'promo_price'
    assert categorize_promo('Fresh Deals!') == 'promo_price'
    assert categorize_promo('12 & 14 Juni 15.490') == 'discount_fixed'
    assert categorize_promo('Beli 1 Rp 16.800') == 'discount_fixed'
    assert categorize_promo('Maks. 4 pck') == 'quantity_limit'
    assert categorize_promo('Maks. 4 box') == 'quantity_limit'
    assert categorize_promo('Gratis Es Batu') == 'freebie'
    assert categorize_promo('Disertai Pembelian 365 Teh Celup 25\'s Hitam Box 25x2gr') == 'freebie'
    assert categorize_promo('Anti Bocor') == 'special'

    # standardize_promo_list
    assert standardize_promo_list(None) is None
    assert standardize_promo_list([]) is None
    assert standardize_promo_list(['']) is None
    r = standardize_promo_list(['DISKON 20% EKSTRA STIKER'])
    assert r is not None
    assert r['normalized'] == ['Diskon 20%', 'Ekstra Stiker']
    assert r['types'] == ['discount_pct', 'bundle']
    assert r['best_type'] == 'discount_pct'
    assert r['discount_pct'] == 20
    assert r['max_qty'] is None
    assert r['display_summary'] == 'Diskon 20%'

    r2 = standardize_promo_list(['maks. 4 pck'])
    assert r2 is not None
    assert r2['best_type'] == 'quantity_limit'
    assert r2['max_qty'] == 4

    print('All assertions passed!')
