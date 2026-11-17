"""The Admin app's trust boundary.

There is no sign-in: the only protection is that a request provably came from this PC's own browser.
Every request must pass all of these, in this order, before any route runs:

1. The peer address is loopback (defence in depth; the server also binds loopback only).
2. The ``Host`` header names loopback (stops DNS rebinding: a hostile page cannot reach us under its own name).
3. No proxy or Tailscale header is present (Funnel delivers internet traffic from 127.0.0.1, so a request
   carrying one of these did not come from this PC).
4. If the browser sent ``Origin`` it must be exactly this server (``http://<Host>``); ``Sec-Fetch-Site``, if sent,
   must say same-origin or none.
5. A write (anything but GET/HEAD) must carry a JSON ``Content-Type``, which a cross-site HTML form cannot send.
"""
from __future__ import annotations

import json
import subprocess

from src.access_core import has_proxy_headers, is_loopback_host, tailscale_serves_port
from src.http_runtime.wsgi_facade import Response, request

LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})
EXTRA_PROXY_HEADERS = frozenset({"forwarded", "x-real-ip", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-port",
                                 "x-original-forwarded-for", "via", "cf-connecting-ip", "true-client-ip"})
SAFE_METHODS = frozenset({"GET", "HEAD"})
MAX_BODY_BYTES = 64 * 1024
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


def _refuse(status: int, message: str) -> Response:
    return Response(json.dumps({"success": False, "error": message}), status=status, content_type="application/json")


def has_forwarding_headers(headers) -> bool:
    """Any proxy / Funnel / Tailscale header (a superset of the Financial Insights check)."""
    return has_proxy_headers(headers) or any(str(k).lower() in EXTRA_PROXY_HEADERS for k in headers)


def check_request() -> Response | None:
    """The ``before_request`` gate: ``None`` lets the request through, otherwise the refusal."""
    if str(request.remote_addr or "") not in LOOPBACK_PEERS:
        return _refuse(403, "the Admin app answers this computer only")
    host = str(request.headers.get("Host", "") or "")
    if not is_loopback_host(host):
        return _refuse(421, "misdirected request")
    if has_forwarding_headers(request.headers):
        return _refuse(403, "proxied requests are not allowed here")
    origin = str(request.headers.get("Origin", "") or "")
    if origin and origin != f"http://{host}":
        return _refuse(403, "cross-origin requests are not allowed")
    if str(request.headers.get("Sec-Fetch-Site", "") or "").lower() not in {"", "same-origin", "none"}:
        return _refuse(403, "cross-origin requests are not allowed")
    if request.method not in SAFE_METHODS and request.method != "OPTIONS":
        if "application/json" not in str(request.headers.get("Content-Type", "") or "").lower():
            return _refuse(415, "send JSON")
        if len(request.body or b"") > MAX_BODY_BYTES:
            return _refuse(413, "request too large")
    return None


def add_security_headers(resp: Response) -> Response:
    for name, value in SECURITY_HEADERS.items():
        resp.headers[name] = value
    return resp


def check_funnel_target(port: int, run=subprocess.run) -> str | None:
    """A message when Tailscale serves or funnels the Admin port (it has no sign-in), else None.

    Skipped (None) when the ``tailscale`` command is unavailable or its output is unreadable.
    """
    if tailscale_serves_port(port, run=run):
        return (f"Tailscale is configured to serve port {port}, which is the Admin app and has no sign-in. "
                "Run 'tailscale funnel reset' (or remove that serve entry) and try again.")
    return None
