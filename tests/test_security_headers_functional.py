"""SEC-07 / F-10 / S-02: CSP, nosniff, no framing and no referrer on the planner server, the Financial Insights
listeners and the gateway proxy; `no-store` on the remote Financial Insights listener."""
from __future__ import annotations

import re

import pytest

from src.gateway.proxy import WorkerProxy
from src.gateway.supervisor import Endpoint
from src.http_runtime import security_headers
from tests.test_trends_access_gate_functional import Rig

REQUIRED = ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy")


def _csp(headers) -> dict[str, str]:
    return {d.split()[0]: d for d in (p.strip() for p in headers.get("Content-Security-Policy").split(";")) if d}


def _assert_base(headers):
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    csp = _csp(headers)
    assert csp["frame-ancestors"] == "frame-ancestors 'none'"
    assert csp["base-uri"] == "base-uri 'none'"
    assert csp["object-src"] == "object-src 'none'"
    assert csp["default-src"] == "default-src 'self'"


def test_inline_script_hashes_cover_inline_blocks_only():
    html = '<script src="a.js"></script><script type="module">import x from "./x.js";</script><script> </script>'
    assert len(security_headers.inline_script_hashes(html)) == 1
    csp = security_headers.csp_for_html(html)
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_proxy_adds_headers_but_never_overrides_the_worker():
    ep = Endpoint(user_id=1, port=5100, pid=1, token="t")
    bare = WorkerProxy._response(200, [("Content-Type", "text/html")], b"<p>x</p>", ep)
    for name in REQUIRED:
        assert bare.headers.get(name), name
    _assert_base(bare.headers)
    own = WorkerProxy._response(200, [("Content-Security-Policy", "default-src 'none'"), ("X-Frame-Options", "SAMEORIGIN")], b"", ep)
    assert own.headers.get("Content-Security-Policy") == "default-src 'none'"
    assert own.headers.get("X-Frame-Options") == "SAMEORIGIN"


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


@pytest.mark.parametrize("path", ["/", "/signin", "/api/ping"])
def test_financial_insights_remote_listener_headers_and_no_store(rig, path):
    resp = rig.call(rig.remote, "GET", path)
    _assert_base(resp.headers)
    assert resp.headers.get("Cache-Control") == "no-store"


def test_financial_insights_pages_admit_only_hashed_inline_scripts(rig):
    rig.add("ann", money_view="dollars")
    _, token = rig.signin()
    for path in ("/", "/signin"):
        resp = rig.call(rig.remote, "GET", path, cookie=token)
        script_src = _csp(resp.headers)["script-src"]
        assert "'unsafe-inline'" not in script_src, path
        body = resp.get_data(as_text=True)
        for token in security_headers.inline_script_hashes(body):
            assert token in script_src, path
        assert re.search(r"<script(?![^>]*src)", body), path  # the page really has an inline block the hash must cover


def test_financial_insights_owner_listener_is_not_forced_no_store(rig):
    resp = rig.call(rig.local, "GET", "/signin")
    _assert_base(resp.headers)


def test_planner_server_responses_carry_the_headers():
    from src.server import app_core

    resp = app_core.app.handle_http("GET", "/", {"Host": "127.0.0.1:5050"})
    if resp.status_code in (301, 302):  # the root redirects to the planner page
        resp = app_core.app.handle_http("GET", resp.headers["Location"], {"Host": "127.0.0.1:5050"})
    assert resp.status_code == 200 and resp.mimetype == "text/html"
    _assert_base(resp.headers)
    assert "'unsafe-inline'" in _csp(resp.headers)["script-src"]  # the page uses inline onclick handlers


def test_planner_server_unknown_route_still_gets_the_headers():
    from src.server import app_core

    resp = app_core.app.handle_http("GET", "/no-such-route", {"Host": "127.0.0.1:5050"})
    assert resp.status_code == 404
    _assert_base(resp.headers)
