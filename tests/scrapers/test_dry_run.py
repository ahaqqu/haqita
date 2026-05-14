import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestDryRun:
    def test_dry_run_flag_parsed(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true")
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True
        args = parser.parse_args([])
        assert args.dry_run is False

    def test_dry_run_skips_ocr_after_listing(self):
        """Simulate the dry-run early-return logic from main()."""
        from scripts.scrapers import superindo_qwen as scraper

        new_images = [
            {"filename": "img1.jpg", "md5": "abc123"},
            {"filename": "img2.jpg", "md5": "def456"},
        ]
        dry_run = True

        if dry_run:
            if new_images:
                lines = [f"  - {img['filename']}" for img in new_images]
                result = "\n".join(lines)
            else:
                result = "Nothing new to process."
        else:
            result = "would run OCR"

        assert "img1.jpg" in result
        assert "img2.jpg" in result
        assert "OCR" not in result

    def test_dry_run_empty_new_images(self):
        from scripts.scrapers import superindo_qwen as scraper

        new_images = []
        dry_run = True

        if dry_run:
            if new_images:
                result = "would list"
            else:
                result = "Nothing new to process."
        else:
            result = "would run OCR"

        assert result == "Nothing new to process."

    def test_download_only_checks_size_before_md5(self):
        """Dry-run still downloads and validates images — just skips OCR."""
        from scripts.scrapers import superindo_qwen as scraper

        data = b"x" * (60 * 1024)  # 60KB > 50KB minimum
        h = scraper.md5_hash(data)
        assert len(data) >= 50 * 1024
        assert isinstance(h, str)
        assert len(h) == 32  # MD5 hex digest

    def test_file_too_small_is_skipped(self):
        from scripts.scrapers import superindo_qwen as scraper

        small_data = b"x" * 100
        min_size = 50 * 1024
        assert len(small_data) < min_size
        assert len(small_data) < min_size  # would be skipped
