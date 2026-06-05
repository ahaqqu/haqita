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


def test_load_config_env_override(monkeypatch):
    """Verify that GEMINI_API_KEY from .env overrides config."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-from-env")
    from scripts.config import load_config
    cfg = load_config()
    assert cfg.get('ocr', {}).get('gemini', {}).get('api_key') == "test-key-from-env"


def test_load_config_sets_store():
    from scripts.config import load_config
    cfg = load_config(store="lotte")
    assert cfg.get('store') == "lotte"
