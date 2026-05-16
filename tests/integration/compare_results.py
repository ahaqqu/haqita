"""
Fuzzy comparison of OCR output against expected assert files.

Comparison rules:
- Case-insensitive for text fields (name, brand, promo, period)
- Product order does not matter — matched by normalized name
- Extra spaces/whitespace ignored
- Price must match exactly (integer comparison)
"""

import json
import re
from pathlib import Path


def _normalize_text(text: str | None) -> str:
    """Lowercase, collapse whitespace, strip."""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', str(text).lower().strip())


def load_asserts(test_data_dir: Path, provider: str, store: str, image_stem: str) -> dict | None:
    """
    Load expected output from test data directory.
    Structure: data/test/<store>/ocr-result/<provider>/<image_stem>.json
    """
    assert_file = test_data_dir / store / "ocr-result" / provider / f"{image_stem}.json"
    if not assert_file.exists():
        return None
    return json.loads(assert_file.read_text(encoding="utf-8"))


def _find_best_match(actual_product: dict, expected_products: list[dict], used_indices: set) -> int | None:
    """
    Find the best matching expected product by normalized name.
    Returns index or None if no match.
    """
    actual_name = _normalize_text(actual_product.get("name"))
    best_idx = None
    best_score = 0

    for i, ep in enumerate(expected_products):
        if i in used_indices:
            continue
        expected_name = _normalize_text(ep.get("name"))
        # Exact normalized name match
        if actual_name == expected_name:
            return i
        # Partial match score (token overlap)
        actual_tokens = set(actual_name.split())
        expected_tokens = set(expected_name.split())
        if actual_tokens and expected_tokens:
            overlap = len(actual_tokens & expected_tokens) / max(len(actual_tokens), len(expected_tokens))
            if overlap > best_score:
                best_score = overlap
                best_idx = i

    # Only return partial match if score is high enough
    if best_score >= 0.5:
        return best_idx
    return None


def compare_products(actual: list[dict], expected: list[dict]) -> list[str]:
    """Compare product lists with fuzzy matching (order-independent, case-insensitive)."""
    diffs = []

    if len(actual) != len(expected):
        diffs.append(f"  Product count: actual={len(actual)}, expected={len(expected)}")

    used_expected = set()

    for i, ap in enumerate(actual):
        match_idx = _find_best_match(ap, expected, used_expected)

        if match_idx is None:
            diffs.append(f"  Product [{i}] UNMATCHED: {ap.get('name', '?')}")
            continue

        used_expected.add(match_idx)
        ep = expected[match_idx]

        # Compare fields with case-insensitive text comparison
        for field in ("brand", "promo", "period"):
            av = _normalize_text(ap.get(field))
            ev = _normalize_text(ep.get(field))
            if av != ev:
                diffs.append(f"  [{ap.get('name', '?')}] {field}: actual={ap.get(field)!r}, expected={ep.get(field)!r}")

        # Unit comparison: normalize spaces
        au = _normalize_text(ap.get("unit"))
        eu = _normalize_text(ep.get("unit"))
        if au != eu:
            diffs.append(f"  [{ap.get('name', '?')}] unit: actual={ap.get('unit')!r}, expected={ep.get('unit')!r}")

        # Price must match exactly
        if ap.get("price") != ep.get("price"):
            diffs.append(f"  [{ap.get('name', '?')}] price: actual={ap.get('price')}, expected={ep.get('price')}")

    # Find unmatched expected products
    for i, ep in enumerate(expected):
        if i not in used_expected:
            diffs.append(f"  MISSING product: {ep.get('name', '?')}")

    return diffs


def compare_rejected(actual: list[dict], expected: list[dict]) -> list[str]:
    """Compare rejected product lists (order-independent, matched by reason)."""
    diffs = []

    actual_reasons = [a.get("reason", "") for a in actual]
    expected_reasons = [e.get("reason", "") for e in expected]

    if len(actual) != len(expected):
        diffs.append(f"  Rejected count: actual={len(actual)}, expected={len(expected)}")

    # Match by reason string
    used = set()
    for ar in actual_reasons:
        found = False
        for i, er in enumerate(expected_reasons):
            if i not in used and ar == er:
                used.add(i)
                found = True
                break
        if not found:
            diffs.append(f"  Rejected UNMATCHED: {ar}")

    for i, er in enumerate(expected_reasons):
        if i not in used:
            diffs.append(f"  MISSING rejected: {er}")

    return diffs


def compare_results(actual: dict, expected: dict) -> list[str]:
    """
    Compare full OCR result against expected with fuzzy matching.
    Returns list of difference strings (empty if semantically identical).
    """
    diffs = []

    if actual.get("products_count") != expected.get("products_count"):
        diffs.append(f"  Products count: actual={actual.get('products_count')}, expected={expected.get('products_count')}")

    if actual.get("rejected_count") != expected.get("rejected_count"):
        diffs.append(f"  Rejected count: actual={actual.get('rejected_count')}, expected={expected.get('rejected_count')}")

    actual_products = actual.get("products", [])
    expected_products = expected.get("products", [])
    diffs.extend(compare_products(actual_products, expected_products))

    actual_rejected = actual.get("rejected", [])
    expected_rejected = expected.get("rejected", [])
    diffs.extend(compare_rejected(actual_rejected, expected_rejected))

    return diffs
