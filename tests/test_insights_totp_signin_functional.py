"""Financial Insights two-factor sign-in over the remote listener: enrolment gate, code step, replay, lockout, reset."""
from __future__ import annotations

import pytest

from src.identity import totp as totp_lib
from tests.test_trends_access_gate_functional import PW, Rig


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def _enrol_via_pages(rig, token):
    begin = rig.call(rig.remote, "POST", "/api/totp/begin", cookie=token)
    assert begin.status_code == 200
    j = begin.get_json()
    assert j["uri"].startswith("otpauth://totp/") and j["secret"] in j["uri"]
    assert "no-store" in begin.headers.get("Cache-Control", "")
    done = rig.call(rig.remote, "POST", "/api/totp/confirm", {"code": totp_lib.totp_at(j["secret"], rig.now[0])}, cookie=token)
    assert done.status_code == 200
    return j["secret"], done.get_json()["recovery_codes"]


def test_new_person_is_sent_to_enrol_and_nothing_else_opens_until_they_do(rig):
    rig.add("ann", totp_required=True)
    resp, token = rig.signin("ann")
    assert resp.get_json() == {"success": True, "must_change": False, "needs_totp": True}
    page = rig.call(rig.remote, "GET", "/", cookie=token)
    assert page.status_code == 302 and page.headers["Location"] == "/totp"
    assert rig.call(rig.remote, "GET", "/totp", cookie=token).status_code == 200
    blocked = rig.call(rig.remote, "GET", "/api/history", cookie=token)
    assert blocked.status_code == 409 and blocked.get_json()["needs_totp"] is True
    assert rig.call(rig.remote, "GET", "/api/whoami", cookie=token).get_json()["needs_totp"] is True
    _enrol_via_pages(rig, token)
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200  # same session carries on
    assert rig.call(rig.remote, "GET", "/", cookie=token).status_code == 200


def test_wrong_enrolment_code_is_refused_and_the_gate_stays_shut(rig):
    rig.add("ann", totp_required=True)
    _, token = rig.signin("ann")
    rig.call(rig.remote, "POST", "/api/totp/begin", cookie=token)
    bad = rig.call(rig.remote, "POST", "/api/totp/confirm", {"code": "abcdef"}, cookie=token)
    assert bad.status_code == 400
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 409


def test_optional_person_signs_in_without_a_factor_and_may_still_enrol(rig):
    rig.add("ann", totp_required=False)
    resp, token = rig.signin("ann")
    assert resp.get_json()["needs_totp"] is False
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200
    _enrol_via_pages(rig, token)
    assert rig.call(rig.remote, "POST", "/api/totp/begin", cookie=token).status_code == 409  # already set up


def _enrolled(rig, name="ann"):
    rig.add(name, totp_required=True)
    _, token = rig.signin(name)
    secret, codes = _enrol_via_pages(rig, token)
    return secret, codes


def _signin(rig, code=None, password=PW, name="ann"):
    body = {"username": name, "password": password}
    if code is not None:
        body["code"] = code
    resp = rig.call(rig.remote, "POST", "/api/signin", body)
    cookie = resp.headers.get("Set-Cookie", "")
    return resp, (cookie.split(";")[0].split("=", 1)[1] if cookie.startswith("trends_session=") else None)


def test_signin_needs_the_code_after_the_password_and_gives_no_session_without_it(rig):
    secret, _ = _enrolled(rig)
    rig.now[0] += 60
    resp, token = _signin(rig)
    assert resp.get_json() == {"success": False, "needs_code": True} and token is None
    resp, token = _signin(rig, code=totp_lib.totp_at(secret, rig.now[0]))
    assert resp.status_code == 200 and token
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200


def test_replayed_code_is_refused_and_logged_without_the_code(rig):
    secret, _ = _enrolled(rig)
    rig.now[0] += 60
    code = totp_lib.totp_at(secret, rig.now[0])
    assert _signin(rig, code=code)[0].status_code == 200
    again, token = _signin(rig, code=code)
    assert again.status_code == 401 and token is None and again.get_json()["error"] == "That code is not right."
    events = rig.store.read_events()
    assert any(e["event"] == "two-factor code failed" for e in events)
    assert all(code not in (e["details"] or "") and secret not in (e["details"] or "") for e in events)


def test_wrong_password_never_reveals_a_second_factor_exists(rig):
    _enrolled(rig)
    resp, _ = _signin(rig, password="wrong password!!")
    assert resp.status_code == 401 and resp.get_json() == {"success": False, "error": "Incorrect username or password."}


def test_code_failures_lock_the_account_like_password_failures(rig):
    secret, _ = _enrolled(rig)
    rig.now[0] += 60
    for _ in range(4):
        assert _signin(rig, code="000000")[0].status_code == 401
    locked = _signin(rig, code="000000")[0]
    assert locked.status_code == 401  # a locked account answers like a wrong code (X-8, owner decision)
    good = _signin(rig, code=totp_lib.totp_at(secret, rig.now[0]))[0]
    assert good.status_code == 401  # a correct code does not lift the lock
    assert any(e["event"] == "locked out" for e in rig.store.read_events())


def test_recovery_code_signs_in_once_and_is_logged(rig):
    _, codes = _enrolled(rig)
    rig.now[0] += 60
    resp, token = _signin(rig, code=codes[0])
    assert resp.status_code == 200 and token
    assert any(e["event"] == "recovery code used" for e in rig.store.read_events())
    assert _signin(rig, code=codes[0])[0].status_code == 401


def test_admin_reset_ends_the_session_and_forces_enrolment_again(rig):
    secret, _ = _enrolled(rig)
    rig.now[0] += 60
    _, token = _signin(rig, code=totp_lib.totp_at(secret, rig.now[0]))
    rig.store.reset_totp(1)
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 401
    resp, token = _signin(rig)
    assert resp.get_json()["needs_totp"] is True
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 409


def test_recovery_code_regeneration_needs_password_and_a_fresh_authenticator_code(rig):
    secret, old = _enrolled(rig)
    rig.now[0] += 60
    _, token = _signin(rig, code=totp_lib.totp_at(secret, rig.now[0]))
    path = "/api/totp/recovery-codes"
    code = totp_lib.totp_at(secret, rig.now[0] + 30)
    rig.now[0] += 30
    assert rig.call(rig.remote, "POST", path, {"current": "nope nope nope", "code": code}, cookie=token).status_code == 400
    assert rig.call(rig.remote, "POST", path, {"current": PW, "code": old[0]}, cookie=token).status_code == 400
    ok = rig.call(rig.remote, "POST", path, {"current": PW, "code": code}, cookie=token)
    assert ok.status_code == 200 and len(ok.get_json()["recovery_codes"]) == 8


def test_local_listener_has_no_second_factor_routes_to_use(rig):
    assert rig.call(rig.local, "POST", "/api/totp/begin").status_code == 400
    assert rig.call(rig.remote, "POST", "/api/totp/begin").status_code == 401


def test_unavailable_credential_store_fails_closed(rig):
    from src.secrets_store import SecretStoreUnavailable

    secret, _ = _enrolled(rig)

    def broken():
        raise SecretStoreUnavailable("none")

    rig.store._totp_key_fn = broken
    rig.store._totp_key_cache = None
    rig.now[0] += 60
    resp, token = _signin(rig, code=totp_lib.totp_at(secret, rig.now[0]))
    assert resp.status_code == 503 and token is None
