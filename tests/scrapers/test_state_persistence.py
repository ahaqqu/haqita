import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Use base_scraper for shared utilities
from scripts.scrapers.base_scraper import load_state, save_state, md5_hash


class TestStatePersistence:
    def test_load_empty_state_when_no_file(self, tmp_path):
        state_dir = tmp_path / "scrape"
        state_file = state_dir / "superindo_state.json"
        assert not state_file.exists()
        state = load_state(state_file)
        assert state == {"last_run": None, "processed": []}

    def test_save_and_reload_state(self, tmp_path):
        state_dir = tmp_path / "scrape"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "superindo_state.json"

        state = {
            "last_run": "2026-05-14T12:00:00",
            "processed": [
                {"filename": "img1.jpg", "md5": "abc123", "image_url": "https://example.com/1.jpg"}
            ]
        }
        save_state(state, state_file)
        assert state_file.exists()

        loaded = load_state(state_file)
        assert loaded["last_run"] == "2026-05-14T12:00:00"
        assert len(loaded["processed"]) == 1
        assert loaded["processed"][0]["md5"] == "abc123"

    def test_invalid_json_state(self, tmp_path):
        state_dir = tmp_path / "scrape"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "superindo_state.json"
        state_file.write_text("not valid json", encoding="utf-8")

        # Should raise JSON decode error
        try:
            load_state(state_file)
            assert False, "Should have raised"
        except json.JSONDecodeError:
            pass


class TestDuplicateDetection:
    def test_known_hash_detected(self):
        known_hashes = {"abc123", "def456"}
        assert "abc123" in known_hashes
        assert "xyz789" not in known_hashes

    def test_md5_consistency(self):
        data1 = b"hello world"
        data2 = b"hello world"
        data3 = b"different content"
        assert md5_hash(data1) == md5_hash(data2)
        assert md5_hash(data1) != md5_hash(data3)

    def test_duplicate_in_same_batch_filtered(self):
        """Simulate the dedup logic within a single run."""
        seen_this_run = set()
        entries = []
        urls = [
            ("https://example.com/a.jpg", "a.jpg"),
            ("https://example.com/a.jpg", "a.jpg"),  # duplicate URL
            ("https://example.com/b.jpg", "b.jpg"),
        ]
        for url, fname in urls:
            h = md5_hash(url.encode())
            if h in seen_this_run:
                continue
            seen_this_run.add(h)
            entries.append((url, h))
        assert len(entries) == 2


class TestImageValidation:
    def test_too_small_file(self):
        data = b"x" * 100  # 100 bytes
        assert len(data) < 50 * 1024

    def test_min_size_threshold(self):
        min_size = 50 * 1024
        assert len(b"x" * (50 * 1024 - 1)) < min_size
        assert len(b"x" * (50 * 1024)) >= min_size
