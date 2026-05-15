"""
Compare OCR output against expected assert files.
Reports differences in product count, rejected count, and field-level diffs.
"""

import json
from pathlib import Path


def load_asserts(asserts_dir: Path, store: str, image_stem: str) -> dict | None:
    """Load expected output from asserts directory."""
    assert_file = asserts_dir / f"integration_test_{store}_{image_stem}.json"
    if not assert_file.exists():
        return None
    return json.loads(assert_file.read_text(encoding="utf-8"))


def compare_products(actual: list[dict], expected: list[dict]) -> list[str]:
    """Compare product lists and return list of differences."""
    diffs = []

    if len(actual) != len(expected):
        diffs.append(f"  Product count: actual={len(actual)}, expected={len(expected)}")

    # Compare by index (order matters for OCR consistency)
    for i in range(max(len(actual), len(expected))):
        a = actual[i] if i < len(actual) else None
        e = expected[i] if i < len(expected) else None

        if a is None:
            diffs.append(f"  Product [{i}]: MISSING (expected: {e.get('name', '?')})")
            continue
        if e is None:
            diffs.append(f"  Product [{i}]: EXTRA (actual: {a.get('name', '?')})")
            continue

        # Compare key fields
        for field in ("name", "brand", "unit", "price", "promo", "period"):
            av = a.get(field)
            ev = e.get(field)
            if av != ev:
                diffs.append(f"  Product [{i}] {field}: actual={av!r}, expected={ev!r}")
                diffs.append(f"    -> name: {a.get('name', '?')}")

    return diffs


def compare_rejected(actual: list[dict], expected: list[dict]) -> list[str]:
    """Compare rejected product lists."""
    diffs = []

    if len(actual) != len(expected):
        diffs.append(f"  Rejected count: actual={len(actual)}, expected={len(expected)}")

    for i in range(max(len(actual), len(expected))):
        a = actual[i] if i < len(actual) else None
        e = expected[i] if i < len(expected) else None

        if a is None:
            diffs.append(f"  Rejected [{i}]: MISSING (expected reason: {e.get('reason', '?')})")
            continue
        if e is None:
            diffs.append(f"  Rejected [{i}]: EXTRA (actual reason: {a.get('reason', '?')})")
            continue

        if a.get("reason") != e.get("reason"):
            diffs.append(f"  Rejected [{i}] reason: actual={a.get('reason')!r}, expected={e.get('reason')!r}")

    return diffs


def compare_results(actual: dict, expected: dict) -> list[str]:
    """
    Compare full OCR result against expected.
    Returns list of difference strings (empty if identical).
    """
    diffs = []

    # Product count
    if actual.get("products_count") != expected.get("products_count"):
        diffs.append(f"  Products count: actual={actual.get('products_count')}, expected={expected.get('products_count')}")

    # Rejected count
    if actual.get("rejected_count") != expected.get("rejected_count"):
        diffs.append(f"  Rejected count: actual={actual.get('rejected_count')}, expected={expected.get('rejected_count')}")

    # Products
    actual_products = actual.get("products", [])
    expected_products = expected.get("products", [])
    diffs.extend(compare_products(actual_products, expected_products))

    # Rejected
    actual_rejected = actual.get("rejected", [])
    expected_rejected = expected.get("rejected", [])
    diffs.extend(compare_rejected(actual_rejected, expected_rejected))

    return diffs
