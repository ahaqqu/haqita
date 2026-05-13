"""
Qwen3-VL OCR Processor for Product Promos
Runs on Windows with Ollama + Qwen3-VL 2B
Extracts product names and prices as structured pairs
"""

import os
import json
import base64
import time
from pathlib import Path
from typing import List, Dict, Any
import requests
import logging

logger = logging.getLogger(__name__)

# Ollama API endpoint (default)
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen3-vl:2b"
MODEL_CTX = 8192

# Prompt optimized for product promo extraction
PROMPT_PRODUCTS = """
Analyze this product promo image. Each product card has this layout (top to bottom):
1. Promo text (left side, if any)
2. BRAND NAME in uppercase (if any, e.g., "AICE", "BANGO", "INDOMIE")
3. Product name (multiple lines possible, but always below the brand)
4. Promo text (left side, if any) + Unit/Price info
5. Additional info like regional pricing (if any)

The brochure contains both Indonesian and English text. Extract text exactly as shown in either language.

Return ONLY a valid JSON array. No explanations, no markdown, no extra text:
[
  {"brand": "AICE", "product": "Sandwich Cookies Panda", "price": "39.900", "unit": "6 x 45 ml", "promo": "BUY 1 GET 1"},
  {"brand": null, "product": "Gula Pasir", "price": "53.000", "unit": "1 kg", "promo": null}
]

Field rules:
- brand: The product BRAND in uppercase above the product name. "LOTTE MART" is the store name, NOT a brand — set to null.
- product: Product name only, without the brand.
- price: The main price. Use the format shown (e.g., "39.900" or "39,900"). Ignore regional pricing text.
- unit: Full quantity ("6 x 45 ml", "48 g - 55 g", "200 g", "500 ml", "1 kg"). Set to null if none.
- promo: Promotional text near this product ("BUY 1 GET 1", "DAPAT 2 pcs", "Max 1"). Set to null if none.

Other rules:
- Extract EVERY visible product. Look carefully — do not skip any.
- Do not include any text outside the JSON array
- If no products found, return []
"""

PROMPT_DATE = """
Look at this product promo image and find the promo validity period or date range (in Indonesian or English).
Return ONLY a single JSON object — no extra text:
{"promo_period": "the date range or validity period as shown"}

Examples:
{"promo_period": "7 - 20 Mei 2026"}
{"promo_period": "Berlaku 1-15 Mei 2026"}
{"promo_period": "Periode 1 s/d 30 Juni 2026"}
{"promo_period": "Valid until 15 May 2026"}

Rules:
- Look for text like "periode", "berlaku", "valid", "promo", "s/d", "sampai", "sd.", date ranges, or expiry dates
- Extract the text exactly as shown
- If no promo period is found, return {"promo_period": null}
"""


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def call_ollama(prompt: str, base64_image: str, timeout: int = 300) -> str:
    """Send a prompt + image to Ollama and return the raw response text"""
    is_cold = not hasattr(call_ollama, "_warmed") or not call_ollama._warmed
    if is_cold:
        print(f"   Loading model (first request may take a while)...")
        call_ollama._warmed = True

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": [base64_image],
        "stream": False,
        "options": {
            "num_ctx": MODEL_CTX
        }
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
    Extract product-price pairs from an image using Qwen3-VL via Ollama
    """
    if not os.path.exists(image_path):
        print(f"[!] Image not found: {image_path}")
        return []
    
    base64_image = encode_image_to_base64(image_path)
    max_retries = 3
    prompts = [
        PROMPT_PRODUCTS,
        PROMPT_PRODUCTS + "\nIMPORTANT: Your previous output was NOT a valid JSON array. Return ONLY a JSON array like [{...}, {...}]. No explanations, no markdown, no extra text.",
        PROMPT_PRODUCTS + "\nCRITICAL: You MUST return ONLY a valid JSON array. Example: [{\"brand\": \"AICE\", \"product\": \"Sandwich Cookies Panda\", \"price\": \"39.900\"}]. Nothing else. No markdown. No additional text before or after."
    ]
    
    for attempt in range(1, max_retries + 1):
        idx = min(attempt - 1, len(prompts) - 1)
        content = call_ollama(prompts[idx], base64_image)
        
        if debug_file:
            debug_info = {
                "image": image_path,
                "attempt": attempt,
                "prompt": prompts[idx],
                "response": content,
                "timestamp": str(__import__('datetime').datetime.now())
            }
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(debug_info, indent=2, ensure_ascii=False) + "\n\n")
        
        if not content:
            if attempt < max_retries:
                print(f"   Retry {attempt}/{max_retries} (empty response)...")
                continue
            return []
        
        products = parse_qwen_response(content)
        
        if products:
            print(f"[OK] Extracted {len(products)} product(s) from {os.path.basename(image_path)}")
            return products
        
        if attempt < max_retries:
            print(f"   Retry {attempt}/{max_retries} (bad format)...")
    
    print(f"[-] No products found in {os.path.basename(image_path)}")
    return []


def extract_promo_date(image_path: str, debug_file: str = None) -> str:
    """Extract promo validity period/date range from an image"""
    if not os.path.exists(image_path):
        return ""
    
    base64_image = encode_image_to_base64(image_path)
    max_retries = 3
    prompts = [
        PROMPT_DATE,
        PROMPT_DATE + "\nIMPORTANT: Return ONLY a JSON object like {\"promo_period\": \"...\"}. No other text.",
        PROMPT_DATE + "\nCRITICAL: ONLY a JSON object. No markdown. No extra words. Example: {\"promo_period\": \"7 - 20 Mei 2026\"}"
    ]
    
    for attempt in range(1, max_retries + 1):
        idx = min(attempt - 1, len(prompts) - 1)
        content = call_ollama(prompts[idx], base64_image)
        
        if debug_file:
            debug_info = {
                "image": image_path,
                "attempt": attempt,
                "prompt": prompts[idx],
                "response": content,
                "timestamp": str(__import__('datetime').datetime.now())
            }
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(debug_info, indent=2, ensure_ascii=False) + "\n\n")
        
        if not content:
            if attempt < max_retries:
                print(f"   Retry date {attempt}/{max_retries} (empty)...")
                continue
            return ""
        
        try:
            data = json.loads(content)
            period = data.get("promo_period", "") or ""
            if period:
                return period
        except json.JSONDecodeError:
            pass
        
        if attempt < max_retries:
            print(f"   Retry date {attempt}/{max_retries} (bad format)...")
    
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
    
    # Process each image with incremental output
    all_results = {}
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    for i, image_path in enumerate(image_files, 1):
        name = os.path.basename(image_path)
        print(f"[{i}/{len(image_files)}] {name}")
        
        t0 = time.time()
        print(f"   Extracting products...")
        products = extract_product_prices(image_path, debug_file=debug_file)
        t1 = time.time()
        promo_date = extract_promo_date(image_path, debug_file=debug_file)
        t2 = time.time()
        
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
        
        print(f"   [{len(products)} products in {t1-t0:.0f}s + date in {t2-t1:.0f}s]")
        
        # Write incremental results after each image
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        
        print()
    
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
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    input_directory = "data/test/lotte"
    output_json = f"output/product_prices_{timestamp}.json"
    debug_log = f"output/qwen_debug_{timestamp}.log"
    
    print("Qwen3-VL Product Promo OCR")
    print("=" * 50)
    print(f"Model: {MODEL_NAME}")
    print(f"Input: {input_directory}")
    print(f"Output: {output_json}")
    print(f"Debug Log: {debug_log}")
    print("=" * 50)
    print()
    
    process_promo_images(input_directory, output_json, debug_file=debug_log)
