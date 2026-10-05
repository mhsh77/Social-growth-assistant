"""Local capture server: receives what the browser extension forwards.

Binds to 127.0.0.1 only. It never contacts X; it just parses JSON your browser already
received while you browsed, and caches the minimum fields in SQLite.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import Sources
from .parser import extract_posts
from .sources import source_for_page
from .store import Store

MAX_BODY_BYTES = 20 * 1024 * 1024
_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


class CaptureServer:
    def __init__(
        self,
        store: Store,
        sources: Sources,
        port: int = 8765,
        raw_dir: Path | None = None,
    ):
        self.store = store
        self.sources = sources
        self.raw_dir = raw_dir  # debug only: save raw payloads so parsing can be fixed
        self.received = 0
        self.accepted = 0
        self._lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(self))
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def ingest(self, body: dict) -> dict:
        page_url = str(body.get("pageUrl", ""))
        label = source_for_page(page_url, self.sources)
        if label is None:
            return {"accepted": 0, "ignored": "not a search or List page"}
        payload = body.get("payload")
        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}-{body.get('operation', 'unknown')}.json"
            (self.raw_dir / name).write_text(json.dumps(body), encoding="utf-8")
        posts = [p.model_copy(update={"sources": [label]}) for p in extract_posts(payload)]
        with self._lock:
            added = self.store.add_candidates(posts)
            self.received += len(posts)
            self.accepted += added
            total = self.store.candidate_count()
        return {"accepted": added, "seen": len(posts), "total": total}


def _make_handler(server: CaptureServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _reply(self, status: int, data: dict) -> None:
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self) -> bool:
            # Defends against DNS rebinding: only accept requests addressed to localhost.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in _ALLOWED_HOSTS

        def do_GET(self):
            if not self._host_ok():
                return self._reply(403, {"error": "bad host"})
            if self.path == "/health":
                return self._reply(200, {"ok": True, "total": server.store.candidate_count()})
            return self._reply(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._reply(403, {"error": "bad host"})
            if self.path != "/ingest":
                return self._reply(404, {"error": "not found"})
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(_EXTENSION_ORIGINS):
                return self._reply(403, {"error": "only the extension may post here"})
            # Requiring JSON forces a CORS preflight for ordinary web pages, which we never
            # approve, so random sites can't push data into your cache.
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._reply(415, {"error": "expected application/json"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                return self._reply(413, {"error": "bad body size"})
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return self._reply(400, {"error": "invalid JSON"})
            if not isinstance(body, dict):
                return self._reply(400, {"error": "expected an object"})
            return self._reply(200, server.ingest(body))

    return Handler
