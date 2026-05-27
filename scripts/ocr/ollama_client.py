"""
Ollama OCR Client — Two-step extraction strategy.

Step 1: /api/generate — "Describe every product you see" (free-form)
Step 2: /api/chat     — "Convert to JSON" using step 1 as context

This two-step approach is proven to produce better results than single-step
JSON extraction. If step 2 fails, retries with chat context showing the
previous bad output so the model knows what went wrong.
"""

import base64
import json
import logging
import os
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Ollama base URL — use env var for Docker (host.docker.internal:11434)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Prompts ──────────────────────────────────────────────────────────────────

PROMPT_DESCRIBE = """
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

PROMPT_CONVERT = """
Now convert the products you described into a valid JSON array with this exact format.
No explanations, no extra text, ONLY the JSON array:
[
  {"brand": "AICE", "name": "Sandwich Cookies Panda", "price": 39900, "unit": "6 x 45 ml", "promo": ["BUY 1 GET 1"]},
  {"brand": null, "name": "Gula Pasir", "price": 53000, "unit": "1 kg", "promo": null}
]

Rules:
- brand: The product brand (uppercase). If only store name is visible, set to null.
- name: Product name only.
- price: Integer in IDR, no dots or commas. Indonesian thousands separator is '.' — ignore it.
- unit: Full quantity (e.g., "85 g", "1.5 L"). Set to null if none.
- promo: Array of promo texts (e.g., ["DAPAT 5 pcs", "Beli 2 Gratis 1"]). Set to null if none.
"""

RETRY_CORRECTION = (
    "That was not valid. Return ONLY a JSON array: "
    '[{"brand": "AICE", "name": "Sandwich Cookies Panda", "price": 39900, "unit": "6 x 45 ml", "promo": ["BUY 1 GET 1"]}] '
    "No other text."
)

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

DATE_RETRY_CORRECTION = (
    'That was not a valid JSON object. Return ONLY {"promo_period": "..."} with no other text.'
)


def _encode_image(image_path: str) -> str:
    """Encode image to base64 string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _call_generate(prompt: str, img_b64: str, model: str, options: dict, timeout: int) -> str:
    """Call /api/generate with image and prompt."""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": options,
    }
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "")


def _call_chat(prompt: str, img_b64: str, prev_output: str, model: str,
               options: dict, correction: str = "", timeout: int = 300) -> str:
    """Call /api/chat with image, prompt, and previous output as context."""
    messages = [
        {"role": "user", "content": prompt, "images": [img_b64]},
        {"role": "assistant", "content": prev_output},
    ]
    if correction:
        messages.append({"role": "user", "content": correction})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
    }
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def _parse_ollama_json(raw_text: str) -> list[dict]:
    """Strip markdown fences and parse JSON array from Ollama response."""
    if not raw_text or not raw_text.strip():
        return []

    clean = raw_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    # Find JSON array
    match = re.search(r"\[.*\]", clean, re.DOTALL)
    if not match:
        logger.debug(f"No JSON array found in Ollama response: {clean[:200]}")
        return []

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Ollama JSON: {e}")
        return []

    if isinstance(data, list):
        return data

    # Fallback: look for nested list
    if isinstance(data, dict):
        for key in ("products", "items", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]

    logger.error(f"Unexpected JSON type from Ollama: {type(data).__name__}")
    return []


def call_ollama_ocr(image_path: str, cfg: dict) -> list[dict]:
    """
    Two-step OCR: describe → convert to JSON.
    Retries up to max_retries on failure.
    """
    if not Path(image_path).exists():
        logger.error(f"Image not found: {image_path}")
        return []

    ollama_cfg = cfg["ocr"].get("ollama", {})
    model = ollama_cfg.get("model", "qwen2.5vl:7b")
    max_retries = ollama_cfg.get("max_retries", 3)
    timeout = ollama_cfg.get("timeout_seconds", 300)

    options = {
        "temperature": ollama_cfg.get("temperature", 0),
        "num_ctx": ollama_cfg.get("num_ctx", 8192),
        "seed": 42,
    }

    img_b64 = _encode_image(image_path)
    prev_output = ""

    for attempt in range(1, max_retries + 1):
        try:
            if attempt == 1:
                # Step 1: free-form description
                desc = _call_generate(PROMPT_DESCRIBE, img_b64, model, options, timeout)
                if not desc:
                    if attempt < max_retries:
                        logger.debug("Retry %d/%d (empty description)", attempt, max_retries)
                        continue
                    return []

                # Step 2: convert to JSON with description as context
                content = _call_chat(PROMPT_CONVERT, img_b64, desc, model, options, timeout=timeout)
            else:
                # Retry: use chat with previous bad output + correction
                content = _call_chat(
                    PROMPT_DESCRIBE, img_b64, prev_output, model, options,
                    correction=RETRY_CORRECTION, timeout=timeout
                )

            if not content:
                if attempt < max_retries:
                    logger.debug("Retry %d/%d (empty response)", attempt, max_retries)
                    continue
                return []

            products = _parse_ollama_json(content)
            if products:
                return products

            prev_output = content[:500]

            if attempt < max_retries:
                logger.debug("Retry %d/%d (bad format)", attempt, max_retries)

        except requests.RequestException as e:
            logger.error("Ollama API error on attempt %d: %s", attempt, e)
            if attempt < max_retries:
                continue
            return []

    return []


def extract_promo_date(image_path: str, cfg: dict) -> str:
    """
    Extract promo validity period from an image.
    Returns empty string if not found.
    """
    if not Path(image_path).exists():
        return ""

    ollama_cfg = cfg["ocr"].get("ollama", {})
    model = ollama_cfg.get("model", "qwen2.5vl:7b")
    max_retries = ollama_cfg.get("max_retries", 3)
    timeout = ollama_cfg.get("timeout_seconds", 300)

    options = {
        "temperature": ollama_cfg.get("temperature", 0),
        "num_ctx": ollama_cfg.get("num_ctx", 8192),
        "seed": 42,
    }

    img_b64 = _encode_image(image_path)
    prev_output = ""

    for attempt in range(1, max_retries + 1):
        try:
            if attempt == 1:
                content = _call_generate(PROMPT_DATE, img_b64, model, options, timeout)
            else:
                content = _call_chat(
                    PROMPT_DATE, img_b64, prev_output, model, options,
                    correction=DATE_RETRY_CORRECTION, timeout=timeout
                )

            if not content:
                if attempt < max_retries:
                    continue
                return ""

            # Parse JSON object
            clean = content.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                period = data.get("promo_period", "") or ""
                if period:
                    return period

            prev_output = content[:500]

        except (requests.RequestException, json.JSONDecodeError):
            if attempt < max_retries:
                continue
            return ""

    return ""
