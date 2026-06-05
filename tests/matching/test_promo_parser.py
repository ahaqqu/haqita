"""Unit tests for scripts/matching/promo_parser.py"""

import pytest
from scripts.matching.promo_parser import parse_promo, parse_period, PromoResult


# ---------------------------------------------------------------------------
# parse_promo
# ---------------------------------------------------------------------------

class TestParsePromo:
    def test_dapat_bundle(self):
        result = parse_promo("DAPAT 5 pcs", 15500)
        assert result.promo_type == "bundle_buy"
        assert result.unit_count == 5
        assert result.effective_unit_price == 3100

    def test_dapat_buah(self):
        result = parse_promo("dapat 3 buah", 30000)
        assert result.promo_type == "bundle_buy"
        assert result.unit_count == 3

    def test_beli_gratis(self):
        result = parse_promo("Beli 2 Gratis 1", 30000)
        assert result.promo_type == "get_free"
        assert result.unit_count == 3
        assert result.effective_unit_price == 10000

    def test_diskon_pct(self):
        result = parse_promo("Diskon 20%", 100000)
        assert result.promo_type == "discount_pct"
        assert result.effective_unit_price == 80000

    def test_diskon_25(self):
        result = parse_promo("Diskon 25%", 24900)
        assert result.promo_type == "discount_pct"
        assert result.effective_unit_price == 18675

    def test_hemat_fixed(self):
        result = parse_promo("Hemat Rp 5.000", 20000)
        assert result.promo_type == "discount_fixed"
        assert result.effective_unit_price == 15000

    def test_multi_price(self):
        result = parse_promo("3 pcs / Rp15.000", 15000)
        assert result.promo_type == "multi_price"
        assert result.unit_count == 3
        assert result.effective_unit_price == 5000

    def test_no_promo(self):
        result = parse_promo(None, 15000)
        assert result.promo_type == "single"
        assert result.unit_count == 1
        assert result.effective_unit_price == 15000

    def test_empty_promo(self):
        result = parse_promo("", 15000)
        assert result.promo_type == "single"

    def test_unrecognized_promo(self):
        result = parse_promo("Harga Spesial", 15000)
        assert result.promo_type == "single"
        assert result.effective_unit_price == 15000

    def test_display_preserved(self):
        result = parse_promo("Diskon 20%", 100000)
        assert result.display == "Diskon 20%"

    def test_array_single_item(self):
        result = parse_promo(["DAPAT 5 pcs"], 15500)
        assert result.promo_type == "bundle_buy"
        assert result.unit_count == 5
        assert result.effective_unit_price == 3100
        assert result.display == "DAPAT 5 pcs"

    def test_array_multiple_items(self):
        result = parse_promo(["DISKON 20%", "Beli 2 Gratis 1"], 100000)
        # DISKON 20%: 80000, Beli 2 Gratis 1: 33333
        assert result.promo_type == "get_free"
        assert result.effective_unit_price == 33333
        assert result.display == "DISKON 20%, Beli 2 Gratis 1"

    def test_array_empty(self):
        result = parse_promo([], 15000)
        assert result.promo_type == "single"
        assert result.unit_count == 1
        assert result.effective_unit_price == 15000

    def test_array_mixed_match(self):
        result = parse_promo(["DISKON 20%", "Harga Spesial"], 100000)
        assert result.promo_type == "discount_pct"
        assert result.effective_unit_price == 80000
        assert result.display == "DISKON 20%, Harga Spesial"


# ---------------------------------------------------------------------------
# parse_period
# ---------------------------------------------------------------------------

class TestParsePeriod:
    def test_range_both_dates(self):
        start, end = parse_period("7 - 20 Mei 2026")
        assert start == "2026-05-07"
        assert end == "2026-05-20"

    def test_different_month(self):
        start, end = parse_period("14 - 17 Mei 2026")
        assert start == "2026-05-14"
        assert end == "2026-05-17"

    def test_oktober(self):
        start, end = parse_period("1 - 15 Okt 2026")
        assert start == "2026-10-01"
        assert end == "2026-10-15"

    def test_none(self):
        start, end = parse_period(None)
        assert start is None
        assert end is None

    def test_empty(self):
        start, end = parse_period("")
        assert start is None
        assert end is None

    def test_unparseable(self):
        start, end = parse_period("some random text")
        assert start is None
        assert end is None

    def test_august_alias(self):
        start, end = parse_period("1 - 10 Agu 2026")
        assert start == "2026-08-01"
        assert end == "2026-08-10"

    def test_single_end_date(self):
        start, end = parse_period("s/d 20 Mei 2026")
        assert start is None
        assert end == "2026-05-20"

    def test_bare_single_date(self):
        start, end = parse_period("20 Mei 2026")
        assert start is None
        assert end == "2026-05-20"
