"""Tests for the deploy + sync hardening fixes.

Covers:
1. ``_apply_d1_schema_remote()`` runs ``wrangler d1 execute ... --remote
   --file=<absolute path>/web/schema.sql`` and reports success/failure.
2. ``deploy_cloudflare()`` invokes the D1 schema apply before sync, and
   aborts the sync when the apply fails (so we never run a 100% "no such
   table" batch sync again).
3. ``deploy_cloudflare(skip_d1_schema=True)`` skips the apply.
4. ``run_sync()`` all-rows-failed guard: when the API returns a 207 whose
   ``errors`` length equals the total batch row count, sync aborts with
   ``status="error"`` and ``error="all_rows_failed"`` instead of falling
   through to "Sync complete.".
5. ``reconcile_r2_images`` / ``list_r2_keys`` / ``run_sync(verify_r2=True)``:
   the R2 reconciliation path lists the bucket, queues missing referenced
   images for re-upload, and prunes stale ``sync_state`` entries.
"""

import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import scripts.deploy as deploy
import scripts.sync_cloudflare as sc


# Silence logging during tests.
@pytest.fixture(autouse=True)
def _silence_logging():
    for name in (deploy.__name__, sc.__name__, "scripts.sync_cloudflare"):
        lg = logging.getLogger(name)
        lg.handlers = [logging.NullHandler()]
    yield


# ---------------------------------------------------------------------------
# Fix 1: _apply_d1_schema_remote
# ---------------------------------------------------------------------------

class TestApplyD1SchemaRemote:
    @patch('scripts.deploy._require_command', return_value="/usr/bin/wrangler")
    @patch('scripts.deploy.subprocess.run')
    def test_runs_wrangler_with_remote_and_file(self, mock_run, mock_require, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr="",
        )
        web = tmp_path / "web"
        web.mkdir()
        (web / "schema.sql").write_text("-- schema", encoding="utf-8")

        with patch.object(deploy, 'WEB_DIR', web):
            result = deploy._apply_d1_schema_remote(dry_run=False, verbose=False)

        assert result is True
        args = mock_run.call_args.args[0]
        # The --file argument must resolve against WEB_DIR's real location,
        # not the caller's cwd (we launch wrangler with cwd=WEB_DIR, so a
        # project-root-relative "--file=./web/schema.sql" would resolve to
        # web/web/schema.sql and fail — the original bug this test guards
        # against).
        expected_schema_arg = f"--file={(web / 'schema.sql').resolve()}"
        assert args == [
            "/usr/bin/wrangler", "d1", "execute", "haqita-db",
            "--remote", expected_schema_arg,
        ]
        assert mock_run.call_args.kwargs["cwd"] == web

    def test_dry_run_returns_true_without_invoking_wrangler(self, tmp_path):
        web = tmp_path / "web"
        web.mkdir()
        (web / "schema.sql").write_text("-- schema", encoding="utf-8")
        with patch.object(deploy, 'WEB_DIR', web):
            with patch('scripts.deploy.subprocess.run') as mock_run:
                result = deploy._apply_d1_schema_remote(dry_run=True, verbose=False)
        assert result is True
        mock_run.assert_not_called()

    @patch('scripts.deploy._require_command', return_value="/usr/bin/wrangler")
    @patch('scripts.deploy.subprocess.run')
    def test_returns_false_on_wrangler_failure(self, mock_run, mock_require, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="✘ no such database",
        )
        web = tmp_path / "web"
        web.mkdir()
        (web / "schema.sql").write_text("-- schema", encoding="utf-8")
        with patch.object(deploy, 'WEB_DIR', web):
            result = deploy._apply_d1_schema_remote(dry_run=False, verbose=False)
        assert result is False

    def test_returns_false_when_schema_file_missing(self, tmp_path):
        web = tmp_path / "web"
        web.mkdir()
        with patch.object(deploy, 'WEB_DIR', web):
            result = deploy._apply_d1_schema_remote(dry_run=False, verbose=False)
        assert result is False


# ---------------------------------------------------------------------------
# Fix 1 (wiring): deploy_cloudflare invokes schema apply
# ---------------------------------------------------------------------------

class TestDeployCloudflareSchemaWiring:
    """deploy_cloudflare() must apply D1 schema between deploy and sync."""

    @pytest.fixture(autouse=True)
    def _set_secret(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_SECRET", "test-secret")

    def _setup_paths(self, tmp_path):
        web = tmp_path / "web"
        web.mkdir()
        (web / "package.json").write_text("{}", encoding="utf-8")
        (web / "schema.sql").write_text("-- schema", encoding="utf-8")
        (tmp_path / "index.html").write_text("<html>", encoding="utf-8")

    @patch('scripts.deploy._apply_d1_schema_remote', return_value=True)
    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "r1"})
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare')
    @patch('scripts.deploy._get_deployed_version', return_value="oldsha")
    @patch('scripts.deploy._get_local_head_sha', return_value="abc123")
    @patch('scripts.deploy.load_config', return_value={})
    def test_invokes_schema_apply_before_sync(
        self, mock_cfg, mock_sha, mock_ver, mock_deploy,
        mock_set_secret, mock_run_sync, mock_apply_schema, tmp_path,
    ):
        mock_deploy.return_value = {"status": "complete", "url": "https://x"}
        self._setup_paths(tmp_path)
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                result = deploy.deploy_cloudflare(dry_run=False, verbose=False)

        mock_apply_schema.assert_called_once_with(False, False)
        assert result["status"] in ("complete", "dry_run")
        assert result.get("d1_schema_applied") is True

    @patch('scripts.deploy._apply_d1_schema_remote', return_value=False)
    @patch('scripts.deploy.run_sync')
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare',
           return_value={"status": "complete", "url": "https://x"})
    @patch('scripts.deploy._get_deployed_version', return_value="oldsha")
    @patch('scripts.deploy._get_local_head_sha', return_value="abc123")
    @patch('scripts.deploy.load_config', return_value={})
    def test_aborts_sync_when_schema_apply_fails(
        self, mock_cfg, mock_sha, mock_ver, mock_deploy,
        mock_set_secret, mock_run_sync, mock_apply_schema, tmp_path,
    ):
        self._setup_paths(tmp_path)
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                result = deploy.deploy_cloudflare(dry_run=False, verbose=False)

        assert result["status"] == "error"
        assert result["error"] == "d1_schema_apply_failed"
        # Sync must NOT run — that's the whole point of the guard.
        mock_run_sync.assert_not_called()

    @patch('scripts.deploy._apply_d1_schema_remote')
    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "r1"})
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare',
           return_value={"status": "complete", "url": "https://x"})
    @patch('scripts.deploy._get_deployed_version', return_value="oldsha")
    @patch('scripts.deploy._get_local_head_sha', return_value="abc123")
    @patch('scripts.deploy.load_config', return_value={"deploy": {"apply_d1_schema": True}})
    def test_skip_d1_schema_flag_skips_apply(
        self, mock_cfg, mock_sha, mock_ver, mock_deploy,
        mock_set_secret, mock_run_sync, mock_apply_schema, tmp_path,
    ):
        self._setup_paths(tmp_path)
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                result = deploy.deploy_cloudflare(
                    dry_run=False, verbose=False, skip_d1_schema=True,
                )

        mock_apply_schema.assert_not_called()
        mock_run_sync.assert_called_once()
        # Note: apply_d1_schema defaults to True in config; --skip-d1-schema wins.
        assert result.get("d1_schema_applied") == "skipped"

    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "r1"})
    @patch('scripts.deploy._apply_d1_schema_remote', return_value=True)
    @patch('scripts.deploy._set_commit_sha_secret', return_value=True)
    @patch('scripts.deploy._deploy_to_cloudflare',
           return_value={"status": "complete", "url": "https://x"})
    @patch('scripts.deploy._get_deployed_version', return_value="abc123")
    @patch('scripts.deploy._get_local_head_sha', return_value="abc123")
    @patch('scripts.deploy.load_config', return_value={"deploy": {"apply_d1_schema": False}})
    def test_config_apply_d1_schema_false_skips_apply(
        self, mock_cfg, mock_sha, mock_ver, mock_deploy,
        mock_set_secret, mock_apply_schema, mock_run_sync, tmp_path,
    ):
        """deploy.apply_d1_schema=false in config disables the apply step."""
        self._setup_paths(tmp_path)
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                result = deploy.deploy_cloudflare(dry_run=False, verbose=False)

        mock_apply_schema.assert_not_called()
        assert result["status"] in ("complete", "dry_run")

    @patch('scripts.deploy.run_sync', return_value={"status": "ok", "sync_run_id": "r1"})
    @patch('scripts.deploy._apply_d1_schema_remote', return_value=True)
    @patch('scripts.deploy._set_commit_sha_secret')
    @patch('scripts.deploy._deploy_to_cloudflare',
           return_value={"status": "complete", "url": "https://x"})
    @patch('scripts.deploy._get_deployed_version', return_value="abc123")
    @patch('scripts.deploy._get_local_head_sha', return_value="abc123")
    @patch('scripts.deploy.load_config', return_value={})
    def test_schema_applied_even_when_deploy_skipped(
        self, mock_cfg, mock_sha, mock_ver, mock_deploy,
        mock_set_secret, mock_apply_schema, mock_run_sync, tmp_path,
    ):
        """Even when SHA matches and deploy is skipped, D1 schema apply still runs.

        This is the original bug: 'no such table' failures happened because the
        schema-apply step never existed. Tying it to deploy-needed=false would
        reopen that hole for any first sync against a freshly-reset D1 whose
        version endpoint already reports the matching SHA.
        """
        self._setup_paths(tmp_path)
        with patch.object(deploy, 'ROOT', tmp_path):
            with patch.object(deploy, 'WEB_DIR', tmp_path / "web"):
                deploy.deploy_cloudflare(dry_run=False, verbose=False)

        mock_deploy.assert_not_called()  # SHA matched — Pages deploy skipped
        mock_apply_schema.assert_called_once()  # but schema apply still ran
        mock_run_sync.assert_called_once()


# ---------------------------------------------------------------------------
# Fix 2: all-rows-failed guard in run_sync
# ---------------------------------------------------------------------------

class TestAllRowsFailedGuard:
    @patch('scripts.sync_cloudflare.load_sync_state', return_value={"uploaded_images": {}})
    @patch('scripts.sync_cloudflare.send_batch_sync')
    def test_all_rows_failed_returns_error(self, mock_send, mock_state, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setattr(sc, 'DATABASE_DIR', tmp_path)
        monkeypatch.setattr(sc, 'OUTPUT_DIR', tmp_path)
        monkeypatch.setattr(sc, 'SYNC_STATE_FILE', tmp_path / "sync_state.json")
        for fname in ["price_history.json", "product_catalog.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")
        for fname in ["promo_catalog.json", "active_promo.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")

        # API reports a 207 with every row failed (mirrors the original bug
        # where 2+370+742+41 = 1155 errors slipped through as "Sync complete.").
        # Build a non-empty batch so total_rows > 0.
        history = {
            "snapshots": [
                {"product_key": "k1", "store": "Lotte", "date": "2026-06-01",
                 "price": 1, "effective_unit_price": 1, "image_path": None},
            ]
        }
        (tmp_path / "price_history.json").write_text(
            __import__("json").dumps(history), encoding="utf-8",
        )
        mock_send.return_value = {
            "stores": {"updated": 0, "skipped": 1},
            "products": {"updated": 0, "skipped": 0},
            "prices": {"updated": 0, "skipped": 1},
            "promos": {"updated": 0, "skipped": 0},
            "errors": [
                {"table": "stores", "key": "Lotte", "error": "no such table"},
                {"table": "prices", "key": "k1:Lotte:2026-06-01", "error": "no such table"},
            ],
        }

        result = sc.run_sync(
            "https://x/api/v1", "secret", dry_run=False, verbose=False,
        )

        assert result["status"] == "error"
        assert result["error"] == "all_rows_failed"
        assert result["errors"][0]["error"] == "no such table"

    @patch('scripts.sync_cloudflare.load_sync_state', return_value={"uploaded_images": {}})
    @patch('scripts.sync_cloudflare.send_batch_sync')
    def test_partial_failure_still_returns_ok(
        self, mock_send, mock_state, tmp_path, monkeypatch,
    ):
        """Some failed, some succeeded — guard must not fire."""
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setattr(sc, 'DATABASE_DIR', tmp_path)
        monkeypatch.setattr(sc, 'OUTPUT_DIR', tmp_path)
        monkeypatch.setattr(sc, 'SYNC_STATE_FILE', tmp_path / "sync_state.json")
        history = {
            "snapshots": [
                {"product_key": "k1", "store": "Lotte", "date": "2026-06-01",
                 "price": 1, "effective_unit_price": 1, "image_path": None},
                {"product_key": "k2", "store": "Lotte", "date": "2026-06-01",
                 "price": 2, "effective_unit_price": 2, "image_path": None},
            ]
        }
        (tmp_path / "price_history.json").write_text(
            __import__("json").dumps(history), encoding="utf-8",
        )
        for fname in ["product_catalog.json", "promo_catalog.json", "active_promo.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")

        mock_send.return_value = {
            "stores": {"updated": 1, "skipped": 0},
            "products": {"updated": 0, "skipped": 0},
            "prices": {"updated": 1, "skipped": 1},  # 1 of 2 prices failed
            "promos": {"updated": 0, "skipped": 0},
            "errors": [
                {"table": "prices", "key": "k2:Lotte:2026-06-01", "error": "boom"},
            ],
        }

        result = sc.run_sync(
            "https://x/api/v1", "secret", dry_run=False, verbose=False,
        )

        # total_rows = 1 store + 2 prices = 3; errors = 1 < 3 -> not all failed
        assert result["status"] == "ok"

    @patch('scripts.sync_cloudflare.load_sync_state', return_value={"uploaded_images": {}})
    @patch('scripts.sync_cloudflare.send_batch_sync')
    def test_empty_batch_does_not_trigger_guard(
        self, mock_send, mock_state, tmp_path, monkeypatch,
    ):
        """total_rows == 0 is a no-op; guard must not classify it as a hard failure."""
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setattr(sc, 'DATABASE_DIR', tmp_path)
        monkeypatch.setattr(sc, 'OUTPUT_DIR', tmp_path)
        monkeypatch.setattr(sc, 'SYNC_STATE_FILE', tmp_path / "sync_state.json")
        for fname in ["price_history.json", "product_catalog.json",
                      "promo_catalog.json", "active_promo.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")
        mock_send.return_value = {"errors": [], "stores": {"skipped": 0}}

        result = sc.run_sync(
            "https://x/api/v1", "secret", dry_run=False, verbose=False,
        )
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Fix 3: R2 reconciliation
# ---------------------------------------------------------------------------

class TestR2Reconcile:
    def _make_image(self, root, local_path, content=b"image data"):
        full = root / local_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return local_path

    def test_list_r2_keys_paginates(self):
        client = MagicMock()
        # First page truncated with two keys + a continuation token.
        client.list_objects_v2.side_effect = [
            {"IsTruncated": True, "Contents": [{"Key": "a"}, {"Key": "b"}],
             "NextContinuationToken": "tok"},
            {"IsTruncated": False, "Contents": [{"Key": "c"}]},
        ]
        keys = sc.list_r2_keys(client, "bucket")
        assert keys == {"a", "b", "c"}
        assert client.list_objects_v2.call_count == 2
        # Second call must carry the continuation token.
        second_kwargs = client.list_objects_v2.call_args_list[1].kwargs
        assert second_kwargs["ContinuationToken"] == "tok"

    def test_list_r2_keys_returns_empty_on_error(self):
        client = MagicMock()
        client.list_objects_v2.side_effect = RuntimeError("net down")
        keys = sc.list_r2_keys(client, "bucket")
        assert keys == set()

    def test_reconcile_detects_missing_in_r2(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        p = self._make_image(tmp_path, "database/scrape/lotte/d/img.jpg")
        history = {"snapshots": [
            {"image_path": p, "store": "Lotte", "date": "d", "product_key": "k",
             "price": 1, "effective_unit_price": 1},
        ]}
        # sync_state has no record of this image and R2 doesn't have it.
        sync_state = {"uploaded_images": {}}
        to_upload, stale = sc.reconcile_r2_images(set(), history, sync_state)
        assert len(to_upload) == 1
        assert to_upload[0]["r2_key"] == "lotte/d/img.jpg"
        assert stale == []

    def test_reconcile_detects_state_known_r2_missing(self, tmp_path, monkeypatch):
        """tracked in sync_state but missing from R2 → re-upload."""
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        p = self._make_image(tmp_path, "database/scrape/lotte/d/img.jpg")
        h = sc.compute_file_hash(tmp_path / p)
        history = {"snapshots": [
            {"image_path": p, "store": "Lotte", "date": "d", "product_key": "k",
             "price": 1, "effective_unit_price": 1},
        ]}
        sync_state = {"uploaded_images": {p: h}}  # state thinks it's uploaded
        # ...but R2 is empty:
        to_upload, stale = sc.reconcile_r2_images(set(), history, sync_state)
        assert len(to_upload) == 1
        # unchanged (state hash equals file hash) so the only reason to reupload
        # is that R2 lacks the object.
        assert to_upload[0]["r2_key"] == "lotte/d/img.jpg"
        assert stale == []

    def test_reconcile_prunes_stale_sync_state_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        p = self._make_image(tmp_path, "database/scrape/lotte/d/img.jpg")
        # Local file content matches recorded hash and R2 has the object -> all good.
        h = sc.compute_file_hash(tmp_path / p)
        r2_keys = {"lotte/d/img.jpg"}
        history = {"snapshots": [
            {"image_path": p, "store": "Lotte", "date": "d", "product_key": "k",
             "price": 1, "effective_unit_price": 1},
        ]}
        # A completely unrelated stale path that nothing references any more.
        sync_state = {"uploaded_images": {
            p: h,
            "database/scrape/lotte/old/gone.jpg": "stalehash",
        }}
        to_upload, stale = sc.reconcile_r2_images(r2_keys, history, sync_state)
        assert to_upload == []
        assert stale == ["database/scrape/lotte/old/gone.jpg"]

    def test_reconcile_dummy_data_prefix(self, tmp_path, monkeypatch):
        """DUMMY_DATA=1 prefixes R2 keys with dummy/."""
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setenv("DUMMY_DATA", "1")
        p = self._make_image(tmp_path, "database/scrape/lotte/d/img.jpg")
        history = {"snapshots": [
            {"image_path": p, "store": "Lotte", "date": "d", "product_key": "k",
             "price": 1, "effective_unit_price": 1},
        ]}
        to_upload, _ = sc.reconcile_r2_images(set(), history, {"uploaded_images": {}})
        assert to_upload[0]["r2_key"] == "dummy/lotte/d/img.jpg"


class TestRunSyncVerifyR2:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, 'ROOT', tmp_path)
        monkeypatch.setattr(sc, 'DATABASE_DIR', tmp_path)
        monkeypatch.setattr(sc, 'OUTPUT_DIR', tmp_path)
        monkeypatch.setattr(sc, 'SYNC_STATE_FILE', tmp_path / "sync_state.json")
        for fname in ["price_history.json", "product_catalog.json",
                      "promo_catalog.json", "active_promo.json"]:
            (tmp_path / fname).write_text("{}", encoding="utf-8")

    @patch('scripts.sync_cloudflare.send_batch_sync')
    @patch('scripts.sync_cloudflare.get_r2_client')
    @patch('scripts.sync_cloudflare.load_sync_state')
    @patch('scripts.sync_cloudflare.upload_images_to_r2')
    def test_verify_r2_lists_bucket_and_queues_missing(
        self, mock_upload, mock_state, mock_r2client, mock_send,
        tmp_path, monkeypatch,
    ):
        self._setup(tmp_path, monkeypatch)
        # One referenced image, not present anywhere.
        img_dir = tmp_path / "database" / "scrape" / "lotte" / "d"
        img_dir.mkdir(parents=True)
        (img_dir / "img.jpg").write_bytes(b"data")
        history = {"snapshots": [
            {"image_path": "database/scrape/lotte/d/img.jpg", "store": "Lotte",
             "date": "d", "product_key": "k", "price": 1, "effective_unit_price": 1},
        ]}
        (tmp_path / "price_history.json").write_text(
            __import__("json").dumps(history), encoding="utf-8",
        )
        mock_state.return_value = {"uploaded_images": {
            "database/scrape/lotte/d/img.jpg": "wrong-hash",
            "database/scrape/lotte/OLD/gone.jpg": "stale",
        }}
        mock_send.return_value = {"stores": {"updated": 0}, "errors": []}
        client = MagicMock()
        client.list_objects_v2.return_value = {"IsTruncated": False, "Contents": []}
        mock_r2client.return_value = client
        # Pretend the upload succeeded for every queued image.
        mock_upload.return_value = {
            "database/scrape/lotte/d/img.jpg": "https://pub-hash.r2.dev/lotte/d/img.jpg",
        }

        result = sc.run_sync(
            "https://x/api/v1", "secret", dry_run=False,
            verbose=False, verify_r2=True,
        )

        assert result["status"] == "ok"
        client.list_objects_v2.assert_called_once()
        # The previously-asserted single re-upload should have happened.
        uploaded_paths = [img["local_path"]
                          for img in mock_upload.call_args.args[0]]
        assert "database/scrape/lotte/d/img.jpg" in uploaded_paths
        # Stale sync_state entry must have been pruned by the state-update step.
        saved = __import__("json").load(open(tmp_path / "sync_state.json"))
        assert "database/scrape/lotte/OLD/gone.jpg" not in saved["uploaded_images"]

    @patch('scripts.sync_cloudflare.get_r2_client')
    def test_dry_run_verify_r2_does_not_call_r2(self, mock_r2client, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        # Empty sync_state and empty history ensures no upload path is hit.
        sc.logger.handlers = [logging.NullHandler()]
        # dry_run should not actually invoke get_r2_client.
        # send_batch_sync is patched to a no-op through dry_run handling.
        result = sc.run_sync(
            "https://x/api/v1", "secret", dry_run=True, verbose=False, verify_r2=True,
        )
        assert result["status"] == "ok"
        mock_r2client.assert_not_called()