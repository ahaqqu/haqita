"""
Multi-tier matching pipeline for cross-store product matching.

Each gate is an isolated function. The orchestrator checks config before calling.
"""

import logging
import os
from enum import Enum

from sklearn.metrics.pairwise import cosine_similarity

from scripts.common.http_client import QuotaExhaustedError, retry_call
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


def _verify_one_pair(client, model_name: str, prompt: str, max_retries: int) -> str | None:
    """Call Gemini once per attempt, retrying transient errors.

    Returns 'YES'/'NO' on a parseable reply, None on unparseable reply or
    after exhausting all retries. Raises QuotaExhaustedError on daily quota
    so the caller can skip remaining pairs.
    """
    def _call():
        return client.models.generate_content(model=model_name, contents=prompt)
    try:
        resp = retry_call(_call, max_retries=max_retries, context="ai_verifier")
    except QuotaExhaustedError:
        raise
    except Exception as e:
        logger.error("AI verification gave up after %d attempts: %s", max_retries, e)
        return None
    reply = resp.text.strip().upper()
    if 'YES' in reply:
        return 'YES'
    if 'NO' in reply:
        return 'NO'
    return None


def _gemini_verify(pairs: list[dict], cfg: dict) -> list[str | None]:
    """Send pairs to Gemini for binary yes/no verification."""
    import google.genai as genai

    api_key = cfg.get('ocr', {}).get('gemini', {}).get('api_key') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not set for AI verifier")
        return [None] * len(pairs)

    ai_cfg = cfg.get('consolidation', {}).get('ai_verifier', {})
    model_name = ai_cfg.get('gemini_model', 'gemini-3-flash-preview')
    max_retries = ai_cfg.get('max_retries', 3)
    client = genai.Client(api_key=api_key)
    results: list[str | None] = []

    for p in pairs:
        prompt = AI_PROMPT_TEMPLATE.format(
            store_a=p['store_a'], name_a=p['name_a'], unit_a=p.get('unit_a', ''), price_a=p.get('price_a', 0),
            store_b=p['store_b'], name_b=p['name_b'], unit_b=p.get('unit_b', ''), price_b=p.get('price_b', 0),
        )
        try:
            results.append(_verify_one_pair(client, model_name, prompt, max_retries))
        except QuotaExhaustedError as e:
            logger.error("Stopping AI verifier early: %s", e)
            results.append(None)
            results.extend([None] * (len(pairs) - len(results)))
            break

    return results


def gate6_ai_verifier(pairs: list[dict], cfg: dict) -> list[str | None]:
    """Gate 6: Send ambiguous pairs to Gemini for binary yes/no."""
    if not cfg.get('consolidation', {}).get('gates', {}).get('gate6_ai_verifier', True):
        return [None] * len(pairs)

    if os.getenv("MOCK_AI_VERIFIER") == "1":
        from agentic_engineering.dummy.mocks.mock_ai_verifier import mock_verify
        return mock_verify(pairs)

    return _gemini_verify(pairs, cfg)


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


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def match_products(
    lotte_products: list[dict],
    superindo_products: list[dict],
    cfg: dict,
    embedding_model=None,
) -> tuple[list, list, list, list, list]:
    """
    Run full matching pipeline.

    Returns: (matched_pairs, lotte_only, superindo_only, review_items, gate_rejections)
        gate_rejections: list of {lotte, superindo, gate, reason} for debugging
    """
    matched_pairs: list[dict] = []
    lotte_only: list[dict] = []
    superindo_only: list[dict] = list(superindo_products)
    review_items: list[dict] = []
    gate_rejections: list[dict] = []

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
        last_rejection: dict | None = None

        for idx_b, prod_b in enumerate(superindo_products):
            if idx_b in matched_b_indices:
                continue

            # Gate 0
            r = gate0_unit_type(prod_a, prod_b, cfg)
            if r == GateResult.SKIP:
                last_rejection = {
                    'lotte': prod_a.get('name', ''),
                    'superindo': prod_b.get('name', ''),
                    'gate': 'gate0_unit_type',
                    'reason': f"incompatible units '{prod_a.get('unit', '')}' vs '{prod_b.get('unit', '')}'",
                }
                continue
            if r == GateResult.MATCH:
                continue

            # Gate 1
            r = gate1_brand(prod_a, prod_b, cfg)
            if r == GateResult.SKIP:
                last_rejection = {
                    'lotte': prod_a.get('name', ''),
                    'superindo': prod_b.get('name', ''),
                    'gate': 'gate1_brand',
                    'reason': f"different brands '{prod_a.get('brand', '')}' vs '{prod_b.get('brand', '')}'",
                }
                continue

            # Gate 2
            r = gate2_token_jaccard(prod_a, prod_b, cfg)
            if r == GateResult.SKIP:
                score = token_overlap(prod_a.get('name', ''), prod_b.get('name', ''))
                threshold = cfg.get('consolidation', {}).get('token_jaccard_min', 0.30)
                last_rejection = {
                    'lotte': prod_a.get('name', ''),
                    'superindo': prod_b.get('name', ''),
                    'gate': 'gate2_token_jaccard',
                    'reason': f"token overlap {score:.2f} below threshold {threshold}",
                }
                continue

            # Gate 3
            r = gate3_exact_match(prod_a, prod_b, cfg)
            if r == GateResult.MATCH:
                best_match = prod_b
                best_score = 1.0
                best_method = 'exact'
                matched_b_indices.add(idx_b)
                last_rejection = None
                break

            # Gate 4
            r = gate4_embedding(prod_a, prod_b, cfg, embedding_model, emb_a, emb_b, idx_a, idx_b)
            if r == GateResult.MATCH:
                score = float(cosine_similarity([emb_a[idx_a]], [emb_b[idx_b]])[0, 0]) if emb_a is not None else 0.85
                if score > best_score:
                    best_match = prod_b
                    best_score = score
                    best_method = 'embedding'
                    matched_b_indices.add(idx_b)
                last_rejection = None
                continue
            elif r == GateResult.AMBIGUOUS:
                score = float(cosine_similarity([emb_a[idx_a]], [emb_b[idx_b]])[0, 0]) if emb_a is not None else 0.7
                if score > best_score:
                    best_match = prod_b
                    best_score = score
                    best_method = 'ai'
                last_rejection = None
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
        else:
            lotte_only.append(prod_a)
            if last_rejection:
                gate_rejections.append(last_rejection)

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
                mp = ai_matched[i]
                review_items.append({
                    'product_a': mp['lotte'],
                    'product_b': mp['superindo'],
                    'reason': 'ai_verifier_unexpected',
                })
        for i in reversed(to_remove):
            removed = matched_pairs.pop(i)
            lotte_only.append(removed['lotte'])
            superindo_only.append(removed['superindo'])
            gate_rejections.append({
                'lotte': removed['lotte'].get('name', ''),
                'superindo': removed['superindo'].get('name', ''),
                'gate': 'gate6_ai_verifier',
                'reason': 'ai_verifier_said_no',
            })

    return matched_pairs, lotte_only, superindo_only, review_items, gate_rejections
