import re
from functools import lru_cache

BRAND_ALIASES: dict[str, str] = {
    'lndomie': 'indomie',
    'lndomi': 'indomie',
    'S0sro': 'sosro',
    'S0s0': 'sosro',
    'Ult rajaya': 'ultrajaya',
    'UItra jaya': 'ultrajaya',
    'Ultrqjaya': 'ultrajaya',
}


def normalize_brand(brand: str | None) -> str:
    if not brand:
        return ''
    b = brand.strip()
    return BRAND_ALIASES.get(b, b).lower().replace(' ', '')


UNIT_TYPE_MAP: dict[str, str] = {
    'g': 'weight', 'gram': 'weight', 'gr': 'weight', 'kg': 'weight',
    'ml': 'volume', 'l': 'volume', 'liter': 'volume', 'lt': 'volume',
    'pcs': 'count', 'pack': 'count', 'sachet': 'count',
    'bks': 'count', 'bungkus': 'count', 'botol': 'count', 'kaleng': 'count',
}


def unit_type(unit: str | None) -> str | None:
    if not unit:
        return None
    token = re.split(r'[\s\d×x]', unit.lower().strip())[-1].strip()
    return UNIT_TYPE_MAP.get(token)


def units_type_compatible(u1: str | None, u2: str | None) -> bool:
    t1, t2 = unit_type(u1), unit_type(u2)
    if t1 is None or t2 is None:
        return True
    return t1 == t2


def parse_unit_to_base(unit: str | None) -> tuple[float, str] | None:
    if not unit:
        return None
    s = unit.lower().replace(',', '.')

    m = re.search(r'(\d+(?:\.\d+)?)\s*[×x]\s*(\d+(?:\.\d+)?)\s*(g|kg|ml|l)', s)
    if m:
        qty = float(m.group(1)) * float(m.group(2))
        u = m.group(3)
        base = qty * 1000 if u == 'kg' else qty * 1000 if u == 'l' else qty
        utype = 'weight' if u in ('g', 'kg') else 'volume'
        return (base, utype)

    m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|gram|l|liter|ml|pcs|pack|sachet|bks|botol)', s)
    if m:
        val = float(m.group(1))
        u = m.group(2)
        conversions = {'kg': 1000, 'l': 1000, 'liter': 1000}
        base = val * conversions.get(u, 1)
        utype = UNIT_TYPE_MAP.get(u, 'count')
        return (base, utype)

    return None


def units_value_compatible(u1: str | None, u2: str | None, tolerance: float = 0.15) -> bool:
    p1, p2 = parse_unit_to_base(u1), parse_unit_to_base(u2)
    if not p1 or not p2:
        return u1 == u2 if u1 and u2 else True
    if p1[1] != p2[1]:
        return False
    ratio = max(p1[0], p2[0]) / max(min(p1[0], p2[0]), 0.001)
    return ratio <= (1 + tolerance)


_UNIT_PATTERN = r'\b\d+(?:[.,]\d+)?\s*(?:[×x]\s*\d+(?:[.,]\d+)?\s*)?(kg|g|gram|ml|l|liter|pcs|pack|sachet|bks)\b'


@lru_cache(maxsize=2048)
def normalize_name(name: str) -> str:
    s = name.lower()
    s = re.sub(_UNIT_PATTERN, '', s)
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def canonical_tokens(name: str) -> frozenset:
    tokens = normalize_name(name).split()
    return frozenset(t for t in tokens if len(t) > 1)


def token_overlap(name_a: str, name_b: str) -> float:
    ta, tb = canonical_tokens(name_a), canonical_tokens(name_b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
