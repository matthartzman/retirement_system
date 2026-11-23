"""SEC-05 and SEC-10: failures lock a username only for the source that made them.

An attacker spraying one username from many addresses must not lock the owner out from the owner's own (known-good)
address; one address guessing is still stopped after five failures; change-password honours the throttle and lock.
"""
from __future__ import annotations

import pytest

from src import access_core
from src.gateway import store as gstore
from src.gateway.store import Actor, GatewayStore
from tests.gateway_rig import PW, Rig

ROOT = Actor(None, "cli")


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


@pytest.fixture()
def store(tmp_path):
    return GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)


def _wait_out_lock(rig, browser):
    """Let the lock lapse while keeping the session alive (its idle limit equals the lock time)."""
    for _ in range(3):
        rig.advance(350)
        assert browser.get("/api/plan/rows").status_code == 200


def test_fifteen_addresses_cannot_lock_out_the_owners_known_good_address(rig):
    b, _uid = rig.signed_in("ann", ip="203.0.113.5")  # a completed sign-in makes this address known-good
    for i in range(15):
        a = rig.browser(ip=f"198.51.100.{i + 10}")
        for _ in range(gstore.MAX_FAILED_BEFORE_LOCK):
            assert a.login("ann", "wrong password!!").status_code in (401, 429)  # 429: the username's soft delay
    rig.advance(700)  # past the soft delay window, still inside the 15 minute hard lock window
    again = rig.browser(ip="203.0.113.5")
    assert again.login("ann").status_code == 200


def test_attacker_addresses_are_not_locked_by_another_sources_failures(rig):
    rig.add_user("ann")
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK - 1):
        rig.browser(ip="198.51.100.1").login("ann", "wrong password!!")
    # a different, unknown address still gets its own five tries, then the right password works there
    assert rig.browser(ip="198.51.100.2").login("ann", "wrong password!!").status_code == 401
    assert rig.browser(ip="198.51.100.2").login("ann").status_code == 200


def test_one_address_guessing_is_locked_after_five_failures(rig):
    rig.add_user("ann")
    a = rig.browser(ip="198.51.100.1")
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK):
        a.login("ann", "wrong password!!")
    assert a.login("ann").status_code == 401  # right password, that address is locked
    rig.advance(gstore.LOCK_SECONDS + 1)
    assert a.login("ann").status_code == 200


def test_distributed_failures_past_the_account_threshold_lock_unknown_addresses_only(store):
    uid = store.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    store.touch_login(uid, 1, source="203.0.113.5")
    for i in range(access_core.MAX_FAILED_ACCOUNT):
        store.record_failure(uid, 10, source=f"10.0.{i // 250}.{i % 250}")
    assert store.is_locked(uid, 11, source="198.51.100.200") is True
    assert store.is_locked(uid, 11, source="203.0.113.5") is False
    assert store.verify_password("ann", PW, now=12, source="198.51.100.200").reason == "locked"
    assert store.verify_password("ann", PW, now=12, source="203.0.113.5").ok
    store.unlock(uid, now=13, actor=ROOT)
    assert store.is_locked(uid, 14, source="198.51.100.200") is False


def test_unlock_clears_source_locks_and_admin_list_shows_them(store):
    uid = store.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK):
        store.record_failure(uid, 5, source="198.51.100.1")
    assert store.list_users(6)[0]["locked"] is True
    store.unlock(uid, now=7, actor=ROOT)
    assert store.list_users(8)[0]["locked"] is False
    assert store.is_locked(uid, 8, source="198.51.100.1") is False


def test_a_successful_sign_in_from_one_address_does_not_clear_another_addresses_count(store):
    uid = store.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK - 1):
        store.record_failure(uid, 5, source="198.51.100.1")
    store.touch_login(uid, 6, source="203.0.113.5")
    assert store.record_failure(uid, 7, source="198.51.100.1") is True


def test_change_password_is_throttled_and_locks_after_failures(rig):
    b, _uid = rig.signed_in("ann")
    codes = []
    for _ in range(30):
        codes.append(b.post("/api/auth/password", json={"current": "wrong password!!", "new": "another long password"}).status_code)
    assert 429 in codes
    assert codes[0] == 400
    _wait_out_lock(rig, b)  # the correct current password works again only once the throttle and lock have lapsed
    r = b.post("/api/auth/password", json={"current": PW, "new": "another long password"})
    assert r.status_code == 200


def test_correct_current_password_is_refused_while_the_source_is_locked(rig):
    b, _uid = rig.signed_in("ann")
    for _ in range(gstore.MAX_FAILED_BEFORE_LOCK):
        b.post("/api/auth/password", json={"current": "wrong password!!", "new": "another long password"})
    r = b.post("/api/auth/password", json={"current": PW, "new": "another long password"})
    assert r.status_code == 429
    _wait_out_lock(rig, b)
    assert b.post("/api/auth/password", json={"current": PW, "new": "another long password"}).status_code == 200


def test_login_rehashes_a_password_stored_with_a_weaker_scrypt_cost(tmp_path):
    weak = GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)
    uid = weak.create_user("ann", "Ann", "user", PW, now=0, actor=ROOT, must_change=False)
    strong = GatewayStore(tmp_path / "gateway.db", scrypt_n=2**5)
    assert strong.verify_password("ann", PW, now=1).ok
    assert strong.get_user(uid)["scrypt_n"] == 2**5
    assert strong.verify_password("ann", PW, now=2).ok
