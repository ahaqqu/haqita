"""
Multi-tier matching pipeline for cross-store product matching.

Each gate is an isolated function. The orchestrator checks config before calling.
"""

import json
import logging
import os
import re
from enum import Enum
from typing import Any

from scripts.matching.normalizer import (
    canonical_tokens,
    normalize_brand,
    token_overlap,
    units_type_compatible,
    units_value_compatible,
)

logger = logging.getLogger(__name__)


class GateResult(Enum):
    SKIP = "skip"
    PASS = "pass"
    MATCH = "match"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    REVIEW = "review"


# ---------------------------------------------------------------------------
# Gate 0 — Unit type pre-filter
# ---------------------------------------------------------------------------

def gate0_unit_type(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 0: Skip if unit types are incompatible (weight vs count)."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate0_unit_type', True):
        return GateResult.PASS
    u1 = a.get('unit')
    u2 = b.get('unit')
    if not units_type_compatible(u1, u2):
        logger.debug("Gate 0 SKIP: incompatible units '%s' vs '%s'", u1, u2)
        return GateResult.SKIP
    return GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 1 — Brand pre-filter
# ---------------------------------------------------------------------------

def gate1_brand(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 1: Skip if normalized brands are known and different."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate1_brand', True):
        return GateResult.PASS
    b1 = normalize_brand(a.get('brand'))
    b2 = normalize_brand(b.get('brand'))
    if b1 and b2 and b1 != b2:
        logger.debug("Gate 1 SKIP: brands '%s' vs '%s'", b1, b2)
        return GateResult.SKIP
    return GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 2 — Token Jaccard pre-filter
# ---------------------------------------------------------------------------

def gate2_token_jaccard(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 2: Skip if token Jaccard overlap < threshold."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate2_token_jaccard', True):
        return GateResult.PASS
    threshold = cfg.get('consolidation', {}).get('token_jaccard_min', 0.30)
    score = token_overlap(a.get('name', ''), b.get('name', ''))
    if score < threshold:
        logger.debug("Gate 2 SKIP: Jaccard=%.2f < %.2f", score, threshold)
        return GateResult.SKIP
    return GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 3 — Exact token-set match
# ---------------------------------------------------------------------------

def gate3_exact_match(a: dict, b: dict, cfg: dict) -> GateResult:
    """Gate 3: Match if canonical tokens are equal AND units compatible."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate3_exact_match', True):
        return GateResult.PASS
    if canonical_tokens(a.get('name', '')) == canonical_tokens(b.get('name', '')):
        u1 = a.get('unit')
        u2 = b.get('unit')
        if units_value_compatible(u1, u2, cfg.get('consolidation', {}).get('unit_tolerance_pct', 15) / 100.0):
            logger.debug("Gate 3 MATCH: exact token match")
            return GateResult.MATCH
    return GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 4 — Embedding similarity
# ---------------------------------------------------------------------------

def gate4_embedding(a: dict, b: dict, cfg: dict, model=None, embeddings_a=None, embeddings_b=None, idx_a: int = 0, idx_b: int = 0) -> GateResult:
    """Gate 4: Embedding similarity. Returns MATCH/AMBIGUOUS/NO_MATCH."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate4_embedding', True):
        return GateResult.PASS

    auto_match = cfg.get('consolidation', {}).get('embedding_auto_match', 0.85)
    ambiguous_low = cfg.get('consolidation', {}).get('embedding_ambiguous_low', 0.55)

    if model is not None and embeddings_a is not None and embeddings_b is not None:
        from sklearn.metrics.pairwise import cosine_similarity
        score = float(cosine_similarity([embeddings_a[idx_a]], [embeddings_b[idx_b]])[0, 0])
    else:
        return GateResult.PASS

    if score >= auto_match:
        if units_value_compatible(a.get('unit'), b.get('unit'), cfg.get('consolidation', {}).get('unit_tolerance_pct', 15) / 100.0):
            logger.debug("Gate 4 MATCH: embedding=%.2f", score)
            return GateResult.MATCH
        return GateResult.NO_MATCH
    if score < ambiguous_low:
        logger.debug("Gate 4 NO_MATCH: embedding=%.2f", score)
        return GateResult.NO_MATCH
    logger.debug("Gate 4 AMBIGUOUS: embedding=%.2f", score)
    return GateResult.AMBIGUOUS


# ---------------------------------------------------------------------------
# Gate 5 — Price plausibility check
# ---------------------------------------------------------------------------

def gate5_price_plausibility(a: dict, b: dict, cfg: dict, effective_price_a: int = 0, effective_price_b: int = 0) -> GateResult:
    """Gate 5: Flag for review if per-unit price ratio > max."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate5_price_plausibility', True):
        return GateResult.PASS
    if effective_price_a <= 0 or effective_price_b <= 0:
        return GateResult.PASS
    ratio_max = cfg.get('consolidation', {}).get('price_ratio_max', 3.0)
    ratio = max(effective_price_a, effective_price_b) / min(effective_price_a, effective_price_b)
    if ratio > ratio_max:
        logger.warning("Gate 5 REVIEW: price ratio %.1fx", ratio)
        return GateResult.REVIEW
    return GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 6 — AI verifier
# ---------------------------------------------------------------------------

AI_PROMPT_TEMPLATE = """You are comparing grocery products from two Indonesian supermarket brochures.
Decide if these two listings refer to the SAME physical product.

Product A ({store_a}): "{name_a}" — {unit_a} — Rp {price_a:,}
Product B ({store_b}): "{name_b}" — {unit_b} — Rp {price_b:,}

Rules:
- SAME: same brand, same variant, same (or very close) size
- DIFFERENT: different brand, different variant, OR clearly different size (e.g. 85g vs 250g)
- OCR spelling typos do NOT make products different
- Different pack sizes are DIFFERENT even if per-unit price is similar

Reply with exactly one word: YES or NO"""


def _detect_docker() -> bool:
    """Detect if running inside Docker."""
    return os.path.exists('/.dockerenv')


def _ollama_verify(pairs: list[dict], cfg: dict) -> list[str | None]:
    """Send pairs to Ollama for binary yes/no verification."""
    import requests

    base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    if _detect_docker():
        base_url = base_url.replace('localhost', 'host.docker.internal')

    model = cfg.get('consolidation', {}).get('ai_verifier', {}).get('ai_model', 'qwen3:4b')
    batch_size = cfg.get('consolidation', {}).get('ai_verifier', {}).get('ai_batch_size', 20)
    timeout = cfg.get('ocr', {}).get('ollama', {}).get('timeout_seconds', 300)

    results: list[str | None] = []

    for i in range(0, len(pairs), batch_size):
        batch = pairs[i:i + batch_size]
        messages = []
        for p in batch:
            prompt = AI_PROMPT_TEMPLATE.format(
                store_a=p['store_a'], name_a=p['name_a'], unit_a=p.get('unit_a', ''), price_a=p.get('price_a', 0),
                store_b=p['store_b'], name_b=p['name_b'], unit_b=p.get('unit_b', ''), price_b=p.get('price_b', 0),
            )
            messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False, "temperature": 0},
                timeout=timeout,
            )
            resp.raise_for_status()
            reply = resp.json().get('message', {}).get('content', '').strip().upper()
            if 'YES' in reply:
                results.append('YES')
            elif 'NO' in reply:
                results.append('NO')
            else:
                results.append(None)
        except Exception as e:
            logger.error("AI verification failed: %s", e)
            results.extend([None] * len(batch))

    return results


def _gemini_verify(pairs: list[dict], cfg: dict) -> list[str | None]:
    """Send pairs to Gemini for binary yes/no verification."""
    import google.genai as genai

    api_key = cfg.get('ocr', {}).get('gemini', {}).get('api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not set for AI verifier")
        return [None] * len(pairs)

    model_name = cfg.get('consolidation', {}).get('ai_verifier', {}).get('gemini_model', 'gemini-3-flash-preview')
    client = genai.Client(api_key=api_key)
    results: list[str | None] = []

    for p in pairs:
        prompt = AI_PROMPT_TEMPLATE.format(
            store_a=p['store_a'], name_a=p['name_a'], unit_a=p.get('unit_a', ''), price_a=p.get('price_a', 0),
            store_b=p['store_b'], name_b=p['name_b'], unit_b=p.get('unit_b', ''), price_b=p.get('price_b', 0),
        )
        try:
            resp = client.models.generate_content(model=model_name, contents=prompt)
            reply = resp.text.strip().upper()
            if 'YES' in reply:
                results.append('YES')
            elif 'NO' in reply:
                results.append('NO')
            else:
                results.append(None)
        except Exception as e:
            logger.error("Gemini AI verification failed: %s", e)
            results.append(None)

    return results


def gate6_ai_verifier(pairs: list[dict], cfg: dict) -> list[str | None]:
    """Gate 6: Send ambiguous pairs to AI (Ollama or Gemini) for binary yes/no."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate6_ai_verifier', True):
        return [None] * len(pairs)

    provider = cfg.get('consolidation', {}).get('ai_verifier', {}).get('provider', 'ollama')
    if provider == 'gemini':
        return _gemini_verify(pairs, cfg)
    return _ollama_verify(pairs, cfg)


# ---------------------------------------------------------------------------
# Embedding model loader
# ---------------------------------------------------------------------------

def load_embedding_model(model_name: str):
    """Load sentence-transformers model. Downloads on first run (~90MB)."""
    from sentence_transformers import SentenceTransformer
    logger.info("Loading embedding model '%s' (first run downloads ~90MB)...", model_name)
    return SentenceTransformer(model_name)


def compute_embeddings(names: list[str], model) -> list:
    """Compute embeddings for a list of names."""
    return model.encode(names, convert_to_numpy=True)


def compute_similarity_matrix(names_a: list[str], names_b: list[str], model) -> list[list[float]]:
    """Returns similarity[i][j] for names_a[i] vs names_b[j]."""
    from sklearn.metrics.pairwise import cosine_similarity
    emb_a = compute_embeddings(names_a, model)
    emb_b = compute_embeddings(names_b, model)
    return cosine_similarity(emb_a, emb_b).tolist()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def match_products(
    lotte_products: list[dict],
    superindo_products: list[dict],
    cfg: dict,
    embedding_model=None,
) -> tuple[list, list, list, list]:
    """
    Run full matching pipeline.

    Returns: (matched_pairs, lotte_only, superindo_only, review_items)
    """
    matched_pairs: list[dict] = []
    lotte_only: list[dict] = []
    superindo_only: list[dict] = list(superindo_products)
    review_items: list[dict] = []

    matched_b_indices: set[int] = set()

    # Pre-compute embeddings if Gate 4 is enabled
    emb_a = None
    emb_b = None
    if embedding_model is not None and cfg.get('consolidation', {}).get('gates', {}).get('gate4_embedding', True):
        names_a = [p.get('name', '') for p in lotte_products]
        names_b = [p.get('name', '') for p in superindo_products]
        emb_a = compute_embeddings(names_a, embedding_model)
        emb_b = compute_embeddings(names_b, embedding_model)

    for idx_a, prod_a in enumerate(lotte_products):
        best_match: dict | None = None
        best_score = 0.0
        best_method = ''

        for idx_b, prod_b in enumerate(superindo_products):
            if idx_b in matched_b_indices:
                continue

            # Gate 0
            r = gate0_unit_type(prod_a, prod_b, cfg)
            if r == GateResult.SKIP:
                continue
            if r == GateResult.MATCH:
                continue

            # Gate 1
            r = gate1_brand(prod_a, prod_b, cfg)
            if r == GateResult.SKIP:
                continue

            # Gate 2
            r = gate2_token_jaccard(prod_a, prod_b, cfg)
            if r == GateResult.SKIP:
                continue

            # Gate 3
            r = gate3_exact_match(prod_a, prod_b, cfg)
            if r == GateResult.MATCH:
                best_match = prod_b
                best_score = 1.0
                best_method = 'exact'
                matched_b_indices.add(idx_b)
                break

            # Gate 4
            r = gate4_embedding(prod_a, prod_b, cfg, embedding_model, emb_a, emb_b, idx_a, idx_b)
            if r == GateResult.MATCH:
                from sklearn.metrics.pairwise import cosine_similarity
                score = float(cosine_similarity([emb_a[idx_a]], [emb_b[idx_b]])[0, 0]) if emb_a is not None else 0.85
                if score > best_score:
                    best_match = prod_b
                    best_score = score
                    best_method = 'embedding'
                    matched_b_indices.add(idx_b)
                continue
            elif r == GateResult.AMBIGUOUS:
                from sklearn.metrics.pairwise import cosine_similarity
                score = float(cosine_similarity([emb_a[idx_a]], [emb_b[idx_b]])[0, 0]) if emb_a is not None else 0.7
                if score > best_score:
                    best_match = prod_b
                    best_score = score
                    best_method = 'ai'
                continue

            # Gate 5 (price plausibility) — only if we have a candidate
            if best_match is not None:
                ea = prod_a.get('_effective_unit_price', prod_a.get('price', 0))
                eb = best_match.get('_effective_unit_price', best_match.get('price', 0))
                r5 = gate5_price_plausibility(prod_a, best_match, cfg, ea, eb)
                if r5 == GateResult.REVIEW:
                    review_items.append({
                        'product_a': prod_a,
                        'product_b': best_match,
                        'reason': 'price_ratio_too_high',
                    })

        if best_match is not None:
            matched_pairs.append({
                'lotte': prod_a,
                'superindo': best_match,
                'match_confidence': round(best_score, 4),
                'match_method': best_method,
            })
            if idx_b in matched_b_indices:
                pass
        else:
            lotte_only.append(prod_a)

    # Remaining unmatched Superindo products
    superindo_only = [p for idx, p in enumerate(superindo_products) if idx not in matched_b_indices]

    # Gate 6 — AI verifier for ambiguous pairs
    ai_matched = [mp for mp in matched_pairs if mp['match_method'] == 'ai']
    if ai_matched:
        ambiguous_pairs = []
        for mp in ai_matched:
            ambiguous_pairs.append({
                'store_a': 'Lotte',
                'name_a': mp['lotte'].get('name', ''),
                'unit_a': mp['lotte'].get('unit', ''),
                'price_a': mp['lotte'].get('price', 0),
                'store_b': 'Superindo',
                'name_b': mp['superindo'].get('name', ''),
                'unit_b': mp['superindo'].get('unit', ''),
                'price_b': mp['superindo'].get('price', 0),
            })

        logger.info("Gate 6: sending %d ambiguous pairs to AI verifier...", len(ambiguous_pairs))
        ai_results = gate6_ai_verifier(ambiguous_pairs, cfg)
        to_remove = []
        for i, result in enumerate(ai_results):
            if result == 'NO':
                to_remove.append(i)
            elif result is None:
                review_items.append({
                    'product_a': ambiguous_pairs[i],
                    'product_b': ambiguous_pairs[i],
                    'reason': 'ai_verifier_unexpected',
                })
            for i in reversed(to_remove):
                removed = matched_pairs.pop(i)
                lotte_only.append(removed['lotte'])
                # Re-add superindo to singles if not matched elsewhere
                superindo_only.append(removed['superindo'])

    return matched_pairs, lotte_only, superindo_only, review_items
