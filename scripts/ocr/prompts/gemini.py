_BODY = """Return ONLY a valid JSON array. No explanation. No markdown. Start with [ and end with ].

Each item must follow this exact structure:
{
  "name": "full product name as shown",
  "brand": "brand name if visible, else null",
  "unit": "size as shown (e.g. '85 g', '1.5 L', '6 x 45 ml'), else null",
  "price": <integer in IDR, numbers only>,
  "promo": "promo text if any (e.g. 'DAPAT 5 pcs', 'Beli 2 Gratis 1'), else null",
  "period": "validity dates if shown, else null"
}

Rules:
- price MUST be an integer. Indonesian '.' separator: "Rp 8.500" → 8500.
- If unsure about a price, OMIT that product entirely.
- Extract EVERY product visible, including small items."""

_PROMPTS = {
    "superindo": f"Extract all product promotions from this Superindo supermarket brochure image.\n\n{_BODY}",
    "lotte": f"Extract all product promotions from this Lotte Mart supermarket brochure image.\n\n{_BODY}",
}


def get_gemini_prompt(store: str = "superindo") -> str:
    return _PROMPTS.get(store, _PROMPTS["superindo"])
