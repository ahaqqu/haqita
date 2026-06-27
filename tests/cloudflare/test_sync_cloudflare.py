"""Unit tests for scripts/sync_cloudflare.py (sync pipeline data to Cloudflare API)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import scripts.sync_cloudflare as sc


def _run_once(fn, *args, **kwargs):
    """Helper to make a mocked retry_call execute the wrapped function once."""
    return fn()


class TestBuildSyncBatch:
    """Tests for build_sync_batch()."""

    def test_extracts_stores_from_snapshots(self):
        history = {
            "snapshots": [
                {"store": "Lotte", "date": "2026-06-13", "product_key": "a", "price": 1, "effective_unit_price": 1},
                {"store": "Superindo", "date": "2026-06-13", "product_key": "b", "price": 2, "effective_unit_price": 2},
            ]
        }
        batch = sc.build_sync_batch(history, {}, [], {})
        assert len(batch["stores"]) == 2
        names = [s["name"] for s in batch["stores"]]
        assert "Lotte" in names
        assert "Superindo" in names

    def test_includes_store_colors_from_display_hints(self):
        history = {
            "snapshots": [
                {"store": "Lotte", "date": "2026-06-13", "product_key": "a", "price": 1, "effective_unit_price": 1},
            ]
        }
        display_hints = {"store_colors": {"Lotte": "#ff0000"}}
        batch = sc.build_sync_batch(history, {}, [], display_hints)
        assert batch["stores"][0]["color"] == "#ff0000"

    def test_maps_catalog_fields_to_products(self):
        catalog = {
            "prod1": {
                "canonical_key": "canonical1",
                "display_name": "Display Name",
                "brand": "BrandX",
                "unit": "100 g",
                "unit_type": "weight",
                "unit_value_g": 100,
            }
        }
        batch = sc.build_sync_batch({"snapshots": []}, catalog, [], {})
        assert len(batch["products"]) == 1
        product = batch["products"][0]
        assert product["key"] == "canonical1"
        assert product["name"] == "Display Name"
        assert product["brand"] == "BrandX"
        assert product["category"] is None
        assert product["unit"] == "100 g"
        assert product["unit_type"] == "weight"
        assert product["unit_value_g"] == 100

    def test_maps_snapshot_fields_to_prices(self):
        snapshot = {
            "product_key": "a--b--100g",
            "store": "Lotte",
            "price": 15000,
            "effective_unit_price": 15000,
            "bundle_size": 2,
            "promo": ["BELI 2 GRATIS 1"],
            "promo_type": "bundle",
            "valid_from": "2026-06-01",
            "valid_until": "2026-06-30",
            "image_path": "database/scrape/lotte/20260613/a.jpg",
            "scrape_time": "2026-06-13T10:00:00",
            "date": "2026-06-13",
            "match_method": "exact",
            "match_confidence": 1.0,
            "standardized_promo": {"type": "bundle", "units": 3, "pay_for": 2},
        }
        batch = sc.build_sync_batch({"snapshots": [snapshot]}, {}, [], {})
        assert len(batch["prices"]) == 1
        price = batch["prices"][0]
        assert price["product_key"] == "a--b--100g"
        assert price["store"] == "Lotte"
        assert price["price"] == 15000
        assert price["effective_unit_price"] == 15000
        assert price["bundle_size"] == 2
        assert price["promo"] == ["BELI 2 GRATIS 1"]
        assert price["promo_type"] == "bundle"
        assert price["valid_from"] == "2026-06-01"
        assert price["valid_until"] == "2026-06-30"
        assert price["image_path"] == "database/scrape/lotte/20260613/a.jpg"
        assert price["scrape_time"] == "2026-06-13T10:00:00"
        assert price["date"] == "2026-06-13"
        assert price["match_method"] == "exact"
        assert price["match_confidence"] == 1.0
        assert price["standardized_promo"] == {"type": "bundle", "units": 3, "pay_for": 2}

    def test_preserves_promo_as_array_or_none(self):
        history = {
            "snapshots": [
                {"store": "Lotte", "date": "2026-06-13", "product_key": "a", "price": 1, "effective_unit_price": 1, "promo": ["DISKON 20%"]},
                {"store": "Lotte", "date": "2026-06-13", "product_key": "b", "price": 2, "effective_unit_price": 2, "promo": None},
            ]
        }
        batch = sc.build_sync_batch(history, {}, [], {})
        assert batch["prices"][0]["promo"] == ["DISKON 20%"]
        assert batch["prices"][1]["promo"] is None

    def test_preserves_standardized_promo_as_dict_or_none(self):
        history = {
            "snapshots": [
                {"store": "Lotte", "date": "2026-06-13", "product_key": "a", "price": 1, "effective_unit_price": 1, "standardized_promo": {"type": "discount", "discount_pct": 20}},
                {"store": "Lotte", "date": "2026-06-13", "product_key": "b", "price": 2, "effective_unit_price": 2, "standardized_promo": None},
            ]
        }
        batch = sc.build_sync_batch(history, {}, [], {})
        assert batch["prices"][0]["standardized_promo"] == {"type": "discount", "discount_pct": 20}
        assert batch["prices"][1]["standardized_promo"] is None

    def test_maps_promo_catalog_fields(self):
        promo_catalog_data = [
            {
                "key": "diskon-20",
                "display": "Diskon 20%",
                "type": "discount",
                "discount_pct": 20,
                "product_count": 5,
                "stores": {"Lotte": 3, "Superindo": 2},
                "example_products": ["a", "b"],
            }
        ]
        batch = sc.build_sync_batch({"snapshots": []}, {}, promo_catalog_data, {})
        assert len(batch["promos"]) == 1
        promo = batch["promos"][0]
        assert promo["key"] == "diskon-20"
        assert promo["display"] == "Diskon 20%"
        assert promo["type"] == "discount"
        assert promo["discount_pct"] == 20
        assert promo["product_count"] == 5
        assert promo["stores"] == {"Lotte": 3, "Superindo": 2}
        assert promo["example_products"] == ["a", "b"]

    def test_generates_sync_run_id(self):
        batch = sc.build_sync_batch({"snapshots": []}, {}, [], {})
        assert "sync_run_id" in batch
        assert isinstance(batch["sync_run_id"], str)
        assert len(batch["sync_run_id"]) > 0

    def test_source_is_haqita_pipeline(self):
        batch = sc.build_sync_batch({"snapshots": []}, {}, [], {})
        assert batch["source"] == "haqita-pipeline-v1"

    def test_handles_empty_history(self):
        batch = sc.build_sync_batch({"snapshots": []}, {}, [], {})
        assert batch["stores"] == []
        assert batch["products"] == []
        assert batch["prices"] == []
        assert batch["promos"] == []


class TestSendBatchSync:
    """Tests for send_batch_sync()."""

    @patch('scripts.sync_cloudflare.requests.post')
    @patch('scripts.sync_cloudflare.retry_call')
    def test_sends_batch_to_api(self, mock_retry, mock_post):
        mock_retry.side_effect = _run_once
        expected_response = {"stores": 1, "products": 2, "prices": 3, "promos": 0}
        mock_response = mock_post.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response

        batch = {"stores": [], "products": [], "prices": [], "promos": []}
        result = sc.send_batch_sync("https://api.example.com/api/v1", "secret", batch, dry_run=False)

        assert result == expected_response
        mock_post.assert_called_once_with(
            "https://api.example.com/api/v1/sync/batch",
            json=batch,
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            timeout=30,
        )

    def test_dry_run_does_not_send(self, capsys):
        sc.setup_logging(False)
        with patch('scripts.sync_cloudflare.requests.post') as mock_post:
            batch = {"stores": [1], "products": [1], "prices": [1], "promos": [1]}
            result = sc.send_batch_sync("https://api.example.com/api/v1", "secret", batch, dry_run=True)

        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "[DRY-RUN]" in output
        assert result["dry_run"] is True
        assert result["stores"] == 1
        mock_post.assert_not_called()

    @patch('scripts.sync_cloudflare.requests.post')
    @patch('scripts.sync_cloudflare.retry_call')
    def test_returns_error_on_401(self, mock_retry, mock_post):
        mock_retry.side_effect = _run_once
        mock_response = mock_post.return_value
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        batch = {"stores": [], "products": [], "prices": [], "promos": []}
        result = sc.send_batch_sync("https://api.example.com/api/v1", "secret", batch, dry_run=False)

        assert "error" in result
        assert "Authentication failed (401)" in result["error"]

    @patch('scripts.sync_cloudflare.requests.post')
    @patch('scripts.sync_cloudflare.retry_call')
    def test_returns_error_on_400(self, mock_retry, mock_post):
        mock_retry.side_effect = _run_once
        mock_response = mock_post.return_value
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Validation failed: missing field"}
        mock_response.text = "Bad Request"

        batch = {"stores": [], "products": [], "prices": [], "promos": []}
        result = sc.send_batch_sync("https://api.example.com/api/v1", "secret", batch, dry_run=False)

        assert "error" in result
        assert "Validation error (400)" in result["error"]
        assert "Validation failed" in result["error"]


class TestGetImagesToUpload:
    """Tests for get_images_to_upload()."""

    def _make_image(self, root, local_path, content=b"image data"):
        full = root / local_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return local_path

    def test_returns_all_images_on_first_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "ROOT", tmp_path)
        path1 = self._make_image(tmp_path, "database/scrape/superindo/20260613/a.jpg")
        path2 = self._make_image(tmp_path, "database/scrape/lotte/20260613/b.jpg")
        history = {
            "snapshots": [
                {"product_key": "a", "store": "Superindo", "date": "2026-06-13", "price": 1, "effective_unit_price": 1, "image_path": path1},
                {"product_key": "b", "store": "Lotte", "date": "2026-06-13", "price": 2, "effective_unit_price": 2, "image_path": path2},
            ]
        }
        to_upload = sc.get_images_to_upload(history, {})
        assert len(to_upload) == 2

    def test_skips_already_uploaded_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "ROOT", tmp_path)
        local_path = self._make_image(tmp_path, "database/scrape/superindo/20260613/a.jpg")
        file_hash = sc.compute_file_hash(tmp_path / local_path)
        history = {
            "snapshots": [
                {"product_key": "a", "store": "Superindo", "date": "2026-06-13", "price": 1, "effective_unit_price": 1, "image_path": local_path},
            ]
        }
        sync_state = {"uploaded_images": {local_path: file_hash}}
        to_upload = sc.get_images_to_upload(history, sync_state)
        assert to_upload == []

    def test_includes_changed_images(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "ROOT", tmp_path)
        local_path = self._make_image(tmp_path, "database/scrape/superindo/20260613/a.jpg")
        history = {
            "snapshots": [
                {"product_key": "a", "store": "Superindo", "date": "2026-06-13", "price": 1, "effective_unit_price": 1, "image_path": local_path},
            ]
        }
        sync_state = {"uploaded_images": {local_path: "oldhash"}}
        to_upload = sc.get_images_to_upload(history, sync_state)
        assert len(to_upload) == 1
        assert to_upload[0]["local_path"] == local_path

    def test_skips_missing_local_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "ROOT", tmp_path)
        history = {
            "snapshots": [
                {"product_key": "a", "store": "Superindo", "date": "2026-06-13", "price": 1, "effective_unit_price": 1, "image_path": "database/scrape/superindo/20260613/missing.jpg"},
            ]
        }
        to_upload = sc.get_images_to_upload(history, {})
        assert to_upload == []

    def test_converts_local_path_to_r2_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "ROOT", tmp_path)
        local_path = self._make_image(tmp_path, "database/scrape/superindo/20260613/abc.jpg")
        history = {
            "snapshots": [
                {"product_key": "a", "store": "Superindo", "date": "2026-06-13", "price": 1, "effective_unit_price": 1, "image_path": local_path},
            ]
        }
        to_upload = sc.get_images_to_upload(history, {})
        assert len(to_upload) == 1
        assert to_upload[0]["r2_key"] == "superindo/20260613/abc.jpg"


class TestComputeFileHash:
    """Tests for compute_file_hash()."""

    def test_returns_md5_hex_string(self, tmp_path):
        file_path = tmp_path / "sample.txt"
        file_path.write_text("hello")
        result = sc.compute_file_hash(file_path)
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path):
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("same content")
        p2.write_text("same content")
        assert sc.compute_file_hash(p1) == sc.compute_file_hash(p2)

    def test_different_content_different_hash(self, tmp_path):
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("content a")
        p2.write_text("content b")
        assert sc.compute_file_hash(p1) != sc.compute_file_hash(p2)


class TestSyncState:
    """Tests for load_sync_state() and save_sync_state()."""

    def test_load_returns_empty_state_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SYNC_STATE_FILE", tmp_path / "nonexistent.json")
        state = sc.load_sync_state()
        assert state["uploaded_images"] == {}
        assert state["last_sync"] is None
        assert state["last_sync_run_id"] is None

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SYNC_STATE_FILE", tmp_path / "sync_state.json")
        state = {
            "uploaded_images": {"database/scrape/a.jpg": "hash1"},
            "last_sync_run_id": "run-123",
        }
        sc.save_sync_state(state)
        loaded = sc.load_sync_state()
        assert loaded["uploaded_images"] == {"database/scrape/a.jpg": "hash1"}
        assert loaded["last_sync_run_id"] == "run-123"

    def test_save_includes_last_sync_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SYNC_STATE_FILE", tmp_path / "sync_state.json")
        state = {"uploaded_images": {}}
        sc.save_sync_state(state)
        loaded = sc.load_sync_state()
        assert "last_sync" in loaded
        assert isinstance(loaded["last_sync"], str)
        assert len(loaded["last_sync"]) > 0
        from datetime import datetime
        assert datetime.fromisoformat(loaded["last_sync"])


class TestUpdateSyncState:
    """Tests for update_sync_state()."""

    def test_adds_new_image_hashes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SYNC_STATE_FILE", tmp_path / "state.json")
        state = {"uploaded_images": {}}
        uploaded_images = [{"local_path": "database/scrape/new.jpg", "hash": "hashnew"}]
        sc.update_sync_state(state, uploaded_images, "run-1")
        assert state["uploaded_images"]["database/scrape/new.jpg"] == "hashnew"

    def test_preserves_existing_image_hashes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SYNC_STATE_FILE", tmp_path / "state.json")
        state = {"uploaded_images": {"database/scrape/old.jpg": "hashold"}}
        uploaded_images = [{"local_path": "database/scrape/new.jpg", "hash": "hashnew"}]
        sc.update_sync_state(state, uploaded_images, "run-1")
        assert state["uploaded_images"]["database/scrape/old.jpg"] == "hashold"
        assert state["uploaded_images"]["database/scrape/new.jpg"] == "hashnew"

    def test_updates_last_sync_run_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SYNC_STATE_FILE", tmp_path / "state.json")
        state = {"uploaded_images": {}}
        sc.update_sync_state(state, [], "run-42")
        assert state["last_sync_run_id"] == "run-42"
