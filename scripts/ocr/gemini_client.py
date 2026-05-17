import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .prompts import get_prompt
from .ocr_processor import _parse_ocr_json


def parse_retry_delay(error_msg: str) -> int | None:
    """Parse retry delay from Gemini API error message."""
    patterns = [
        r'retry in (\d+\.?\d*)s',
        r'retryDelay.*?(\d+)s',
        r'Please retry in (\d+\.?\d*)s',
    ]
    for pattern in patterns:
        match = re.search(pattern, error_msg.lower())
        if match:
            return int(float(match.group(1))) + 1
    return None


def call_gemini_ocr(image_path: str, cfg: dict, max_retries: int = 3) -> list[dict]:
    load_dotenv()
    gemini_cfg = cfg['ocr'].get('gemini', {})
    store = cfg.get('store', 'superindo')
    prompt = get_prompt('gemini', store)

    api_key = gemini_cfg.get('api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)
    model = gemini_cfg.get('model')
    if not model:
        raise ValueError("Gemini model not configured in config.yaml under ocr.gemini.model")

    with open(image_path, 'rb') as f:
        img_bytes = f.read()

    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                ]
            )
            return _parse_ocr_json(response.text)
        except Exception as e:
            last_error = e
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate limit" in err_str.lower():
                wait_time = parse_retry_delay(err_str) or 60
                print(f"[!] Rate limit hit. Waiting {wait_time}s before retry ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            elif attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[!] OCR failed: {e}. Retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise last_error
    raise last_error
