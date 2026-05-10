"""
Qwen2-VL OCR Processor for Product Promos
Runs natively on Windows with Ollama + Qwen2-VL
Extracts product names and prices as structured pairs
"""

import os
import json
import base64
from pathlib import Path
from typing import List, Dict, Any
import requests

# Ollama API endpoint (default)
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5vl:3b"  # Use "qwen2.5vl:7b" for better accuracy if VRAM allows, or "qwen3-vl" for latest

# Prompt optimized for product promo extraction
PROMPT = """
Analyze this product promo image and extract all product-price pairs.
Return ONLY a valid JSON array with this exact structure:
[
  {"product": "product name", "price": "price value", "unit": "unit if any"},
  ...
]

Rules:
- Extract every visible product with its price
- If price has unit (e.g., "/kg", "/pcs"), include it in "unit" field
- If no unit, set "unit" to null
- Do not include any text outside the JSON array
- If no products found, return empty array []
- Be precise with product names and prices exactly as shown
"""


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


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
                print(f"⚠️  Model '{MODEL_NAME}' not found. Available models: {model_names}")
                print(f"   Run: ollama pull {MODEL_NAME}")
                return False
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Ollama is not running. Start it with: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error checking Ollama: {e}")
        return False


def extract_product_prices(image_path: str, debug_file: str = None) -> List[Dict[str, Any]]:
    """
    Extract product-price pairs from an image using Qwen2-VL via Ollama
    
    Args:
        image_path: Path to the image file
        debug_file: Optional path to save debug info
        
    Returns:
        List of dictionaries with product, price, and unit
    """
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        return []
    
    # Encode image
    base64_image = encode_image_to_base64(image_path)
    
    # Prepare request for Ollama
    payload = {
        "model": MODEL_NAME,
        "prompt": PROMPT,
        "images": [base64_image],
        "stream": False,
        "format": "json"  # Request JSON output
    }
    
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=300  # 2 minutes timeout for large images
        )
        
        # Save debug info if requested
        if debug_file:
            debug_info = {
                "image": image_path,
                "request_payload": payload,
                "response_status": response.status_code,
                "response_headers": dict(response.headers),
                "response_body": response.text,
                "timestamp": str(__import__('datetime').datetime.now())
            }
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(debug_info, indent=2, ensure_ascii=False) + "\n\n")
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("response", "")
            
            # Parse JSON from response
            try:
                # Clean up response - sometimes there's extra text
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                products = json.loads(content)
                
                if isinstance(products, list):
                    print(f"✅ Extracted {len(products)} product(s) from {os.path.basename(image_path)}")
                    return products
                else:
                    print(f"⚠️  Unexpected response format for {image_path}")
                    return []
                    
            except json.JSONDecodeError as e:
                print(f"⚠️  Failed to parse JSON from {image_path}: {e}")
                print(f"   Raw response: {content[:200]}...")
                return []
        else:
            print(f"❌ Ollama API error ({response.status_code}): {response.text}")
            return []
            
    except requests.exceptions.Timeout:
        print(f"⏱️  Timeout processing {image_path}")
        return []
    except Exception as e:
        print(f"❌ Error processing {image_path}: {e}")
        return []


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
        print("\n💡 To fix:")
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
        print(f"❌ No images found in {input_dir}")
        return
    
    print(f"📸 Found {len(image_files)} image(s) to process\n")
    
    # Process each image
    all_results = {}
    
    for i, image_path in enumerate(image_files, 1):
        print(f"[{i}/{len(image_files)}] Processing: {os.path.basename(image_path)}")
        
        products = extract_product_prices(image_path, debug_file=debug_file)
        
        # Store relative path as key
        rel_path = os.path.relpath(image_path, input_dir)
        all_results[rel_path] = {
            "products": products,
            "count": len(products)
        }
        
        # Show extracted products
        for prod in products:
            price = prod.get("price", "N/A")
            unit = prod.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            print(f"   • {prod.get('product', 'Unknown')}: {price}{unit_str}")
        
        print()
    
    # Save results
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Results saved to: {output_file}")
    
    # Summary
    total_products = sum(r["count"] for r in all_results.values())
    print(f"\n📊 Summary: {total_products} products extracted from {len(image_files)} images")


if __name__ == "__main__":
    # Default: process images from data/logs/images
    input_directory = "data/logs/images"
    output_json = "output/product_prices.json"
    debug_log = "output/qwen_debug.log"  # Debug log file
    
    print("🔍 Qwen2-VL Product Promo OCR")
    print("=" * 50)
    print(f"Model: {MODEL_NAME}")
    print(f"Input: {input_directory}")
    print(f"Output: {output_json}")
    print(f"Debug Log: {debug_log}")
    print("=" * 50)
    print()
    
    process_promo_images(input_directory, output_json, debug_file=debug_log)
