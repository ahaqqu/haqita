_SUPERINDO = """List all products in this Superindo promo brochure.
Return ONLY a JSON array. No other text.
[
  {"name": "product name", "price": 12345, "unit": "size if visible", "promo": "promo text if any"}
]"""

_LOTTE = """List all products in this Lotte Mart promo brochure.
Return ONLY a JSON array. No other text.
[
  {"name": "product name", "price": 12345, "unit": "size if visible", "promo": "promo text if any"}
]"""

_PROMPTS = {
    "superindo": _SUPERINDO,
    "lotte": _LOTTE,
}


def get_ollama_prompt(store: str = "superindo") -> str:
    return _PROMPTS.get(store, _SUPERINDO)
