"""Unit tests for scripts/matching/normalizer.py"""

import pytest
from scripts.matching.normalizer import (
    BRAND_ALIASES,
    canonical_tokens,
    normalize_brand,
    normalize_name,
    parse_unit_to_base,
    token_overlap,
    unit_type,
    units_type_compatible,
    units_value_compatible,
)


# ---------------------------------------------------------------------------
# normalize_brand
# ---------------------------------------------------------------------------

class TestNormalizeBrand:
    def test_lowercase(self):
        assert normalize_brand("INDOMIE") == "indomie"

    def test_strips_whitespace(self):
        assert normalize_brand("  Sosro  ") == "sosro"

    def test_known_alias(self):
        assert normalize_brand("lndomie") == "indomie"
        assert normalize_brand("S0sro") == "sosro"
        assert normalize_brand("Ult rajaya") == "ultrajaya"

    def test_none_returns_empty(self):
        assert normalize_brand(None) == ""

    def test_empty_returns_empty(self):
        assert normalize_brand("") == ""

    def test_unknown_brand_passthrough(self):
        assert normalize_brand("Golden Farm") == "golden farm"


# ---------------------------------------------------------------------------
# unit_type
# ---------------------------------------------------------------------------

class TestUnitType:
    def test_weight_units(self):
        assert unit_type("100 g") == "weight"
        assert unit_type("1 kg") == "weight"

    def test_volume_units(self):
        assert unit_type("500 ml") == "volume"
        assert unit_type("1.5 L") == "volume"

    def test_count_units(self):
        assert unit_type("6 pcs") == "count"
        assert unit_type("1 pack") == "count"
        assert unit_type("1 tub") == "count"

    def test_none_returns_none(self):
        assert unit_type(None) is None

    def test_unknown_returns_none(self):
        assert unit_type("set") == "count"  # 'set' is in UNIT_TYPE_MAP

    def test_suffix_match(self):
        assert unit_type("1100's") == "count"  # matches 's'


# ---------------------------------------------------------------------------
# units_type_compatible
# ---------------------------------------------------------------------------

class TestUnitsTypeCompatible:
    def test_same_type(self):
        assert units_type_compatible("100 g", "500 g") is True

    def test_different_types(self):
        assert units_type_compatible("100 g", "500 ml") is False

    def test_unknown_allows(self):
        assert units_type_compatible("100 g", "unknown") is True
        assert units_type_compatible(None, "500 ml") is True

    def test_both_none(self):
        assert units_type_compatible(None, None) is True


# ---------------------------------------------------------------------------
# parse_unit_to_base
# ---------------------------------------------------------------------------

class TestParseUnitToBase:
    def test_simple_grams(self):
        result = parse_unit_to_base("85 g")
        assert result == (85.0, "weight")

    def test_kg_to_g(self):
        result = parse_unit_to_base("1 kg")
        assert result == (1000.0, "weight")

    def test_liters_to_ml(self):
        result = parse_unit_to_base("1.5 L")
        assert result == (1500.0, "volume")

    def test_multiplier(self):
        result = parse_unit_to_base("2 x 800 ml")
        assert result == (1600.0, "volume")

    def test_count(self):
        result = parse_unit_to_base("3 pcs")
        assert result == (3.0, "count")

    def test_none_returns_none(self):
        assert parse_unit_to_base(None) is None

    def test_unparseable_returns_none(self):
        assert parse_unit_to_base("set") is None


# ---------------------------------------------------------------------------
# units_value_compatible
# ---------------------------------------------------------------------------

class TestUnitsValueCompatible:
    def test_same_value(self):
        assert units_value_compatible("100 g", "100 g") is True

    def test_within_tolerance(self):
        assert units_value_compatible("100 g", "110 g") is True

    def test_outside_tolerance(self):
        assert units_value_compatible("85 g", "250 g") is False

    def test_different_types(self):
        assert units_value_compatible("100 g", "100 ml") is False

    def test_unknown_allows(self):
        assert units_value_compatible("100 g", "unknown") is True


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------

class TestNormalizeName:
    def test_lowercase(self):
        assert normalize_name("Indomie Goreng") == "indomie goreng"

    def test_strips_units(self):
        result = normalize_name("Indomie Goreng 85 g")
        assert "85" not in result

    def test_collapses_whitespace(self):
        assert normalize_name("Hello   World") == "hello world"

    def test_caching(self):
        r1 = normalize_name("Test Product")
        r2 = normalize_name("Test Product")
        assert r1 is r2  # Same cached object


# ---------------------------------------------------------------------------
# canonical_tokens
# ---------------------------------------------------------------------------

class TestCanonicalTokens:
    def test_order_independent(self):
        a = canonical_tokens("Indomie Goreng")
        b = canonical_tokens("Goreng Indomie")
        assert a == b

    def test_empty_string(self):
        assert canonical_tokens("") == frozenset()

    def test_special_chars_removed(self):
        tokens = canonical_tokens("Hello, World!")
        assert "hello" in tokens
        assert "world" in tokens


# ---------------------------------------------------------------------------
# token_overlap (Jaccard)
# ---------------------------------------------------------------------------

class TestTokenOverlap:
    def test_identical(self):
        assert token_overlap("Indomie Goreng", "Indomie Goreng") == 1.0

    def test_no_overlap(self):
        assert token_overlap("Indomie Goreng", "Ultra Milk") == 0.0

    def test_partial_overlap(self):
        score = token_overlap("Indomie Goreng", "Indomie Kuah")
        assert 0.0 < score < 1.0

    def test_word_order_swap(self):
        assert token_overlap("Indomie Goreng", "Goreng Indomie") == 1.0

    def test_both_empty(self):
        assert token_overlap("", "") == 1.0

    def test_one_empty(self):
        assert token_overlap("Indomie", "") == 0.0
