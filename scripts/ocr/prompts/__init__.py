from .gemini import get_gemini_prompt


def get_prompt(store: str = "superindo") -> str:
    return get_gemini_prompt(store)
