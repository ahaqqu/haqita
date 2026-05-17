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
        publish_html_mod.CONSOLIDATED_SRC = root / "output" / "consolidation" / "consolidated_latest.json"
        publish_html_mod.PRICE_HISTORY_SRC = root / "database" / "price_history.json"
        old_argv = sys.argv
        try:
            sys.argv = ["publish_html.py"] + (extra_args or [])
            publish_html_mod.main()
        finally:
            sys.argv = old_argv

    def test_copies_both_files_when_sources_exist(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": []}))
            hist_src.write_text(json.dumps({"snapshots": []}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "consolidated_latest.json").exists()
            assert (html_dir / "price_history.json").exists()
            out = capsys.readouterr().out
            assert "[OK]" in out

    def test_warns_when_consolidated_missing(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_dir = root / "database"
            db_dir.mkdir(parents=True)

            hist_src = db_dir / "price_history.json"
            hist_src.write_text(json.dumps({"snapshots": []}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "price_history.json").exists()
            out = capsys.readouterr().out
            assert "[WARN]" in out
            assert "consolidated_latest.json" in out

    def test_warns_when_price_history_missing(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            cons_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            cons_src.write_text(json.dumps({"products": []}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            assert (html_dir / "consolidated_latest.json").exists()
            out = capsys.readouterr().out
            assert "[WARN]" in out
            assert "price_history.json" in out

    def test_warns_when_both_missing(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._run_with_root(root)

            out = capsys.readouterr().out
            assert out.count("[WARN]") == 2

    def test_creates_html_dir_if_not_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": []}))
            hist_src.write_text(json.dumps({"snapshots": []}))

            html_dir = root / "output" / "html"
            assert not html_dir.exists()

            self._run_with_root(root)

            assert html_dir.exists()

    def test_preserves_file_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": [{"key": "a"}]}))
            hist_src.write_text(json.dumps({"snapshots": [{"product_key": "a"}]}))

            self._run_with_root(root)

            html_dir = root / "output" / "html"
            cons_dst = html_dir / "consolidated_latest.json"
            hist_dst = html_dir / "price_history.json"
            with open(cons_dst, encoding="utf-8") as f:
                assert json.load(f) == {"products": [{"key": "a"}]}
            with open(hist_dst, encoding="utf-8") as f:
                assert json.load(f) == {"snapshots": [{"product_key": "a"}]}

    def test_dry_run_does_not_copy(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": []}))
            hist_src.write_text(json.dumps({"snapshots": []}))

            self._run_with_root(root, extra_args=["--dry-run"])

            html_dir = root / "output" / "html"
            assert not (html_dir / "consolidated_latest.json").exists()
            assert not (html_dir / "price_history.json").exists()
            out = capsys.readouterr().out
            assert "[WOULD COPY]" in out
            assert "[DRY-RUN]" in out

    def test_dry_run_shows_verbose_info(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": [{"key": "a"}]}))
            hist_src.write_text(json.dumps({"snapshots": []}))

            self._run_with_root(root, extra_args=["--dry-run", "--verbose"])

            out = capsys.readouterr().out
            assert "Size:" in out
            assert "WOULD COPY" in out

    def test_verbose_shows_file_size(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": [{"key": "a"}]}))
            hist_src.write_text(json.dumps({"snapshots": []}))

            self._run_with_root(root, extra_args=["--verbose"])

            out = capsys.readouterr().out
            assert "Size:" in out
            assert "[OK]" in out

    def test_summary_shows_counts(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            cons_src.write_text(json.dumps({"products": []}))

            self._run_with_root(root)

            out = capsys.readouterr().out
            assert "1 file(s) copied" in out
            assert "1 warning(s)" in out

    def test_dry_run_summary(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cons_dir = root / "output" / "consolidation"
            db_dir = root / "database"
            cons_dir.mkdir(parents=True)
            db_dir.mkdir(parents=True)

            cons_src = cons_dir / "consolidated_latest.json"
            hist_src = db_dir / "price_history.json"
            cons_src.write_text(json.dumps({"products": []}))
            hist_src.write_text(json.dumps({"snapshots": []}))

            self._run_with_root(root, extra_args=["--dry-run"])

            out = capsys.readouterr().out
            assert "2 file(s) would be copied" in out
