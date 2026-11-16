"""Shared identity store: schema, grants, epochs, roles, status, expiry, last-admin rule, audit, CLI."""
from __future__ import annotations

import sqlite3

import pytest

from src.identity import IdentityStore, LastAdminError, SCHEMA_VERSION
from src.identity import cli
from src.identity.store import LOCK_SECONDS

PW = "correct horse"


def _store(tmp_path):
    return IdentityStore(tmp_path / "local_state" / "identity.db", scrypt_n=2**4)


def test_schema_version_continues_from_access_db(tmp_path):
    store = _store(tmp_path)
    conn = sqlite3.connect(store.path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 3
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "app_grants", "totp", "activity", "admin_audit"} <= tables
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert {"role", "status", "expires_at", "session_epoch", "notes"} <= cols and "money_view" not in cols


def test_password_policy_lockout_and_lowercase_usernames(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.add_user("Ann", "ann", "short")
    uid = store.add_user("Ann", "  ANN ", PW)
    assert store.get_user(uid)["username"] == "ann"
    with pytest.raises(ValueError):
        store.add_user("Ann2", "Ann", PW)
    for _ in range(5):
        assert not store.verify_login("ann", "nope nope nope", 100).ok
    assert store.verify_login("ann", PW, 101).reason == "locked"
    assert store.verify_login("ann", PW, 100 + LOCK_SECONDS + 1).ok


def test_money_view_lives_on_the_insights_grant(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW, money_view="both")
    assert store.get_grant(uid, "insights")["money_view"] == "both"
    store.set_money_view(uid, "dollars")
    assert store.get_grant(uid, "insights")["money_view"] == "dollars"
    assert store.get_user(uid)["money_view"] == "dollars"
    with pytest.raises(ValueError):
        store.set_money_view(uid, "cents")
    bare = store.add_user("Bob", "bob", PW, insights=False)
    assert store.get_grant(bare, "insights") is None
    with pytest.raises(ValueError):
        store.set_money_view(bare, "dollars")


def test_grant_views_round_trip_and_planner_has_no_money_view(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    store.set_grant(uid, "insights", money_view="percent", views=["trends"])
    assert store.get_grant(uid, "insights")["views"] == ["trends"]
    store.set_grant(uid, "planner", money_view="dollars", views=["x"])
    assert store.get_grant(uid, "planner")["money_view"] is None and store.get_grant(uid, "planner")["views"] is None
    with pytest.raises(ValueError):
        store.set_grant(uid, "other")
    assert [g["app"] for g in store.list_grants(uid)] == ["insights", "planner"]


def test_epoch_bumps_on_every_revoking_change(tmp_path):
    store = _store(tmp_path)
    admin = store.add_user("Root", "root", PW, role="admin", insights=False)
    uid = store.add_user("Ann", "ann", PW)
    seen = [store.session_epoch(uid)]

    def bumped():
        now = store.session_epoch(uid)
        assert now > seen[-1]
        seen.append(now)

    store.set_password(uid, "another long one", False); bumped()
    store.set_grant(uid, "insights", money_view="both"); bumped()
    store.set_money_view(uid, "dollars"); bumped()
    store.set_grant(uid, "planner"); assert store.session_epoch(uid) == seen[-1]  # a new grant revokes nothing
    store.revoke_grant(uid, "planner"); bumped()
    store.set_status(uid, "disabled"); bumped()
    store.set_status(uid, "active"); assert store.session_epoch(uid) == seen[-1]
    store.update_user(uid, expires_at=1.0, now=5.0); bumped()
    store.end_sessions(uid); bumped()
    assert store.session_epoch(admin) == 0
    store.set_password(uid, "third long one", False, end_sessions=False)
    assert store.session_epoch(uid) == seen[-1]


def test_unchanged_grant_does_not_bump_epoch(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    before = store.session_epoch(uid)
    store.set_grant(uid, "insights", money_view="percent")
    assert store.session_epoch(uid) == before


def test_disabled_and_expired_accounts_are_refused_like_a_wrong_password(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    assert store.verify_login("ann", PW, 10).ok
    store.set_status(uid, "disabled", now=10)
    refused = store.verify_login("ann", PW, 11)
    wrong = store.verify_login("nobody", PW, 11)
    assert (refused.ok, refused.reason, refused.user_id) == (wrong.ok, wrong.reason, wrong.user_id) == (False, "bad", None)
    assert not store.can_sign_in(uid, 11)
    store.set_status(uid, "active", now=12)
    store.update_user(uid, expires_at=100.0, now=12)
    assert store.verify_login("ann", PW, 50).ok and store.can_sign_in(uid, 50)
    assert not store.verify_login("ann", PW, 100).ok and not store.can_sign_in(uid, 100)


def test_last_active_admin_is_protected(tmp_path):
    store = _store(tmp_path)
    a = store.add_user("A", "a", PW, role="admin", insights=False, now=0)
    with pytest.raises(LastAdminError):
        store.update_user(a, role="user", now=1)
    with pytest.raises(LastAdminError):
        store.set_status(a, "disabled", now=1)
    with pytest.raises(LastAdminError):
        store.update_user(a, expires_at=2.0, now=5)
    with pytest.raises(LastAdminError):
        store.delete_user(a, now=1)
    b = store.add_user("B", "b", PW, role="admin", insights=False, now=0)
    store.set_status(b, "disabled", now=1)  # a is still active, so b may go
    with pytest.raises(LastAdminError):
        store.delete_user(a, now=1)  # b is disabled, so a is again the last
    store.set_status(b, "active", now=2)
    store.update_user(a, role="user", now=3)
    assert store.get_user(a)["role"] == "user"
    store.update_user(b, expires_at=10.0, now=3)  # in the future: still active
    with pytest.raises(LastAdminError):
        store.update_user(b, expires_at=4.0, now=5)


def test_an_expired_admin_does_not_count_as_the_other_admin(tmp_path):
    store = _store(tmp_path)
    a = store.add_user("A", "a", PW, role="admin", insights=False, now=0)
    store.add_user("B", "b", PW, role="admin", insights=False, now=0, expires_at=50.0)
    with pytest.raises(LastAdminError):
        store.set_status(a, "disabled", now=60)


def test_non_admins_can_be_removed_freely_and_delete_clears_grants(tmp_path):
    store = _store(tmp_path)
    store.add_user("A", "a", PW, role="admin", insights=False)
    uid = store.add_user("Ann", "ann", PW)
    store.delete_user(uid)
    assert store.get_user(uid) is None and store.list_grants(uid) == []


def test_activity_carries_the_app_and_filters_by_it(tmp_path):
    store = _store(tmp_path)
    store.log_event("ann", "remote", "signed in", now=1)
    store.log_event("ann", "remote", "opened plan", now=2, app="planner")
    assert {e["app"] for e in store.read_events()} == {"insights", "planner"}
    assert [e["event"] for e in store.read_events(app="planner")] == ["opened plan"]
    assert [e["event"] for e in store.read_events(person="ann", since=1.5)] == ["opened plan"]


def test_admin_audit_is_recorded_and_bounded(tmp_path):
    store = _store(tmp_path)
    store.log_admin("root", "disable", "ann", "x" * 1000, now=1)
    store.log_admin("root", "enable", "ann", now=2)
    rows = store.read_audit()
    assert [r["action"] for r in rows] == ["enable", "disable"]
    assert len(rows[1]["details"]) == 300


def test_create_admin_cli(tmp_path, capsys):
    db = tmp_path / "identity.db"
    answers = iter([PW, PW])
    assert cli.main(["create-admin", "--username", "Owner", "--db", str(db)], read_password=lambda _p: next(answers)) == 0
    store = IdentityStore(db, scrypt_n=2**4)
    user = store.get_user_by_username("owner")
    assert user["role"] == "admin" and user["status"] == "active" and not user["must_change"]
    assert store.get_grant(user["id"], "insights") is None
    assert store.read_audit()[0]["action"] == "create-admin"
    assert PW not in capsys.readouterr().out


def test_create_admin_cli_refuses_mismatch_short_and_duplicate(tmp_path):
    db = tmp_path / "identity.db"
    args = ["create-admin", "--username", "owner", "--db", str(db)]
    mismatch = iter([PW, "different one!"])
    assert cli.main(args, read_password=lambda _p: next(mismatch)) == 1
    short = iter(["short", "short"])
    assert cli.main(args, read_password=lambda _p: next(short)) == 1
    ok = iter([PW, PW])
    assert cli.main(args, read_password=lambda _p: next(ok)) == 0
    again = iter([PW, PW])
    assert cli.main(args, read_password=lambda _p: next(again)) == 1


def test_reset_totp_removes_the_factor_and_ends_sessions(tmp_path):
    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
    uid = store.add_user("Ann", "ann", "correct horse")
    assert store.reset_totp(uid) is False
    store._run("INSERT INTO totp(user_id, secret, enrolled_at) VALUES (?, ?, 1)", (uid, b"x"))
    epoch = store.session_epoch(uid)
    assert store.reset_totp(uid) is True
    assert store._run("SELECT COUNT(*) AS n FROM totp").fetchall()[0]["n"] == 0
    assert store.session_epoch(uid) > epoch
