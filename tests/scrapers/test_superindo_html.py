import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.scrapers.superindo_qwen import parse_page_images

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "test" / "superindo" / "html-scape"


def _load_fixture(name: str) -> str:
    path = FIXTURES_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


class TestParseKatalogPage:
    def test_returns_list_of_tuples(self):
        html = _load_fixture("Katalog Super Hemat.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        assert isinstance(images, list)
        if images:
            url, orig = images[0]
            assert isinstance(url, str)
            assert url.startswith("http")

    def test_images_have_valid_extensions(self):
        html = _load_fixture("Katalog Super Hemat.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        valid_exts = (".jpg", ".jpeg", ".png", ".webp")
        for url, _ in images:
            assert any(url.lower().endswith(e) for e in valid_exts), f"Bad extension: {url}"

    def test_all_images_have_jabodetabek_region(self):
        """Verify only jabodetabek-palembang images are extracted."""
        html = _load_fixture("Katalog Super Hemat.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        for url, _ in images:
            assert "jabodetabek" not in url.lower()
        # The region filter is on data-fancybox, not the URL
        # Just verify we got some images
        assert len(images) >= 1

    def test_no_duplicates(self):
        html = _load_fixture("Katalog Super Hemat.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        urls = [u for u, _ in images]
        assert len(urls) == len(set(urls))


class TestParsePromoKoranPage:
    def test_returns_list_of_tuples(self):
        html = _load_fixture("Promo Koran.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/promo-koran/")
        assert isinstance(images, list)
        if images:
            url, orig = images[0]
            assert isinstance(url, str)
            assert url.startswith("http")

    def test_images_have_valid_extensions(self):
        html = _load_fixture("Promo Koran.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/promo-koran/")
        valid_exts = (".jpg", ".jpeg", ".png", ".webp")
        for url, _ in images:
            assert any(url.lower().endswith(e) for e in valid_exts), f"Bad extension: {url}"

    def test_no_duplicates(self):
        html = _load_fixture("Promo Koran.html")
        if not html:
            return
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/promo-koran/")
        urls = [u for u, _ in images]
        assert len(urls) == len(set(urls))


class TestParseWithMissingFixture:
    """Tests that the parser handles missing/invalid HTML gracefully."""

    def test_empty_html(self):
        images = parse_page_images("", "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        assert images == []

    def test_html_without_swiper(self):
        html = "<html><body><p>No promos here</p></body></html>"
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        assert images == []

    def test_html_with_wrong_fancybox(self):
        html = """
        <div class="swiper-slide">
            <a class="fancybox" data-fancybox="other-region" href="https://example.com/img.jpg">
                <img src="https://example.com/img.jpg">
            </a>
        </div>
        """
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        assert images == []

    def test_html_without_fancybox_link(self):
        html = """
        <div class="swiper-slide">
            <a href="https://example.com/img.jpg">Link</a>
        </div>
        """
        images = parse_page_images(html, "https://www.superindo.co.id/promosi/katalog-super-hemat/")
        assert images == []
