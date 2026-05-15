from .ollama import get_ollama_prompt
from .gemini import get_gemini_prompt

PROMPTS = {
    "ollama": get_ollama_prompt,
    "gemini": get_gemini_prompt,
}


def get_prompt(provider: str, store: str = "superindo") -> str:
    fn = PROMPTS.get(provider)
    if not fn:
        raise ValueError(f"Unknown OCR provider: {provider}")
    return fn(store)
