"""
Name, unit, and brand normalization for product matching.

All functions are pure (no side effects) and cached where beneficial.
"""

import re
from functools import lru_cache


# ---------------------------------------------------------------------------
# Brand normalization
# ---------------------------------------------------------------------------

BRAND_ALIASES: dict[str, str] = {
    'lndomie': 'indomie',
    'lndomi': 'indomie',
    's0sro': 'sosro',
    's0s0': 'sosro',
    'ult rajaya': 'ultrajaya',
    'ultra jaya': 'ultrajaya',
    'ultrqjaya': 'ultrajaya',
}


def normalize_brand(brand: str | None) -> str:
    """Returns lowercase, space-stripped brand. Maps known OCR-typos to canonical names."""
    if not brand:
        return ''
    b = brand.lower().strip()
    return BRAND_ALIASES.get(b, b)


# ---------------------------------------------------------------------------
# Unit type detection
# ---------------------------------------------------------------------------

UNIT_TYPE_MAP: dict[str, str] = {
    'g': 'weight', 'gram': 'weight', 'gr': 'weight', 'kg': 'weight',
    'ml': 'volume', 'l': 'volume', 'liter': 'volume', 'lt': 'volume',
    'pcs': 'count', 'pack': 'count', 'sachet': 'count',
    'bks': 'count', 'bungkus': 'count', 'botol': 'count', 'kaleng': 'count',
    'pck': 'count', 'pch': 'count', 'tub': 'count', 'box': 'count',
    'bag': 'count', 'set': 'count', 's': 'count',
}


def unit_type(unit: str | None) -> str | None:
    """Returns 'weight', 'volume', 'count', or None if unrecognisable."""
    if not unit:
        return None
    u = unit.lower().strip().rstrip('.,')
    # Try exact match first
    if u in UNIT_TYPE_MAP:
        return UNIT_TYPE_MAP[u]
    # Try stripping trailing 's' (e.g. "1100's" -> "1100'" -> not in map, skip)
    # Try matching known suffixes inside the string
    for suffix, utype in UNIT_TYPE_MAP.items():
        if u.endswith(suffix):
            return utype
    return None


def units_type_compatible(u1: str | None, u2: str | None) -> bool:
    """True if types match OR either unit is unknown (lenient for OCR noise)."""
    t1 = unit_type(u1)
    t2 = unit_type(u2)
    if t1 is None or t2 is None:
        return True  # Unknown — don't block
    return t1 == t2


# ---------------------------------------------------------------------------
# Unit value normalization
# ---------------------------------------------------------------------------

# Matches: "85 g", "1.5 L", "2 x 800 ml", "6 x 45 ml", "1100's"
_UNIT_VALUE_RE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*'           # first number
    r'(?:[×xX]\s*(\d+(?:[.,]\d+)?))?' # optional multiplier: "x 800"
    r'\s*'
    r'([a-z]+(?:\'[a-z]*)?)',         # unit suffix: "ml", "g", "'s"
    re.IGNORECASE,
)


def parse_unit_to_base(unit: str | None) -> tuple[float, str] | None:
    """
    Returns (normalized_value, unit_type) or None.

    Examples:
        "85 g"            → (85.0, "weight")
        "1.5 L"           → (1500.0, "volume")
        "2 x 800 ml"      → (1600.0, "volume")
        "6 x 45 ml"       → (270.0, "volume")
        "3 pcs"           → (3.0, "count")
        "1100's"          → (1100.0, "count")
    """
    if not unit:
        return None

    m = _UNIT_VALUE_RE.search(unit)
    if not m:
        return None

    qty = float(m.group(1).replace(',', '.'))
    multiplier = float(m.group(2).replace(',', '.')) if m.group(2) else 1.0
    raw_unit = m.group(3).lower()

    utype = unit_type(raw_unit)
    if utype is None:
        return None

    total = qty * multiplier

    # Convert to base: kg→g, L→ml
    if utype == 'weight' and raw_unit == 'kg':
        total *= 1000
    elif utype == 'volume' and raw_unit in ('l', 'lt', 'liter'):
        total *= 1000

    return (total, utype)


def units_value_compatible(u1: str | None, u2: str | None, tolerance: float = 0.15) -> bool:
    """True if unit values are within tolerance (default ±15% for OCR noise)."""
    p1 = parse_unit_to_base(u1)
    p2 = parse_unit_to_base(u2)
    if p1 is None or p2 is None:
        return True  # Unknown — don't block
    v1, t1 = p1
    v2, t2 = p2
    if t1 != t2:
        return False  # Different types (weight vs volume)
    if v1 == 0 or v2 == 0:
        return True
    ratio = min(v1, v2) / max(v1, v2)
    return ratio >= (1.0 - tolerance)


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

# Strips unit-like tokens from product names so they don't interfere with matching.
_UNIT_TOKEN_RE = re.compile(
    r'\b\d+(?:[.,]\d+)?\s*(?:[×xX]\s*\d+(?:[.,]\d+)?\s*)?'
    r'(?:kg|g|gram|ml|l|liter|lt|pcs|pack|sachet|bks|bungkus|botol|kaleng|'
    r'pck|pch|tub|box|bag|set|s)\b',
    re.IGNORECASE,
)


@lru_cache(maxsize=2048)
def normalize_name(name: str) -> str:
    """Lowercase, strip units, strip punctuation, collapse whitespace. Cached."""
    n = name.lower()
    n = _UNIT_TOKEN_RE.sub('', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def canonical_tokens(name: str) -> frozenset:
    """Order-independent token set for exact matching."""
    return frozenset(normalize_name(name).split())


def token_overlap(name_a: str, name_b: str) -> float:
    """Jaccard similarity on token sets. Returns 0.0–1.0."""
    a = canonical_tokens(name_a)
    b = canonical_tokens(name_b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
