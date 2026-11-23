"""SEC-02 / SEC-03: privileged gateway jobs verify the OPEN handle, not the name, and never reset a running worker's tree.

The Windows calls cannot run here: the comparison logic is a pure function, the Windows operations are driven by a
fake, and the POSIX operations are exercised with real symlinks (the Linux analogue of a junction swap)."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

from src.gateway import acl, fsguard, logs
from src.gateway import backup_store as bs


# ---- pure comparison (Windows spellings) ----
@pytest.mark.parametrize("final,root,ok", [
    (r"C:\data\users\1\plan.rpx", r"C:\data\users\1", True),
    (r"c:\DATA\users\1", r"C:\data\users\1", True),
    (r"C:\data\users\10\plan.rpx", r"C:\data\users\1", False),   # prefix of another folder name
    (r"C:\data\users\2\x", r"C:\data\users\1", False),
    (r"D:\elsewhere", r"C:\data\users\1", False),
    (r"C:\data\users\1\..\2\x", r"C:\data\users\1", False),
])
def test_final_path_inside_windows_spellings(final, root, ok):
    assert fsguard.final_path_inside(final, root, windows=True) is ok


def test_extended_prefix_is_stripped():
    from src.gateway import winapi

    assert winapi.strip_extended_prefix("\\\\?\\C:\\a") == "C:\\a"
    assert winapi.strip_extended_prefix("\\\\?\\UNC\\srv\\share\\a") == "\\\\srv\\share\\a"
    assert winapi.strip_extended_prefix("C:\\a") == "C:\\a"


# ---- the Windows operations, with a fake that stands in for CreateFileW / GetFinalPathNameByHandle ----
class FakeWinOps:
    """A tiny file system: name -> (final path, is_link). Records open handles so the test can see they stay open."""

    def __init__(self, table):
        self.table, self.open_handles, self.closed = table, {}, []
        self.next = 1

    def open(self, path):
        if path not in self.table:
            raise FileNotFoundError(path)
        h, self.next = self.next, self.next + 1
        self.open_handles[h] = path
        return h

    def is_link(self, handle):
        return self.table[self.open_handles[handle]][1]

    def final_path(self, handle, path):
        return self.table[self.open_handles[handle]][0]

    def close(self, handle):
        self.closed.append(self.open_handles.pop(handle))


def _abs(p: str) -> str:
    return os.path.abspath(p)


def test_pinned_accepts_a_path_that_resolves_inside_and_holds_the_handle_for_the_body():
    root, f = _abs("/d/u1"), _abs("/d/u1/plan.rpx")
    ops = FakeWinOps({root: (root, False), f: (f, False)})
    with fsguard.pinned(f, root, ops=ops) as final:
        assert final == f
        assert f in ops.open_handles.values()  # still open while the caller works
    assert not ops.open_handles and sorted(ops.closed) == sorted([root, f])


def test_pinned_refuses_a_junction_swapped_in_after_a_name_check():
    root, f = _abs("/d/u1"), _abs("/d/u1/local_state/app.db")
    # the name looks fine and is not itself a link, but the OPEN handle resolves into another user's folder
    ops = FakeWinOps({root: (root, False), f: (_abs("/d/u2/local_state/app.db"), False)})
    with pytest.raises(fsguard.UnsafePathError):
        with fsguard.pinned(f, root, ops=ops):
            pytest.fail("must not run the body")
    assert not ops.open_handles  # handles released even on refusal


def test_pinned_refuses_a_final_component_link_and_a_linked_root():
    root, f = _abs("/d/u1"), _abs("/d/u1/x")
    with pytest.raises(fsguard.UnsafePathError):
        with fsguard.pinned(f, root, ops=FakeWinOps({root: (root, False), f: (f, True)})):
            pass
    with pytest.raises(fsguard.UnsafePathError):
        with fsguard.pinned(f, root, ops=FakeWinOps({root: (root, True), f: (f, False)})):
            pass


def test_pinned_missing_file_is_a_plain_oserror():
    root = _abs("/d/u1")
    with pytest.raises(FileNotFoundError):
        with fsguard.pinned(_abs("/d/u1/none"), root, ops=FakeWinOps({root: (root, False)})):
            pass


# ---- the real POSIX operations with real symlinks ----
posix = pytest.mark.skipif(sys.platform == "win32", reason="symlink analogue of a junction swap")


@posix
def test_posix_pinned_refuses_symlink_final_and_intermediate(tmp_path):
    u1, u2 = tmp_path / "u1", tmp_path / "u2"
    (u1 / "d").mkdir(parents=True)
    u2.mkdir()
    (u1 / "d" / "f").write_text("mine")
    (u2 / "secret").write_text("theirs")
    with fsguard.pinned(u1 / "d" / "f", u1) as final:
        assert final.endswith("f")
    (u1 / "lnk").symlink_to(u2)
    for target in (u1 / "lnk", u1 / "lnk" / "secret"):
        with pytest.raises(fsguard.UnsafePathError):
            with fsguard.pinned(target, u1):
                pass
    (u1 / "flnk").symlink_to(u2 / "secret")
    with pytest.raises(fsguard.UnsafePathError):
        with fsguard.pinned(u1 / "flnk", u1):
            pass


def _db(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.execute("INSERT INTO t VALUES (?)", (value,))
    con.commit()
    con.close()


@posix
def test_backup_skips_a_swapped_link_and_reports_it_without_reading_the_target(tmp_path, monkeypatch):
    root = tmp_path / "data"
    u1, u2 = root / "users" / "1", root / "users" / "2"
    u1.mkdir(parents=True)
    u2.mkdir(parents=True)
    _db(u2 / "local_state" / "app.db", "other-user-secret")
    (u1 / "plan.rpx").write_bytes(b"x")
    (u1 / "local_state").symlink_to(u2 / "local_state")
    # defeat the name check on purpose: the open-handle check alone must still refuse (the race outcome)
    monkeypatch.setattr(bs.fsguard, "has_reparse_point", lambda *a, **k: False)
    read: list[str] = []
    real = bs.sqlite_bytes
    monkeypatch.setattr(bs, "sqlite_bytes", lambda p: (read.append(str(p)), real(p))[1])
    dest = tmp_path / "out.rpbk"
    _, report = bs.write_archive(dest, b"k" * 32, data_root=root, user_ids=[1], gateway_db=None, now=1_700_000_000.0)
    assert not any("u2" in p or "/2/" in p for p in read), read
    assert any("link inside the workspace" in e for e in report["errors"]), report


@posix
def test_log_trim_uses_one_handle_and_keeps_the_tail(tmp_path):
    folder = tmp_path / "users" / "1"
    log_file = folder / logs.CONSOLE_LOG
    log_file.parent.mkdir(parents=True)
    log_file.write_bytes(b"A" * 5000 + b"TAIL")
    out = logs.prune_worker_logs(tmp_path, lambda uid: False, max_bytes=1000)
    assert out["trimmed"] == 1
    data = log_file.read_bytes()
    assert data.startswith(b"[older output trimmed by the gateway]\n") and data.endswith(b"TAIL") and len(data) < 1100


@posix
def test_log_trim_refuses_a_linked_log_folder(tmp_path, monkeypatch):
    folder, other = tmp_path / "users" / "1", tmp_path / "elsewhere"  # outside users/: only user 1 is visited
    (other / "local_state" / "logs").mkdir(parents=True)
    victim = other / "local_state" / "logs" / "worker_console.log"
    victim.write_bytes(b"B" * 5000)
    folder.mkdir(parents=True)
    (folder / "local_state").symlink_to(other / "local_state")
    monkeypatch.setattr(logs.fsguard, "has_reparse_point", lambda *a, **k: False)  # the race: the name check passed
    out = logs.prune_worker_logs(tmp_path, lambda uid: False, max_bytes=1000)
    assert out == {"trimmed": 0, "removed": 0} and victim.read_bytes() == b"B" * 5000


# ---- SEC-03: no recursive reset under a worker that may be running ----
def test_acl_lock_refuses_to_reset_a_tree_with_content_unless_the_worker_is_stopped(tmp_path, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(acl, "_icacls", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(acl, "_remove_other_entries", lambda *a, **k: [])
    monkeypatch.setattr(acl, "_guard", lambda p: Path(p))
    folder = tmp_path / "users" / "1"
    (folder / "local_state").mkdir(parents=True)
    (folder / "plan.rpx").write_bytes(b"x")
    with pytest.raises(acl.AclError, match="worker"):
        acl.lock_user_folder(folder, account_sid="S-1-5-21-1", gateway_sid="S-1-5-18")
    assert calls == []  # nothing was changed
    acl.lock_user_folder(folder, account_sid="S-1-5-21-1", gateway_sid="S-1-5-18", worker_stopped=True)
    assert any("/reset" in a for call in calls for a in call)
    calls.clear()
    empty = tmp_path / "users" / "2"
    acl.lock_user_folder(empty, account_sid="S-1-5-21-1", gateway_sid="S-1-5-18")  # new account: no content, fine
    assert calls and not any("/reset" in a for call in calls for a in call)
