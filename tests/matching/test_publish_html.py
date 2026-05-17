"""Unit tests for publish_html.py (Stage 4: Publish HTML)."""

import json
import os
import pytest
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

import scripts.publish_html as publish_html_mod


class TestPublishHtml:
    def _run_with_root(self, root, extra_args=None):
        """Run main with patched ROOT and argv."""
        publish_html_mod.ROOT = root
        publish_html_mod.HTML_DIR = root / "output" / "html"
        publish_html_mod.DATABASE_DIR = root / "database"
        publish_html_mod.PRICE_HISTORY_SRC = root / "database" / "price_history.json"
        publish_html_mod.CATALOG_SRC = root / "database" / "product_catalog.json"
        old_argv = sys.argv
        try:
            sys.argv = ["publish_html.py"] + (extra_args or [])
            publish_html_mod.main()
        finally:
            sys.argv = old_argv

    def test_generates_active_promo_from_database(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({
                "snapshots": [{
                    "product_key": "a--b--100g", "name": "A", "brand": "B",
                    "unit": "100 g", "date": "2026-05-17", "store": "Lotte",
                    "price": 10000, "effective_unit_price": 10000,
                    "promo": None, "valid_from": None, "valid_until": None,
                    "bundle_size": 1, "promo_type": "single",
                    "match_method": None, "match_confidence": None,
                    "image_path": None,
                }],
                "metadata": {},
            }))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "active_promo.json").exists()
            assert (html_dir / "price_history.json").exists()
            out = capsys.readouterr().out
            assert "[OK]" in out
            assert "generated from database" in out

    def test_active_promo_is_generated_not_copied(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "active_promo.json").exists()
            out = capsys.readouterr().out
            assert "generated from database" in out

    def test_warns_when_price_history_missing(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "active_promo.json").exists()
            out = capsys.readouterr().out
            assert "[WARN]" in out
            assert "price_history.json" in out

    def test_creates_html_dir_if_not_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            html_dir = root / "output" / "html"
            assert not html_dir.exists()

            self._run_with_root(root)

            assert html_dir.exists()

    def test_active_promo_content_matches_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({
                "snapshots": [
                    {
                        "product_key": "a--b--100g", "name": "Product A", "brand": "B",
                        "unit": "100 g", "date": "2026-05-17", "store": "Lotte",
                        "price": 10000, "effective_unit_price": 10000,
                        "promo": None, "valid_from": None, "valid_until": None,
                        "bundle_size": 1, "promo_type": "single",
                        "match_method": None, "match_confidence": None,
                        "image_path": None,
                    },
                    {
                        "product_key": "a--b--100g", "name": "Product A", "brand": "B",
                        "unit": "100 g", "date": "2026-05-17", "store": "Superindo",
                        "price": 12000, "effective_unit_price": 12000,
                        "promo": None, "valid_from": None, "valid_until": None,
                        "bundle_size": 1, "promo_type": "single",
                        "match_method": "exact", "match_confidence": 1.0,
                        "image_path": None,
                    },
                ],
                "metadata": {},
            }))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            with open(html_dir / "active_promo.json", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data["products"]) == 1
            assert data["products"][0]["price_min"] == 10000
            assert data["products"][0]["price_max"] == 12000
            assert len(data["singles"]) == 0

    def test_dry_run_does_not_write(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            self._run_with_root(root, extra_args=["--dry-run"])

            html_dir = root / "output" / "html"
            assert not (html_dir / "active_promo.json").exists()
            assert not (html_dir / "price_history.json").exists()
            out = capsys.readouterr().out
            assert "[WOULD GENERATE]" in out
            assert "[DRY-RUN]" in out

    def test_dry_run_shows_verbose_info(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            self._run_with_root(root, extra_args=["--dry-run", "--verbose"])

            out = capsys.readouterr().out
            assert "Generated size:" in out
            assert "WOULD GENERATE" in out

    def test_verbose_shows_file_size(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            self._run_with_root(root, extra_args=["--verbose"])

            out = capsys.readouterr().out
            assert "Size:" in out
            assert "[OK]" in out

    def test_summary_shows_counts(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            review_src = db_dir / "review_queue.json"
            review_src.write_text(json.dumps({"items": []}))

            self._run_with_root(root)

            out = capsys.readouterr().out
            assert "3 file(s) written" in out
            assert "0 warning(s)" in out

    def test_dry_run_summary(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            review_src = db_dir / "review_queue.json"
            review_src.write_text(json.dumps({"items": []}))

            self._run_with_root(root, extra_args=["--dry-run"])

            out = capsys.readouterr().out
            assert "3 file(s) would be written" in out

    def test_expired_products_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({
                "snapshots": [{
                    "product_key": "a--b--100g", "name": "Expired", "brand": "B",
                    "unit": "100 g", "date": "2026-05-10", "store": "Lotte",
                    "price": 10000, "effective_unit_price": 10000,
                    "promo": None, "valid_from": "2026-05-01", "valid_until": "2026-05-15",
                    "bundle_size": 1, "promo_type": "single",
                    "match_method": None, "match_confidence": None,
                    "image_path": None,
                }],
                "metadata": {},
            }))

            review_src = db_dir / "review_queue.json"
            review_src.write_text(json.dumps({"items": []}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            with open(html_dir / "active_promo.json", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data["products"]) == 0
            assert len(data["singles"]) == 0

    def test_copies_review_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": [], "metadata": {}}))

            review_src = db_dir / "review_queue.json"
            review_src.write_text(json.dumps({"items": [{"reason": "test"}]}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "review_queue.json").exists()
            with open(html_dir / "review_queue.json", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data["items"]) == 1
