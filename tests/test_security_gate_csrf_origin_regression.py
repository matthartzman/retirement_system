"""Finding ARC-001 (system review 2026-09-25, Wave 1 item WI-101):
_security_gate issued an X-CSRF-Token (see security_audit._csrf_token_for_
current_request and base_routes.py's login/session endpoints) but never
checked it, and had no Origin/Referer/Host allow-list at all -- a plain
auto-submitting cross-site form (no JavaScript, no CORS preflight needed)
could POST/PUT/DELETE any non-GET route and overwrite plan data, exfiltrate a
full DB copy, or swap in an attacker-controlled database.

This pins the fix: a request naming a foreign Origin/Referer is rejected
outright; a same-origin (or header-less, non-browser) request additionally
needs a valid CSRF token once it presents Origin/Referer evidence at all;
and a request carrying its own bearer-style credential is exempt from the
token check (it is not cookie/browser-auto-attached, so is not a CSRF
target). Mirrors tests/test_trends_reporter_origin_check_regression.py's
existing pattern for the sibling app.
"""
from __future__ import annotations

from src.server import create_app
from src.server.security_audit import _csrf_token_for_current_request


def _client():
    return create_app().test_client()


def test_foreign_origin_post_is_rejected_even_without_a_token():
    resp = _client().post(
        "/api/plan-data/client_data.csv",
        data="a,b,c",
        content_type="text/plain",
        headers={"Host": "127.0.0.1:5050", "Origin": "http://evil.example"},
    )
    assert resp.status_code == 403


def test_same_origin_post_with_no_content_type_and_no_token_is_rejected():
    resp = _client().post(
        "/api/plan-data/client_data.csv",
        data="a,b,c",
        headers={"Host": "127.0.0.1:5050", "Origin": "http://127.0.0.1:5050"},
    )
    assert resp.status_code == 403


def test_same_origin_post_with_a_valid_token_is_not_csrf_rejected():
    client = _client()
    token = _csrf_token_for_current_request()
    resp = client.post(
        "/api/plan-data/does-not-exist.csv",
        json={"csv_content": "x"},
        headers={
            "Host": "127.0.0.1:5050",
            "Origin": "http://127.0.0.1:5050",
            "X-CSRF-Token": token,
        },
    )
    # Not a CSRF/Origin rejection (403 with the CSRF/Origin error shape);
    # the route itself may still reject the made-up file name on its own
    # terms, but never with this gate's error.
    assert resp.status_code != 403 or "CSRF" not in (resp.get_json() or {}).get("error", "") and "Cross-origin" not in (resp.get_json() or {}).get("error", "")


def test_request_with_no_origin_or_referer_still_succeeds_without_a_token():
    # Non-browser automation and the desktop bridge send neither header and
    # never send a CSRF token; must not be blocked by this gate alone.
    resp = _client().get("/api/ping")
    assert resp.status_code == 200


def test_bearer_credentialed_post_is_exempt_from_the_token_check():
    resp = _client().post(
        "/api/plan-data/does-not-exist.csv",
        json={"csv_content": "x"},
        headers={
            "Host": "127.0.0.1:5050",
            "Origin": "http://127.0.0.1:5050",
            "Authorization": "Bearer whatever",
        },
    )
    body = resp.get_json() or {}
    assert "CSRF" not in body.get("error", "")


def test_desktop_bridge_marked_app_is_exempt_from_the_whole_gate():
    app = create_app()
    prior = getattr(app, "_no_http_transport", False)
    app._no_http_transport = True
    try:
        resp = app.test_client().post(
            "/api/plan-data/does-not-exist.csv",
            json={"csv_content": "x"},
            headers={"Origin": "http://evil.example"},
        )
        body = resp.get_json() or {}
        assert "Cross-origin" not in body.get("error", "")
        assert "CSRF" not in body.get("error", "")
    finally:
        app._no_http_transport = prior
