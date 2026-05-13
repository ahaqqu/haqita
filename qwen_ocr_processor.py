"""
Qwen2.5VL OCR Processor for Product Promos
Runs natively on Windows with Ollama + Qwen2.5VL
Extracts product names and prices as structured pairs
"""

import os
import json
import base64
import io
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image
import requests
import logging

logger = logging.getLogger(__name__)

# Ollama API endpoint (default)
OLLAMA_BASE_URL = "http://localhost:11434"
QWN_MODEL = os.environ.get("QWN_MODEL", "3b")

if QWN_MODEL == "qwen3":
    MODEL_NAME = "qwen3-vl:2b"
    MODEL_CTX = 8192     # 2B Q4_K_M is only 1.9GB — plenty of VRAM for higher ctx
    MAX_DIM = 672
elif QWN_MODEL == "7b":
    MODEL_NAME = "qwen2.5vl:7b"
    MODEL_CTX = 4096
    MAX_DIM = 672
else:
    MODEL_NAME = "qwen2.5vl:3b"
    MODEL_CTX = 4096
    MAX_DIM = 672

# Prompt optimized for product promo extraction
PROMPT_PRODUCTS = """
Analyze this product promo image. Each product card has this layout (top to bottom):
1. Promo text (left side, if any)
2. BRAND NAME in uppercase (if any, e.g., "AICE", "BANGO", "INDOMIE")
3. Product name (multiple lines possible, but always below the brand)
4. Promo text (left side, if any) + Unit/Price info
5. Additional info like regional pricing (if any)

Return ONLY a valid JSON array with this exact structure:
[
  {"brand": "brand name", "product": "product name", "price": "price value", "unit": "unit if any", "promo": "promo text if any"},
  ...
]

Field rules:
- brand: The product BRAND — uppercase text directly above the product name. "LOTTE MART" is the store/supermarket name, NOT a brand. If the only uppercase text is "LOTTE MART", set brand to null.
- product: Product name without the brand.
- price: The main product price only. Ignore regional pricing text like "harga pulau jawa", "medan", "makassar".
- unit: Full quantity text. Examples: "6 x 45 ml", "48 g - 55 g", "200 g", "500 ml", "1 kg". Set to null if none.
- promo: Promotional text near this product (e.g., "BUY 1 GET 1", "DAPAT 2 pcs", "Max 1"). Set to null if none.

Other rules:
- Extract every visible product card. Do not skip any.
- Do not include any text outside the JSON array
- If no products found, return empty array []
- Be precise — extract exactly what is shown in the image
"""

PROMPT_DATE = """
Look at this product promo image and find the promo validity period or date range.
Return ONLY a single JSON object:
{"promo_period": "the date range or validity period as shown"}

Examples:
- {"promo_period": "25 Maret - 1 April 2026"}
- {"promo_period": "Berlaku 1-15 Mei 2026"}
- {"promo_period": "Periode 1 s/d 30 Juni 2026"}
- {"promo_period": "Valid until 15 May 2026"}

Rules:
- Look for text like "periode", "berlaku", "valid", "promo", "s/d", "sampai", "sd.", date ranges, or expiry dates
- If no promo period is found, return {"promo_period": null}
- Return ONLY the JSON object, nothing else
"""


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def resize_image_for_ollama(image_path: str) -> str:
    """Load image, resize to fit model constraints, return base64 string.
    Qwen2.5VL requires image dimensions divisible by 14 (patch size).
    """
    img = Image.open(image_path)
    patch_size = 14

    if img.width > MAX_DIM or img.height > MAX_DIM:
        ratio = min(MAX_DIM / img.width, MAX_DIM / img.height)
        w = int(img.width * ratio / patch_size) * patch_size
        h = int(img.height * ratio / patch_size) * patch_size
    else:
        w = (img.width // patch_size) * patch_size
        h = (img.height // patch_size) * patch_size

    if w < patch_size: w = patch_size
    if h < patch_size: h = patch_size

    if (w, h) != (img.width, img.height):
        img = img.resize((w, h), Image.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=90)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def call_ollama(prompt: str, base64_image: str, timeout: int = 300) -> str:
    """Send a prompt + image to Ollama and return the raw response text"""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": [base64_image],
        "stream": False,
        "options": {"num_ctx": MODEL_CTX}
    }
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=timeout
    )
    if response.status_code != 200:
        print(f"[!] Ollama API error ({response.status_code}): {response.text[:200]}")
        return ""

    content = response.json().get("response", "")
    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def check_ollama_running() -> bool:
    """Check if Ollama is running and model is available"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]
            if MODEL_NAME in model_names:
                return True
            else:
                print(f"[!] Model '{MODEL_NAME}' not found. Available models: {model_names}")
                print(f"    Run: ollama pull {MODEL_NAME}")
                return False
        return False
    except requests.exceptions.ConnectionError:
        print("[!] Ollama is not running. Start it with: ollama serve")
        return False
    except Exception as e:
        print(f"[!] Error checking Ollama: {e}")
        return False


def extract_product_prices(image_path: str, debug_file: str = None) -> List[Dict[str, Any]]:
    """
    Extract product-price pairs from an image using Qwen2.5VL via Ollama
    
    Args:
        image_path: Path to the image file
        debug_file: Optional path to save debug info
        
    Returns:
        List of dictionaries with product, price, and unit
    """
    if not os.path.exists(image_path):
        print(f"[!] Image not found: {image_path}")
        return []
    
    base64_image = resize_image_for_ollama(image_path)
    content = call_ollama(PROMPT_PRODUCTS, base64_image)
    
    if debug_file:
        debug_info = {
            "image": image_path,
            "prompt": PROMPT_PRODUCTS,
            "response": content,
            "timestamp": str(__import__('datetime').datetime.now())
        }
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(debug_info, indent=2, ensure_ascii=False) + "\n\n")
    
    if not content:
        return []
    
    products = parse_qwen_response(content)
    
    if products:
        # Post-processing: "LOTTE MART" is the store name, not a product brand
        for p in products:
            brand = p.get("brand")
            if brand and str(brand).upper() == "LOTTE MART":
                p["brand"] = None
        print(f"[OK] Extracted {len(products)} product(s) from {os.path.basename(image_path)}")
    else:
        print(f"[-] No products found in {os.path.basename(image_path)}")
    
    return products


def extract_promo_date(image_path: str, debug_file: str = None) -> str:
    """Extract promo validity period/date range from an image"""
    if not os.path.exists(image_path):
        return ""
    
    base64_image = resize_image_for_ollama(image_path)
    content = call_ollama(PROMPT_DATE, base64_image)
    
    if debug_file:
        debug_info = {
            "image": image_path,
            "prompt": PROMPT_DATE,
            "response": content,
            "timestamp": str(__import__('datetime').datetime.now())
        }
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(debug_info, indent=2, ensure_ascii=False) + "\n\n")
    
    if not content:
        return ""
    
    try:
        data = json.loads(content)
        return data.get("promo_period", "") or ""
    except json.JSONDecodeError:
        return ""


def process_promo_images(input_dir: str, output_file: str = "output/product_prices.json", debug_file: str = None):
    """
    Process all promo images in a directory and extract product-price pairs
    
    Args:
        input_dir: Directory containing promo images
        output_file: Output JSON file path
        debug_file: Optional debug log file path
    """
    # Check if Ollama is running
    if not check_ollama_running():
        print("\nTo fix:")
        print("   1. Install Ollama: https://ollama.com/download")
        print(f"   2. Pull model: ollama pull {MODEL_NAME}")
        print("   3. Start Ollama: ollama serve")
        return
    
    # Create output directory
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Find all images
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    image_files = []
    
    for root, _, files in os.walk(input_dir):
        for file in files:
            if Path(file).suffix.lower() in image_extensions:
                image_files.append(os.path.join(root, file))
    
    if not image_files:
        print(f"[!] No images found in {input_dir}")
        return
    
    print(f"[*] Found {len(image_files)} image(s) to process\n")
    
    # Process each image
    all_results = {}
    
    for i, image_path in enumerate(image_files, 1):
        print(f"[{i}/{len(image_files)}] Processing: {os.path.basename(image_path)}")
        
        products = extract_product_prices(image_path, debug_file=debug_file)
        promo_date = extract_promo_date(image_path, debug_file=debug_file)
        
        # Store relative path as key
        rel_path = os.path.relpath(image_path, input_dir)
        entry = {
            "products": products,
            "count": len(products)
        }
        if promo_date:
            entry["promo_period"] = promo_date
        
        all_results[rel_path] = entry
        
        # Show extracted products
        if promo_date:
            print(f"   Period: {promo_date}")
        for prod in products:
            brand = prod.get("brand", "")
            product = prod.get("product", "Unknown")
            price = prod.get("price", "N/A")
            unit = prod.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            brand_str = f"[{brand}] " if brand else ""
            print(f"   - {brand_str}{product}: {price}{unit_str}")
        
        print()
    
    # Save results
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"[*] Results saved to: {output_file}")
    
    # Summary
    total_products = sum(r["count"] for r in all_results.values())
    print(f"\n[*] Summary: {total_products} products extracted from {len(image_files)} images")

def parse_qwen_response(response_text: str) -> list:
    """
    Parses the model's JSON output into a list of product dicts.
    The model returns a flat JSON array: [{product, price, unit, promo}, ...]
    """
    if not response_text or not response_text.strip():
        return []

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse model output as JSON: {e}")
        logger.debug(f"Raw output: {response_text[:500]}")
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ('products', 'items', 'results'):
            if key in data and isinstance(data[key], list):
                return data[key]
        logger.error(f"No product list found in response. Keys: {list(data.keys())}")
        return []

    logger.error(f"Unexpected JSON type: {type(data).__name__}")
    return []

if __name__ == "__main__":
    # Default: process images from data/logs/images
    input_directory = "data/logs/images"
    output_json = "output/product_prices.json"
    debug_log = "output/qwen_debug.log"  # Debug log file
    
    print("Qwen2.5VL Product Promo OCR")
    print("=" * 50)
    print(f"Model: {MODEL_NAME}")
    print(f"Input: {input_directory}")
    print(f"Output: {output_json}")
    print(f"Debug Log: {debug_log}")
    print("=" * 50)
    print()
    
    process_promo_images(input_directory, output_json, debug_file=debug_log)
