"""Lokaler Webserver für die Anzeige im Kiosk-Browser.

Endpunkte (nur lesend, daher keine Sessions/CSRF nötig):
  GET /              -> index.html
  GET /assets/...    -> statische Dateien
  GET /api/state     -> aktueller Zustand als JSON
  GET /api/events    -> Server-Sent Events bei jeder Änderung
  GET /api/cover     -> aktuelles Cover-Bild
  GET /healthz       -> einfacher Gesundheitscheck
Standardmäßig nur an 127.0.0.1 gebunden.
"""

import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .logger import get_logger
from .ratelimit import KeyedRateLimiter

log = get_logger("web")

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                                "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
                                "form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
}

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".json": "application/json",
}
LONG_CACHE = {".woff2", ".woff", ".ttf", ".png", ".jpg", ".jpeg", ".svg", ".ico"}


class InfoHandler(BaseHTTPRequestHandler):
    server_version = "InfoDisplay"
    sys_version = ""

    # ------------------------------------------------------------ Hilfen
    def log_message(self, fmt, *args):
        log.debug("%s %s", self.client_address[0], fmt % args)

    def _headers(self, status, content_type, length=None, cache="no-cache", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _send_bytes(self, status, body, content_type, cache="no-cache"):
        self._headers(status, content_type, len(body), cache)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8", "no-store")

    def _send_error_page(self, status):
        """Einheitliche Fehlerseiten im Projektdesign (404.html / 500.html)."""
        page = "404.html" if status == 404 else "500.html"
        try:
            with open(os.path.join(self.server.web_root, page), "rb") as fh:
                body = fh.read()
        except OSError:
            body = f"<!doctype html><title>Fehler {status}</title><h1>Fehler {status}</h1>".encode()
        self._send_bytes(status, body, STATIC_TYPES[".html"], "no-store")

    # ------------------------------------------------------------ Routing
    def do_GET(self):
        try:
            if not self.server.limiter.allow(self.client_address[0]):
                self._send_json(429, {"error": "Zu viele Anfragen"})
                return
            url = urlsplit(self.path)
            route = {
                "/api/state": self._api_state,
                "/api/events": self._api_events,
                "/api/cover": lambda: self._api_cover(url.query),
                "/healthz": lambda: self._send_json(200, {"status": "ok"}),
            }.get(url.path)
            if route:
                route()
            else:
                self._static(url.path)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            log.exception("Fehler bei %s", self.path)
            try:
                self._send_error_page(500)
            except OSError:
                pass

    do_HEAD = do_GET

    def _method_not_allowed(self):
        self._send_json(405, {"error": "Methode nicht erlaubt"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed

    # ------------------------------------------------------------ Endpunkte
    def _api_state(self):
        self._send_json(200, self.server.state.snapshot())

    def _api_cover(self, query):
        cover = self.server.state.get_cover()
        wanted = parse_qs(query).get("id", [""])[0]
        if cover is None or (wanted and wanted != cover[0]):
            self._send_error_page(404)
            return
        self._send_bytes(200, cover[2], cover[1], "public, max-age=86400")

    def _api_events(self):
        if not self.server.sse_slots.acquire(blocking=False):
            self._send_json(503, {"error": "Zu viele offene Verbindungen"})
            return
        try:
            self._headers(200, "text/event-stream; charset=utf-8", cache="no-store",
                          extra={"X-Accel-Buffering": "no"})
            version = -1
            while not self.server.stopping.is_set():
                new_version = self.server.state.wait_for_change(version, 15)
                if new_version != version:
                    version = new_version
                    payload = json.dumps(self.server.state.snapshot(), ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(f"event: state\ndata: {payload}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        finally:
            self.server.sse_slots.release()

    def _static(self, path):
        rel = unquote(path).lstrip("/") or "index.html"
        root = self.server.web_root
        full = os.path.realpath(os.path.join(root, rel))
        ext = os.path.splitext(full)[1].lower()
        if (not full.startswith(root + os.sep) or ext not in STATIC_TYPES or not os.path.isfile(full)
                or os.path.basename(full).startswith(".")):
            self._send_error_page(404)
            return
        with open(full, "rb") as fh:
            body = fh.read()
        cache = "public, max-age=86400" if ext in LONG_CACHE else "no-cache"
        self._send_bytes(200, body, STATIC_TYPES[ext], cache)


class InfoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, cfg, state):
        super().__init__((cfg.web_host, cfg.web_port), InfoHandler)
        self.state = state
        self.web_root = cfg.web_root
        self.limiter = KeyedRateLimiter(cfg.http_rate_per_sec, cfg.http_burst)
        self.sse_slots = threading.BoundedSemaphore(max(1, cfg.max_sse_clients))
        self.stopping = threading.Event()

    def shutdown(self):
        self.stopping.set()
        self.state.wake_all()
        super().shutdown()


mimetypes.init()
