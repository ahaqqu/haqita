import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from scripts.common.http_client import QuotaExhaustedError, retry_call

from .prompts import get_prompt
from .ocr_processor import _parse_ocr_json


QuotaExhaustedError  # re-exported for backward compatibility with run_ocr.py


def call_gemini_ocr(image_path: str, cfg: dict, max_retries: int = 3) -> list[dict]:
    load_dotenv()
    gemini_cfg = cfg['ocr'].get('gemini', {})
    store = cfg.get('store', 'superindo')
    prompt = get_prompt(store)

    api_key = gemini_cfg.get('api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)
    model = gemini_cfg.get('model')
    if not model:
        raise ValueError("Gemini model not configured in config.yaml under ocr.gemini.model")

    with open(image_path, 'rb') as f:
        img_bytes = f.read()

    def _call():
        return client.models.generate_content(
            model=model,
            contents=[
                prompt,
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            ],
        )

    response = retry_call(_call, max_retries=max_retries, context="gemini_ocr")
    return _parse_ocr_json(response.text)
