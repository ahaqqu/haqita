"""
Shared consolidation logic — rebuild active promo view from database.
Used by both Stage 3 (consolidate.py) and Stage 4 (publish_html.py).
"""

import ast
from datetime import datetime

from scripts.matching.promo_parser import standardize_promo_list

DISPLAY_HINTS = {
    "stores": {"Lotte": "Lotte", "Superindo": "Superindo"},
    "store_colors": {"Lotte": "#0057A8", "Superindo": "#E8211D"},
    "currency": "IDR",
}


# ---------------------------------------------------------------------------
# Shared helpers — used by both consolidate.py and consolidation.py
# ---------------------------------------------------------------------------

def _normalize_promo(v) -> list[str] | None:
    """Normalize promo to list[str] | None. Handles old string data."""
    if v is None:
        return None
    if isinstance(v, list):
        result = [str(x).strip() for x in v if x and str(x).strip()]
        return result if result else None
    # Handle old stringified Python list: "['A', 'B']" or plain string
    s = str(v).strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            items = ast.literal_eval(s)
            result = [str(x).strip() for x in items if x and str(x).strip()]
            return result if result else None
        except (ValueError, SyntaxError):
            pass
    return [s] if s else None


def build_store_entry(store_name: str, price: float, effective_unit_price: float,
                      bundle_size: int = 1, promo: list[str] = None, promo_type: str = "single",
                      valid_from: str = None, valid_until: str = None, image_path: str = None,
                      standardized_promo: dict = None) -> dict:
    """Build a store entry dict for a product."""
    entry = {
        "store": store_name,
        "price": price,
        "effective_unit_price": effective_unit_price,
        "bundle_size": bundle_size,
        "promo": promo,
        "promo_type": promo_type,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "image_path": image_path,
    }
    if standardized_promo is not None:
        entry["standardized_promo"] = standardized_promo
    return entry


def calc_price_stats(store_entries: list[dict]) -> dict:
    """Compute price_min, price_max, cheapest_store, price_gap, savings_pct."""
    eff_prices = [s["effective_unit_price"] for s in store_entries if s["effective_unit_price"] > 0]
    price_min = min(eff_prices) if eff_prices else 0
    price_max = max(eff_prices) if eff_prices else 0
    cheapest = None
    if eff_prices:
        cheapest_store = min(store_entries, key=lambda s: s["effective_unit_price"] if s["effective_unit_price"] > 0 else float("inf"))
        cheapest = cheapest_store["store"]
    price_gap = price_max - price_min if price_min > 0 else 0
    savings_pct = round((price_gap / price_max * 100), 1) if price_max > 0 else 0.0
    return {
        "price_min": price_min,
        "price_max": price_max,
        "cheapest_store": cheapest,
        "price_gap": price_gap,
        "savings_pct": savings_pct,
    }


def build_promo_summary(store_entries: list[dict]) -> dict:
    """Detect promos and build summary string."""
    has_promo = any(s["promo"] for s in store_entries)
    promo_parts = [
        f"{', '.join(s['promo'])} di {s['store']}"
        for s in store_entries if s["promo"]
    ]
    promo_summary = "; ".join(promo_parts) if promo_parts else ""
    return {"has_promo": has_promo, "promo_summary": promo_summary}


def calc_valid_until(store_entries: list[dict]) -> str | None:
    """Get earliest valid_until date across stores."""
    valid_dates = [s["valid_until"] for s in store_entries if s["valid_until"]]
    return min(valid_dates) if valid_dates else None


def build_consolidated_product(pkey: str, name: str, brand: str, unit: str,
                                unit_type: str, unit_value_g, store_entries: list[dict],
                                match_method: str = "unknown", match_confidence: float = 0.5) -> dict:
    """Build a full matched product dict with all computed fields."""
    stats = calc_price_stats(store_entries)
    promo = build_promo_summary(store_entries)
    valid_until = calc_valid_until(store_entries)

    return {
        "key": pkey,
        "name": name,
        "brand": brand,
        "unit": unit,
        "unit_type": unit_type,
        "unit_value_g": unit_value_g,
        "stores": store_entries,
        "price_min": stats["price_min"],
        "price_max": stats["price_max"],
        "cheapest_store": stats["cheapest_store"],
        "price_gap": stats["price_gap"],
        "savings_pct": stats["savings_pct"],
        "has_promo": promo["has_promo"],
        "promo_summary": promo["promo_summary"],
        "valid_until": valid_until,
        "match_method": match_method,
        "match_confidence": match_confidence,
    }


def build_single_product(pkey: str, name: str, brand: str, unit: str,
                          unit_type: str, unit_value_g, store_name: str,
                          price: float, effective_unit_price: float,
                          promo: list[str] = None, valid_from: str = None,
                          valid_until: str = None, image_path: str = None,
                          standardized_promo: dict = None) -> dict:
    """Build a single (unmatched) product dict."""
    entry = {
        "key": pkey,
        "name": name,
        "brand": brand,
        "unit": unit,
        "unit_type": unit_type,
        "unit_value_g": unit_value_g,
        "store": store_name,
        "price": price,
        "effective_unit_price": effective_unit_price,
        "promo": promo,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "image_path": image_path,
    }
    if standardized_promo is not None:
        entry["standardized_promo"] = standardized_promo
    return entry


def build_match_methods(consolidated_products: list[dict]) -> dict:
    """Count match methods used across consolidated products."""
    methods = {}
    for p in consolidated_products:
        m = p.get("match_method", "unknown")
        methods[m] = methods.get(m, 0) + 1
    return methods


def build_stats(consolidated_products: list[dict], singles: list[dict],
                total_lotte: int, total_superindo: int,
                flagged_for_review: int = 0, validation_rejected: int = 0) -> dict:
    """Build stats dict for consolidated output."""
    matched_count = len(consolidated_products)
    lotte_only = sum(1 for s in singles if s["store"] == "Lotte")
    superindo_only = sum(1 for s in singles if s["store"] == "Superindo")

    return {
        "total_products_lotte": total_lotte,
        "total_products_superindo": total_superindo,
        "matched_across_stores": matched_count,
        "lotte_only": lotte_only,
        "superindo_only": superindo_only,
        "match_methods": build_match_methods(consolidated_products),
        "flagged_for_review": flagged_for_review,
        "validation_rejected": validation_rejected,
    }


# ---------------------------------------------------------------------------
# Database rebuild — used by Stage 4 (publish_html.py)
# ---------------------------------------------------------------------------


def generate_consolidated_from_history(history: dict, catalog: dict, today: str) -> dict:
    """
    Rebuild active_promo.json from database/price_history.json + product_catalog.json.

    1. Filter snapshots: valid_until >= today OR valid_until is null (treat as active)
    2. Get latest snapshot per (product_key, store) — dedup by date
    3. Group by product_key:
       - 2+ stores → matched product (build stores[] array)
       - 1 store → single
    4. Compute display fields: price_min, price_max, cheapest_store, price_gap, savings_pct
    5. Return consolidated dict with same schema as current output
    """
    snapshots = history.get("snapshots", [])

    active = []
    for snap in snapshots:
        vu = snap.get("valid_until")
        if vu is None or vu >= today:
            active.append(snap)

    latest = {}
    for snap in active:
        pkey = snap.get("product_key") or snap.get("key", "")
        store = snap.get("store", "")
        key = (pkey, store)
        if key not in latest or snap.get("date", "") > latest[key].get("date", ""):
            latest[key] = snap

    # Enrich all snapshots with standardized_promo
    for snap in history["snapshots"]:
        raw = snap.get("promo")
        if raw is not None and raw != "" and raw != []:
            snap["standardized_promo"] = standardize_promo_list(raw)
        elif "standardized_promo" in snap:
            del snap["standardized_promo"]

    product_groups = {}
    for (pkey, store), snap in latest.items():
        if pkey not in product_groups:
            product_groups[pkey] = []
        product_groups[pkey].append(snap)

    consolidated_products = []
    singles = []

    for pkey, stores_snaps in product_groups.items():
        cat = catalog.get(pkey, {})

        name = stores_snaps[0].get("name", "")
        brand = stores_snaps[0].get("brand") or cat.get("brand")
        unit = stores_snaps[0].get("unit") or cat.get("unit")
        unit_type_str = stores_snaps[0].get("unit_type", cat.get("unit_type", "unknown"))
        unit_value_g = stores_snaps[0].get("unit_value_g", cat.get("unit_value_g"))

        if len(stores_snaps) >= 2:
            store_entries = []
            for snap in stores_snaps:
                store_entries.append(build_store_entry(
                    store_name=snap["store"],
                    price=snap.get("price", 0),
                    effective_unit_price=snap.get("effective_unit_price", snap.get("price", 0)),
                    bundle_size=snap.get("bundle_size", 1),
                    promo=_normalize_promo(snap.get("promo")),
                    promo_type=snap.get("promo_type", "single"),
                    valid_from=snap.get("valid_from"),
                    valid_until=snap.get("valid_until"),
                    image_path=snap.get("image_path"),
                    standardized_promo=snap.get("standardized_promo"),
                ))

            match_method = None
            match_confidence = None
            for snap in stores_snaps:
                mm = snap.get("match_method")
                mc = snap.get("match_confidence")
                if mm and (match_confidence is None or (mc is not None and mc > match_confidence)):
                    match_method = mm
                    match_confidence = mc

            consolidated_products.append(build_consolidated_product(
                pkey=pkey, name=name, brand=brand, unit=unit,
                unit_type=unit_type_str, unit_value_g=unit_value_g,
                store_entries=store_entries,
                match_method=match_method or "unknown",
                match_confidence=match_confidence or 0.5,
            ))
        else:
            snap = stores_snaps[0]
            singles.append(build_single_product(
                pkey=pkey, name=name, brand=brand, unit=unit,
                unit_type=unit_type_str, unit_value_g=unit_value_g,
                store_name=snap["store"],
                price=snap.get("price", 0),
                effective_unit_price=snap.get("effective_unit_price", snap.get("price", 0)),
                promo=_normalize_promo(snap.get("promo")),
                valid_from=snap.get("valid_from"),
                valid_until=snap.get("valid_until"),
                image_path=snap.get("image_path"),
                standardized_promo=snap.get("standardized_promo"),
            ))

    matched_count = len(consolidated_products)
    lotte_count = sum(1 for s in singles if s["store"] == "Lotte")
    superindo_count = sum(1 for s in singles if s["store"] == "Superindo")

    return {
        "generated_at": datetime.now().isoformat(),
        "scrape_dates": {},
        "source_files": [],
        "display_hints": DISPLAY_HINTS,
        "products": consolidated_products,
        "singles": singles,
        "stats": build_stats(
            consolidated_products=consolidated_products,
            singles=singles,
            total_lotte=matched_count + lotte_count,
            total_superindo=matched_count + superindo_count,
        ),
    }
