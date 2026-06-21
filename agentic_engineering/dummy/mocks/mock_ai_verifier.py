import os


def mock_verify(pairs: list[dict]) -> list[str | None]:
    """Return deterministic YES for all ambiguous pairs."""
    return ["YES"] * len(pairs)


def is_mock_enabled() -> bool:
    return os.getenv("MOCK_AI_VERIFIER") == "1"
