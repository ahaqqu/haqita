"""
Shared consolidation logic — rebuild active promo view from database.
Used by both Stage 3 (consolidate.py) and Stage 4 (publish_html.py).
"""

from datetime import datetime


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
                store_entries.append({
                    "store": snap["store"],
                    "price": snap.get("price", 0),
                    "effective_unit_price": snap.get("effective_unit_price", snap.get("price", 0)),
                    "bundle_size": snap.get("bundle_size", 1),
                    "promo": snap.get("promo"),
                    "promo_type": snap.get("promo_type", "single"),
                    "valid_from": snap.get("valid_from"),
                    "valid_until": snap.get("valid_until"),
                    "image_path": snap.get("image_path"),
                })

            eff_prices = [s["effective_unit_price"] for s in store_entries if s["effective_unit_price"] > 0]
            price_min = min(eff_prices) if eff_prices else 0
            price_max = max(eff_prices) if eff_prices else 0
            cheapest = None
            if eff_prices:
                cheapest_store = min(store_entries, key=lambda s: s["effective_unit_price"] if s["effective_unit_price"] > 0 else float("inf"))
                cheapest = cheapest_store["store"]
            price_gap = price_max - price_min if price_min > 0 else 0
            savings_pct = round((price_gap / price_max * 100), 1) if price_max > 0 else 0.0

            has_promo = any(s["promo"] for s in store_entries)
            promo_parts = []
            for s in store_entries:
                if s["promo"]:
                    promo_parts.append(f"{s['promo']} di {s['store']}")
            promo_summary = "; ".join(promo_parts) if promo_parts else ""

            valid_dates = [s["valid_until"] for s in store_entries if s["valid_until"]]
            valid_until = min(valid_dates) if valid_dates else None

            match_method = None
            match_confidence = None
            for snap in stores_snaps:
                mm = snap.get("match_method")
                mc = snap.get("match_confidence")
                if mm and (match_confidence is None or (mc is not None and mc > match_confidence)):
                    match_method = mm
                    match_confidence = mc

            consolidated_products.append({
                "key": pkey,
                "name": name,
                "brand": brand,
                "unit": unit,
                "unit_type": unit_type_str,
                "unit_value_g": unit_value_g,
                "stores": store_entries,
                "price_min": price_min,
                "price_max": price_max,
                "cheapest_store": cheapest,
                "price_gap": price_gap,
                "savings_pct": savings_pct,
                "has_promo": has_promo,
                "promo_summary": promo_summary,
                "valid_until": valid_until,
                "match_method": match_method or "unknown",
                "match_confidence": match_confidence or 0.5,
            })
        else:
            snap = stores_snaps[0]
            singles.append({
                "key": pkey,
                "name": name,
                "brand": brand,
                "unit": unit,
                "unit_type": unit_type_str,
                "unit_value_g": unit_value_g,
                "store": snap["store"],
                "price": snap.get("price", 0),
                "effective_unit_price": snap.get("effective_unit_price", snap.get("price", 0)),
                "promo": snap.get("promo"),
                "valid_from": snap.get("valid_from"),
                "valid_until": snap.get("valid_until"),
                "image_path": snap.get("image_path"),
            })

    matched_count = len(consolidated_products)
    lotte_count = sum(1 for s in singles if s["store"] == "Lotte")
    superindo_count = sum(1 for s in singles if s["store"] == "Superindo")

    match_methods = {}
    for p in consolidated_products:
        m = p.get("match_method", "unknown")
        match_methods[m] = match_methods.get(m, 0) + 1

    return {
        "generated_at": datetime.now().isoformat(),
        "scrape_dates": {},
        "source_files": [],
        "display_hints": {
            "stores": {"Lotte": "Lotte Mart", "Superindo": "Superindo"},
            "store_colors": {"Lotte": "#0057A8", "Superindo": "#E8211D"},
            "currency": "IDR",
            "locale": "id-ID",
        },
        "products": consolidated_products,
        "singles": singles,
        "stats": {
            "total_products_lotte": matched_count + lotte_count,
            "total_products_superindo": matched_count + superindo_count,
            "matched_across_stores": matched_count,
            "lotte_only": lotte_count,
            "superindo_only": superindo_count,
            "match_methods": match_methods,
            "flagged_for_review": 0,
            "validation_rejected": 0,
        },
    }
