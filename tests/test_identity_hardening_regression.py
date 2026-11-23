"""X-8 (lock timing oracle, atomic TOTP key creation) and SEC-06 (scrypt cost, common passwords)."""
from __future__ import annotations

import threading
import time

import pytest

from src import access_core
from src.common_passwords import is_common_password
from src.identity import totp as totp_lib
from src.identity.store import IdentityStore

PW = "a long enough password"


def test_default_scrypt_cost_was_raised_and_still_fits_the_memory_cap():
    assert access_core.DEFAULT_SCRYPT_N >= 2**16
    access_core.hash_password("x", b"\0" * 16, access_core.DEFAULT_SCRYPT_N)  # 64 MiB: under the 128 MiB maxmem


@pytest.mark.parametrize("pw", ["password123", "Password123", "PASSWORD-123", "1234567890", "qwertyuiop", "aaaaaaaaaaaa",
                                "abcdefghijkl", "Retirement2026", "iloveyou123", "p@ssw0rd123"])
def test_common_passwords_are_refused(pw):
    assert is_common_password(pw)
    with pytest.raises(ValueError, match="everyone tries first"):
        access_core.check_password_policy(pw, 10)


@pytest.mark.parametrize("pw", ["a long enough password", "correct horse battery", "Tr0ub4dor&3-staple", "temporary password 1"])
def test_ordinary_long_passwords_still_pass(pw):
    access_core.check_password_policy(pw, 10)
    assert not is_common_password(pw)


def test_the_length_rule_still_comes_first():
    with pytest.raises(ValueError, match="at least"):
        access_core.check_password_policy("short", 10)


def _store(tmp_path):
    return IdentityStore(tmp_path / "identity.db", scrypt_n=2**4, totp_key=lambda: b"k" * 32)


def test_a_locked_account_still_costs_a_password_hash(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.add_user("Ann", "ann", PW, now=0)
    for _ in range(access_core.MAX_FAILED_BEFORE_LOCK):
        store.verify_login("ann", "wrong password here", 10)
    calls = []
    real = access_core.password_matches
    monkeypatch.setattr(access_core, "password_matches", lambda *a, **k: calls.append(1) or real(*a, **k))
    res = store.verify_login("ann", PW, 11)  # locked: the right password still fails
    assert res.reason == "locked" and not res.ok
    assert calls == [1]  # the hash was computed before the lock short-circuit, as for an unlocked account


def test_default_key_is_minted_once_under_concurrent_first_use(monkeypatch):
    stored: dict[str, str] = {}
    sets: list[str] = []

    def get(name, *a, **k):
        return stored.get(name, "")

    def set_(name, value, *a, **k):
        time.sleep(0.05)  # widen the race window
        sets.append(value)
        stored[name] = value

    from src import secrets_store

    monkeypatch.setattr(secrets_store, "get_secret", get)
    monkeypatch.setattr(secrets_store, "set_secret", set_)
    keys: list[bytes] = []
    start = threading.Barrier(6)

    def run():
        start.wait()
        keys.append(totp_lib.default_key())

    threads = [threading.Thread(target=run) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(sets) == 1, "two callers each minted a key"
    assert len(set(keys)) == 1 and len(keys) == 6
