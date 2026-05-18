"""Shared configuration loading — load config.yaml with .env overrides."""

import os
from pathlib import Path


def load_config(store: str | None = None) -> dict:
    import yaml
    from dotenv import load_dotenv
    load_dotenv()

    config_path = Path(__file__).resolve().parent.parent / 'config.yaml'
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    env_provider = os.getenv('OCR_PROVIDER')
    if env_provider:
        cfg.setdefault('ocr', {})['provider'] = env_provider

    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = env_key

    env_ai = os.getenv('AI_VERIFIER_PROVIDER')
    if env_ai:
        cfg.setdefault('consolidation', {}).setdefault('ai_verifier', {})['provider'] = env_ai

    if store:
        cfg['store'] = store

    return cfg
