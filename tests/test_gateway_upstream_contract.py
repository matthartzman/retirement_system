"""The header contract Phase 3's proxy must apply between the gateway and a user's worker."""
from __future__ import annotations

from src.gateway.upstream import STRIPPED_REQUEST_HEADERS, Identity, upstream_headers

CLIENT = {
    "Host": "node.example.ts.net:8443",
    "Origin": "https://node.example.ts.net:8443",
    "Referer": "https://node.example.ts.net:8443/static/dashboard.html",
    "Cookie": "__Host-rp_session=abc",
    "Authorization": "Bearer stolen",
    "X-API-Token": "guess",
    "X-CSRF-Token": "csrf",
    "X-Forwarded-For": "203.0.113.5",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": "node.example.ts.net",
    "Forwarded": "for=203.0.113.5",
    "X-Real-IP": "203.0.113.5",
    "Tailscale-User-Login": "someone",
    "Connection": "keep-alive, X-Custom-Hop",
    "X-Custom-Hop": "1",
    "Keep-Alive": "timeout=5",
    "Transfer-Encoding": "chunked",
    "Content-Length": "999",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Gateway-User-Id": "1",
}


def test_strips_credentials_proxy_and_hop_headers_and_injects_the_worker_token():
    out = upstream_headers(CLIENT, worker_port=50123, worker_token="tok-123", body_length=17)
    lower = {k.lower(): v for k, v in out.items()}
    for name in ["cookie", "authorization", "x-csrf-token", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host",
                 "forwarded", "x-real-ip", "tailscale-user-login", "connection", "keep-alive", "transfer-encoding",
                 "x-custom-hop", "x-gateway-user-id", "referer"]:
        assert name not in lower, name
    assert lower["x-api-token"] == "tok-123"
    assert lower["host"] == "127.0.0.1:50123"
    assert lower["origin"] == "http://127.0.0.1:50123"
    assert lower["content-length"] == "17"
    assert lower["content-type"] == "application/json" and lower["accept"] == "application/json"


def test_origin_is_only_added_when_the_client_sent_one():
    out = upstream_headers({"Host": "x", "Accept": "*/*"}, worker_port=1, worker_token="t", body_length=0)
    assert "origin" not in {k.lower() for k in out}
    assert {k.lower() for k in out} >= {"host", "x-api-token"}


def test_stripped_list_names_the_documented_headers():
    for name in ["authorization", "x-api-token", "cookie", "x-csrf-token", "forwarded", "x-real-ip"]:
        assert name in STRIPPED_REQUEST_HEADERS


def test_identity_is_immutable():
    ident = Identity(1, "ann", "Ann", "user")
    try:
        ident.role = "admin"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Identity must be frozen")
    assert ident.is_admin is False and Identity(2, "r", "R", "admin").is_admin is True
