import re
from dataclasses import dataclass


@dataclass
class PromoResult:
    promo_type: str
    display: str
    unit_count: int
    effective_unit_price: int


_PATTERNS = [
    (r'dapat\s+(\d+)\s*(?:pcs|buah|pack)?', 'bundle_buy'),
    (r'beli\s+(\d+)\s*gratis\s+(\d+)', 'get_free'),
    (r'(\d+)\s*(?:pcs|buah)?\s*/\s*(?:Rp\.?\s*)?([\d.,]+)', 'multi_price'),
    (r'diskon\s+(\d+)\s*%', 'discount_pct'),
    (r'hemat\s+(?:Rp\.?\s*)?([\d.,]+)', 'discount_fixed'),
]


def parse_promo(promo_text: str | None, base_price: int) -> PromoResult:
    if not promo_text:
        return PromoResult('single', '', 1, base_price)

    text = promo_text.lower().strip()

    for pattern, ptype in _PATTERNS:
        m = re.search(pattern, text)
        if m:
            if ptype == 'bundle_buy':
                count = int(m.group(1))
                return PromoResult(ptype, promo_text, count, round(base_price / count))
            elif ptype == 'get_free':
                buy, free = int(m.group(1)), int(m.group(2))
                total = buy + free
                return PromoResult(ptype, promo_text, total, round(base_price / total))
            elif ptype == 'multi_price':
                count = int(m.group(1))
                total_str = re.sub(r'\.(?=\d{3})', '', m.group(2)).replace(',', '')
                try:
                    total = int(float(total_str))
                    return PromoResult(ptype, promo_text, count, round(total / count))
                except ValueError:
                    pass
            elif ptype == 'discount_pct':
                pct = int(m.group(1))
                unit_price = round(base_price * (1 - pct / 100))
                return PromoResult(ptype, promo_text, 1, unit_price)
            elif ptype == 'discount_fixed':
                discount_str = re.sub(r'\.(?=\d{3})', '', m.group(1))
                try:
                    discount = int(float(discount_str))
                    return PromoResult(ptype, promo_text, 1, max(base_price - discount, 1))
                except ValueError:
                    pass

    return PromoResult('single', promo_text, 1, base_price)


def parse_valid_until(period: str | None) -> str | None:
    if not period:
        return None
    MONTHS = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'mei': '05', 'jun': '06', 'jul': '07', 'agu': '08',
        'sep': '09', 'okt': '10', 'nov': '11', 'des': '12',
        'may': '05', 'aug': '08', 'oct': '10', 'dec': '12'
    }
    m = re.findall(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})', period)
    if m:
        day, month_str, year = m[-1]
        month = MONTHS.get(month_str[:3].lower())
        if month:
            return f"{year}-{month}-{int(day):02d}"
    return None
