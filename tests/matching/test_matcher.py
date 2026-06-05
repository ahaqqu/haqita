"""Unit tests for scripts/matching/matcher.py gates (no embedding model download)."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.matching.matcher import (
    GateResult,
    gate0_unit_type,
    gate1_brand,
    gate2_token_jaccard,
    gate3_exact_match,
    gate4_embedding,
    gate5_price_plausibility,
)


def _cfg(**overrides):
    """Build a minimal config dict with all gates enabled."""
    cfg = {
        'consolidation': {
            'gates': {
                'gate0_unit_type': True,
                'gate1_brand': True,
                'gate2_token_jaccard': True,
                'gate3_exact_match': True,
                'gate4_embedding': True,
                'gate5_price_plausibility': True,
                'gate6_ai_verifier': True,
            },
            'token_jaccard_min': 0.30,
            'unit_tolerance_pct': 15,
            'price_ratio_max': 3.0,
        }
    }
    for key, val in overrides.items():
        if key.startswith('consolidation.'):
            parts = key.split('.')
            d = cfg
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = val
        else:
            cfg['consolidation'][key] = val
    return cfg


# ---------------------------------------------------------------------------
# Gate 0 — Unit type pre-filter
# ---------------------------------------------------------------------------

class TestGate0UnitType:
    def test_compatible_units(self):
        a = {'unit': '100 g'}
        b = {'unit': '500 g'}
        assert gate0_unit_type(a, b, _cfg()) == GateResult.PASS

    def test_incompatible_units(self):
        a = {'unit': '100 g'}
        b = {'unit': '500 ml'}
        assert gate0_unit_type(a, b, _cfg()) == GateResult.SKIP

    def test_unknown_unit_passes(self):
        a = {'unit': '100 g'}
        b = {'unit': 'unknown_unit'}
        assert gate0_unit_type(a, b, _cfg()) == GateResult.PASS

    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate0_unit_type'] = False
        a = {'unit': '100 g'}
        b = {'unit': '500 ml'}
        assert gate0_unit_type(a, b, cfg) == GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 1 — Brand pre-filter
# ---------------------------------------------------------------------------

class TestGate1Brand:
    def test_same_brand(self):
        a = {'brand': 'Indomie'}
        b = {'brand': 'Indomie'}
        assert gate1_brand(a, b, _cfg()) == GateResult.PASS

    def test_different_brands(self):
        a = {'brand': 'Indomie'}
        b = {'brand': 'Supermi'}
        assert gate1_brand(a, b, _cfg()) == GateResult.SKIP

    def test_alias_resolved(self):
        a = {'brand': 'lndomie'}
        b = {'brand': 'Indomie'}
        assert gate1_brand(a, b, _cfg()) == GateResult.PASS

    def test_no_brand_passes(self):
        a = {'brand': None}
        b = {'brand': 'Indomie'}
        assert gate1_brand(a, b, _cfg()) == GateResult.PASS

    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate1_brand'] = False
        a = {'brand': 'Indomie'}
        b = {'brand': 'Supermi'}
        assert gate1_brand(a, b, cfg) == GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 2 — Token Jaccard pre-filter
# ---------------------------------------------------------------------------

class TestGate2TokenJaccard:
    def test_high_overlap(self):
        a = {'name': 'Indomie Goreng Ayam Geprek'}
        b = {'name': 'Indomie Goreng'}
        assert gate2_token_jaccard(a, b, _cfg()) == GateResult.PASS

    def test_low_overlap(self):
        a = {'name': 'Indomie Goreng'}
        b = {'name': 'Ultra Milk Chocolate'}
        assert gate2_token_jaccard(a, b, _cfg()) == GateResult.SKIP

    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate2_token_jaccard'] = False
        a = {'name': 'Indomie Goreng'}
        b = {'name': 'Ultra Milk Chocolate'}
        assert gate2_token_jaccard(a, b, cfg) == GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 3 — Exact token-set match
# ---------------------------------------------------------------------------

class TestGate3ExactMatch:
    def test_exact_same(self):
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '85 g'}
        assert gate3_exact_match(a, b, _cfg()) == GateResult.MATCH

    def test_word_order_swap(self):
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Goreng Indomie', 'unit': '85 g'}
        assert gate3_exact_match(a, b, _cfg()) == GateResult.MATCH

    def test_different_names(self):
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Kuah', 'unit': '85 g'}
        assert gate3_exact_match(a, b, _cfg()) == GateResult.PASS

    def test_incompatible_units(self):
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '100 ml'}
        assert gate3_exact_match(a, b, _cfg()) == GateResult.PASS

    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate3_exact_match'] = False
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '85 g'}
        assert gate3_exact_match(a, b, cfg) == GateResult.PASS


# ---------------------------------------------------------------------------
# Gate 5 — Price plausibility
# ---------------------------------------------------------------------------

class TestGate5PricePlausibility:
    def test_similar_prices(self):
        a = {'name': 'A'}
        b = {'name': 'B'}
        assert gate5_price_plausibility(a, b, _cfg(), 10000, 12000) == GateResult.PASS

    def test_5x_ratio(self):
        a = {'name': 'A'}
        b = {'name': 'B'}
        assert gate5_price_plausibility(a, b, _cfg(), 10000, 50000) == GateResult.REVIEW

    def test_zero_price_passes(self):
        a = {'name': 'A'}
        b = {'name': 'B'}
        assert gate5_price_plausibility(a, b, _cfg(), 0, 50000) == GateResult.PASS

    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate5_price_plausibility'] = False
        a = {'name': 'A'}
        b = {'name': 'B'}
        assert gate5_price_plausibility(a, b, cfg, 10000, 50000) == GateResult.PASS


# ---------------------------------------------------------------------------
# AI verifier (mocked)
# ---------------------------------------------------------------------------

from scripts.matching.matcher import gate6_ai_verifier


class TestGate6AIVerifier:
    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate6_ai_verifier'] = False
        pairs = [{'store_a': 'A', 'name_a': 'X', 'store_b': 'B', 'name_b': 'Y'}]
        results = gate6_ai_verifier(pairs, cfg)
        assert results == [None]

    @patch('scripts.matching.matcher._gemini_verify')
    def test_gemini_yes(self, mock_verify):
        mock_verify.return_value = ['YES']
        cfg = _cfg()
        pairs = [{'store_a': 'Lotte', 'name_a': 'X', 'store_b': 'Superindo', 'name_b': 'X'}]
        results = gate6_ai_verifier(pairs, cfg)
        assert results == ['YES']

    @patch('scripts.matching.matcher._gemini_verify')
    def test_gemini_no(self, mock_verify):
        mock_verify.return_value = ['NO']
        cfg = _cfg()
        pairs = [{'store_a': 'Lotte', 'name_a': 'X', 'store_b': 'Superindo', 'name_b': 'Y'}]
        results = gate6_ai_verifier(pairs, cfg)
        assert results == ['NO']

    @patch('scripts.matching.matcher._gemini_verify')
    def test_gemini_garbage(self, mock_verify):
        mock_verify.return_value = ['MAYBE']
        cfg = _cfg()
        pairs = [{'store_a': 'Lotte', 'name_a': 'X', 'store_b': 'Superindo', 'name_b': 'Y'}]
        results = gate6_ai_verifier(pairs, cfg)
        assert results == ['MAYBE']


# ---------------------------------------------------------------------------
# Gate 4 — Embedding (mocked model)
# ---------------------------------------------------------------------------

class TestGate4Embedding:
    def test_gate_disabled(self):
        cfg = _cfg()
        cfg['consolidation']['gates']['gate4_embedding'] = False
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '85 g'}
        assert gate4_embedding(a, b, cfg) == GateResult.PASS

    def test_no_model_returns_pass(self):
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '85 g'}
        assert gate4_embedding(a, b, _cfg()) == GateResult.PASS

    def test_no_model_no_embeddings(self):
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '85 g'}
        assert gate4_embedding(a, b, _cfg()) == GateResult.PASS

    def test_high_similarity_matches(self):
        """Test with mocked model returning high similarity."""
        import numpy as np
        mock_model = object()
        mock_emb_a = np.array([[0.1, 0.2, 0.3]])
        mock_emb_b = np.array([[0.1, 0.2, 0.3]])
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Indomie Goreng', 'unit': '85 g'}
        result = gate4_embedding(a, b, _cfg(), model=mock_model,
                                 embeddings_a=mock_emb_a, embeddings_b=mock_emb_b,
                                 idx_a=0, idx_b=0)
        assert result == GateResult.MATCH

    def test_low_similarity_no_match(self):
        import numpy as np
        mock_model = object()
        mock_emb_a = np.array([[1.0, 0.0, 0.0]])
        mock_emb_b = np.array([[0.0, 1.0, 0.0]])
        a = {'name': 'Indomie Goreng', 'unit': '85 g'}
        b = {'name': 'Ultra Milk', 'unit': '1 L'}
        result = gate4_embedding(a, b, _cfg(), model=mock_model,
                                 embeddings_a=mock_emb_a, embeddings_b=mock_emb_b,
                                 idx_a=0, idx_b=0)
        assert result == GateResult.NO_MATCH


# ---------------------------------------------------------------------------
# _gemini_verify
# ---------------------------------------------------------------------------

from scripts.matching.matcher import _gemini_verify


class TestGeminiVerify:
    def test_empty_pairs(self):
        cfg = _cfg()
        assert _gemini_verify([], cfg) == []

    @patch('google.genai')
    def test_no_api_key(self, mock_genai):
        cfg = _cfg()
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = ''
        pairs = [{'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'B'}]
        results = _gemini_verify(pairs, cfg)
        assert results == [None]

    @patch('google.genai')
    def test_yes_response(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.text = "YES"
        mock_client.models.generate_content.return_value = mock_resp

        cfg = _cfg()
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = 'test-key'
        pairs = [{'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'A'}]
        results = _gemini_verify(pairs, cfg)
        assert results == ['YES']

    @patch('google.genai')
    @patch('scripts.common.http_client.time.sleep')
    def test_503_retries_then_succeeds(self, mock_sleep, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.text = "YES"
        mock_client.models.generate_content.side_effect = [
            Exception("503 UNAVAILABLE. high demand"),
            Exception("503 UNAVAILABLE. high demand"),
            mock_resp,
        ]

        cfg = _cfg()
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = 'test-key'
        pairs = [{'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'A'}]
        results = _gemini_verify(pairs, cfg)
        assert results == ['YES']
        assert mock_client.models.generate_content.call_count == 3

    @patch('google.genai')
    @patch('scripts.common.http_client.time.sleep')
    def test_503_exhausts_retries_returns_none(self, mock_sleep, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE. high demand")

        cfg = _cfg()
        cfg.setdefault('consolidation', {}).setdefault('ai_verifier', {})['max_retries'] = 2
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = 'test-key'
        pairs = [{'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'A'}]
        results = _gemini_verify(pairs, cfg)
        assert results == [None]
        assert mock_client.models.generate_content.call_count == 2

    @patch('google.genai')
    @patch('scripts.common.http_client.time.sleep')
    def test_per_minute_rate_limit_retries(self, mock_sleep, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.text = "YES"
        mock_client.models.generate_content.side_effect = [
            Exception("429 RESOURCE_EXHAUSTED: Please retry in 30s"),
            mock_resp,
        ]

        cfg = _cfg()
        cfg.setdefault('consolidation', {}).setdefault('ai_verifier', {})['max_retries'] = 2
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = 'test-key'
        pairs = [{'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'A'}]
        results = _gemini_verify(pairs, cfg)
        assert results == ['YES']
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 45

    @patch('google.genai')
    @patch('scripts.common.http_client.time.sleep')
    def test_daily_quota_does_not_retry(self, mock_sleep, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric GenerateRequests per day"
        )

        cfg = _cfg()
        cfg.setdefault('consolidation', {}).setdefault('ai_verifier', {})['max_retries'] = 3
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = 'test-key'
        pairs = [
            {'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'A'},
            {'store_a': 'Lotte', 'name_a': 'B', 'store_b': 'Superindo', 'name_b': 'B'},
        ]
        results = _gemini_verify(pairs, cfg)
        assert results == [None, None]
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

    @patch('google.genai')
    @patch('scripts.common.http_client.time.sleep')
    def test_per_pair_retries_are_independent(self, mock_sleep, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        yes_resp = MagicMock()
        yes_resp.text = "YES"
        no_resp = MagicMock()
        no_resp.text = "NO"
        third_resp = MagicMock()
        third_resp.text = "YES"
        mock_client.models.generate_content.side_effect = [
            Exception("503 UNAVAILABLE"),
            yes_resp,
            no_resp,
            third_resp,
        ]

        cfg = _cfg()
        cfg.setdefault('ocr', {}).setdefault('gemini', {})['api_key'] = 'test-key'
        pairs = [
            {'store_a': 'Lotte', 'name_a': 'A', 'store_b': 'Superindo', 'name_b': 'A'},
            {'store_a': 'Lotte', 'name_a': 'B', 'store_b': 'Superindo', 'name_b': 'B'},
            {'store_a': 'Lotte', 'name_a': 'C', 'store_b': 'Superindo', 'name_b': 'C'},
        ]
        results = _gemini_verify(pairs, cfg)
        assert results == ['YES', 'NO', 'YES']
        assert mock_client.models.generate_content.call_count == 4
