import base64
import os

import requests

from .prompts import get_prompt
from .ocr_processor import _parse_ocr_json

# Ollama base URL — use env var for Docker (host.docker.internal:11434)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def call_ollama_ocr(image_path: str, cfg: dict) -> list[dict]:
    ollama_cfg = cfg['ocr'].get('ollama', {})
    store = cfg.get('store', 'superindo')
    prompt = get_prompt('ollama', store)

    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": ollama_cfg['model'],
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {
            "temperature": ollama_cfg.get('temperature', 0),
            "num_ctx": ollama_cfg.get('num_ctx', 8192),
            "seed": 42
        }
    }
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload,
                         timeout=ollama_cfg.get('timeout_seconds', 300))
    resp.raise_for_status()
    raw_text = resp.json()['response']
    return _parse_ocr_json(raw_text)
