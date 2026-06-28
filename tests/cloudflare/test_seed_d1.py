"""Unit tests for scripts/seed_d1.py (D1 seed script)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import scripts.seed_d1 as seed_d1


class TestGenerateStoreInserts:
    """Tests for generate_store_inserts()."""

    def test_extracts_unique_stores_from_snapshots(self):
        """Should return one INSERT per unique store name."""
        history = {
            "snapshots": [
                {"store": "Lotte", "product_key": "k1"},
                {"store": "Superindo", "product_key": "k2"},
                {"store": "Lotte", "product_key": "k3"},
            ]
        }
        result = seed_d1.generate_store_inserts(history)
        assert len(result) == 2
        assert "Lotte" in result[0]
        assert "Superindo" in result[1]

    def test_includes_store_colors_from_display_hints(self, tmp_path, monkeypatch):
        """Should include color from display_hints if available."""
        active_promo_path = tmp_path / "active_promo.json"
        active_promo_path.write_text(
            json.dumps({"display_hints": {"store_colors": {"Superindo": "#E8211D"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(seed_d1, "ACTIVE_PROMO_SRC", active_promo_path)

        history = {"snapshots": [{"store": "Superindo"}]}
        result = seed_d1.generate_store_inserts(history)

        assert len(result) == 1
        assert "'Superindo'" in result[0]
        assert "'#E8211D'" in result[0]

    def test_handles_single_store(self):
        """Should work with only one store."""
        history = {"snapshots": [{"store": "Superindo"}]}
        result = seed_d1.generate_store_inserts(history)
        assert len(result) == 1
        assert "Superindo" in result[0]

    def test_handles_empty_history(self):
        """Should return empty list for empty history."""
        history = {"snapshots": []}
        result = seed_d1.generate_store_inserts(history)
        assert result == []

    def test_uses_insert_or_replace_for_idempotency(self):
        """Should use INSERT OR REPLACE, not INSERT."""
        history = {"snapshots": [{"store": "Lotte"}]}
        result = seed_d1.generate_store_inserts(history)
        assert "INSERT OR REPLACE" in result[0]


class TestGenerateProductInserts:
    """Tests for generate_product_inserts()."""

    def test_maps_catalog_fields_to_table_columns(self):
        """Should map canonical_key->key, display_name->name, etc."""
        catalog = {
            "k1": {
                "canonical_key": "k1",
                "display_name": "Test Product",
                "brand": "BrandX",
                "unit": "100g",
                "unit_type": "weight",
                "unit_value_g": 100.0,
            }
        }
        result = seed_d1.generate_product_inserts(catalog)

        assert len(result) == 1
        assert "INSERT OR REPLACE INTO products" in result[0]
        assert "'k1'" in result[0]
        assert "'Test Product'" in result[0]
        assert "'BrandX'" in result[0]
        assert "'100g'" in result[0]
        assert "'weight'" in result[0]
        assert "100.0" in result[0]

    def test_sets_category_to_null(self):
        """Category is not in the catalog — should be NULL."""
        catalog = {
            "k1": {
                "canonical_key": "k1",
                "display_name": "Test Product",
                "brand": "BrandX",
                "unit": "100g",
                "unit_type": "weight",
                "unit_value_g": 100.0,
            }
        }
        result = seed_d1.generate_product_inserts(catalog)
        assert "NULL" in result[0]

    def test_handles_null_brand(self):
        """Should handle null brand values."""
        catalog = {
            "k1": {
                "canonical_key": "k1",
                "display_name": "Test Product",
                "brand": None,
                "unit": "box",
                "unit_type": "count",
                "unit_value_g": None,
            }
        }
        result = seed_d1.generate_product_inserts(catalog)
        assert len(result) == 1
        assert "NULL" in result[0]

    def test_handles_empty_catalog(self):
        """Should return empty list for empty catalog."""
        result = seed_d1.generate_product_inserts({})
        assert result == []


class TestGeneratePriceInserts:
    """Tests for generate_price_inserts()."""

    def _snapshot(self, overrides=None):
        base = {
            "product_key": "k1",
            "store": "Superindo",
            "price": 10000,
            "effective_unit_price": 10000,
            "bundle_size": 2,
            "promo": ["DISKON 20%", "maks. 4 pck"],
            "promo_type": "discount_pct",
            "valid_from": "2026-06-01",
            "valid_until": "2026-06-30",
            "image_path": "database/scrape/img.jpg",
            "scrape_time": "2026-06-13T09:08:07",
            "date": "2026-06-13",
            "match_method": "exact",
            "match_confidence": 1.0,
            "standardized_promo": {"discount_pct": 20, "max_qty": 4},
        }
        if overrides:
            base.update(overrides)
        return base

    def _values_list(self, statement):
        """Extract the VALUES tuple from an INSERT statement."""
        values_part = statement.split("VALUES (")[1].rstrip(");")
        return self._split_values(values_part)

    def _split_values(self, values_str):
        """Split a SQL VALUES list respecting single-quoted strings."""
        values = []
        current = []
        i = 0
        n = len(values_str)
        while i < n:
            ch = values_str[i]
            if ch == "'":
                current.append(ch)
                i += 1
                while i < n:
                    current.append(values_str[i])
                    if values_str[i] == "'":
                        if i + 1 < n and values_str[i + 1] == "'":
                            current.append("'")
                            i += 2
                        else:
                            i += 1
                            break
                    else:
                        i += 1
            elif ch == "," and i + 1 < n and values_str[i + 1] == " ":
                values.append("".join(current).strip())
                current = []
                i += 2
            else:
                current.append(ch)
                i += 1
        if current:
            values.append("".join(current).strip())
        return values

    def test_maps_all_snapshot_fields(self):
        """Should map all snapshot fields to prices table columns."""
        history = {"snapshots": [self._snapshot()]}
        result = seed_d1.generate_price_inserts(history)

        assert len(result) == 1
        assert "INSERT OR REPLACE INTO prices" in result[0]
        assert "'k1'" in result[0]
        assert "'Superindo'" in result[0]
        assert "10000" in result[0]
        assert "2" in result[0]
        assert "'discount_pct'" in result[0]
        assert "'2026-06-01'" in result[0]
        assert "'2026-06-30'" in result[0]
        assert "'database/scrape/img.jpg'" in result[0]
        assert "'2026-06-13T09:08:07'" in result[0]
        assert "'2026-06-13'" in result[0]
        assert "'exact'" in result[0]
        assert "1.0" in result[0]

    def test_json_encodes_promo_array(self):
        """Should JSON-encode the promo array."""
        history = {"snapshots": [self._snapshot()]}
        result = seed_d1.generate_price_inserts(history)
        assert '["DISKON 20%", "maks. 4 pck"]' in result[0]

    def test_handles_null_promo(self):
        """Should use NULL for null promo."""
        history = {"snapshots": [self._snapshot({"promo": None})]}
        result = seed_d1.generate_price_inserts(history)
        values = self._values_list(result[0])
        assert values[5] == "NULL"

    def test_json_encodes_standardized_promo(self):
        """Should JSON-encode the standardized_promo object."""
        history = {"snapshots": [self._snapshot()]}
        result = seed_d1.generate_price_inserts(history)
        assert '{"discount_pct": 20, "max_qty": 4}' in result[0]

    def test_handles_missing_standardized_promo(self):
        """Should use NULL when standardized_promo is absent."""
        snapshot = self._snapshot()
        snapshot.pop("standardized_promo")
        history = {"snapshots": [snapshot]}
        result = seed_d1.generate_price_inserts(history)
        values = self._values_list(result[0])
        assert values[15] == "NULL"

    def test_uses_insert_or_replace(self):
        """Should use INSERT OR REPLACE for idempotency."""
        history = {"snapshots": [self._snapshot()]}
        result = seed_d1.generate_price_inserts(history)
        assert "INSERT OR REPLACE" in result[0]

    def test_escapes_single_quotes_in_values(self):
        """Should escape single quotes in string values."""
        history = {"snapshots": [self._snapshot({"product_key": "Jeruk's"})]}
        result = seed_d1.generate_price_inserts(history)
        assert "'Jeruk''s'" in result[0]


class TestGeneratePromoInserts:
    """Tests for generate_promo_inserts()."""

    def test_maps_promo_catalog_fields(self):
        """Should map key, display, type, discount_pct, product_count."""
        promo_catalog = [
            {
                "key": "diskon-20persen",
                "display": "Diskon 20%",
                "type": "discount_pct",
                "discount_pct": 20,
                "product_count": 64,
                "stores": {"Superindo": 64},
                "example_products": ["Rinso", "Bango"],
            }
        ]
        result = seed_d1.generate_promo_inserts(promo_catalog)

        assert len(result) == 1
        assert "INSERT OR REPLACE INTO promos" in result[0]
        assert "'diskon-20persen'" in result[0]
        assert "'Diskon 20%'" in result[0]
        assert "'discount_pct'" in result[0]
        assert "20" in result[0]
        assert "64" in result[0]

    def test_json_encodes_stores_object(self):
        """Should JSON-encode the stores dict."""
        promo_catalog = [
            {
                "key": "diskon-20persen",
                "display": "Diskon 20%",
                "type": "discount_pct",
                "discount_pct": 20,
                "product_count": 64,
                "stores": {"Superindo": 64},
                "example_products": [],
            }
        ]
        result = seed_d1.generate_promo_inserts(promo_catalog)
        assert '{"Superindo": 64}' in result[0]

    def test_json_encodes_example_products_array(self):
        """Should JSON-encode the example_products array."""
        promo_catalog = [
            {
                "key": "diskon-20persen",
                "display": "Diskon 20%",
                "type": "discount_pct",
                "discount_pct": 20,
                "product_count": 64,
                "stores": {},
                "example_products": ["Rinso", "Bango"],
            }
        ]
        result = seed_d1.generate_promo_inserts(promo_catalog)
        assert '["Rinso", "Bango"]' in result[0]

    def test_handles_empty_promo_catalog(self):
        """Should return empty list for empty catalog."""
        result = seed_d1.generate_promo_inserts([])
        assert result == []


class TestGenerateSeedSql:
    """Tests for generate_seed_sql()."""

    def _price_snapshot(self):
        return {
            "product_key": "k1",
            "store": "Superindo",
            "price": 10000,
            "effective_unit_price": 10000,
            "bundle_size": 1,
            "promo": None,
            "promo_type": "single",
            "valid_from": None,
            "valid_until": None,
            "image_path": None,
            "scrape_time": "2026-06-13T09:08:07",
            "date": "2026-06-13",
            "match_method": None,
            "match_confidence": None,
            "standardized_promo": None,
        }

    def test_combines_all_inserts_in_correct_order(self):
        """Should output stores first, then products, then prices, then promos."""
        history = {"snapshots": [self._price_snapshot()]}
        catalog = {
            "k1": {
                "canonical_key": "k1",
                "display_name": "Test Product",
                "brand": "BrandX",
                "unit": "100g",
                "unit_type": "weight",
                "unit_value_g": 100.0,
            }
        }
        promo_catalog = [
            {
                "key": "promo-1",
                "display": "Promo 1",
                "type": "discount_pct",
                "discount_pct": 10,
                "product_count": 1,
                "stores": {},
                "example_products": [],
            }
        ]
        sql = seed_d1.generate_seed_sql(history, catalog, promo_catalog)
        lines = [line for line in sql.split("\n") if line.strip()]

        assert len(lines) == 4
        assert "INSERT OR REPLACE INTO stores" in lines[0]
        assert "INSERT OR REPLACE INTO products" in lines[1]
        assert "INSERT OR REPLACE INTO prices" in lines[2]
        assert "INSERT OR REPLACE INTO promos" in lines[3]

    def test_each_statement_ends_with_semicolon(self):
        """Every INSERT statement must end with a semicolon."""
        history = {"snapshots": [self._price_snapshot()]}
        catalog = {
            "k1": {
                "canonical_key": "k1",
                "display_name": "Test Product",
                "brand": "BrandX",
                "unit": "100g",
                "unit_type": "weight",
                "unit_value_g": 100.0,
            }
        }
        promo_catalog = []
        sql = seed_d1.generate_seed_sql(history, catalog, promo_catalog)
        lines = [line for line in sql.split("\n") if line.strip()]

        assert len(lines) == 3
        for line in lines:
            assert line.endswith(";")


class TestMainFunction:
    """Tests for main() CLI behavior."""

    def _setup_data_files(self, tmp_path, monkeypatch):
        """Create minimal data files and patch seed_d1 paths."""
        hist_file = tmp_path / "price_history.json"
        hist_file.write_text(
            json.dumps({"snapshots": [], "metadata": {}}),
            encoding="utf-8",
        )
        catalog_file = tmp_path / "product_catalog.json"
        catalog_file.write_text(json.dumps({"catalog": {}}), encoding="utf-8")
        promo_file = tmp_path / "promo_catalog.json"
        promo_file.write_text(json.dumps([]), encoding="utf-8")

        monkeypatch.setattr(seed_d1, "PRICE_HISTORY_SRC", hist_file)
        monkeypatch.setattr(seed_d1, "CATALOG_SRC", catalog_file)
        monkeypatch.setattr(seed_d1, "PROMO_CATALOG_SRC", promo_file)
        monkeypatch.setattr(seed_d1, "ACTIVE_PROMO_SRC", tmp_path / "active_promo.json")

    def test_writes_seed_file(self, tmp_path, monkeypatch):
        """Should create seed.sql file."""
        seed_file = tmp_path / "seed.sql"
        monkeypatch.setattr(seed_d1, "SEED_FILE", seed_file)
        self._setup_data_files(tmp_path, monkeypatch)

        monkeypatch.setattr(sys, "argv", ["seed_d1.py"])
        seed_d1.main()

        assert seed_file.exists()
        assert seed_file.stat().st_size > 0

    def test_prints_row_counts(self, capsys, tmp_path, monkeypatch):
        """Should print row counts for each table."""
        seed_file = tmp_path / "seed.sql"
        monkeypatch.setattr(seed_d1, "SEED_FILE", seed_file)
        self._setup_data_files(tmp_path, monkeypatch)

        monkeypatch.setattr(sys, "argv", ["seed_d1.py"])
        seed_d1.main()

        captured = capsys.readouterr()
        assert "Stores:" in captured.out
        assert "Products:" in captured.out
        assert "Prices:" in captured.out
        assert "Promos:" in captured.out
