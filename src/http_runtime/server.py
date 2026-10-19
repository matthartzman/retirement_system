from __future__ import annotations

"""Stdlib local HTTP server adapter for the retirement dashboard."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .host_guard import assert_safe_to_bind, body_too_large
from .wsgi_facade import Response


class _Handler(BaseHTTPRequestHandler):
    server_version = "RetirementStdlibHTTP/1.0"

    def _handle(self) -> None:
        try:
            length = max(0, int(self.headers.get("Content-Length") or 0))
        except ValueError:
            length = -1
        if length < 0 or body_too_large(length):
            self.send_response(413 if length >= 0 else 400)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            return
        body = self.rfile.read(length) if length else b""
        headers = {k: v for k, v in self.headers.items()}
        app = getattr(self.server, "retirement_app")
        response: Response = app.handle_http(self.command, self.path, headers, body, self.client_address[0] if self.client_address else "127.0.0.1")
        payload = response.get_data()
        self.send_response(int(response.status_code))
        sent_length = False
        for key, value in response.headers.items():
            if str(key).lower() == "content-length":
                sent_length = True
            self.send_header(str(key), str(value))
        if not sent_length:
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command.upper() != "HEAD":
            self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib API
        self._handle()

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - console diagnostics only
        return


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], app: Any) -> None:
        super().__init__(server_address, _Handler)
        self.retirement_app = app


def _configured_token() -> str:
    from ..runtime_config import load_runtime_config  # noqa: PLC0415

    return str(load_runtime_config().server_api_token or "")


def run_local_server(app: Any, host: str = "127.0.0.1", port: int = 5050, debug: bool = False) -> None:  # noqa: ARG001
    assert_safe_to_bind(host, _configured_token())
    server = LocalHTTPServer((host, int(port)), app)
    print(f"Retirement stdlib HTTP runtime listening on http://{host}:{int(port)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
