"""``acl._lock`` (``acl setup``) leaves only the entries it grants: an explicit entry for any other account, such as
one Explorer adds when an administrator clicks Continue on a locked folder, is removed, so re-running setup repairs
the folder. Portable: ``icacls`` and the DACL reader are replaced with recorders (the real ones need Windows;
``tests/test_gateway_acl_functional.py`` covers them there).
"""
from __future__ import annotations

import pytest

from src.gateway import acl

GATEWAY = acl.SYSTEM
STRAY = "S-1-12-1-1111111111-2222222222-3333333333-444444444"  # e.g. an administrator's own sign-in


class Recorder:
    def __init__(self, aces: list[str]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.aces = aces

    def icacls(self, *args: str) -> None:
        self.calls.append(args)
        if args[1] == "/remove":
            self.aces = [s for s in self.aces if f"*{s}" != args[2]]

    def read_dacl(self, path):
        return acl.Dacl(protected=True, aces=tuple(acl.Ace(s, True, 0x1F01FF, False) for s in self.aces))


@pytest.fixture()
def rec(monkeypatch):
    def make(aces):
        r = Recorder(aces)
        monkeypatch.setattr(acl, "_icacls", r.icacls)
        monkeypatch.setattr(acl, "read_dacl", r.read_dacl)
        return r
    return make


def test_an_explicit_entry_for_another_account_is_removed(tmp_path, rec):
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / "gateway.db").write_bytes(b"")
    r = rec([acl.SYSTEM, acl.ADMINISTRATORS, STRAY])
    acl.lock_gateway_only(folder, gateway_sid=GATEWAY)
    verbs = [c[1] for c in r.calls]
    assert verbs == ["/inheritance:r", "/remove", "/reset"]  # grant first, then remove, then the children inherit
    assert r.calls[1] == (str(folder), "/remove", f"*{STRAY}", "/C", "/Q")
    assert r.calls[2][0] == str(folder / "*")
    assert set(r.aces) == {acl.SYSTEM, acl.ADMINISTRATORS}


def test_the_granted_accounts_are_kept_and_nothing_is_removed_when_clean(tmp_path, rec):
    folder = tmp_path / "users" / "1"
    worker = "S-1-5-21-1-2-3-1005"
    r = rec([acl.SYSTEM, acl.ADMINISTRATORS, worker])
    acl.lock_user_folder(folder, account_sid=worker, gateway_sid=GATEWAY)
    assert [c[1] for c in r.calls] == ["/inheritance:r"]  # empty folder: no reset; nothing extra: no remove
    r2 = rec([acl.SYSTEM, acl.ADMINISTRATORS, acl.USERS])
    acl.lock_install_readonly(tmp_path / "app", gateway_sid=GATEWAY)
    assert "/remove" not in [c[1] for c in r2.calls]


def test_a_lock_that_leaves_no_access_list_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(acl, "_icacls", lambda *a: None)
    monkeypatch.setattr(acl, "read_dacl", lambda p: acl.Dacl(protected=True, aces=None))
    with pytest.raises(acl.AclError):
        acl.lock_gateway_only(tmp_path / "x", gateway_sid=GATEWAY)
