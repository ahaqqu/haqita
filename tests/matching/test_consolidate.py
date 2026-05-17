"""Integration tests for the full consolidation pipeline."""

import json
import os
import pytest
import tempfile
import shutil
from pathlib import Path

from scripts.consolidate import (
    atomic_write_json,
    append_to_price_history,
    consolidate,
    extract_products,
    generate_consolidated_from_history,
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
# Step 0: Extended price_history schema + generate_consolidated_from_history
# ---------------------------------------------------------------------------

class TestAppendToPriceHistory:
    def test_new_fields_included(self):
        history = {'snapshots': [], 'metadata': {'last_updated': '', 'total_runs': 0, 'schema_version': '1.2'}}
        products = [{
            'product_key': 'test--brand--100g', 'name': 'Test', 'brand': 'Brand',
            'unit': '100 g', 'store': 'Lotte',
            'price': 10000, 'effective_unit_price': 10000,
            'promo': 'DAPAT 3 pcs', 'valid_from': '2026-05-01',
            'valid_until': '2026-05-20', 'bundle_size': 3,
            'promo_type': 'bundle_buy', 'match_method': 'exact',
            'match_confidence': 1.0, 'image_path': 'database/scrape/lotte/img.jpg',
            'scrape_time': '2026-05-17T08:00:00',
        }]
        result = append_to_price_history(history, products, '2026-05-17')
        snap = result['snapshots'][0]
        assert snap['product_key'] == 'test--brand--100g'
        assert snap['valid_from'] == '2026-05-01'
        assert snap['valid_until'] == '2026-05-20'
        assert snap['bundle_size'] == 3
        assert snap['promo_type'] == 'bundle_buy'
        assert snap['match_method'] == 'exact'
        assert snap['match_confidence'] == 1.0
        assert snap['image_path'] == 'database/scrape/lotte/img.jpg'
        assert snap['scrape_time'] == '2026-05-17T08:00:00'

    def test_defaults_for_missing_fields(self):
        history = {'snapshots': [], 'metadata': {'last_updated': '', 'total_runs': 0, 'schema_version': '1.2'}}
        products = [{
            'product_key': 'test--brand--100g', 'name': 'Test', 'brand': 'Brand',
            'unit': '100 g', 'store': 'Lotte',
            'price': 10000, 'effective_unit_price': 10000, 'promo': None,
        }]
        result = append_to_price_history(history, products, '2026-05-17')
        snap = result['snapshots'][0]
        assert snap['bundle_size'] == 1
        assert snap['promo_type'] == 'single'
        assert snap['match_method'] is None
        assert snap['match_confidence'] is None
        assert snap['image_path'] is None
        assert snap['scrape_time'] is None

    def test_dedup_same_product_date_store(self):
        history = {'snapshots': [], 'metadata': {'last_updated': '', 'total_runs': 0, 'schema_version': '1.2'}}
        products = [
            {'product_key': 'test--brand--100g', 'name': 'Test', 'brand': 'Brand',
             'unit': '100 g', 'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000, 'promo': None},
            {'product_key': 'test--brand--100g', 'name': 'Test', 'brand': 'Brand',
             'unit': '100 g', 'store': 'Lotte', 'price': 11000, 'effective_unit_price': 11000, 'promo': None},
        ]
        result = append_to_price_history(history, products, '2026-05-17')
        assert len(result['snapshots']) == 1

    def test_metadata_updated(self):
        history = {'snapshots': [], 'metadata': {'last_updated': '', 'total_runs': 0, 'schema_version': '1.2'}}
        products = [{
            'product_key': 'test--brand--100g', 'name': 'Test', 'brand': 'Brand',
            'unit': '100 g', 'store': 'Lotte',
            'price': 10000, 'effective_unit_price': 10000, 'promo': None,
        }]
        result = append_to_price_history(history, products, '2026-05-17')
        assert result['metadata']['total_runs'] == 1
        assert result['metadata']['last_updated'] != ''


class TestGenerateConsolidatedFromHistory:
    def test_single_store_product(self):
        history = {
            'snapshots': [{
                'product_key': 'test--brand--100g', 'name': 'Test Product',
                'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-17',
                'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000,
                'promo': None, 'valid_from': None, 'valid_until': None,
                'bundle_size': 1, 'promo_type': 'single',
                'match_method': None, 'match_confidence': None,
                'image_path': None,
            }],
            'metadata': {},
        }
        catalog = {}
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert len(result['products']) == 0
        assert len(result['singles']) == 1
        assert result['singles'][0]['key'] == 'test--brand--100g'
        assert result['singles'][0]['store'] == 'Lotte'
        assert result['singles'][0]['price'] == 10000

    def test_matched_product_two_stores(self):
        history = {
            'snapshots': [
                {
                    'product_key': 'test--brand--100g', 'name': 'Test Product',
                    'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-17',
                    'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000,
                    'promo': None, 'valid_from': None, 'valid_until': None,
                    'bundle_size': 1, 'promo_type': 'single',
                    'match_method': 'exact', 'match_confidence': 1.0,
                    'image_path': None,
                },
                {
                    'product_key': 'test--brand--100g', 'name': 'Test Product',
                    'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-17',
                    'store': 'Superindo', 'price': 12000, 'effective_unit_price': 12000,
                    'promo': None, 'valid_from': None, 'valid_until': None,
                    'bundle_size': 1, 'promo_type': 'single',
                    'match_method': 'exact', 'match_confidence': 1.0,
                    'image_path': None,
                },
            ],
            'metadata': {},
        }
        catalog = {}
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert len(result['products']) == 1
        assert len(result['singles']) == 0
        p = result['products'][0]
        assert p['key'] == 'test--brand--100g'
        assert p['price_min'] == 10000
        assert p['price_max'] == 12000
        assert p['cheapest_store'] == 'Lotte'
        assert p['price_gap'] == 2000
        assert p['savings_pct'] == 16.7
        assert len(p['stores']) == 2

    def test_expired_product_filtered(self):
        history = {
            'snapshots': [{
                'product_key': 'test--brand--100g', 'name': 'Test Product',
                'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-10',
                'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000,
                'promo': None, 'valid_from': '2026-05-01', 'valid_until': '2026-05-15',
                'bundle_size': 1, 'promo_type': 'single',
                'match_method': None, 'match_confidence': None,
                'image_path': None,
            }],
            'metadata': {},
        }
        catalog = {}
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert len(result['products']) == 0
        assert len(result['singles']) == 0

    def test_null_valid_until_treated_as_active(self):
        history = {
            'snapshots': [{
                'product_key': 'test--brand--100g', 'name': 'Test Product',
                'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-10',
                'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000,
                'promo': None, 'valid_from': None, 'valid_until': None,
                'bundle_size': 1, 'promo_type': 'single',
                'match_method': None, 'match_confidence': None,
                'image_path': None,
            }],
            'metadata': {},
        }
        catalog = {}
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert len(result['singles']) == 1

    def test_catalog_metadata_enriched(self):
        history = {
            'snapshots': [{
                'product_key': 'test--brand--100g', 'name': 'Test',
                'brand': None, 'unit': None, 'date': '2026-05-17',
                'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000,
                'promo': None, 'valid_from': None, 'valid_until': None,
                'bundle_size': 1, 'promo_type': 'single',
                'match_method': None, 'match_confidence': None,
                'image_path': None,
            }],
            'metadata': {},
        }
        catalog = {
            'test--brand--100g': {
                'brand': 'EnrichedBrand', 'unit': '200 g',
                'unit_type': 'weight', 'unit_value_g': 200.0,
            }
        }
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert result['singles'][0]['brand'] == 'EnrichedBrand'
        assert result['singles'][0]['unit'] == '200 g'
        assert result['singles'][0]['unit_type'] == 'weight'

    def test_display_hints_present(self):
        history = {'snapshots': [], 'metadata': {}}
        catalog = {}
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert 'display_hints' in result
        assert result['display_hints']['currency'] == 'IDR'
        assert result['display_hints']['stores'] == ['Lotte', 'Superindo']

    def test_stats_computed(self):
        history = {
            'snapshots': [
                {
                    'product_key': 'a--brand--100g', 'name': 'A',
                    'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-17',
                    'store': 'Lotte', 'price': 10000, 'effective_unit_price': 10000,
                    'promo': None, 'valid_from': None, 'valid_until': None,
                    'bundle_size': 1, 'promo_type': 'single',
                    'match_method': None, 'match_confidence': None, 'image_path': None,
                },
                {
                    'product_key': 'b--brand--100g', 'name': 'B',
                    'brand': 'Brand', 'unit': '100 g', 'date': '2026-05-17',
                    'store': 'Lotte', 'price': 5000, 'effective_unit_price': 5000,
                    'promo': None, 'valid_from': None, 'valid_until': None,
                    'bundle_size': 1, 'promo_type': 'single',
                    'match_method': None, 'match_confidence': None, 'image_path': None,
                },
            ],
            'metadata': {},
        }
        catalog = {}
        result = generate_consolidated_from_history(history, catalog, '2026-05-17')
        assert result['stats']['total_products_lotte'] == 2
        assert result['stats']['lotte_only'] == 2
        assert result['stats']['matched_across_stores'] == 0


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
