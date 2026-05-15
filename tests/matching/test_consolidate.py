"""Integration tests for the full consolidation pipeline."""

import json
import os
import pytest
import tempfile
import shutil
from pathlib import Path

from scripts.consolidate import (
    atomic_write_json,
    consolidate,
    extract_products,
    load_config,
    load_price_history,
    make_product_key,
    update_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_DATA_DIR = PROJECT_ROOT / 'data' / 'test'


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'test.json')
            atomic_write_json({'key': 'value'}, path)
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            assert data == {'key': 'value'}

    def test_corrupt_file_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'test.json')
            with open(path, 'w') as f:
                f.write('{invalid json')
            atomic_write_json({'fixed': True}, path)
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            assert data == {'fixed': True}


# ---------------------------------------------------------------------------
# Product key
# ---------------------------------------------------------------------------

class TestMakeProductKey:
    def test_basic(self):
        key = make_product_key("Indomie Goreng", "Indomie", "85 g")
        assert key == "indomie-goreng--indomie--85-g"

    def test_no_brand(self):
        key = make_product_key("Daging Sapi", None, "100 g")
        assert key == "daging-sapi----100-g"

    def test_no_unit(self):
        key = make_product_key("Indomie Goreng", "Indomie", None)
        assert key == "indomie-goreng--indomie--"

    def test_special_chars(self):
        key = make_product_key("Hello, World!", "Brand", "1 kg")
        assert "," not in key
        assert "!" not in key


# ---------------------------------------------------------------------------
# extract_products
# ---------------------------------------------------------------------------

class TestExtractProducts:
    def test_wrapper_schema(self):
        data = {'products': [{'name': 'A'}], 'store': 'Lotte'}
        assert extract_products(data) == [{'name': 'A'}]

    def test_raw_schema(self):
        data = [{'name': 'A'}]
        assert extract_products(data) == []  # list has no 'products' key

    def test_empty_products(self):
        data = {'products': []}
        assert extract_products(data) == []


# ---------------------------------------------------------------------------
# Catalog update
# ---------------------------------------------------------------------------

class TestUpdateCatalog:
    def test_new_entry(self):
        catalog = {}
        products = [{
            'key': 'test--brand--100g', 'name': 'Test', 'brand': 'brand',
            'unit': '100 g', 'unit_type': 'weight', 'unit_value_g': 100.0,
            'store': 'Lotte',
        }]
        result = update_catalog(catalog, products, '2026-05-14')
        assert 'test--brand--100g' in result
        assert result['test--brand--100g']['appearance_count'] == 1

    def test_existing_entry_updated(self):
        catalog = {
            'test--brand--100g': {
                'canonical_key': 'test--brand--100g',
                'display_name': 'Test', 'brand': 'brand', 'unit': '100 g',
                'unit_type': 'weight', 'unit_value_g': 100.0,
                'first_seen': '2026-05-13', 'last_seen': '2026-05-13',
                'appearance_count': 1, 'stores_found': ['Lotte'],
                'name_variants': [{'name': 'Test', 'count': 1, 'store': 'Lotte'}],
                'confidence': 0.3, 'manually_verified': False,
            }
        }
        products = [{
            'key': 'test--brand--100g', 'name': 'Test', 'brand': 'brand',
            'unit': '100 g', 'unit_type': 'weight', 'unit_value_g': 100.0,
            'store': 'Lotte',
        }]
        result = update_catalog(catalog, products, '2026-05-14')
        assert result['test--brand--100g']['appearance_count'] == 2
        assert result['test--brand--100g']['last_seen'] == '2026-05-14'

    def test_new_store_added(self):
        catalog = {
            'test--brand--100g': {
                'canonical_key': 'test--brand--100g',
                'display_name': 'Test', 'brand': 'brand', 'unit': '100 g',
                'unit_type': 'weight', 'unit_value_g': 100.0,
                'first_seen': '2026-05-13', 'last_seen': '2026-05-13',
                'appearance_count': 1, 'stores_found': ['Lotte'],
                'name_variants': [{'name': 'Test', 'count': 1, 'store': 'Lotte'}],
                'confidence': 0.3, 'manually_verified': False,
            }
        }
        products = [{
            'key': 'test--brand--100g', 'name': 'Test', 'brand': 'brand',
            'unit': '100 g', 'unit_type': 'weight', 'unit_value_g': 100.0,
            'store': 'Superindo',
        }]
        result = update_catalog(catalog, products, '2026-05-14')
        assert 'Superindo' in result['test--brand--100g']['stores_found']


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

class TestPriceHistory:
    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'price_history.json'
            history = load_price_history(path)
            assert 'snapshots' in history
            assert history['snapshots'] == []

    def test_load_existing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'price_history.json'
            path.write_text(json.dumps({'snapshots': [{'a': 1}], 'metadata': {}}))
            history = load_price_history(path)
            assert len(history['snapshots']) == 1


# ---------------------------------------------------------------------------
# Empty store handling
# ---------------------------------------------------------------------------

class TestEmptyStore:
    def test_zero_lotte_products(self, capsys):
        """Consolidation should continue with singles only if one store is empty."""
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td) / 'output/consolidation'
            database_dir = Path(td) / 'database'
            ocr_dir = Path(td) / 'output/ocr'
            ocr_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)

            # Only Superindo file
            superindo_file = ocr_dir / 'superindo_promos.json'
            superindo_file.write_text(json.dumps({
                'store': 'Superindo',
                'scraped_at': '2026-05-14T08:15:00',
                'products': [
                    {
                        'name': 'Test Product',
                        'brand': 'Test',
                        'unit': '100 g',
                        'price': 10000,
                        'promo': None,
                        'period': '14 - 20 Mei 2026',
                    }
                ],
            }))

            cfg = load_config()
            # Disable embedding to avoid model download in tests
            cfg['consolidation']['gates']['gate4_embedding'] = False
            cfg['consolidation']['gates']['gate6_ai_verifier'] = False

            consolidate(cfg, None, ocr_dir, output_dir, database_dir)

            latest = output_dir / 'consolidated_latest.json'
            assert latest.exists()
            with open(latest, encoding='utf-8') as f:
                data = json.load(f)
            assert data['stats']['total_products_lotte'] == 0
            assert data['stats']['total_products_superindo'] == 1


# ---------------------------------------------------------------------------
# Full end-to-end pipeline (uses real test data)
# ---------------------------------------------------------------------------

class TestFullPipeline:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ocr_dir = Path(self.tmpdir) / 'output/ocr'
        self.output_dir = Path(self.tmpdir) / 'output/consolidation'
        self.database_dir = Path(self.tmpdir) / 'database'
        self.ocr_dir.mkdir(parents=True)

        # Copy real test data
        lotte_src = TEST_DATA_DIR / 'lotte' / 'ocr-result' / 'gemini' / 'ht1.json'
        superindo_src = TEST_DATA_DIR / 'superindo' / 'ocr-result' / 'gemini' / 'sample_katalog_1.json'

        if lotte_src.exists():
            shutil.copy(lotte_src, self.ocr_dir / 'lotte_promos.json')
        if superindo_src.exists():
            shutil.copy(superindo_src, self.ocr_dir / 'superindo_promos.json')

        yield

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_end_to_end(self, capsys):
        """Full pipeline with real OCR data — no embedding model."""
        cfg = load_config()
        cfg['consolidation']['gates']['gate4_embedding'] = False
        cfg['consolidation']['gates']['gate6_ai_verifier'] = False

        consolidate(cfg, self.ocr_dir, self.ocr_dir, self.output_dir, self.database_dir)

        latest = self.output_dir / 'consolidated_latest.json'
        assert latest.exists()

        with open(latest, encoding='utf-8') as f:
            data = json.load(f)

        assert 'products' in data
        assert 'singles' in data
        assert 'stats' in data
        assert data['stats']['total_products_lotte'] > 0
        assert data['stats']['total_products_superindo'] > 0

        # Check that database files were created
        assert (self.database_dir / 'product_catalog.json').exists()
        assert (self.database_dir / 'price_history.json').exists()
        assert (self.database_dir / 'review_queue.json').exists()

        # Check consolidated products have required fields
        for p in data['products']:
            assert 'key' in p
            assert 'stores' in p
            assert 'match_method' in p
            assert 'match_confidence' in p
            for s in p['stores']:
                assert 'store' in s
                assert 'price' in s
                assert 'effective_unit_price' in s

        # Check singles have required fields
        for s in data['singles']:
            assert 'key' in s
            assert 'name' in s
            assert 'store' in s
            assert 'price' in s
