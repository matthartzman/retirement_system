"""X-8: a locked account costs the same password work as any other refusal, and two first uses of the TOTP sealing key
cannot mint two keys."""
from __future__ import annotations

import threading

from src import access_core, secrets_store
from src.identity import totp
from src.identity.store import IdentityStore

KEY = b"k" * 32


def _store(tmp_path):
    return IdentityStore(tmp_path / "identity.db", scrypt_n=2**4, totp_key=lambda: KEY)


def test_a_locked_account_still_burns_a_password_check(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.add_user("Ann", "ann", "correct horse battery")
    for _ in range(60):  # past any lock threshold
        store.verify_login("ann", "wrong password here", now=1000.0)
    burned = []
    real = access_core.burn_password_check
    monkeypatch.setattr(access_core, "burn_password_check", lambda pw, n: (burned.append(1), real(pw, n))[1])
    result = store.verify_login("ann", "correct horse battery", now=1001.0)
    assert result.reason == "locked" and burned == [1]


def test_default_key_is_created_once_under_concurrency(monkeypatch):
    stored = {}

    def get(name):
        return stored.get(name)

    def put(name, value):
        threading.Event().wait(0.01)  # widen the race window
        stored[name] = value

    monkeypatch.setattr(secrets_store, "get_secret", get)
    monkeypatch.setattr(secrets_store, "set_secret", put)
    keys = []
    threads = [threading.Thread(target=lambda: keys.append(totp.default_key())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(keys) == 8 and len(set(keys)) == 1
