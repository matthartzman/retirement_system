"""SEC-04: the admin-issued temporary password alone no longer lets anyone start TOTP enrollment.

A one-time enrollment code (shown to the admin once, stored only as a hash, short expiry, single use, wrong tries
counted toward the sign-in throttle) is needed as well, and completing enrollment is audited."""
from __future__ import annotations

import io

import pytest

from src.gateway import cli
from src.gateway import store as gstore
from src.gateway.store import GatewayStore
from tests.gateway_rig import CLI, PW, Rig

START = "/api/auth/totp/enrol/start"
CONFIRM = "/api/auth/totp/enrol/confirm"


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


def _pending(rig, name="ann"):
    uid = rig.add_user(name)
    b = rig.browser()
    assert b.login(name).status_code == 200
    return b, uid


def test_temporary_password_alone_cannot_start_enrolment(rig):
    b, uid = _pending(rig)
    r = b.post(START)
    assert r.status_code == 403 and r.get_json()["enrol_code_required"] is True
    assert "secret" not in r.get_json()
    assert rig.store.totp_status(uid) == "none"  # no secret was minted for the attacker


def test_wrong_code_is_refused_audited_and_counted_toward_the_lock(rig):
    b, uid = _pending(rig)
    rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)
    for _ in range(4):
        r = b.post(START, json={"enrol_code": "AAAAA-BBBBB"})
        assert r.status_code == 403
    assert rig.store.totp_status(uid) == "none"
    r = b.post(START, json={"enrol_code": "AAAAA-BBBBB"})
    assert r.status_code == 401  # fifth failure from this source locks it, like a wrong password
    events = [e["event"] for e in rig.store.read_audit(100)]
    assert events.count("enrol code failed") == 5 and "account locked" in events


def test_correct_code_enrols_and_is_spent(rig):
    b, uid = _pending(rig)
    code = rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)
    assert len(code.replace("-", "")) == gstore.ENROL_CODE_LENGTH
    lowered = code.lower().replace("-", " ")  # forgiving about case and separators
    start = b.post(START, json={"enrol_code": lowered}).get_json()
    assert start["secret"]
    r = b.post(CONFIRM, json={"code": rig.code(uid)})
    assert r.status_code == 200
    assert rig.store.enrol_code_state(uid, rig.now[0]) == "none"
    done = [e for e in rig.store.read_audit(100) if e["event"] == "enrollment completed"]
    assert len(done) == 1 and done[0]["target_user_id"] == uid


def test_code_expires(rig):
    b, uid = _pending(rig)
    code = rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)
    rig.advance(gstore.ENROL_CODE_SECONDS + 1)  # the 5-minute pending session has lapsed too: sign in again
    b = rig.browser(ip="198.51.100.9")
    assert b.login("ann").status_code == 200
    r = b.post(START, json={"enrol_code": code})
    assert r.status_code == 403 and r.get_json()["enrol_code_required"] is True
    assert rig.store.enrol_code_state(uid, rig.now[0]) == "expired"


def test_only_a_hash_is_stored(rig):
    uid = rig.add_user("ann")
    code = rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)
    row = rig.store.get_user(uid)
    assert code.replace("-", "") not in repr(row) and row["enrol_code_hash"]
    assert code not in repr(rig.store.read_audit(100))


def test_a_new_code_replaces_the_old_and_a_reset_voids_it(rig):
    uid = rig.add_user("ann")
    first = rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)
    second = rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)
    assert not rig.store.verify_enrol_code(uid, first, rig.now[0])
    assert rig.store.verify_enrol_code(uid, second, rig.now[0])
    rig.store.reset_totp(uid, now=rig.now[0], actor=CLI)
    assert not rig.store.verify_enrol_code(uid, second, rig.now[0])
    rig.store.set_password(uid, PW, must_change=True, now=rig.now[0], actor=CLI)
    assert rig.store.enrol_code_state(uid, rig.now[0]) == "none"


def test_enrolled_account_cannot_be_issued_a_code(rig):
    b, uid = rig.signed_in("ann")
    with pytest.raises(ValueError):
        rig.store.issue_enrol_code(uid, now=rig.now[0], actor=CLI)


def test_admin_api_returns_the_code_once_on_create_and_resets(rig):
    admin, _aid = rig.signed_in("root", role="admin")
    r = admin.post("/api/auth/admin/users", json={"username": "Bob", "display_name": "Bob", "role": "user",
                                                    "temp_password": "temporary password 1"})
    body = r.get_json()
    uid, code = body["id"], body["enrol_code"]
    assert body["enrol_code_minutes"] == gstore.ENROL_CODE_SECONDS // 60 and code
    assert code not in repr(admin.get("/api/auth/admin/users").get_json())  # never listed afterwards
    b = rig.browser(ip="198.51.100.3")
    assert b.login("bob", "temporary password 1").get_json()["next"] == "enrol"
    assert b.post(START).status_code == 403
    assert b.post(START, json={"enrol_code": code}).get_json()["secret"]
    # reset-totp, reset-password and the explicit route each hand the admin a fresh code
    again = admin.post(f"/api/auth/admin/users/{uid}/enrol-code").get_json()["enrol_code"]
    assert again != code and not rig.store.verify_enrol_code(uid, code, rig.now[0])
    assert admin.post(f"/api/auth/admin/users/{uid}/reset-totp").get_json()["enrol_code"]
    assert admin.post(f"/api/auth/admin/users/{uid}/reset-password",
                      json={"temp_password": "another temporary 22"}).get_json()["enrol_code"]


def test_console_routes_return_the_code(rig):
    admin, _aid = rig.signed_in("root", role="admin")
    base = "/api/auth/admin/console"
    r = admin.post(f"{base}/users", json={"username": "cat", "display_name": "Cat", "role": "user",
                                           "temp_password": "temporary password 1"}).get_json()
    assert r["enrol_code"]
    assert admin.post(f"{base}/users/enrol-code", json={"id": r["id"]}).get_json()["enrol_code"]
    assert admin.post(f"{base}/users/reset-totp", json={"id": r["id"]}).get_json()["enrol_code"]


def test_cli_prints_a_code_for_create_admin_and_break_glass(tmp_path):
    db = tmp_path / "gateway.db"

    def run(*args):
        out, err = io.StringIO(), io.StringIO()
        rc = cli.main([*args, "--db", str(db), "--password-stdin"], stdin=io.StringIO(PW + "\n"), stdout=out,
                      stderr=err, scrypt_n=2**4)
        return rc, out.getvalue()

    rc, out = run("create-admin", "--username", "root")
    assert rc == 0 and "One-time enrollment code" in out
    store = GatewayStore(db, scrypt_n=2**4)
    code = out.split("shown only now): ")[1].split()[0]
    uid = store.find_user("root")["id"]
    assert store.verify_enrol_code(uid, code, __import__("time").time())
    rc, out = run("break-glass", "--username", "root")
    assert rc == 0 and "One-time enrollment code" in out
    new = out.split("shown only now): ")[1].split()[0]
    assert new != code and not store.verify_enrol_code(uid, code, __import__("time").time())
