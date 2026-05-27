import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.gemini_client import QuotaExhaustedError
from scripts.ocr.run_ocr import run_ocr


@pytest.fixture
def cfg():
    return {
        'store': 'lotte',
        'ocr': {'provider': 'gemini', 'gemini': {'model': 'test-model', 'api_key': 'test-key'}},
    }


class TestRunOcrQuotaExhausted:
    def test_breaks_on_quota_exhausted(self, cfg, tmp_path):
        scrape_dir = tmp_path / "scrape"
        output_dir = tmp_path / "ocr"
        scrape_dir.mkdir()

        for name in ["img1.jpg", "img2.jpg", "img3.jpg"]:
            (scrape_dir / name).write_bytes(b"fake")

        processed_images = []

        def mock_preprocess(path, cfg):
            return path

        def mock_extract(path, cfg):
            processed_images.append(Path(path).name)
            if Path(path).name == "img2.jpg":
                raise QuotaExhaustedError("Daily quota exhausted")
            return [{"name": "Product", "price": 5000}]

        with patch('scripts.ocr.run_ocr.preprocess_for_ocr', side_effect=mock_preprocess), \
             patch('scripts.ocr.run_ocr.extract_products', side_effect=mock_extract), \
             patch('scripts.ocr.run_ocr.save_ocr_state'), \
             patch('scripts.ocr.run_ocr.load_ocr_state', return_value={'processed': [], 'last_run': None}):
            with pytest.raises(QuotaExhaustedError):
                run_ocr(cfg, scrape_dir, output_dir)

        assert processed_images == ["img1.jpg", "img2.jpg"]
        assert "img3.jpg" not in processed_images

    def test_saves_state_before_raising(self, cfg, tmp_path):
        scrape_dir = tmp_path / "scrape"
        output_dir = tmp_path / "ocr"
        scrape_dir.mkdir()

        (scrape_dir / "img1.jpg").write_bytes(b"fake1")
        (scrape_dir / "img2.jpg").write_bytes(b"fake2")

        saved_state = {}

        def mock_preprocess(path, cfg):
            return path

        def mock_extract(path, cfg):
            if Path(path).name == "img2.jpg":
                raise QuotaExhaustedError("Daily quota exhausted")
            return [{"name": "Product", "price": 5000}]

        def mock_save_state(store, state):
            saved_state.update(state)

        with patch('scripts.ocr.run_ocr.preprocess_for_ocr', side_effect=mock_preprocess), \
             patch('scripts.ocr.run_ocr.extract_products', side_effect=mock_extract), \
             patch('scripts.ocr.run_ocr.save_ocr_state', side_effect=mock_save_state), \
             patch('scripts.ocr.run_ocr.load_ocr_state', return_value={'processed': [], 'last_run': None}):
            with pytest.raises(QuotaExhaustedError):
                run_ocr(cfg, scrape_dir, output_dir)

        assert "img1.jpg" in saved_state.get('processed', [])

    def test_quota_exhausted_not_in_rejected(self, cfg, tmp_path):
        scrape_dir = tmp_path / "scrape"
        output_dir = tmp_path / "ocr"
        scrape_dir.mkdir()

        (scrape_dir / "img1.jpg").write_bytes(b"fake")

        def mock_preprocess(path, cfg):
            return path

        def mock_extract(path, cfg):
            raise QuotaExhaustedError("Daily quota exhausted")

        with patch('scripts.ocr.run_ocr.preprocess_for_ocr', side_effect=mock_preprocess), \
             patch('scripts.ocr.run_ocr.extract_products', side_effect=mock_extract), \
             patch('scripts.ocr.run_ocr.save_ocr_state'), \
             patch('scripts.ocr.run_ocr.load_ocr_state', return_value={'processed': [], 'last_run': None}):
            with pytest.raises(QuotaExhaustedError):
                run_ocr(cfg, scrape_dir, output_dir)

        output_file = list(output_dir.glob("*.json"))
        assert len(output_file) == 1
        data = json.loads(output_file[0].read_text(encoding="utf-8"))
        assert data["rejected"] == []
        assert "Daily quota exhausted" in data["quota_exhausted"]

    def test_skipped_count_logged(self, cfg, tmp_path, capsys):
        scrape_dir = tmp_path / "scrape"
        output_dir = tmp_path / "ocr"
        scrape_dir.mkdir()

        for name in ["img1.jpg", "img2.jpg", "img3.jpg", "img4.jpg"]:
            (scrape_dir / name).write_bytes(b"fake")

        def mock_preprocess(path, cfg):
            return path

        def mock_extract(path, cfg):
            if Path(path).name == "img2.jpg":
                raise QuotaExhaustedError("Daily quota exhausted")
            return [{"name": "Product", "price": 5000}]

        with patch('scripts.ocr.run_ocr.preprocess_for_ocr', side_effect=mock_preprocess), \
             patch('scripts.ocr.run_ocr.extract_products', side_effect=mock_extract), \
             patch('scripts.ocr.run_ocr.save_ocr_state'), \
             patch('scripts.ocr.run_ocr.load_ocr_state', return_value={'processed': [], 'last_run': None}):
            with pytest.raises(QuotaExhaustedError):
                run_ocr(cfg, scrape_dir, output_dir)

        captured = capsys.readouterr()
        assert "3 image(s) skipped due to quota exhaustion" in captured.out
