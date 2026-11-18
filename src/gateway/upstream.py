"""The seam between the gateway and a user's worker (Phase 3 plugs the reverse proxy in here).

The gate calls ``upstream.forward(request, identity)`` only for an authenticated request (active
session, two-factor done, no pending password change) whose path the gateway does not own.
``upstream_headers`` is the header contract the proxy must apply to every forwarded request.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Protocol

from src.http_runtime.wsgi_facade import LocalRequest, Response

# Hop-by-hop headers (RFC 9110 section 7.6.1) plus every header that carries a credential, a
# client-chosen address or gateway-internal state. Names listed in ``Connection`` are dropped too.
HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
                        "proxy-authorization", "proxy-authenticate"})
STRIPPED_REQUEST_HEADERS = HOP_BY_HOP | frozenset({
    "authorization", "x-api-token", "cookie", "x-csrf-token", "forwarded", "x-real-ip", "host", "origin", "referer",
    "content-length",
})
STRIPPED_PREFIXES = ("x-forwarded-", "tailscale-", "x-gateway-")


@dataclass(frozen=True)
class Identity:
    """The authenticated user a forwarded request belongs to.

    ``kind`` is the account kind (Phase 9). Only an identity whose kind is exactly ``"member"`` may ever be
    forwarded to a worker; the gate answers every other kind itself, and the proxy refuses it as a second layer."""

    user_id: int
    username: str
    display_name: str
    role: str
    kind: str = "member"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_member(self) -> bool:
        return self.kind == "member"


class Upstream(Protocol):
    def forward(self, req: LocalRequest, identity: Identity) -> Response: ...


class PlaceholderUpstream:
    """Answers in place of the planner until Phase 3 connects each user's worker."""

    def forward(self, req: LocalRequest, identity: Identity) -> Response:
        if req.path.startswith("/api/"):
            body = {"success": False, "gateway_placeholder": True,
                    "error": "The planner is not connected to this gateway yet."}
            return Response(json.dumps(body), status=503, content_type="application/json")
        html = ("<!doctype html><meta charset=utf-8><title>Retirement Planner</title>"
                "<p>Signed in. The planner is not connected to this gateway yet.</p>"
                "<p><a href=\"/gateway/account\">Your account</a></p>")
        return Response(html, status=503, content_type="text/html; charset=utf-8")


def upstream_headers(client_headers: Mapping[str, str], *, worker_port: int, worker_token: str,
                     body_length: int) -> dict[str, str]:
    """Headers for the request to the worker: client credentials and proxy headers removed, token injected.

    ``Host`` and (only when the client sent one) ``Origin`` are rewritten to the worker's exact
    loopback address, which the worker compares as strings. ``Content-Length`` is set from the
    re-framed body. The worker trusts the token, so the gateway's own CSRF and Origin checks must
    already have passed.
    """
    connection_named = {p.strip().lower() for p in str(client_headers.get("Connection", "") or "").split(",") if p.strip()}
    out: dict[str, str] = {}
    had_origin = False
    for key, value in client_headers.items():
        k = str(key).lower()
        if k == "origin":
            had_origin = True
        if k in STRIPPED_REQUEST_HEADERS or k in connection_named or k.startswith(STRIPPED_PREFIXES):
            continue
        out[str(key)] = str(value)
    address = f"127.0.0.1:{int(worker_port)}"
    out["Host"] = address
    if had_origin:
        out["Origin"] = f"http://{address}"
    out["X-API-Token"] = worker_token
    out["Content-Length"] = str(int(body_length))
    return out
