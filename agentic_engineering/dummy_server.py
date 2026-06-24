"""Self-contained dummy HTTP server for supermarket scraper fixtures."""

import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = 18080

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PAGES_DIR = PROJECT_ROOT / "agentic_engineering" / "pages"
IMAGES_DIR = PROJECT_ROOT / "agentic_engineering" / "images"
LOTTE_IMAGES_DIR = IMAGES_DIR / "lotte"
SUPERINDO_IMAGES_DIR = IMAGES_DIR / "superindo"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dummy_server")


class DummyHandler(BaseHTTPRequestHandler):
    """Serve static HTML and image fixtures for scraper integration tests."""

    def log_message(self, format, *args):
        logger.info(format % args)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_text(self, status, body):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path):
        if not path.is_file():
            self._send_text(404, "Not found")
            return

        content_type, _ = mimetypes.guess_type(str(path))
        if content_type is None:
            content_type = "application/octet-stream"

        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path

        if path == "/lotte/all-promo-mart":
            self._send_file(PAGES_DIR / "lotte_all_promo_mart.html")
        elif path == "/superindo/promosi/katalog-super-hemat/":
            self._send_file(PAGES_DIR / "superindo_katalog.html")
        elif path == "/superindo/promosi/promo-koran/":
            self._send_file(PAGES_DIR / "superindo_koran.html")
        elif path.startswith("/lotte/promo/"):
            filename = Path(path).name
            self._send_file(LOTTE_IMAGES_DIR / filename)
        elif path.startswith("/superindo/promo/"):
            filename = Path(path).name
            self._send_file(SUPERINDO_IMAGES_DIR / filename)
        else:
            self._send_text(404, "Not found")


def main():
    server = HTTPServer((HOST, PORT), DummyHandler)
    print(f"Dummy supermarket server running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
