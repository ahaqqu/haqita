import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.ocr_processor import validate_product, _parse_ocr_json


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


class TestParseOcrJson:
    def test_plain_json_array(self):
        result = _parse_ocr_json('[{"name": "A", "price": 5000}]')
        assert len(result) == 1
        assert result[0]["name"] == "A"

    def test_markdown_fenced(self):
        result = _parse_ocr_json('```json\n[{"name": "B", "price": 10000}]\n```')
        assert len(result) == 1
        assert result[0]["name"] == "B"

    def test_markdown_fenced_no_lang(self):
        result = _parse_ocr_json('```\n[{"name": "C", "price": 15000}]\n```')
        assert len(result) == 1
        assert result[0]["name"] == "C"

    def test_with_extra_text(self):
        result = _parse_ocr_json('Here are the products:\n[{"name": "D", "price": 20000}]\nDone.')
        assert len(result) == 1
        assert result[0]["name"] == "D"

    def test_invalid_json_raises(self):
        import pytest
        with pytest.raises(json.JSONDecodeError):
            _parse_ocr_json('[invalid json]')

    def test_no_json_array_raises(self):
        import pytest
        with pytest.raises(ValueError, match="No JSON array found"):
            _parse_ocr_json("Just text without any array")

    def test_empty_string_raises(self):
        import pytest
        with pytest.raises(ValueError, match="No JSON array found"):
            _parse_ocr_json("")
