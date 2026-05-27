"""Unit tests for _normalize_promo in consolidation.py and ocr_processor.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.matching.consolidation import _normalize_promo as consolidate_normalize
from scripts.ocr.ocr_processor import _normalize_promo as ocr_normalize


class TestConsolidationNormalizePromo:
    """Test read-time normalization in consolidation.py (handles old data)."""

    def test_none_input(self):
        assert consolidate_normalize(None) is None

    def test_empty_string(self):
        assert consolidate_normalize("") is None

    def test_empty_list(self):
        assert consolidate_normalize([]) is None

    def test_list_input(self):
        assert consolidate_normalize(["DISKON 20%", "Beli 2 Gratis 1"]) == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_list_with_none_filtered(self):
        assert consolidate_normalize(["DISKON 20%", None, "Beli 2 Gratis 1"]) == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_list_with_empty_strings_filtered(self):
        assert consolidate_normalize(["DISKON 20%", "", "  "]) == ["DISKON 20%"]

    def test_plain_string(self):
        assert consolidate_normalize("DISKON 20%") == ["DISKON 20%"]

    def test_old_stringified_list_format(self):
        """Handles old corrupted data: "['A', 'B']" """
        assert consolidate_normalize("['DISKON 20%', 'Beli 2 Gratis 1']") == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_old_stringified_list_single_item(self):
        assert consolidate_normalize("['DAPAT 5 pcs']") == ["DAPAT 5 pcs"]

    def test_whitespace_trimmed(self):
        assert consolidate_normalize("  DISKON 20%  ") == ["DISKON 20%"]

    def test_invalid_stringified_list_fallback(self):
        """If ast.literal_eval fails, treat as plain string."""
        assert consolidate_normalize("['invalid") == ["['invalid"]


class TestOcrNormalizePromo:
    """Test entry normalization in ocr_processor.py (handles fresh OCR data)."""

    def test_none_input(self):
        assert ocr_normalize(None) is None

    def test_empty_string(self):
        assert ocr_normalize("") is None

    def test_empty_list(self):
        assert ocr_normalize([]) is None

    def test_single_string(self):
        assert ocr_normalize("DISKON 20%") == ["DISKON 20%"]

    def test_list_input(self):
        assert ocr_normalize(["DISKON 20%", "Beli 2 Gratis 1"]) == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_list_with_none_filtered(self):
        assert ocr_normalize(["DISKON 20%", None, "Beli 2 Gratis 1"]) == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_list_with_empty_strings_filtered(self):
        assert ocr_normalize(["DISKON 20%", "", "  ", "Beli 2 Gratis 1"]) == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_whitespace_trimmed(self):
        assert ocr_normalize(["  DISKON 20%  ", "  Beli 2 Gratis 1  "]) == ["DISKON 20%", "Beli 2 Gratis 1"]

    def test_numeric_input_converted(self):
        assert ocr_normalize([123, 456]) == ["123", "456"]

    def test_single_none_in_list(self):
        assert ocr_normalize([None]) is None
