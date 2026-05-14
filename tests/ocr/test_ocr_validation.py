import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import validate_product


class TestValidateProduct:
    def test_valid_product(self):
        raw = {
            "name": "Indomie Goreng Ayam Geprek",
            "brand": "Indomie",
            "unit": "85 g",
            "price": 15500,
            "promo": "DAPAT 5 pcs",
            "period": "7 - 20 Mei 2026",
        }
        result, reason = validate_product(raw, "test.jpg")
        assert result is not None
        assert reason is None
        assert result["name"] == "Indomie Goreng Ayam Geprek"
        assert result["price"] == 15500

    def test_name_too_short(self):
        raw = {"name": "X", "price": 5000}
        result, reason = validate_product(raw, "test.jpg")
        assert result is None
        assert reason == "name_too_short"

    def test_empty_name(self):
        raw = {"name": "", "price": 5000}
        result, reason = validate_product(raw, "test.jpg")
        assert result is None
        assert "name" in reason

    def test_missing_price(self):
        raw = {"name": "Product A"}
        result, reason = validate_product(raw, "test.jpg")
        assert result is None
        assert "price" in reason

    def test_null_price(self):
        raw = {"name": "Product A", "price": None}
        result, reason = validate_product(raw, "test.jpg")
        assert result is None
        assert "price" in reason

    def test_zero_price(self):
        raw = {"name": "Product A", "price": 0}
        result, reason = validate_product(raw, "test.jpg")
        assert result is None
        assert "price" in reason

    def test_brand_preserved(self):
        raw = {"name": "ABC Kecap", "brand": "ABC", "price": 5000}
        result, reason = validate_product(raw, "test.jpg")
        assert result is not None
        assert result["brand"] == "ABC"

    def test_missing_brand(self):
        raw = {"name": "Gula Pasir", "price": 15000}
        result, reason = validate_product(raw, "test.jpg")
        assert result is not None
        assert result["brand"] is None

    def test_promo_preserved(self):
        raw = {"name": "Item", "promo": "DAPAT 2 pcs", "price": 10000}
        result, reason = validate_product(raw, "test.jpg")
        assert result is not None
        assert result["promo"] == "DAPAT 2 pcs"

    def test_image_source_set(self):
        raw = {"name": "Item", "price": 5000}
        result, reason = validate_product(raw, "promo_abc.jpg")
        assert result is not None
        assert result["image_source"] == "promo_abc.jpg"

    def test_ocr_confidence_default(self):
        raw = {"name": "Item", "price": 5000}
        result, reason = validate_product(raw, "test.jpg")
        assert result is not None
        assert result["ocr_confidence"] == 1.0

    def test_ocr_raw_price(self):
        raw = {"name": "Item", "price": "Rp 5.000"}
        result, reason = validate_product(raw, "test.jpg")
        assert result is not None
        assert result["ocr_raw_price"] == "Rp 5.000"
