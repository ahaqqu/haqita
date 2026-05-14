import json
import logging

import requests

from .normalizer import (
    normalize_brand, units_type_compatible, units_value_compatible,
    canonical_tokens, token_overlap, normalize_name
)

logger = logging.getLogger(__name__)


def load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {model_name} ...")
    model = SentenceTransformer(model_name)
    logger.info("Embedding model ready.")
    return model


def compute_similarity_matrix(names_a: list[str], names_b: list[str], model) -> list[list[float]]:
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    all_names = names_a + names_b
    embs = model.encode(all_names, convert_to_numpy=True)
    embs_a = embs[:len(names_a)]
    embs_b = embs[len(names_a):]
    matrix = cosine_similarity(embs_a, embs_b)
    return matrix.tolist()


def price_plausibility_ok(price_a: int, unit_a: str | None,
                           price_b: int, unit_b: str | None,
                           max_ratio: float = 3.0) -> bool:
    from .normalizer import parse_unit_to_base
    p_a = parse_unit_to_base(unit_a)
    p_b = parse_unit_to_base(unit_b)
    if not p_a or not p_b or p_a[0] == 0 or p_b[0] == 0:
        return True
    pu_a = price_a / p_a[0]
    pu_b = price_b / p_b[0]
    ratio = max(pu_a, pu_b) / min(pu_a, pu_b)
    return ratio <= max_ratio


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


def verify_with_ai(pairs: list[dict], cfg: dict) -> list[dict | None]:
    results = []
    batch_prompt = "\n\n---\n\n".join([
        AI_PROMPT_TEMPLATE.format(
            store_a=p['product_a']['store'], name_a=p['product_a']['name'],
            unit_a=p['product_a'].get('unit', 'unknown'),
            price_a=p['product_a']['effective_unit_price'],
            store_b=p['product_b']['store'], name_b=p['product_b']['name'],
            unit_b=p['product_b'].get('unit', 'unknown'),
            price_b=p['product_b']['effective_unit_price'],
        )
        for p in pairs
    ])
    batch_prompt += f"\n\nAnswer for each pair above, one per line (YES or NO only):"

    try:
        resp = requests.post("http://localhost:11434/api/generate", json={
            "model": cfg['consolidation']['ai_model'],
            "prompt": batch_prompt,
            "stream": False,
            "options": {"temperature": 0, "seed": 42}
        }, timeout=60)
        resp.raise_for_status()
        lines = resp.json()['response'].strip().splitlines()

        for i, (pair, line) in enumerate(zip(pairs, lines)):
            answer = line.strip().lower()
            if answer in ('yes', 'ya', 'y', 'match', 'sama'):
                results.append({**pair, 'match_method': 'ai', 'match_confidence': 0.75})
            elif answer in ('no', 'tidak', 'n', 'beda'):
                results.append(None)
            else:
                logger.warning(f"Unexpected AI response for pair {i}: {line!r}")
                results.append({'__review': True, **pair, 'reason': f'ai_uncertain: {line}'})
    except Exception as e:
        logger.error(f"AI verification failed: {e}")
        results = [None] * len(pairs)

    return results


def match_products(lotte_products: list[dict], superindo_products: list[dict],
                   cfg: dict, embedding_model=None) -> tuple[list, list, list, list]:
    emb_auto = cfg['consolidation']['embedding_auto_match']
    emb_low = cfg['consolidation']['embedding_ambiguous_low']
    jaccard_min = cfg['consolidation']['token_jaccard_min']
    unit_tol = cfg['consolidation']['unit_tolerance_pct'] / 100

    matched_lotte_idx = set()
    matched_superindo_idx = set()
    matched_pairs = []
    ambiguous_pairs = []
    review_items = []

    for i, a in enumerate(lotte_products):
        for j, b in enumerate(superindo_products):
            if j in matched_superindo_idx:
                continue

            if not units_type_compatible(a.get('unit'), b.get('unit')):
                continue

            ba, bb = normalize_brand(a.get('brand')), normalize_brand(b.get('brand'))
            if ba and bb and ba != bb:
                continue

            overlap = token_overlap(a['name'], b['name'])
            if overlap < jaccard_min:
                continue

            if canonical_tokens(a['name']) == canonical_tokens(b['name']) and \
               units_value_compatible(a.get('unit'), b.get('unit'), unit_tol):
                matched_pairs.append({
                    'product_a': {**a, 'store': 'Lotte'},
                    'product_b': {**b, 'store': 'Superindo'},
                    'match_method': 'exact',
                    'match_confidence': 1.0,
                    '_idx_a': i, '_idx_b': j
                })
                matched_lotte_idx.add(i)
                matched_superindo_idx.add(j)
                break

    remaining_lotte = [(i, p) for i, p in enumerate(lotte_products) if i not in matched_lotte_idx]
    remaining_superindo = [(j, p) for j, p in enumerate(superindo_products) if j not in matched_superindo_idx]

    if remaining_lotte and remaining_superindo and embedding_model:
        names_a = [normalize_name(p['name']) for _, p in remaining_lotte]
        names_b = [normalize_name(p['name']) for _, p in remaining_superindo]
        sim_matrix = compute_similarity_matrix(names_a, names_b, embedding_model)

        for ri, (i, a) in enumerate(remaining_lotte):
            best_rj = max(range(len(remaining_superindo)), key=lambda x: sim_matrix[ri][x])
            best_score = sim_matrix[ri][best_rj]
            rj, b = remaining_superindo[best_rj]

            if rj in matched_superindo_idx:
                continue
            if not units_type_compatible(a.get('unit'), b.get('unit')):
                continue

            pair = {
                'product_a': {**a, 'store': 'Lotte'},
                'product_b': {**b, 'store': 'Superindo'},
                '_idx_a': i, '_idx_b': rj,
                '_score': best_score
            }

            if best_score >= emb_auto and units_value_compatible(a.get('unit'), b.get('unit'), unit_tol):
                matched_pairs.append({
                    **pair, 'match_method': 'embedding', 'match_confidence': round(best_score, 3)
                })
                matched_lotte_idx.add(i)
                matched_superindo_idx.add(rj)
            elif best_score >= emb_low:
                if not price_plausibility_ok(
                    a.get('effective_unit_price', a['price']),
                    a.get('unit'),
                    b.get('effective_unit_price', b['price']),
                    b.get('unit'),
                    cfg['consolidation']['price_ratio_max']
                ):
                    review_items.append({**pair, 'reason': 'price_ratio_too_high'})
                else:
                    ambiguous_pairs.append(pair)

    if ambiguous_pairs:
        ai_results = verify_with_ai(ambiguous_pairs, cfg)
        for pair, result in zip(ambiguous_pairs, ai_results):
            if result is None:
                continue
            if result.get('__review'):
                review_items.append(result)
            else:
                matched_pairs.append(result)
                matched_lotte_idx.add(pair['_idx_a'])
                matched_superindo_idx.add(pair['_idx_b'])

    lotte_only = [p for i, p in enumerate(lotte_products) if i not in matched_lotte_idx]
    superindo_only = [p for j, p in enumerate(superindo_products) if j not in matched_superindo_idx]

    return matched_pairs, lotte_only, superindo_only, review_items
