"""Integration-style tests for GitHub API helpers using a local mock server."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import parse_qs, urlparse
import json
import unittest

from pnp import github


class _Handler(BaseHTTPRequestHandler):
    release_payload: dict[str, object] | None = None
    upload_payload: bytes | None = None
    upload_name: str | None = None

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""

        if parsed.path.endswith("/releases"):
            _Handler.release_payload = json.loads(body.decode("utf-8"))
            data = json.dumps({"id": 42}).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if "/assets" in parsed.path:
            query = parse_qs(parsed.query)
            _Handler.upload_name = query.get("name", [None])[0]
            _Handler.upload_payload = body
            data = json.dumps({"state": "uploaded"}).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


class GithubIntegrationTests(unittest.TestCase):
    def test_create_release_and_upload_asset(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        host, port = server.server_address
        base = f"http://{host}:{port}"
        t = Thread(target=server.serve_forever, daemon=True)
        t.start()
        old_api = github.API
        old_uploads = github.UPLOADS_API
        github.API = base
        github.UPLOADS_API = base
        try:
            resp = github.create_release(
                token="x",
                repo="owner/repo",
                tag="v1.0.0",
                name="v1.0.0",
                body="notes",
            )
            self.assertEqual(resp["id"], 42)
            self.assertEqual(_Handler.release_payload, {
                "tag_name": "v1.0.0",
                "name": "v1.0.0",
                "body": "notes",
                "draft": False,
                "prerelease": False,
            })

            with TemporaryDirectory() as tmp:
                f = Path(tmp) / "asset.bin"
                f.write_bytes(b"abc")
                uploaded = github.upload_asset(
                    token="x",
                    repo="owner/repo",
                    release_id=42,
                    filepath=str(f),
                )
            self.assertEqual(uploaded["state"], "uploaded")
            self.assertEqual(_Handler.upload_name, "asset.bin")
            self.assertEqual(_Handler.upload_payload, b"abc")
        finally:
            github.API = old_api
            github.UPLOADS_API = old_uploads
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
