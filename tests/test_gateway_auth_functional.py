"""Gateway sign-in over HTTP: 401/302, two-factor, cookies, sessions, CSRF and Origin, throttling, lockout."""
from __future__ import annotations

import pytest

from src.gateway import store as gstore
from src.gateway.app import COOKIE_NAME, safe_next
from tests.gateway_rig import PUBLIC_ORIGIN, PW, Rig


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


# ---- unauthenticated ----
def test_unauthenticated_api_gets_401_json(rig):
    b = rig.browser()
    r = b.get("/api/plan/rows")
    assert r.status_code == 401 and r.mimetype == "application/json"
    assert r.get_json() == {"success": False, "authenticated": False, "error": "sign in required"}
    r = b.get("/api/auth/session")
    assert r.status_code == 401 and r.get_json()["authenticated"] is False
    assert rig.upstream.calls == []


def test_unauthenticated_html_gets_302_to_login(rig):
    b = rig.browser()
    r = b.get("/")
    assert r.status_code == 302 and r.headers["Location"] == "/login?next=%2F"
    r = b.get("/static/dashboard.html?step=income")
    assert r.status_code == 302 and r.headers["Location"] == "/login?next=%2Fstatic%2Fdashboard.html%3Fstep%3Dincome"
    r = b.get("//evil.example/x")
    assert r.status_code == 302 and r.headers["Location"] == "/login"


def test_safe_next():
    assert safe_next("/a/b?c=1") == "/a/b?c=1"
    for bad in ["", "//evil.example", "/\\evil", "https://evil.example/", "javascript:alert(1)", "/login", "a/b",
                "/x\r\nSet-Cookie: a=b"]:
        assert safe_next(bad) == "/", bad


def test_login_page_is_public_and_hardened(rig):
    r = rig.browser().get("/login")
    assert r.status_code == 200 and r.mimetype == "text/html"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert rig.browser().get("/gateway/static/gateway.js").mimetype == "text/javascript"
    assert rig.browser().get("/gateway/static/nope.js").status_code == 404
    assert rig.browser().get("/gateway/static/..%2Fstore.py").status_code == 404


# ---- first login: password, then mandatory TOTP enrolment ----
def test_first_login_requires_totp_enrolment(rig):
    uid = rig.add_user("ann")
    b = rig.browser()
    r = b.login("ann")
    assert r.status_code == 200 and r.get_json()["next"] == "enrol"
    pending_cookie = b.cookies[COOKIE_NAME]
    # A pending session reaches nothing but the two-factor step.
    assert b.get("/api/plan/rows").status_code == 401
    r = b.get("/")
    assert r.status_code == 302 and r.headers["Location"] == "/gateway/enrol"
    assert b.get("/gateway/enrol").status_code == 200
    assert b.get("/api/auth/session").get_json()["stage"] == "pending"
    start = b.post("/api/auth/totp/enrol/start").get_json()
    assert start["secret"] and start["otpauth_uri"].startswith("otpauth://totp/")
    assert f"secret={start['secret']}" in start["otpauth_uri"]
    bad = "000000" if rig.code(uid) != "000000" else "111111"
    assert b.post("/api/auth/totp/enrol/confirm", json={"code": bad}).status_code == 400
    r = b.post("/api/auth/totp/enrol/confirm", json={"code": rig.code(uid)})
    assert r.status_code == 200
    assert b.cookies[COOKIE_NAME] != pending_cookie  # rotated on promotion
    old_csrf = b.csrf
    b.refresh_csrf()
    assert b.csrf and b.csrf != old_csrf
    r = b.get("/api/plan/rows")
    assert r.status_code == 200 and r.get_json() == {"upstream": True, "user_id": uid}
    method, path, identity = rig.upstream.calls[-1]
    assert (method, path) == ("GET", "/api/plan/rows")
    assert (identity.user_id, identity.username, identity.role) == (uid, "ann", "user")
    # The pending cookie is dead.
    stale = rig.browser()
    stale.cookies[COOKIE_NAME] = pending_cookie
    assert stale.get("/api/plan/rows").status_code == 401


def test_enrolled_user_must_pass_totp_and_wrong_codes_lock_the_account(rig):
    b, uid = rig.signed_in("ann")
    b2 = rig.browser(ip="198.51.100.7")
    assert b2.login("ann").get_json()["next"] == "totp"
    assert b2.get("/api/plan/rows").status_code == 401
    assert b2.get("/").headers["Location"] == "/login?next=%2F"
    bad = "000000" if rig.code(uid) != "000000" else "111111"
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK - 1):
        assert b2.post("/api/auth/totp/verify", json={"code": bad}).status_code == 400
    r = b2.post("/api/auth/totp/verify", json={"code": bad})
    assert r.status_code == 401  # locked: the pending session is ended
    assert COOKIE_NAME not in b2.cookies
    b3 = rig.browser(ip="198.51.100.8")
    r = b3.login("ann")
    assert r.status_code == 401
    assert r.get_json()["error"] == b3.login("nobody").get_json()["error"]  # same text: no username probing
    rig.advance(gstore.LOCK_SECONDS + 1)
    assert b3.login("ann").status_code == 200
    assert b3.post("/api/auth/totp/verify", json={"code": rig.code(uid)}).status_code == 200


def test_totp_code_cannot_be_replayed(rig):
    b, uid = rig.signed_in("ann")
    b2 = rig.browser()
    b2.login("ann")
    code = rig.code(uid)
    assert b2.post("/api/auth/totp/verify", json={"code": code}).status_code == 200
    b3 = rig.browser()
    b3.login("ann")
    assert b3.post("/api/auth/totp/verify", json={"code": code}).status_code == 400


def test_wrong_password_lockout_and_generic_errors(rig):
    rig.add_user("ann")
    b = rig.browser()
    texts = set()
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK):
        r = b.login("ann", "wrong password!!")
        assert r.status_code == 401
        texts.add(r.get_json()["error"])
    r = b.login("ann")  # right password, account locked
    assert r.status_code == 401
    texts.add(r.get_json()["error"])
    assert len(texts) == 1
    events = [e["event"] for e in rig.store.read_audit(limit=20)]
    assert "account locked" in events and "login failed" in events


def test_disabled_account_cannot_sign_in_and_live_session_ends(rig):
    b, uid = rig.signed_in("ann")
    rig.store.create_user("root", "Root", "admin", PW, now=rig.now[0], actor=gstore.Actor(None, "t"), must_change=False)
    rig.store.set_disabled(uid, True, now=rig.now[0], actor=gstore.Actor(None, "t"))
    assert b.get("/api/plan/rows").status_code == 401
    assert rig.browser().login("ann").status_code == 401


# ---- cookies, session expiry and logout ----
def test_session_cookie_flags(rig):
    rig.add_user("ann")
    b = rig.browser()
    b.login("ann")
    cookie = b.last_set_cookie
    assert COOKIE_NAME.startswith("__Host-") and cookie.startswith(COOKIE_NAME + "=")
    attrs = [a.strip() for a in cookie.split(";")[1:]]
    assert "HttpOnly" in attrs and "Secure" in attrs and "SameSite=Strict" in attrs and "Path=/" in attrs
    assert not any(a.lower().startswith("domain") for a in attrs)
    assert not any(a.lower().startswith("max-age") for a in attrs)


def test_idle_session_expires(rig):
    b, _uid = rig.signed_in("ann")
    rig.advance(gstore.IDLE_SECONDS - 60)  # the rig already moved the clock 31 s past sign-in
    assert b.get("/api/plan/rows").status_code == 200  # activity extends it
    rig.advance(gstore.IDLE_SECONDS - 5)
    assert b.get("/api/plan/rows").status_code == 200
    rig.advance(gstore.IDLE_SECONDS + 1)
    assert b.get("/api/plan/rows").status_code == 401
    assert b.get("/").status_code == 302


def test_logout_invalidates_the_cookie(rig):
    b, _uid = rig.signed_in("ann")
    cookie = b.cookies[COOKIE_NAME]
    r = b.post("/api/auth/logout")
    assert r.status_code == 200
    raw = b.last_set_cookie
    assert raw.startswith(COOKIE_NAME + "=;") and "Max-Age=0" in raw and "Secure" in raw and "HttpOnly" in raw
    assert COOKIE_NAME not in b.cookies
    replay = rig.browser()
    replay.cookies[COOKIE_NAME] = cookie
    assert replay.get("/api/plan/rows").status_code == 401
    assert replay.get("/api/auth/session").status_code == 401


def test_session_endpoint_payload_matches_the_planner_frontend(rig):
    b, uid = rig.signed_in("ann")
    j = b.get("/api/auth/session").get_json()
    assert j["success"] is True and j["authenticated"] is True and j["stage"] == "active"
    assert j["csrf_token"] == b.csrf
    assert j["user"] == {"id": uid, "username": "ann", "display_name": "Ann", "role": "user", "must_change": False}


# ---- CSRF, Origin and Content-Type ----
def test_csrf_token_required_on_unsafe_methods(rig):
    b, _uid = rig.signed_in("ann")
    assert b.post("/api/plan/save", csrf=False).status_code == 403
    assert b.post("/api/plan/save", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert b.request("DELETE", "/api/plan/thing", csrf=False).status_code == 403
    assert b.post("/api/plan/save").status_code == 200
    assert b.post("/api/auth/logout", csrf=False).status_code == 403
    assert rig.upstream.calls[-1][:2] == ("POST", "/api/plan/save")


def test_origin_check(rig):
    b, _uid = rig.signed_in("ann")
    assert b.post("/api/plan/save", origin="https://evil.example").status_code == 403
    assert b.post("/api/plan/save", origin=False).status_code == 403
    assert b.post("/api/plan/save", origin="http://127.0.0.1:5064").status_code == 403  # local origin on Funnel
    assert b.get("/api/plan/rows", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert b.get("/api/plan/rows", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
    rig.add_user("bob")
    assert rig.browser().login("bob", origin="https://evil.example").status_code == 403


def test_unsafe_body_content_type_allow_list(rig):
    b, _uid = rig.signed_in("ann")
    r = b.request("POST", "/api/plan/save", body=b"a=b", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 403
    r = b.request("POST", "/api/plan/save", body=b"--x", content_type="multipart/form-data; boundary=x")
    assert r.status_code == 403
    r = b.request("POST", "/api/plan/save", body=b"hello", content_type="text/plain")
    assert r.status_code == 200


def test_local_listener_rules(rig):
    rig.add_user("ann")
    b = rig.browser(ip="127.0.0.1", listener="local")
    assert b.get("/login").status_code == 200
    assert b.get("/login", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 403
    assert b.get("/login", headers={"Tailscale-User-Login": "x"}).status_code == 403
    assert b.get("/login", headers={"Host": "evil.example:5064"}).status_code == 421
    assert b.login("ann").status_code == 200
    assert b.login("ann", origin=PUBLIC_ORIGIN).status_code == 403


# ---- throttling ----
def test_per_ip_throttle_uses_rightmost_forwarded_entry_on_funnel(rig):
    rig.add_user("ann")
    attacker = rig.browser(ip="203.0.113.66")
    for i in range(11):
        # A client-chosen left-most entry must not pick a fresh bucket.
        r = attacker.login(f"nobody{i}", headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.66"})
        assert r.status_code == 401
    r = attacker.login("ann", headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.66"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert rig.browser(ip="198.51.100.1").login("ann").status_code == 200  # another address is unaffected
    assert "login throttled" in [e["event"] for e in rig.store.read_audit(limit=5)]
    rig.advance(601)
    assert attacker.login("ann").status_code == 200


def test_local_listener_throttles_by_socket_address(rig):
    rig.add_user("ann")
    b = rig.browser(ip="127.0.0.1", listener="local")
    for i in range(11):
        b.login(f"nobody{i}")
    assert b.login("ann").status_code == 429


def test_global_throttle(rig):
    rig.add_user("ann")
    for i in range(51):
        assert rig.browser(ip=f"192.0.2.{i}").login(f"nobody{i}").status_code == 401
    r = rig.browser(ip="198.51.100.99").login("ann")
    assert r.status_code == 429


# ---- forced password change ----
def test_must_change_password_gate_and_change(rig):
    uid = rig.add_user("ann", must_change=True)
    b = rig.browser()
    b.login("ann")
    b.post("/api/auth/totp/enrol/start")
    b.post("/api/auth/totp/enrol/confirm", json={"code": rig.code(uid)})
    b.refresh_csrf()
    r = b.get("/api/plan/rows")
    assert r.status_code == 409 and r.get_json()["must_change"] is True
    assert b.get("/").headers["Location"] == "/gateway/account"
    assert b.get("/gateway/account").status_code == 200
    other = rig.browser(ip="198.51.100.2")
    rig.advance(31)
    other.login("ann")
    other.post("/api/auth/totp/verify", json={"code": rig.code(uid)})
    assert other.get("/api/auth/session").get_json()["stage"] == "active"
    r = b.post("/api/auth/password", json={"current": "wrong password!!", "new": "brand new password 1"})
    assert r.status_code == 400
    r = b.post("/api/auth/password", json={"current": PW, "new": "short"})
    assert r.status_code == 400
    r = b.post("/api/auth/password", json={"current": PW, "new": "brand new password 1"})
    assert r.status_code == 200
    b.refresh_csrf()
    assert b.get("/api/plan/rows").status_code == 200
    assert other.get("/api/plan/rows").status_code == 401  # other sessions ended
    assert "password changed" in [e["event"] for e in rig.store.read_audit(limit=10)]


# ---- the seam ----
def test_placeholder_upstream_when_no_proxy_is_plugged_in(tmp_path):
    rig = Rig(tmp_path, upstream=None)
    b, _uid = rig.signed_in("ann")
    r = b.get("/api/plan/rows")
    assert r.status_code == 503 and r.get_json()["gateway_placeholder"] is True
    r = b.get("/")
    assert r.status_code == 503 and r.mimetype == "text/html"


def test_gateway_owned_paths_are_never_forwarded(rig):
    b, _uid = rig.signed_in("ann")
    assert b.get("/api/auth/nope").status_code == 404
    assert b.get("/gateway/nope").status_code == 404
    assert all(not p.startswith(("/api/auth/", "/gateway/")) for _m, p, _i in rig.upstream.calls)


def test_audit_records_logins_with_the_real_user_and_client_ip(rig):
    b, uid = rig.signed_in("ann", ip="203.0.113.9")
    b.post("/api/auth/logout")
    rows = rig.store.read_audit(limit=20)
    ok = next(r for r in rows if r["event"] == "login succeeded")
    assert ok["actor_user_id"] == uid and ok["client_ip"] == "203.0.113.9" and ok["listener"] == "funnel"
    assert any(r["event"] == "totp enrolled" and r["actor_user_id"] == uid for r in rows)
    assert any(r["event"] == "logout" and r["actor_user_id"] == uid for r in rows)
    assert PW not in repr(rows) and b.csrf not in repr(rows)


def test_enrolment_qr_encodes_the_same_otpauth_uri_as_the_manual_key(rig):
    import segno

    rig.add_user("ann")
    b = rig.browser()
    b.login("ann")
    start = b.post("/api/auth/totp/enrol/start").get_json()
    uri, qr = start["otpauth_uri"], start["qr_svg_data_uri"]
    assert f"secret={start['secret']}" in uri  # the manual key is still returned as the fallback
    assert qr.startswith("data:image/svg+xml")
    # Rendered locally: identical to segno's own encoding of exactly this URI, and not of any other.
    assert qr == segno.make(uri, error="m", micro=False).svg_data_uri(scale=5, border=4)
    assert qr != segno.make(uri.replace(start["secret"], "A" * 32), error="m", micro=False).svg_data_uri(scale=5, border=4)
    assert b.post("/api/auth/totp/enrol/start").get_json()["qr_svg_data_uri"] == qr  # same pending secret
    csp = b.get("/gateway/enrol").headers["Content-Security-Policy"]
    assert "img-src 'self' data:" in csp and "http" not in csp
