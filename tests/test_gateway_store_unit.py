"""gateway.db: schema versioning, accounts, lockout, TOTP, sessions, the last-admin rule, audit."""
from __future__ import annotations

import sqlite3

import pytest

from src.gateway import store as gstore
from src.gateway import totp
from src.gateway.store import Actor, GatewayStore, LastAdminError

PW = "a long enough password"
ROOT = Actor(None, "cli")


@pytest.fixture()
def store(tmp_path):
    return GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)


def _admin(store, name="root", now=0.0):
    return store.create_user(name, name.title(), "admin", PW, now=now, actor=ROOT, must_change=False)


def _user(store, name="ann", now=0.0):
    return store.create_user(name, name.title(), "user", PW, now=now, actor=ROOT, must_change=False)


def test_schema_version_is_recorded_and_reopen_is_idempotent(tmp_path):
    s = GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)
    assert s.schema_version() == gstore.SCHEMA_VERSION >= 1
    _admin(s)
    s2 = GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)
    assert s2.schema_version() == gstore.SCHEMA_VERSION
    assert s2.find_user("root") is not None
    conn = sqlite3.connect(tmp_path / "gateway.db")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"users", "totp_secrets", "sessions", "audit_log"} <= tables


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "gateway.db"
    GatewayStore(path, scrypt_n=2**4)
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {gstore.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        GatewayStore(path, scrypt_n=2**4)


def test_create_user_validates_and_hashes(store):
    uid = _user(store)
    row = store.get_user(uid)
    assert row["role"] == "user" and PW.encode() not in row["pw_hash"]
    with pytest.raises(ValueError):
        store.create_user("ann", "Ann 2", "user", PW, now=0, actor=ROOT)  # duplicate
    with pytest.raises(ValueError):
        store.create_user("Bad Name!", "x", "user", PW, now=0, actor=ROOT)
    with pytest.raises(ValueError):
        store.create_user("bob", "Bob", "owner", PW, now=0, actor=ROOT)
    with pytest.raises(ValueError):
        store.create_user("bob", "Bob", "user", "short", now=0, actor=ROOT)
    assert store.create_user("Bob", "Bob", "user", PW, now=0, actor=ROOT) == store.find_user("bob")["id"]


def test_list_users_never_returns_secrets(store):
    uid = _user(store)
    store.begin_totp_enrolment(uid, now=0)
    text = repr(store.list_users(now=0))
    assert "pw_hash" not in text and "pw_salt" not in text and "secret" not in text
    entry = store.list_users(now=0)[0]
    assert entry["username"] == "ann" and entry["totp"] == "pending" and entry["locked"] is False


def test_lockout_after_five_failures_and_generic_reason(store):
    uid = _user(store)
    for _ in range(4):
        assert store.verify_password("ann", "wrong password!", now=100).reason == "bad"
    res = store.verify_password("ann", "wrong password!", now=100)
    assert not res.ok and res.reason == "locked"
    assert store.verify_password("ann", PW, now=101).reason == "locked"  # right password, still locked
    assert store.verify_password("ann", PW, now=100 + gstore.LOCK_SECONDS + 1).ok
    assert store.verify_password("nobody", PW, now=0).reason == "unknown"
    store.set_disabled(uid, True, now=0, actor=ROOT)
    assert store.verify_password("ann", PW, now=10_000).reason == "disabled"


def test_record_failure_counts_toward_the_same_lock(store):
    uid = _user(store)
    for _ in range(4):
        assert store.record_failure(uid, now=5) is False
    assert store.record_failure(uid, now=5) is True
    assert store.verify_password("ann", PW, now=6).reason == "locked"
    store.unlock(uid, now=7, actor=ROOT)
    assert store.verify_password("ann", PW, now=8).ok


def test_totp_enrol_confirm_verify_and_replay(store):
    uid = _user(store)
    assert store.totp_status(uid) == "none"
    secret = store.begin_totp_enrolment(uid, now=0)
    assert store.begin_totp_enrolment(uid, now=1) == secret  # same pending secret until confirmed
    assert store.totp_status(uid) == "pending"
    now = 80_000.0  # within the 24-hour enrol-by deadline of the account's creation at 0
    assert not store.confirm_totp(uid, "000000" if totp.code_at(secret, int(now // 30)) != "000000" else "111111", now=now)
    code = totp.code_at(secret, int(now // 30))
    assert store.confirm_totp(uid, code, now=now)
    assert store.totp_status(uid) == "enrolled"
    with pytest.raises(ValueError):
        store.begin_totp_enrolment(uid, now=now)
    assert not store.verify_totp(uid, code, now=now)  # replay of the confirming code
    later = now + 30
    assert store.verify_totp(uid, totp.code_at(secret, int(later // 30)), now=later)
    store.reset_totp(uid, now=later, actor=ROOT)
    assert store.totp_status(uid) == "none"


def test_session_idle_and_absolute_expiry(store):
    uid = _user(store)
    token, csrf = store.create_session(uid, "active", now=0, client_ip="1.2.3.4")
    sess = store.get_session(token, now=10)
    assert sess["user_id"] == uid and sess["csrf_token"] == csrf and sess["stage"] == "active"
    assert store.get_session(token + "x", now=10) is None
    assert store.get_session(token, now=gstore.IDLE_SECONDS + 1) is None  # idle
    assert store.get_session(token, now=0) is None  # deleted, not merely hidden

    token, _ = store.create_session(uid, "active", now=0, client_ip="")
    t = 0.0
    while t + gstore.IDLE_SECONDS / 2 < gstore.ABSOLUTE_SECONDS:
        t += gstore.IDLE_SECONDS / 2
        assert store.get_session(token, now=t) is not None
        store.touch_session(token, now=t)
    t = gstore.ABSOLUTE_SECONDS - 1
    assert store.get_session(token, now=t) is not None
    store.touch_session(token, now=t)
    assert store.get_session(token, now=gstore.ABSOLUTE_SECONDS + 1) is None  # 2 s idle: absolute limit


def test_pending_session_has_a_short_life(store):
    uid = _user(store)
    token, _ = store.create_session(uid, "pending", now=0, client_ip="")
    assert store.get_session(token, now=gstore.PENDING_SECONDS - 1) is not None
    assert store.get_session(token, now=gstore.PENDING_SECONDS + 1) is None


def test_session_token_stored_only_as_hash_and_rotation(store, tmp_path):
    uid = _user(store)
    token, csrf = store.create_session(uid, "pending", now=0, client_ip="")
    raw = (tmp_path / "gateway.db").read_bytes()
    assert token.encode() not in raw
    new_token, new_csrf = store.rotate_session(token, "active", now=1)
    assert new_token != token and new_csrf != csrf
    assert store.get_session(token, now=2) is None
    assert store.get_session(new_token, now=2)["stage"] == "active"


def test_disable_delete_and_reset_end_sessions(store):
    _admin(store)
    uid = _user(store)
    token, _ = store.create_session(uid, "active", now=0, client_ip="")
    store.set_disabled(uid, True, now=1, actor=ROOT)
    assert store.get_session(token, now=2) is None
    store.set_disabled(uid, False, now=3, actor=ROOT)
    token, _ = store.create_session(uid, "active", now=3, client_ip="")
    store.set_password(uid, "another long password", must_change=True, now=4, actor=ROOT, event="password reset")
    assert store.get_session(token, now=5) is None
    token, _ = store.create_session(uid, "active", now=5, client_ip="")
    store.delete_user(uid, now=6, actor=ROOT)
    assert store.get_session(token, now=7) is None and store.get_user(uid) is None


def test_last_admin_cannot_be_demoted_disabled_or_deleted(store):
    a = _admin(store, "root")
    with pytest.raises(LastAdminError):
        store.set_role(a, "user", now=0, actor=ROOT)
    with pytest.raises(LastAdminError):
        store.set_disabled(a, True, now=0, actor=ROOT)
    with pytest.raises(LastAdminError):
        store.delete_user(a, now=0, actor=ROOT)
    b = _admin(store, "second")
    store.set_disabled(b, True, now=0, actor=ROOT)  # b disabled: a is still the last *active* admin
    with pytest.raises(LastAdminError):
        store.set_role(a, "user", now=0, actor=ROOT)
    store.set_disabled(b, False, now=0, actor=ROOT)
    store.set_role(a, "user", now=0, actor=ROOT)  # b remains
    assert store.count_active_admins() == 1
    with pytest.raises(LastAdminError):
        store.delete_user(b, now=0, actor=ROOT)
    store.set_role(a, "admin", now=0, actor=ROOT)
    store.delete_user(b, now=0, actor=ROOT)
    assert store.count_active_admins() == 1


def test_admin_actions_are_audited_with_the_acting_admin(store):
    a = _admin(store, "root")
    actor = Actor(a, "root", client_ip="9.9.9.9", listener="funnel")
    uid = store.create_user("ann", "Ann", "user", PW, now=1, actor=actor)
    store.set_role(uid, "admin", now=2, actor=actor)
    store.set_role(uid, "user", now=3, actor=actor)
    store.set_disabled(uid, True, now=4, actor=actor)
    store.set_disabled(uid, False, now=5, actor=actor)
    store.unlock(uid, now=6, actor=actor)
    store.set_password(uid, "another long password", must_change=True, now=7, actor=actor, event="password reset")
    store.reset_totp(uid, now=8, actor=actor)
    store.delete_user(uid, now=9, actor=actor)
    rows = store.read_audit(limit=50)
    events = [r["event"] for r in rows if r["actor_user_id"] == a]
    for ev in ["user created", "role changed", "user disabled", "user enabled", "user unlocked", "password reset",
               "totp reset", "user deleted"]:
        assert ev in events, ev
    deleted = next(r for r in rows if r["event"] == "user deleted")
    assert deleted["target_username"] == "ann" and deleted["client_ip"] == "9.9.9.9" and deleted["listener"] == "funnel"
    assert PW not in repr(rows)


def test_audit_details_are_truncated(store):
    store.audit("note", now=0, actor=ROOT, details="x" * 2000)
    assert len(store.read_audit(limit=1)[0]["details"]) <= 300
