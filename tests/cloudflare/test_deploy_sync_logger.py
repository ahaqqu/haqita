"""Tests for commit c3ff44a: sync logger propagation and dry_run parameter fix.

Verifies:
1. setup_logging() configures scripts.sync_cloudflare logger with same handlers
2. deploy_cloudflare(dry_run=True) passes dry_run to _set_commit_sha_secret
3. run_sync() called from deploy_cloudflare respects dry_run flag
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import scripts.deploy as deploy
import scripts.sync_cloudflare as sc


def _run_once(fn, *args, **kwargs):
    """Helper to make a mocked retry_call execute the wrapped function once."""
    return fn()


class TestSyncLoggerPropagation:
    """setup_logging() should propagate handlers to scripts.sync_cloudflare logger."""

    def test_sync_logger_gets_file_handler(self, tmp_path):
        """Verify sync_logger has a FileHandler (fh) after setup_logging."""
        # Point LOG_DIR to tmp_path so we don't pollute output/
        with patch.object(deploy, 'ROOT', tmp_path):
            logger = deploy.setup_logging(verbose=True)
            sync_logger = logging.getLogger("scripts.sync_cloudflare")
            handlers = sync_logger.handlers
            assert any(isinstance(h, logging.FileHandler) for h in handlers), \
                "sync_logger should have a FileHandler"

    def test_sync_logger_gets_stream_handler(self, tmp_path):
        """Verify sync_logger has a StreamHandler (ch) after setup_logging."""
        with patch.object(deploy, 'ROOT', tmp_path):
            logger = deploy.setup_logging(verbose=True)
            sync_logger = logging.getLogger("scripts.sync_cloudflare")
            handlers = sync_logger.handlers
            assert any(isinstance(h, logging.StreamHandler) for h in handlers), \
                "sync_logger should have a StreamHandler"

    def test_sync_logger_propagates_to_file(self, tmp_path):
        """Sync log messages appear in the deploy log file."""
        with patch.object(deploy, 'ROOT', tmp_path):
            logger = deploy.setup_logging(verbose=True)
            sync_logger = logging.getLogger("scripts.sync_cloudflare")
            test_msg = "SYNC_TEST_MESSAGE_FROM_UNIT_TEST"
            sync_logger.info(test_msg)
            # Flush handlers
            for h in sync_logger.handlers:
                h.flush()
            log_dir = tmp_path / "output" / "logs"
            log_files = list(log_dir.glob("deploy_*.log"))
            assert log_files, f"No deploy log files found in {log_dir}"
            content = log_files[0].read_text(encoding="utf-8")
            assert test_msg in content, \
                f"Expected '{test_msg}' in log file, got:\n{content[:500]}"

    def test_sync_logger_propagates_to_stdout(self, tmp_path):
        """Sync log messages appear on stdout (StreamHandler)."""
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                logger = deploy.setup_logging(verbose=True)
                sync_logger = logging.getLogger("scripts.sync_cloudflare")
                test_msg = "SYNC_STDOUT_TEST_MESSAGE"
                sync_logger.info(test_msg)
                for h in sync_logger.handlers:
                    h.flush()
                output = mock_stdout.getvalue()
                assert test_msg in output, \
                    f"Expected '{test_msg}' in stdout, got:\n{output[:500]}"

    def test_sync_logger_level_is_debug(self, tmp_path):
        """sync_logger should be set to DEBUG level."""
        with patch.object(deploy, 'ROOT', tmp_path):
            deploy.setup_logging(verbose=True)
            sync_logger = logging.getLogger("scripts.sync_cloudflare")
            assert sync_logger.level == logging.DEBUG


class TestDryRunParameter:
    """deploy_cloudflare should pass dry_run flag to _set_commit_sha_secret."""

    @patch('scripts.deploy._require_command')
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare', return_value={"status": "complete", "url": "https://haqita.pages.dev"})
    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "test-run"})
    @patch('scripts.deploy.load_config', return_value={})
    @patch('scripts.deploy.os.getenv', return_value="test-secret")
    def test_dry_run_passes_dry_run_param_to_set_commit_sha(self, mock_getenv, mock_cfg,
                                                              mock_run_sync, mock_deploy,
                                                              mock_set_secret, mock_require,
                                                              tmp_path):
        """When not in dry_run mode, _set_commit_sha_secret receives dry_run=False."""
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
                (tmp_path / "index.html").write_text("<html>", encoding="utf-8")
                with patch.object(deploy, '_get_local_head_sha', return_value="abc123"):
                    with patch.object(deploy, '_get_deployed_version', return_value="oldsha"):
                        result = deploy.deploy_cloudflare(dry_run=False, verbose=False)

                        # _set_commit_sha_secret should be called with dry_run=False
                        mock_set_secret.assert_called_once_with("abc123", dry_run=False)
                        mock_deploy.assert_called_once()

    @patch('scripts.deploy._require_command')
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare', return_value={"status": "complete", "url": "https://haqita.pages.dev"})
    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "test-run"})
    @patch('scripts.deploy.load_config', return_value={})
    def test_dry_run_returns_deploy_needed_true(self, mock_cfg, mock_run_sync,
                                                  mock_deploy, mock_set_secret, mock_require,
                                                  tmp_path):
        """When deployed version differs, deploy_needed should be True in result."""
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
                (tmp_path / "index.html").write_text("<html>", encoding="utf-8")
                with patch.object(deploy, '_get_local_head_sha', return_value="abc123"):
                    with patch.object(deploy, '_get_deployed_version', return_value="oldsha"):
                        result = deploy.deploy_cloudflare(dry_run=True, verbose=False)
                        assert result["deploy_needed"] is True

    @patch('scripts.deploy._require_command')
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare', return_value={"status": "complete", "url": "https://haqita.pages.dev"})
    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "test-run"})
    @patch('scripts.deploy.load_config', return_value={})
    def test_dry_run_returns_dry_run_status(self, mock_cfg, mock_run_sync,
                                              mock_deploy, mock_set_secret, mock_require,
                                              tmp_path):
        """When dry_run=True, result status should be 'dry_run'."""
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
                (tmp_path / "index.html").write_text("<html>", encoding="utf-8")
                with patch.object(deploy, '_get_local_head_sha', return_value="abc123"):
                    with patch.object(deploy, '_get_deployed_version', return_value="oldsha"):
                        result = deploy.deploy_cloudflare(dry_run=True, verbose=False)
                        assert result["status"] == "dry_run"

    @patch('scripts.deploy._require_command')
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare', return_value={"status": "complete", "url": "https://haqita.pages.dev"})
    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "test-run"})
    @patch('scripts.deploy.load_config', return_value={})
    def test_dry_run_skips_deploy_when_up_to_date(self, mock_cfg, mock_run_sync,
                                                    mock_deploy, mock_set_secret, mock_require,
                                                    tmp_path):
        """When deployed version matches local SHA, deploy should be skipped."""
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
                (tmp_path / "index.html").write_text("<html>", encoding="utf-8")
                with patch.object(deploy, '_get_local_head_sha', return_value="abc123"):
                    with patch.object(deploy, '_get_deployed_version', return_value="abc123"):
                        result = deploy.deploy_cloudflare(dry_run=True, verbose=False)
                        assert result["deploy_needed"] is False
                        # _deploy_to_cloudflare should NOT be called when up-to-date
                        mock_deploy.assert_not_called()
                        # But sync should still run
                        mock_run_sync.assert_called_once()


class TestEndToEndDryRun:
    """End-to-end dry-run flow: deploy_cloudflare with mocked external calls."""

    @patch('scripts.deploy.load_config', return_value={})
    @patch('scripts.deploy.run_sync')
    def test_dry_run_end_to_end_console_output(self, mock_run_sync, mock_cfg, tmp_path, capsys):
        """Running deploy_cloudflare(dry_run=True) produces expected console output."""
        mock_run_sync.return_value = {"status": "ok", "sync_run_id": "test-001"}

        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
                (tmp_path / "index.html").write_text("<html>", encoding="utf-8")

                with patch.object(deploy, '_require_command'):
                    with patch.object(deploy, '_install_deps_if_needed'):
                        with patch.object(deploy, '_copy_static_files'):
                            with patch.object(deploy, '_run_typecheck'):
                                with patch.object(deploy, '_get_local_head_sha', return_value="abc123"):
                                    with patch.object(deploy, '_get_deployed_version', return_value="oldsha"):
                                        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                                            deploy.logger = logging.getLogger("test.deploy")
                                            deploy.logger.setLevel(logging.DEBUG)
                                            deploy.logger.handlers = []
                                            ch = logging.StreamHandler(sys.stdout)
                                            ch.setLevel(logging.DEBUG)
                                            deploy.logger.addHandler(ch)

                                            result = deploy.deploy_cloudflare(dry_run=True, verbose=True)

                                            output = mock_stdout.getvalue()
                                            assert "DRY-RUN" in output
                                            assert "Syncing data to deployed API" in output

        deploy.logger = logging.getLogger(deploy.__name__)
        deploy.logger.handlers = []


class TestRunSyncCallable:
    """run_sync() is callable from deploy.py and respects dry_run."""

    def test_run_sync_dry_run_returns_status_ok(self, tmp_path, monkeypatch):
        """run_sync(dry_run=True) should return ok status without API calls."""
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setattr(sc, 'DATABASE_DIR', tmp_path)
        monkeypatch.setattr(sc, 'OUTPUT_DIR', tmp_path)
        monkeypatch.setattr(sc, 'SYNC_STATE_FILE', tmp_path / "sync_state.json")

        # Create empty data files so batch building doesn't crash
        for fname in ["price_history.json", "product_catalog.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")
        for fname in ["promo_catalog.json", "active_promo.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")

        # Prevent logging from polluting test output
        sc.logger.handlers = []
        sc.logger.addHandler(logging.NullHandler())

        result = sc.run_sync("https://example.com/api/v1", "", dry_run=True, verbose=False)

        assert result["status"] == "ok"
        assert "sync_run_id" in result

    def test_run_sync_dry_run_prints_dry_run_message(self, tmp_path, monkeypatch):
        """run_sync(dry_run=True) should print '[DRY-RUN]' messages."""
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setattr(sc, 'DATABASE_DIR', tmp_path)
        monkeypatch.setattr(sc, 'OUTPUT_DIR', tmp_path)
        monkeypatch.setattr(sc, 'SYNC_STATE_FILE', tmp_path / "sync_state.json")

        for fname in ["price_history.json", "product_catalog.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")
        for fname in ["promo_catalog.json", "active_promo.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            sc.logger.handlers = []
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            sc.logger.addHandler(ch)

            sc.run_sync("https://example.com/api/v1", "", dry_run=True, verbose=False)
            output = mock_stdout.getvalue()
            assert "[DRY-RUN]" in output

        sc.logger.handlers = []


class TestSetCommitShaSecret:
    """_set_commit_sha_secret() should pass the value via stdin, not as positional arg."""

    @patch('scripts.deploy._require_command')
    @patch('scripts.deploy.subprocess.run')
    def test_passes_sha_via_stdin(self, mock_run, mock_require, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["wrangler", "pages", "secret", "put", "COMMIT_SHA"],
            returncode=0,
            stdout="",
            stderr="",
        )

        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                result = deploy._set_commit_sha_secret("abc123def456", dry_run=False)

        assert result is True
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("input") == "abc123def456"
        args = mock_run.call_args.args[0]
        assert args == ["wrangler", "pages", "secret", "put", "COMMIT_SHA"]

    @patch('scripts.deploy._require_command')
    @patch('scripts.deploy.subprocess.run')
    def test_returns_false_on_failure(self, mock_run, mock_require, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["wrangler", "pages", "secret", "put", "COMMIT_SHA"],
            returncode=1,
            stdout="",
            stderr="error",
        )

        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                result = deploy._set_commit_sha_secret("abc123", dry_run=False)

        assert result is False

    def test_dry_run_returns_true(self, tmp_path):
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                (tmp_path / "web").mkdir(parents=True, exist_ok=True)
                result = deploy._set_commit_sha_secret("abc123", dry_run=True)
        assert result is True
