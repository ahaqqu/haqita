import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .prompts import get_prompt
from .ocr_processor import _parse_ocr_json


def call_gemini_ocr(image_path: str, cfg: dict) -> list[dict]:
    load_dotenv()
    gemini_cfg = cfg['ocr'].get('gemini', {})
    store = cfg.get('store', 'superindo')
    prompt = get_prompt('gemini', store)

    api_key = gemini_cfg.get('api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)
    model = gemini_cfg.get('model', 'gemini-2.0-flash')

    with open(image_path, 'rb') as f:
        img_bytes = f.read()

    response = client.models.generate_content(
        model=model,
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
        ]
    )
    return _parse_ocr_json(response.text)
