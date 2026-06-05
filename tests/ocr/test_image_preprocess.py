import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.image_preprocess import split_image_halves


def _create_test_image(width: int, height: int, path: str):
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    img.save(path, "JPEG", quality=85)


def _cleanup(path: str):
    try:
        Path(path).unlink(missing_ok=True)
    except PermissionError:
        pass


class TestSplitImageHalves:
    def test_split_creates_two_files(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            _create_test_image(800, 600, path)
            top, bot = split_image_halves(path)
            assert Path(top).exists()
            assert Path(bot).exists()
            from PIL import Image
            with Image.open(top) as top_img, Image.open(bot) as bot_img:
                assert top_img.size == (800, 300)
                assert bot_img.size == (800, 300)
            _cleanup(top)
            _cleanup(bot)
        finally:
            _cleanup(path)

    def test_odd_height_split(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            _create_test_image(800, 601, path)
            top, bot = split_image_halves(path)
            from PIL import Image
            with Image.open(top) as top_img, Image.open(bot) as bot_img:
                assert top_img.size == (800, 300)
                assert bot_img.size == (800, 301)
            _cleanup(top)
            _cleanup(bot)
        finally:
            _cleanup(path)

    def test_minimum_height_split(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            _create_test_image(100, 2, path)
            top, bot = split_image_halves(path)
            from PIL import Image
            with Image.open(top) as top_img, Image.open(bot) as bot_img:
                assert top_img.size == (100, 1)
                assert bot_img.size == (100, 1)
            _cleanup(top)
            _cleanup(bot)
        finally:
            _cleanup(path)
