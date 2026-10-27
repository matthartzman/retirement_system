"""Which listener a request arrived on, and the checks that keep the two apart.

Tailscale Funnel delivers every internet request from 127.0.0.1, so the client address cannot
tell the owner from a guest. The port is the trust boundary: 5057 (local) and 5058 (remote) each
get their own ``ListenerApp`` wrapper that tags requests, and nothing infers it any other way.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Literal

from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest, request

Listener = Literal["local", "remote"]


class ListenerApp:
    """Wraps the shared app so each request carries ``environ["listener"]``."""

    def __init__(self, app: Any, listener: Listener) -> None:
        self.app = app
        self.listener = listener

    def handle_http(self, method: str, target: str, headers: dict | None = None, body: bytes = b"", remote_addr: str = "127.0.0.1"):
        req = LocalRequest(method, target, HeaderMap(headers or {}), body, remote_addr=remote_addr, environ={"listener": self.listener})
        return self.app.dispatch_request(req)


def current_listener() -> str:
    """"remote" only when the request came through the remote wrapper; a bare app is local."""
    return str(request.environ.get("listener") or "local")


def has_proxy_headers(headers: dict) -> bool:
    for key in headers:
        k = str(key).lower()
        if k == "x-forwarded-for" or k.startswith("tailscale-"):
            return True
    return False


def is_loopback_host(host_header: str) -> bool:
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        name = host.split("]", 1)[0] + "]"
    else:
        name = host.rsplit(":", 1)[0] if ":" in host else host
    return name in {"127.0.0.1", "localhost", "[::1]"}


def check_funnel_target(local_port: int = 5057, run=subprocess.run) -> str | None:
    """A message when Tailscale serves or funnels the local port (a misconfiguration), else None.

    Skipped (None) when the ``tailscale`` command is unavailable or its output is unreadable.
    """
    try:
        out = run(["tailscale", "serve", "status", "--json"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    text = getattr(out, "stdout", "") or ""
    try:
        json.loads(text)
    except ValueError:
        return None
    if re.search(rf"[:/]{local_port}\b", text):
        return (f"Tailscale is configured to serve port {local_port}, which has no sign-in. "
                "Run 'tailscale funnel reset' and point Funnel at the remote port only.")
    return None
