"""Worker-account bookkeeping without touching Windows accounts: the Win32 calls are replaced by fakes,
so this checks the flow, the stored DPAPI blob and that no password is ever logged."""
from __future__ import annotations

import logging
import os

import pytest

from src.gateway import accounts
from src.gateway.store import GatewayStore

pytestmark = [pytest.mark.unit, pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")]


def test_passwords_are_long_and_mixed():
    seen = set()
    for _ in range(50):
        pw = accounts.new_password()
        assert len(pw) == accounts.PASSWORD_LENGTH
        assert any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
        seen.add(pw)
    assert len(seen) == 50


class FakeWindows:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.rights: dict[str, set] = {}
        self.acl: list[tuple] = []
        self.profiles_deleted: list[str] = []

    def install(self, mp):
        mp.setattr(accounts, "net_user_add", self.add)
        mp.setattr(accounts, "net_user_reset_password", lambda n, p: self.users[n].update(pw=p))
        mp.setattr(accounts, "net_user_change_password", self.change)
        mp.setattr(accounts, "net_user_set_disabled", lambda n, d: self.users[n].update(disabled=d))
        mp.setattr(accounts, "net_user_delete", lambda n: self.users.pop(n, None) is not None)
        mp.setattr(accounts, "grant_worker_rights", lambda sid: self.rights.setdefault(sid, set()).update(accounts.WORKER_RIGHTS))
        mp.setattr(accounts, "remove_all_rights", lambda sid: self.rights.pop(sid, None))
        mp.setattr(accounts, "delete_profile", lambda sid: self.profiles_deleted.append(sid) or True)
        mp.setattr(accounts.winapi, "lookup_account_sid", lambda n: self.users[n]["sid"] if n in self.users else None)
        mp.setattr(accounts.acl, "lock_user_folder", lambda path, **kw: self.acl.append((path, kw)))

    def add(self, name, pw, comment):
        if name in self.users:
            return False
        self.users[name] = {"pw": pw, "sid": f"S-1-5-21-1-2-3-{1000 + len(self.users)}", "disabled": False}
        return True

    def change(self, name, old, new):
        if self.users[name]["pw"] != old:
            raise OSError(86, "wrong old password")
        self.users[name]["pw"] = new


@pytest.fixture
def mgr(tmp_path, monkeypatch, caplog):
    fake = FakeWindows()
    fake.install(monkeypatch)
    store = GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)
    now = [1_000_000.0]
    m = accounts.WindowsAccountManager(store, tmp_path / "data", gateway_sid="S-1-5-18", rotate_days=1,
                                       clock=lambda: now[0])
    caplog.set_level(logging.DEBUG)
    return m, fake, store, now


def test_create_grants_rights_locks_the_folder_and_stores_only_a_protected_password(mgr, tmp_path, caplog):
    m, fake, store, _ = mgr
    ws = tmp_path / "data" / "users" / "7"
    m.ensure(7, ws)
    pw = fake.users["rpw_7"]["pw"]
    sid = fake.users["rpw_7"]["sid"]
    assert fake.rights[sid] == set(accounts.WORKER_RIGHTS)
    assert fake.acl == [(ws, {"account_sid": sid, "gateway_sid": "S-1-5-18", "worker_stopped": True})]
    row = store.get_worker_account(7)
    assert row["sid"] == sid and pw.encode() not in bytes(row["secret"])
    assert m.credentials(7) == ("rpw_7", pw)
    assert pw not in caplog.text
    assert all("secret" not in r for r in store.list_worker_accounts())
    m.ensure(7, ws)  # idempotent
    assert len(fake.users) == 1


def test_a_leftover_account_gets_a_fresh_password(mgr, tmp_path):
    m, fake, _store, _ = mgr
    fake.add("rpw_3", "unknown old password", "")
    m.ensure(3, tmp_path / "w3")
    assert m.credentials(3)[1] == fake.users["rpw_3"]["pw"] != "unknown old password"


def test_disable_remove_and_rotation(mgr, tmp_path, caplog):
    m, fake, store, now = mgr
    m.ensure(5, tmp_path / "w5")
    sid = fake.users["rpw_5"]["sid"]
    old = fake.users["rpw_5"]["pw"]
    now[0] += 2 * 86400
    m.housekeeping({5})  # due: rotated by a change with the old password
    new = fake.users["rpw_5"]["pw"]
    assert new != old and m.credentials(5)[1] == new and old not in caplog.text and new not in caplog.text
    m.disable(5, True)
    assert fake.users["rpw_5"]["disabled"] and store.get_worker_account(5)["state"] == "disabled"
    with pytest.raises(RuntimeError):
        m.credentials(5)
    m.disable(5, False)
    m.housekeeping(set())  # the gateway user is gone: clean-up
    assert "rpw_5" not in fake.users and sid not in fake.rights and fake.profiles_deleted == [sid]
    assert store.get_worker_account(5) is None


def test_prefix_and_name_rules(tmp_path, monkeypatch):
    store = GatewayStore(tmp_path / "g.db", scrypt_n=2**4)
    with pytest.raises(ValueError):
        accounts.WindowsAccountManager(store, tmp_path, prefix="bad prefix", gateway_sid="S-1-5-18")
    m = accounts.WindowsAccountManager(store, tmp_path, prefix="rpwtest_", gateway_sid="S-1-5-18")
    assert m.account_name(12) == "rpwtest_12"
    with pytest.raises(ValueError):
        m.account_name(10**13)
