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
PROMPT_PRODUCTS_FIRST = """
Look at this promo brochure image. Describe every product you see.
For each product, tell me:
- The BRAND name (uppercase text, if visible)
- The product name
- The price
- The quantity or unit (e.g., "200 g", "6 x 45 ml", "1 kg")
- Any promo text (e.g., "BUY 1 GET 1", "DAPAT 2 pcs")

The brochure uses both Indonesian and English. Extract text exactly as shown.
List them one by one — do not skip any product.
"""

PROMPT_PRODUCTS_SECOND = """
Now convert the products you described into a valid JSON array with this exact format.
No explanations, no extra text, ONLY the JSON array:
[
  {"brand": "AICE", "product": "Sandwich Cookies Panda", "price": "39.900", "unit": "6 x 45 ml", "promo": "BUY 1 GET 1"},
  {"brand": null, "product": "Gula Pasir", "price": "53.000", "unit": "1 kg", "promo": null}
]

Rules:
- brand: The product brand (uppercase). If only "LOTTE MART" is visible, set to null.
- product: Product name only.
- price: Just the number. Ignore "Rp", "Harga", regional pricing.
- unit: Full quantity. Set to null if none.
- promo: Promo text. Set to null if none.
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
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def call_ollama_chat(prompt: str, base64_image: str, prev_output: str, correction: str = "", timeout: int = 300) -> str:
    """Send prompt + image + previous output as context via /api/chat"""
    messages = [
        {"role": "user", "content": prompt, "images": [base64_image]},
        {"role": "assistant", "content": prev_output}
    ]
    if correction:
        messages.append({"role": "user", "content": correction})
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": MODEL_CTX}
    }
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=timeout
    )
    if response.status_code != 200:
        print(f"[!] Ollama API error ({response.status_code}): {response.text[:200]}")
        return ""

    content = response.json().get("message", {}).get("content", "")
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
    if not os.path.exists(image_path):
        print(f"[!] Image not found: {image_path}")
        return []
    
    base64_image = encode_image_to_base64(image_path)
    max_retries = 3
    prev_output = ""
    
    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            desc = call_ollama(PROMPT_PRODUCTS_FIRST, base64_image)
            if not desc:
                if attempt < max_retries:
                    print(f"   Retry {attempt}/{max_retries} (empty description)...")
                    continue
                return []
            content = call_ollama_chat(PROMPT_PRODUCTS_SECOND, base64_image, desc, "")
        else:
            # Retry with chat context showing previous bad output
            correction = (
                "That was not valid. Return ONLY a JSON array: "
                '[{"brand": "AICE", "product": "Sandwich Cookies Panda", "price": "39.900", "unit": "6 x 45 ml", "promo": "BUY 1 GET 1"}] '
                "No other text."
            )
            content = call_ollama_chat(PROMPT_PRODUCTS_FIRST, base64_image, prev_output, correction)
        
        if debug_file:
            debug_info = {
                "image": image_path,
                "attempt": attempt,
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
        
        prev_output = content[:500]
        
        if attempt < max_retries:
            print(f"   Retry {attempt}/{max_retries} (bad format)...")
    
    print(f"[-] No products found in {os.path.basename(image_path)}")
    return []


def extract_promo_date(image_path: str, debug_file: str = None) -> str:
    if not os.path.exists(image_path):
        return ""
    
    base64_image = encode_image_to_base64(image_path)
    max_retries = 3
    prev_output = ""
    correction = ""
    
    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            content = call_ollama(PROMPT_DATE, base64_image)
        else:
            correction = "That was not a valid JSON object. Return ONLY {\"promo_period\": \"...\"} with no other text."
            content = call_ollama_chat(PROMPT_DATE, base64_image, prev_output, correction)
        
        if debug_file:
            used_prompt = PROMPT_DATE
            if attempt > 1:
                used_prompt = f"{PROMPT_DATE}\n[Previous bad output]: {prev_output[:200]}\n[Correction]: {correction}"
            debug_info = {
                "image": image_path,
                "attempt": attempt,
                "prompt": used_prompt,
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
        
        prev_output = content[:500]
        
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
    
    input_directory = "data/test/lotte/image-brochure"
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
