"""Tests for scripts/config.py — shared config loader."""

import os
import tempfile
from pathlib import Path


def test_load_config_basic():
    from scripts.config import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert 'ocr' in cfg
    assert 'scrapers' in cfg or 'consolidation' in cfg


def test_load_config_env_overrides(monkeypatch):
    """Verify that .env overrides are applied."""
    monkeypatch.setenv("OCR_PROVIDER", "gemini")
    monkeypatch.setenv("AI_VERIFIER_PROVIDER", "gemini")
    from scripts.config import load_config
    cfg = load_config()
    assert cfg.get('ocr', {}).get('provider') == "gemini"
    assert cfg.get('consolidation', {}).get('ai_verifier', {}).get('provider') == "gemini"


def test_load_config_sets_store():
    from scripts.config import load_config
    cfg = load_config(store="lotte")
    assert cfg.get('store') == "lotte"
