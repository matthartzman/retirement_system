"""Admin console phase 2: access expiry, notes, edit name and end sessions (integration design, section 5).

Expiry is a login-path security control, so most of this file is about enforcement: sign-in, the second-factor step,
an already-open session, the last-admin rule, and the break-glass recovery path.
"""
from __future__ import annotations

import pytest

from src.gateway import store as gstore
from src.gateway.store import Actor, GatewayStore, LastAdminError
from tests.gateway_rig import CLI, PW, Rig
from tests.test_gateway_admin_console_functional import API, Recorder, rig  # noqa: F401 - the shared fixture

DAY = 86400.0


# ---------- store ----------

@pytest.fixture()
def store(tmp_path):
    return GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)


def _user(store, name="ann", role="user", now=1000.0):
    return store.create_user(name, name.title(), role, PW, now=now, actor=CLI, must_change=False)


def test_schema_is_version_three_and_an_old_database_migrates_without_losing_rows(tmp_path):
    path = tmp_path / "gateway.db"
    s = GatewayStore(path, scrypt_n=2**4)
    uid = _user(s)
    import sqlite3
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE users DROP COLUMN expires_at")
    con.execute("ALTER TABLE users DROP COLUMN notes")
    con.execute("ALTER TABLE users DROP COLUMN modules")
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()
    s2 = GatewayStore(path, scrypt_n=2**4)
    assert s2.schema_version() == gstore.SCHEMA_VERSION == 3
    row = s2.get_user(uid)
    assert row["username"] == "ann" and row["expires_at"] is None and row["notes"] == ""


def test_expired_user_cannot_pass_the_password_check_and_the_reason_is_not_special(store):
    uid = _user(store)
    store.set_profile(uid, expires_at=5000.0, now=1000.0, actor=CLI)
    assert store.verify_password("ann", PW, 4999.0).ok is True
    check = store.verify_password("ann", PW, 5000.0)
    assert check.ok is False and check.user_id == uid
    store.set_profile(uid, expires_at=None, now=5001.0, actor=CLI)
    assert store.verify_password("ann", PW, 5002.0).ok is True


def test_an_open_session_is_refused_after_the_expiry_and_cleaned_up(store):
    uid = _user(store)
    token, _ = store.create_session(uid, "active", 1000.0, "1.1.1.1")
    store.set_profile(uid, expires_at=1500.0, now=1000.0, actor=CLI)
    assert store.get_session(token, 1499.0) is not None
    assert store.get_session(token, 1500.0) is None
    assert store.count_user_sessions(uid, 1500.0) == 0


def test_a_pending_second_factor_session_is_refused_after_the_expiry_too(store):
    uid = _user(store)
    token, _ = store.create_session(uid, "pending", 1000.0, "1.1.1.1")
    store.set_profile(uid, expires_at=1100.0, now=1000.0, actor=CLI)
    assert store.get_session(token, 1101.0) is None


def test_the_last_admin_cannot_be_expired_but_a_second_admin_can(store):
    a = _user(store, "root", "admin")
    with pytest.raises(LastAdminError):
        store.set_profile(a, expires_at=900.0, now=1000.0, actor=CLI)  # already in the past
    assert store.get_user(a)["expires_at"] is None
    b = _user(store, "second", "admin")
    store.set_profile(b, expires_at=900.0, now=1000.0, actor=CLI)
    assert store.count_active_admins(now=1000.0) == 1
    with pytest.raises(LastAdminError):
        store.set_disabled(a, True, now=1000.0, actor=CLI)  # an expired admin does not count as a spare


def test_an_expired_admin_does_not_count_as_active_for_demoting_the_other(store):
    a = _user(store, "root", "admin")
    b = _user(store, "second", "admin")
    store.set_profile(b, expires_at=1500.0, now=1000.0, actor=CLI)
    with pytest.raises(LastAdminError):
        store.set_role(a, "user", now=2000.0, actor=CLI)  # b has expired, a is the only usable admin


def test_profile_updates_name_notes_and_audits_without_the_notes_text(store):
    uid = _user(store)
    store.set_profile(uid, display_name="  Ann Alpha  ", notes="called about the 401k, secret-ish", now=1000.0, actor=CLI)
    row = store.get_user(uid)
    assert row["display_name"] == "Ann Alpha" and row["notes"].startswith("called")
    last = store.read_audit(limit=1)[0]
    assert last["event"] == "profile changed" and last["target_username"] == "ann"
    assert "name" in last["details"] and "notes" in last["details"]
    assert "401k" not in repr(store.read_audit(limit=50))


def test_profile_validation(store):
    uid = _user(store)
    for bad in ({"display_name": "   "}, {"display_name": "x\x00y"}, {"display_name": "a" * 81}, {"notes": "n" * 501},
                {"notes": "bad" + chr(7)}, {"expires_at": float("inf")}, {"expires_at": float("nan")}, {"expires_at": -1.0}):
        with pytest.raises(ValueError):
            store.set_profile(uid, now=1000.0, actor=CLI, **bad)
    with pytest.raises(LookupError):
        store.set_profile(999, notes="x", now=1000.0, actor=CLI)


def test_notes_and_expiry_are_never_in_the_session_or_identity_rows(store):
    uid = _user(store)
    store.set_profile(uid, notes="private", expires_at=9e9, now=1000.0, actor=CLI)
    token, _ = store.create_session(uid, "active", 1000.0, "1.1.1.1")
    sess = store.get_session(token, 1001.0)
    assert "notes" not in sess and "private" not in repr(sess)


def test_end_sessions_removes_every_session_and_audits(store):
    uid = _user(store)
    t1, _ = store.create_session(uid, "active", 1000.0, "1.1.1.1")
    t2, _ = store.create_session(uid, "active", 1000.0, "2.2.2.2")
    assert store.end_sessions(uid, now=1001.0, actor=CLI) == 2
    assert store.get_session(t1, 1002.0) is None and store.get_session(t2, 1002.0) is None
    assert store.read_audit(limit=1)[0]["event"] == "sessions ended"
    with pytest.raises(LookupError):
        store.end_sessions(999, now=1001.0, actor=CLI)


# ---------- HTTP ----------

def test_features_are_on_and_the_list_carries_expiry_and_notes_for_admins(rig):  # noqa: F811
    admin, _ = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    rig.store.set_profile(uid, notes="hello", expires_at=rig.now[0] + DAY, now=rig.now[0], actor=CLI)
    body = admin.get(f"{API}/users").get_json()
    f = body["features"]
    assert f["expiry"] is True and f["notes"] is True and f["end_sessions"] is True and f["edit_name"] is True
    assert f["grants"] is False and f["require_totp"] is False and f["modules"] is True
    ann = next(u for u in body["users"] if u["id"] == uid)
    assert ann["notes"] == "hello" and ann["expires_at"] == pytest.approx(rig.now[0] + DAY) and ann["expired"] is False


def test_update_saves_name_notes_and_expiry_and_audits_the_admin(rig):  # noqa: F811
    admin, aid = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    r = admin.post(f"{API}/users/update", json={"id": uid, "role": "user", "display_name": "Ann Alpha",
                                                  "notes": "contractor", "expires_at": rig.now[0] + 30 * DAY})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = rig.store.get_user(uid)
    assert row["display_name"] == "Ann Alpha" and row["notes"] == "contractor" and row["expires_at"] is not None
    ev = rig.store.read_audit(limit=3)
    assert any(e["event"] == "profile changed" and e["actor_username"] == "root" for e in ev)
    # omitting a key keeps it; null clears expiry
    assert admin.post(f"{API}/users/update", json={"id": uid, "role": "user"}).status_code == 200
    assert rig.store.get_user(uid)["notes"] == "contractor"
    assert admin.post(f"{API}/users/update", json={"id": uid, "expires_at": None}).status_code == 200
    assert rig.store.get_user(uid)["expires_at"] is None


def test_update_rejects_bad_values_with_a_400(rig):  # noqa: F811
    admin, _ = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    for bad in ({"expires_at": "tomorrow"}, {"expires_at": True}, {"notes": 5}, {"display_name": ""}, {"notes": "n" * 501}):
        assert admin.post(f"{API}/users/update", json={"id": uid, **bad}).status_code == 400, bad


def test_setting_a_past_expiry_ends_the_sessions_and_stops_the_worker(rig):  # noqa: F811
    admin, _ = rig.signed_in("root", role="admin")
    ann, uid = rig.signed_in("ann")
    assert ann.get("/api/auth/session").status_code == 200
    r = admin.post(f"{API}/users/update", json={"id": uid, "expires_at": rig.now[0] - 10})
    assert r.status_code == 200
    assert ann.get("/api/auth/session").status_code == 401
    assert ("user_disabled", uid, True) in rig.recorder.calls


def test_an_expired_user_cannot_sign_in_and_gets_the_generic_error(rig):  # noqa: F811
    uid = rig.add_user("ann")
    rig.store.set_profile(uid, expires_at=rig.now[0] - 1, now=rig.now[0], actor=CLI)
    b = rig.browser()
    wrong = rig.browser().login("ann", "wrong password here")
    r = b.login("ann")
    assert r.status_code == 401 and r.get_json()["error"] == wrong.get_json()["error"]


def test_a_session_opened_before_the_expiry_stops_working_when_it_passes(rig):  # noqa: F811
    admin, _ = rig.signed_in("root", role="admin")
    ann, uid = rig.signed_in("ann")
    rig.store.set_profile(uid, expires_at=rig.now[0] + 100, now=rig.now[0], actor=CLI)
    assert ann.get("/api/auth/session").status_code == 200
    rig.advance(101)
    assert ann.get("/api/auth/session").status_code == 401
    assert ann.get("/").status_code in (302, 401)
    assert admin.get(f"{API}/users").status_code == 200  # the admin is unaffected


def test_the_second_factor_step_refuses_an_account_that_expired_mid_sign_in(rig):  # noqa: F811
    uid = rig.add_user("ann")
    b = rig.browser()
    assert b.login("ann").status_code == 200
    rig.store.set_profile(uid, expires_at=rig.now[0] + 5, now=rig.now[0], actor=CLI)
    rig.advance(6)
    assert b.post("/api/auth/totp/enrol/start").status_code in (401, 302)


def test_end_sessions_route_signs_the_person_out_and_releases_the_worker(rig):  # noqa: F811
    admin, _ = rig.signed_in("root", role="admin")
    ann, uid = rig.signed_in("ann")
    assert admin.post(f"{API}/users/end-sessions", json={"id": uid}).status_code == 200
    assert ann.get("/api/auth/session").status_code == 401
    assert ("signed_out", uid, 0) in rig.recorder.calls
    assert admin.post(f"{API}/users/end-sessions", json={"id": 9999}).status_code == 404
    assert admin.post(f"{API}/users/end-sessions", json={}).status_code == 400


def test_the_new_fields_and_routes_are_admin_only(rig):  # noqa: F811
    ann, uid = rig.signed_in("ann")
    other = rig.add_user("bob")
    assert ann.post(f"{API}/users/update", json={"id": other, "notes": "x"}).status_code == 403
    assert ann.post(f"{API}/users/end-sessions", json={"id": other}).status_code == 403
    assert ann.get(f"{API}/users").status_code == 403
    assert rig.store.get_user(other)["notes"] == ""
    assert rig.browser().post(f"{API}/users/end-sessions", json={"id": other}).status_code == 401


def test_a_user_never_sees_their_own_notes_or_expiry(rig):  # noqa: F811
    ann, uid = rig.signed_in("ann")
    rig.store.set_profile(uid, notes="admin eyes only", expires_at=rig.now[0] + DAY, now=rig.now[0], actor=CLI)
    blob = ann.get("/api/auth/session").get_data(as_text=True)
    assert "admin eyes only" not in blob and "notes" not in blob and "expires" not in blob
    assert all("admin eyes only" not in repr(c) for c in rig.upstream.calls)


def test_disabling_the_only_usable_admin_through_expiry_is_refused_over_http(rig):  # noqa: F811
    admin, aid = rig.signed_in("root", role="admin")
    r = admin.post(f"{API}/users/update", json={"id": aid, "expires_at": rig.now[0] - 5})
    assert r.status_code == 409 and r.get_json()["last_admin"] is True


def test_break_glass_clears_an_expiry_so_a_locked_out_admin_can_recover(tmp_path):
    from src.gateway import cli
    import io
    db = tmp_path / "gateway.db"
    s = GatewayStore(db, scrypt_n=2**4)
    a = _user(s, "root", "admin")
    b = _user(s, "second", "admin")
    with s._tx() as conn:  # an expiry that already passed, written directly (the last-admin rule would refuse it)
        conn.execute("UPDATE users SET expires_at=1.0 WHERE id IN (?,?)", (a, b))
    code = cli.main(["break-glass", "--db", str(db), "--username", "root", "--password-stdin"],
                    stdin=io.StringIO("a brand new long password\n"), stdout=io.StringIO(), stderr=io.StringIO(),
                    scrypt_n=2**4)
    assert code == 0
    assert GatewayStore(db, scrypt_n=2**4).get_user(a)["expires_at"] is None


# ---------- Financial Insight modules (stored, not enforced) ----------

def test_modules_default_to_all_off_and_round_trip(store):
    uid = _user(store)
    base = {"snapshot": False, "trends": False, "projections": False, "money_view": "percent"}
    assert next(u for u in store.list_users(2000.0) if u["id"] == uid)["modules"] == base
    store.set_profile(uid, modules={"trends": True, "money_view": "both"}, now=1000.0, actor=CLI)
    got = next(u for u in store.list_users(2000.0) if u["id"] == uid)["modules"]
    assert got == {"snapshot": False, "trends": True, "projections": False, "money_view": "both"}
    assert store.read_audit(limit=1)[0]["details"] == "modules"
    n = len(store.read_audit(limit=50))
    store.set_profile(uid, modules={"trends": True, "money_view": "both"}, now=1001.0, actor=CLI)
    assert len(store.read_audit(limit=50)) == n  # unchanged value, no audit row


def test_modules_validation(store):
    uid = _user(store)
    for bad in ("all", {"live": True}, {"trends": "yes"}, {"money_view": "euros"}, [True]):
        with pytest.raises(ValueError):
            store.set_profile(uid, modules=bad, now=1000.0, actor=CLI)


def test_a_database_already_at_version_three_without_modules_gains_the_column(tmp_path):
    import sqlite3
    path = tmp_path / "gateway.db"
    s = GatewayStore(path, scrypt_n=2**4)
    uid = _user(s)
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE users DROP COLUMN modules")
    con.commit()
    con.close()
    s2 = GatewayStore(path, scrypt_n=2**4)
    assert s2.schema_version() == 3
    assert next(u for u in s2.list_users(0.0) if u["id"] == uid)["modules"]["trends"] is False


def test_modules_are_saved_through_the_update_route_and_on_create(rig):  # noqa: F811
    admin, _ = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    r = admin.post(f"{API}/users/update", json={"id": uid, "modules": {"snapshot": True, "projections": True}})
    assert r.status_code == 200, r.get_data(as_text=True)
    ann = next(u for u in admin.get(f"{API}/users").get_json()["users"] if u["id"] == uid)
    assert ann["modules"] == {"snapshot": True, "trends": False, "projections": True, "money_view": "percent"}
    c = admin.post(f"{API}/users", json={"username": "bo", "display_name": "Bo", "role": "user",
                                           "temp_password": "temporary password 1", "notes": "n",
                                           "modules": {"trends": True}})
    assert c.status_code == 200, c.get_data(as_text=True)
    bo = rig.store.get_user(c.get_json()["id"])
    assert bo["notes"] == "n" and '"trends": true' in bo["modules"]
    bad = admin.post(f"{API}/users", json={"username": "cy", "display_name": "Cy", "role": "user",
                                             "temp_password": "temporary password 1", "modules": {"x": True}})
    assert bad.status_code == 400 and rig.store.find_user("cy") is None  # validated before anything is created
    assert admin.post(f"{API}/users/update", json={"id": uid, "modules": {"trends": "on"}}).status_code == 400


def test_modules_are_admin_only_and_never_reach_the_user_or_the_worker(rig):  # noqa: F811
    ann, uid = rig.signed_in("ann")
    rig.store.set_profile(uid, modules={"trends": True}, now=rig.now[0], actor=CLI)
    other = rig.add_user("bob")
    assert ann.post(f"{API}/users/update", json={"id": other, "modules": {"trends": True}}).status_code == 403
    assert next(u for u in rig.store.list_users(rig.now[0]) if u["id"] == other)["modules"]["trends"] is False
    blob = ann.get("/api/auth/session").get_data(as_text=True)
    assert "modules" not in blob and "trends" not in blob
    assert all("trends" not in repr(c) for c in rig.upstream.calls)
