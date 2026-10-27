"""Remote access: accounts, password hashing, lockout, throttle and idle sessions."""
from __future__ import annotations

import pytest

from financial_trends_reporter.access_store import LOCK_SECONDS, AccessStore
from financial_trends_reporter.sessions import SessionTable


def _store(tmp_path):
    return AccessStore(tmp_path / "access.db", scrypt_n=2**4)


def test_password_hash_is_salted_and_verifies(tmp_path):
    store = _store(tmp_path)
    a = store.add_user("Ann", "ann", "correct horse")
    b = store.add_user("Bob", "bob", "correct horse")
    ua, ub = store.get_user(a), store.get_user(b)
    assert ua["pw_salt"] != ub["pw_salt"] and ua["pw_hash"] != ub["pw_hash"]
    assert b"correct horse" not in ua["pw_hash"]
    assert store.verify_login("ann", "correct horse", 0).ok
    assert not store.verify_login("ann", "wrong password", 0).ok


def test_short_password_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.add_user("Ann", "ann", "short")


def test_five_wrong_passwords_lock_for_15_minutes_then_clear(tmp_path):
    store = _store(tmp_path)
    store.add_user("Ann", "ann", "correct horse")
    for _ in range(5):
        assert not store.verify_login("ann", "nope nope nope", 100).ok
    assert store.verify_login("ann", "correct horse", 101).reason == "locked"
    assert store.verify_login("ann", "correct horse", 100 + LOCK_SECONDS + 1).ok


def test_reset_clears_lockout(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", "correct horse")
    for _ in range(5):
        store.verify_login("ann", "nope nope nope", 100)
    store.set_password(uid, "another pass 1", must_change=True)
    result = store.verify_login("ann", "another pass 1", 101)
    assert result.ok and result.must_change


def test_unknown_user_and_wrong_password_give_same_result_shape(tmp_path):
    store = _store(tmp_path)
    store.add_user("Ann", "ann", "correct horse")
    unknown = store.verify_login("nobody", "whatever whatever", 0)
    wrong = store.verify_login("ann", "whatever whatever", 0)
    assert (unknown.ok, unknown.reason, unknown.must_change) == (wrong.ok, wrong.reason, wrong.must_change)


def test_duplicate_username_rejected(tmp_path):
    store = _store(tmp_path)
    store.add_user("Ann", "ann", "correct horse")
    with pytest.raises(ValueError):
        store.add_user("Ann 2", "ANN", "correct horse")


def test_global_delay_grows_after_20_failures_in_10_minutes(tmp_path):
    store = _store(tmp_path)
    for i in range(20):
        store.verify_login(f"user{i}", "guess guess guess", 1000)
    assert store.global_delay(1000) == 0
    for i in range(3):
        store.verify_login(f"more{i}", "guess guess guess", 1000)
    assert store.global_delay(1000) > 0
    assert store.global_delay(1000 + 601) == 0


def test_idle_session_expires_after_10_minutes_and_note_interaction_extends_it():
    now = [0.0]
    table = SessionTable(clock=lambda: now[0])
    token = table.create(7)
    now[0] = 590
    table.note_interaction(token, idle_ms=0)  # the person just touched the page
    now[0] = 1100
    assert table.get(token) is not None
    now[0] = 1190
    assert table.get(token) is None


def test_pings_that_report_no_new_interaction_do_not_extend_the_session():
    now = [0.0]
    table = SessionTable(clock=lambda: now[0])
    token = table.create(7)
    for t in range(5, 600, 5):
        now[0] = t
        table.note_interaction(token, idle_ms=t * 1000)  # last touched at t=0
    now[0] = 601
    assert table.get(token) is None


def test_end_user_kills_all_sessions():
    table = SessionTable()
    t1, t2, other = table.create(1), table.create(1), table.create(2)
    table.end_user(1)
    assert table.get(t1) is None and table.get(t2) is None and table.get(other) is not None
