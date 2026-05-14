import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import clean_price, clean_unit


class TestCleanPrice:
    def test_rp_with_dots(self):
        assert clean_price("Rp 8.500") == 8500

    def test_rp_without_space(self):
        assert clean_price("Rp8.500") == 8500

    def test_plain_number(self):
        assert clean_price("8500") == 8500

    def test_comma_separator(self):
        assert clean_price("8,500") == 8500

    def test_space_separator(self):
        assert clean_price("8 500") == 8500

    def test_millions_with_dots(self):
        assert clean_price("Rp 150.000") == 150000

    def test_lowercase_rp(self):
        assert clean_price("rp 5.000") == 5000

    def test_invalid_string(self):
        assert clean_price("???") is None

    def test_none_input(self):
        assert clean_price(None) is None

    def test_below_min_price(self):
        assert clean_price("50") is None

    def test_above_max_price(self):
        assert clean_price("2000000") is None

    def test_integer_input(self):
        assert clean_price(15500) == 15500

    def test_rp_with_period_space(self):
        assert clean_price("Rp. 15.500") == 15500

    def test_no_thousands_separator(self):
        assert clean_price("1000") == 1000


class TestCleanUnit:
    def test_clean_5g_ocr_corruption(self):
        assert clean_unit("Sg") == "5g"

    def test_clean_8g_ocr_corruption(self):
        assert clean_unit("Bg") == "8g"

    def test_clean_100_ocr_corruption(self):
        assert clean_unit("IOO") == "100"

    def test_clean_lowercase_l_as_1(self):
        assert clean_unit("l g") == "1 g"

    def test_clean_none(self):
        assert clean_unit(None) is None

    def test_clean_empty(self):
        assert clean_unit("") is None

    def test_clean_unchanged(self):
        assert clean_unit("85 g") == "85 g"
