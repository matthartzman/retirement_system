"""access.db -> identity.db migration: hashes verify, money view lands on the grant, the old file is renamed."""
from __future__ import annotations

import sqlite3

import pytest

from financial_trends_reporter.access_store import AccessStore
from src.identity import IdentityStore, open_identity_store

PW = "correct horse"


def _legacy(tmp_path):
    legacy = AccessStore(tmp_path / "data" / "access.db", scrypt_n=2**4)
    ann = legacy.add_user("Ann", "ann", PW, money_view="dollars")
    bob = legacy.add_user("Bob", "bob", PW, money_view="both")
    legacy.set_password(bob, "bob own password", False)
    legacy.touch_last_signin(ann, 123.0)
    legacy.log_event("ann", "remote", "signed in", "from phone", "ua", now=5.0)
    legacy.log_event("bob", "remote", "viewed", now=6.0)
    return legacy


def _new(tmp_path):
    return IdentityStore(tmp_path / "local_state" / "identity.db", scrypt_n=2**4)


def test_migrated_hashes_still_verify_without_a_reset(tmp_path):
    legacy = _legacy(tmp_path)
    store = _new(tmp_path)
    result = store.migrate_access_db(legacy.path)
    assert result["migrated"] and result["users"] == 2 and result["events"] == 2
    assert store.verify_login("ann", PW, 10).ok
    login = store.verify_login("bob", "bob own password", 10)
    assert login.ok and not login.must_change
    assert store.verify_login("ann", "wrong password!", 10).ok is False
    assert store.verify_login("ann", PW, 10).must_change is True  # unchanged temp-password flag


def test_user_rows_are_copied_unchanged_with_default_new_columns(tmp_path):
    legacy = _legacy(tmp_path)
    old = {u["username"]: legacy.get_user(u["id"]) for u in legacy.list_users()}
    store = _new(tmp_path)
    store.migrate_access_db(legacy.path)
    for name, o in old.items():
        n = store.get_user_by_username(name)
        for col in ("id", "display_name", "pw_hash", "pw_salt", "scrypt_n", "must_change", "created_at", "last_signin_at"):
            assert n[col] == o[col], (name, col)
        assert (n["role"], n["status"], n["expires_at"], n["session_epoch"]) == ("user", "active", None, 0)


def test_money_view_lands_on_the_insights_grant(tmp_path):
    legacy = _legacy(tmp_path)
    store = _new(tmp_path)
    store.migrate_access_db(legacy.path)
    ann, bob = store.get_user_by_username("ann"), store.get_user_by_username("bob")
    ga, gb = store.get_grant(ann["id"], "insights"), store.get_grant(bob["id"], "insights")
    assert (ga["money_view"], gb["money_view"]) == ("dollars", "both")
    assert ga["views"] is None and ga["granted_by"] == "migration"
    assert store.get_grant(ann["id"], "planner") is None


def test_activity_is_copied_with_app_insights(tmp_path):
    legacy = _legacy(tmp_path)
    store = _new(tmp_path)
    store.migrate_access_db(legacy.path)
    events = store.read_events()
    assert [(e["person"], e["event"], e["app"]) for e in events] == [("bob", "viewed", "insights"), ("ann", "signed in", "insights")]
    assert events[1]["details"] == "from phone" and events[1]["source"] == "ua"


def test_access_db_is_renamed_never_deleted(tmp_path):
    legacy = _legacy(tmp_path)
    original = legacy.path
    store = _new(tmp_path)
    result = store.migrate_access_db(original)
    assert not original.exists()
    renamed = original.with_name("access.db.migrated")
    assert renamed.exists() and result["renamed_to"] == str(renamed)
    # the renamed file is still a readable copy of the original data
    assert sqlite3.connect(renamed).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2


def test_migration_runs_once_and_never_overwrites_an_earlier_rename(tmp_path):
    legacy = _legacy(tmp_path)
    store = _new(tmp_path)
    store.migrate_access_db(legacy.path)
    assert store.migrate_access_db(legacy.path) == {"migrated": False, "users": 0, "events": 0, "renamed_to": None}
    # a second old file appears; identity.db already has users, so it is left alone
    second = tmp_path / "data" / "access.db"
    sqlite3.connect(second).close()
    assert store.migrate_access_db(second)["migrated"] is False and second.exists()
    # an empty identity.db plus a leftover .migrated: the new rename picks a fresh name
    fresh = IdentityStore(tmp_path / "other" / "identity.db", scrypt_n=2**4)
    result = fresh.migrate_access_db(second)
    assert result["migrated"] and result["users"] == 0
    assert (tmp_path / "data" / "access.db.migrated").exists() and (tmp_path / "data" / "access.db.migrated.2").exists()


def test_no_access_db_means_a_plain_empty_store(tmp_path):
    store = open_identity_store(tmp_path / "identity.db", legacy_access_path=tmp_path / "data" / "access.db", scrypt_n=2**4)
    assert store.list_users() == []


def test_open_identity_store_migrates_on_first_start(tmp_path):
    legacy = _legacy(tmp_path)
    store = open_identity_store(tmp_path / "identity.db", legacy_access_path=legacy.path, scrypt_n=2**4)
    assert [u["username"] for u in store.list_users()] == ["ann", "bob"]
    assert not legacy.path.exists()


def test_a_version_one_access_db_migrates_with_percent_default(tmp_path):
    path = tmp_path / "data" / "access.db"
    path.parent.mkdir()
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, display_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,"
        " pw_hash BLOB NOT NULL, pw_salt BLOB NOT NULL, scrypt_n INTEGER NOT NULL, must_change INTEGER NOT NULL DEFAULT 1,"
        " created_at REAL NOT NULL, updated_at REAL NOT NULL, failed_count INTEGER NOT NULL DEFAULT 0,"
        " locked_until REAL NOT NULL DEFAULT 0, last_signin_at REAL)"
    )
    conn.execute("INSERT INTO users(display_name, username, pw_hash, pw_salt, scrypt_n, created_at, updated_at)"
                 " VALUES ('Old','old',x'00',x'00',16384,0,0)")
    conn.commit()
    conn.close()
    store = _new(tmp_path)
    assert store.migrate_access_db(path)["users"] == 1
    assert store.get_grant(store.get_user_by_username("old")["id"], "insights")["money_view"] == "percent"


def test_owner_becomes_first_admin_after_migration(tmp_path):
    from src.identity import cli

    legacy = _legacy(tmp_path)
    db = tmp_path / "local_state" / "identity.db"
    answers = iter([PW, PW])
    rc = cli.main(["create-admin", "--username", "owner", "--db", str(db), "--access-db", str(legacy.path)],
                  read_password=lambda _p: next(answers))
    assert rc == 0
    store = IdentityStore(db, scrypt_n=2**4)
    assert {u["username"]: u["role"] for u in store.list_users()} == {"ann": "user", "bob": "user", "owner": "admin"}
    assert (tmp_path / "data" / "access.db.migrated").exists()


def test_legacy_financial_insights_store_is_unchanged(tmp_path):
    """FI keeps its schema-2 access.db until Phase 3; the re-exported names are the shared ones."""
    from financial_trends_reporter import access_store as fi
    from src.identity import store as shared

    assert fi.LoginResult is shared.LoginResult and fi.MONEY_VIEWS is shared.MONEY_VIEWS
    legacy = _legacy(tmp_path)
    assert sqlite3.connect(legacy.path).execute("PRAGMA user_version").fetchone()[0] == 2
    with pytest.raises(ValueError):
        legacy.add_user("Ann", "ann", PW)
