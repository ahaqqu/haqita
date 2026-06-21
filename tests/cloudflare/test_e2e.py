"""
End-to-end integration test for the Cloudflare migration.

Tests the full flow: pipeline output → sync script → API → data verification.

Prerequisites:
    - Local API running (wrangler pages dev --local)
    - Local D1 seeded (python scripts/seed_d1.py --apply)
    - SCRAPER_SECRET set in environment

Usage:
    python -m pytest tests/cloudflare/test_e2e.py -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
API_URL = os.getenv("E2E_API_URL", "http://localhost:8787/api/v1")
SCRAPER_SECRET = os.getenv("SCRAPER_SECRET", "dev-secret-for-local-testing")


@pytest.fixture(scope="module")
def api_available():
    """Verify the API is running before tests."""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        if resp.status_code != 200:
            pytest.skip("API not running. Start with: cd web && npx wrangler pages dev --local")
    except requests.ConnectionError:
        pytest.skip("API not running. Start with: cd web && npx wrangler pages dev --local")
    return True


class TestE2EFullFlow:
    """End-to-end test: pipeline data → sync → API → verify."""

    def test_stores_endpoint_returns_correct_stores(self, api_available):
        """GET /stores should return Lotte and Superindo."""
        resp = requests.get(f"{API_URL}/stores")
        assert resp.status_code == 200
        data = resp.json()
        store_names = [s["name"] for s in data["data"]]
        assert "Lotte" in store_names
        assert "Superindo" in store_names

    def test_products_endpoint_returns_paginated_results(self, api_available):
        """GET /products should return paginated products with correct shape."""
        resp = requests.get(f"{API_URL}/products?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "pagination" in data
        assert len(data["data"]) <= 5
        assert "has_more" in data["pagination"]
        if data["data"]:
            product = data["data"][0]
            assert "key" in product
            assert "name" in product
            assert "stores" in product
            assert "price_min" in product

    def test_product_detail_returns_full_data(self, api_available):
        """GET /products/:key should return product with stores array."""
        list_resp = requests.get(f"{API_URL}/products?limit=1")
        products = list_resp.json()["data"]
        if not products:
            pytest.skip("No products in database")
        key = products[0]["key"]

        resp = requests.get(f"{API_URL}/products/{key}")
        assert resp.status_code == 200
        product = resp.json()
        assert product["key"] == key
        assert "stores" in product
        assert isinstance(product["stores"], list)

    def test_product_history_returns_snapshots(self, api_available):
        """GET /products/:key/history should return snapshots sorted by date."""
        list_resp = requests.get(f"{API_URL}/products?limit=1")
        products = list_resp.json()["data"]
        if not products:
            pytest.skip("No products in database")
        key = products[0]["key"]

        resp = requests.get(f"{API_URL}/products/{key}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "snapshots" in data
        if data["snapshots"]:
            dates = [s["date"] for s in data["snapshots"]]
            assert dates == sorted(dates)

    def test_search_returns_matching_products(self, api_available):
        """GET /search?q=... should return products matching the query."""
        resp = requests.get(f"{API_URL}/search?q=indomie&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        for product in data["data"]:
            text = f"{product.get('name', '')} {product.get('brand', '')} {product.get('unit', '')}".lower()
            assert "indomie" in text

    def test_promos_endpoint_returns_promo_catalog(self, api_available):
        """GET /promos should return promos sorted by product_count."""
        resp = requests.get(f"{API_URL}/promos")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        if len(data["data"]) > 1:
            counts = [p["product_count"] for p in data["data"]]
            assert counts == sorted(counts, reverse=True)

    def test_brochures_endpoint_returns_brochure_metadata(self, api_available):
        """GET /brochures should return brochures grouped by image_path."""
        resp = requests.get(f"{API_URL}/brochures")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        if data["data"]:
            brochure = data["data"][0]
            assert "image_path" in brochure
            assert "store" in brochure
            assert "product_count" in brochure

    def test_stats_endpoint_returns_correct_counts(self, api_available):
        """GET /stats should return summary stats matching seed data."""
        resp = requests.get(f"{API_URL}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert "total_products_lotte" in stats
        assert "total_products_superindo" in stats
        assert stats["total_products_lotte"] > 0
        assert stats["total_products_superindo"] > 0

    def test_sync_batch_with_valid_data(self, api_available):
        """POST /sync/batch with valid data should upsert successfully."""
        batch = {
            "source": "e2e-test",
            "sync_run_id": "e2e_test_001",
            "stores": [{"name": "TestStore", "color": "#FF0000"}],
            "products": [{
                "key": "e2e-test-product",
                "name": "E2E Test Product",
                "brand": "TestBrand",
                "unit": "100g",
                "unit_type": "weight",
                "unit_value_g": 100,
            }],
            "prices": [{
                "product_key": "e2e-test-product",
                "store": "TestStore",
                "price": 9999,
                "effective_unit_price": 9999,
                "bundle_size": 1,
                "promo": None,
                "scrape_time": "2026-06-21T12:00:00",
                "date": "2026-06-21",
            }],
            "promos": [],
        }
        headers = {"Authorization": f"Bearer {SCRAPER_SECRET}", "Content-Type": "application/json"}
        resp = requests.post(f"{API_URL}/sync/batch", json=batch, headers=headers)
        assert resp.status_code == 200
        result = resp.json()
        assert result["sync_run_id"] == "e2e_test_001"
        assert len(result["errors"]) == 0

        detail_resp = requests.get(f"{API_URL}/products/e2e-test-product")
        assert detail_resp.status_code == 200
        product = detail_resp.json()
        assert product["name"] == "E2E Test Product"

    def test_sync_batch_idempotent(self, api_available):
        """POST /sync/batch twice with same data should not create duplicates."""
        batch = {
            "source": "e2e-test",
            "sync_run_id": "e2e_test_002",
            "stores": [],
            "products": [{
                "key": "e2e-idempotent-test",
                "name": "Idempotent Test",
                "brand": "Test",
                "unit": "50g",
                "unit_type": "weight",
                "unit_value_g": 50,
            }],
            "prices": [{
                "product_key": "e2e-idempotent-test",
                "store": "TestStore",
                "price": 5000,
                "effective_unit_price": 5000,
                "bundle_size": 1,
                "promo": None,
                "scrape_time": "2026-06-21T13:00:00",
                "date": "2026-06-21",
            }],
            "promos": [],
        }
        headers = {"Authorization": f"Bearer {SCRAPER_SECRET}", "Content-Type": "application/json"}

        resp1 = requests.post(f"{API_URL}/sync/batch", json=batch, headers=headers)
        assert resp1.status_code == 200

        resp2 = requests.post(f"{API_URL}/sync/batch", json=batch, headers=headers)
        assert resp2.status_code == 200

        search_resp = requests.get(f"{API_URL}/search?q=Idempotent&limit=10")
        results = search_resp.json()["data"]
        matching = [p for p in results if p["key"] == "e2e-idempotent-test"]
        assert len(matching) == 1

    def test_sync_batch_rejects_invalid_auth(self, api_available):
        """POST /sync/batch without auth should return 401."""
        resp = requests.post(
            f"{API_URL}/sync/batch",
            json={"source": "test", "sync_run_id": "x", "stores": [], "products": [], "prices": [], "promos": []}
        )
        assert resp.status_code == 401

    def test_security_headers_present(self, api_available):
        """API responses should include security headers."""
        resp = requests.get(f"{API_URL}/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Referrer-Policy" in resp.headers

    def test_404_for_unknown_route(self, api_available):
        """Unknown API routes should return 404 JSON."""
        resp = requests.get(f"{API_URL}/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    def test_400_for_invalid_query_params(self, api_available):
        """Invalid query params should return 400."""
        resp = requests.get(f"{API_URL}/products?limit=0")
        assert resp.status_code == 400
