_BODY = """Return ONLY a valid JSON array. No explanation. No markdown. Start with [ and end with ].

Each item must follow this exact structure:
{
  "name": "full product name as shown",
  "brand": "brand name if visible, else null",
  "unit": "size as shown (e.g. '85 g', '1.5 L', '6 x 45 ml'), else null",
  "price": <integer in IDR, numbers only, as shown in brochure as per definition in rules below>,
  "promo": <an array of promo texts if shown (e.g. 'MAX 1', 'LOTTE MART Point SPECIAL PRICE', 'Dapat 5 pcs', 'BUY 1 GET 1'), else null>,
  "period": "validity dates if shown, else null"
}

Rules:
- Brochure may show both "original_price" and "discounted_price". 
- "discounted_price" usually red font or red background, but not always. 
- "original_price" usually black font, but not always.
- If both prices shown, put "discounted_price" in "price" field.
- If only one price is shown, put it in "price" field.
- DO NOT include both "original_price" and "discounted_price" in "promo"
- Field "price" MUST be an integer. Indonesian '.' separator: "Rp 8.500" → 8500. Exactly as shown in brochure, do not convert to per-unit price or apply any discount calculation.
- Extract EVERY product visible, including small items."""

_PROMPTS = {
    "superindo": f"Extract all product promotions from this Superindo supermarket brochure image.\n\n{_BODY}",
    "lotte": f"Extract all product promotions from this Lotte Mart supermarket brochure image.\n\n{_BODY}",
}

def get_gemini_prompt(store: str = "superindo") -> str:
    return _PROMPTS.get(store, _PROMPTS["superindo"])
