import base64, json, os, sys, re
from google import genai
from google.genai import types

# ========== CONFIG ==========
IMAGE_PATH = r"data\test\superindo\image-brochure\sample_katalog_1.jpg"
STORE = "superindo"  # "lotte" or "superindo"
# ============================

PROMPTS = {
    "superindo": "Extract all product promotions from this Superindo supermarket brochure image.",
    "lotte": "Extract all product promotions from this Lotte Mart supermarket brochure image.",
}

BODY = """Return ONLY a valid JSON array. No explanation. No markdown. Start with [ and end with ].

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

def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            m = re.match(r"^\s*GEMINI_API_KEY\s*=\s*(.+?)\s*$", line)
            if m:
                os.environ.setdefault("GEMINI_API_KEY", m.group(1))
                return

load_env()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    api_key = input("Enter Gemini API key: ").strip()
    if not api_key:
        print("No API key provided.")
        sys.exit(1)

client = genai.Client(api_key=api_key)

with open(IMAGE_PATH, "rb") as f:
    img_bytes = f.read()

prompt = f"{PROMPTS[STORE]}\n\n{BODY}"

print(f"Model: gemini-3-flash-preview")
print(f"Store: {STORE}")
print(f"Image: {IMAGE_PATH}")
print(f"Image size: {len(img_bytes)} bytes")
print("Sending request...")

response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=[prompt, types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")],
)

print(f"\n--- RAW RESPONSE ---\n{response.text}\n--- END ---\n")

try:
    data = json.loads(response.text)
    print(f"Parsed {len(data)} products:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
except json.JSONDecodeError:
    print("Response is not valid JSON (may need prompt adjustment)")
