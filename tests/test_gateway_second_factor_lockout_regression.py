"""Wrong second-factor codes keep counting toward the account lock across password re-entries.

An attacker who already knows a password must not be able to reset the failure counter by
re-entering the password between batches of wrong codes (that gave unlimited code guesses, bounded
only by the per-address throttle).
"""
from __future__ import annotations

import pytest

from src.gateway import store as gstore
from src.gateway.store import Actor, GatewayStore

PW = "a long enough password"
ROOT = Actor(None, "cli")


@pytest.fixture()
def store(tmp_path):
    return GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)


def test_correct_password_alone_does_not_reset_wrong_code_count(store):
    uid = store.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    locked = False
    for cycle in range(3):  # three password entries, two wrong codes each
        assert store.verify_password("ann", PW, now=10 + cycle).ok
        for _ in range(2):
            locked = store.record_failure(uid, now=10 + cycle) or locked
    assert locked, "six wrong codes across three sign-ins never locked the account"
    assert store.verify_password("ann", PW, now=20).reason == "locked"


def test_a_completed_sign_in_clears_the_count(store):
    uid = store.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    for _ in range(3):
        store.record_failure(uid, now=1)
    store.clear_failures(uid)
    for _ in range(4):
        assert store.record_failure(uid, now=2) is False
    assert gstore.MAX_FAILED_BEFORE_LOCK == 5


def test_a_failure_recorded_while_locked_keeps_the_lock(store):
    """Parallel guesses can pass the lock check together; the late ones must not unlock the account."""
    uid = store.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    for _ in range(5):
        store.record_failure(uid, now=10)
    assert store.is_locked(uid, 11)
    assert store.record_failure(uid, now=11) is True
    assert store.is_locked(uid, 12)
    assert store.verify_password("ann", PW, now=13).reason == "locked"
