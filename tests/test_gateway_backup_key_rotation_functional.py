"""SEC-08: the backup key can be sealed at rest, rotated without orphaning old archives, and its file permissions are
checked. DPAPI and the DACL reader are replaced by fakes; the real calls need Windows (owner steps in the review)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest

from src.gateway import acl, key_acl, ops
from src.gateway import backup_crypto as bc


def fake_dpapi():
    """A reversible stand-in for machine-scope DPAPI that is not the identity (so a leak of the plain key shows)."""
    def protect(data: bytes) -> bytes:
        return b"DPAPI:" + bytes(b ^ 0x5A for b in data)

    def unprotect(blob: bytes) -> bytes:
        if not blob.startswith(b"DPAPI:"):
            raise OSError("not a DPAPI blob")
        return bytes(b ^ 0x5A for b in blob[6:])
    return protect, unprotect


_REAL_LOCK_DOWN = bc._lock_down_key_file  # kept for its own test below; the fixture swaps the module attribute


@pytest.fixture(autouse=True)
def _no_icacls(monkeypatch):
    """This file's contract (see its docstring) is that DPAPI and the DACL are fakes: no real icacls here.
    ``write_keyring_file`` locks the new key file down to Administrators and SYSTEM and then renames it from the same
    process, which only works while the caller's token has the Administrators entry ENABLED (an elevated shell, SYSTEM,
    the CI runner). In an ordinary non-elevated session ``os.replace`` fails with WinError 5. The tests here are about
    sealing, rotating and exporting; the real icacls runs in test_gateway_backup_key_lock_down_integration.py, once
    for each kind of token."""
    monkeypatch.setattr(bc, "_lock_down_key_file", lambda _tmp: None)


def _roundtrip(master, payload=b"archive bytes " * 100000):
    sink = io.BytesIO()
    w = bc.EncryptingWriter(sink, master)
    w.write(payload)
    w.finish()
    return sink.getvalue()


def _open(blob, master):
    return bc.DecryptingReader(io.BytesIO(blob), master).read()


def test_legacy_single_key_file_still_reads_and_is_a_one_key_ring(tmp_path):
    f = tmp_path / "k"
    master = bc.write_key_file(f)
    ring = bc.read_key_file(f)
    assert bytes(ring) == master and list(ring.keys) == [bc.key_id(master)]
    assert _open(_roundtrip(ring), ring) == b"archive bytes " * 100000


def test_seal_hides_the_key_and_reads_back(tmp_path):
    f = tmp_path / "k"
    master = bc.write_key_file(f)
    protect, unprotect = fake_dpapi()
    bc.write_keyring_file(f, bc.read_key_file(f), protect=protect)
    raw = f.read_bytes()
    assert bc.is_sealed(f) and master not in raw and base64.b64encode(master) not in raw
    assert bytes(bc.read_key_file(f, unprotect=unprotect)) == master
    with pytest.raises(bc.WrongKeyError):  # another machine's DPAPI cannot open it
        bc.read_key_file(f, unprotect=lambda b: (_ for _ in ()).throw(OSError("wrong machine")))


def test_sealed_file_needs_dpapi_where_there_is_none(tmp_path, monkeypatch):
    f = tmp_path / "k"
    protect, _ = fake_dpapi()
    bc.write_keyring_file(f, bc.KeyRing(bc.generate_key()), protect=protect)
    monkeypatch.setattr(bc, "default_protect", lambda: None)
    with pytest.raises(bc.WrongKeyError, match="DPAPI"):
        bc.read_key_file(f)


def test_rotation_keeps_old_archives_readable_by_key_id():
    old = bc.KeyRing(bc.generate_key())
    archive_old = _roundtrip(old)
    new = bc.rotate_keyring(old)
    assert bytes(new) != bytes(old) and len(new.keys) == 2
    archive_new = _roundtrip(new)
    assert _open(archive_old, new) == _open(archive_new, new)  # both decrypt under the rotated ring
    with pytest.raises(bc.WrongKeyError):  # the old ring alone cannot read what the new key wrote
        _open(archive_new, old)
    with pytest.raises(bc.WrongKeyError):
        _open(archive_old, bc.KeyRing(bc.generate_key()))


def test_corrupt_key_ring_is_refused(tmp_path):
    f = tmp_path / "k"
    f.write_bytes(b'{"format": "rp-backup-keyring", "current": "00", "keys": []}')
    with pytest.raises(bc.WrongKeyError):
        bc.read_key_file(f)
    f.write_bytes(b"not a key at all!!")
    with pytest.raises(bc.WrongKeyError):
        bc.read_key_file(f)


# ---- ops key ... ----
def _run(args, crypt):
    out, err = io.StringIO(), io.StringIO()

    def refuse(text, code=2):
        err.write(text + "\n")
        return code
    ns = ops._parser().parse_args(args)
    rc = ops._key(ns, lambda t="": out.write(t + "\n"), refuse, crypt=crypt)
    return rc, out.getvalue(), err.getvalue()


def test_ops_key_seal_then_rotate_keeps_it_sealed_and_old_archives_open(tmp_path):
    crypt = fake_dpapi()
    f = tmp_path / "keys" / "backup.key"
    f.parent.mkdir()
    master = bc.write_key_file(f)
    archive_old = _roundtrip(bc.read_key_file(f))
    rc, out, err = _run(["key", "seal", "--key-file", str(f)], crypt)
    assert rc == 0 and bc.is_sealed(f), err
    assert _run(["key", "seal", "--key-file", str(f)], crypt)[0] == 0  # idempotent
    rc, out, err = _run(["key", "rotate", "--key-file", str(f)], crypt)
    assert rc == 0 and bc.is_sealed(f), err  # stays sealed
    ring = bc.read_key_file(f, unprotect=crypt[1])
    assert bytes(ring) != master and len(ring.keys) == 2
    assert _open(archive_old, ring)  # the archive written before the rotation still opens
    assert master not in f.read_bytes()


def test_ops_key_seal_is_refused_without_dpapi(tmp_path):
    f = tmp_path / "backup.key"
    bc.write_key_file(f)
    rc, _out, err = _run(["key", "seal", "--key-file", str(f)], None)
    assert rc == 1 and "Windows DPAPI" in err and not bc.is_sealed(f)


def test_ops_key_export_never_overwrites(tmp_path):
    crypt = fake_dpapi()
    f = tmp_path / "keys" / "backup.key"
    f.parent.mkdir()
    bc.write_key_file(f)
    out_file = tmp_path / "offline" / "copy.json"
    out_file.parent.mkdir()
    rc, *_ = _run(["key", "export", "--key-file", str(f), "--out", str(out_file)], crypt)
    assert rc == 0 and bytes(bc.read_key_file(out_file)) == bytes(bc.read_key_file(f))
    assert _run(["key", "export", "--key-file", str(f), "--out", str(out_file)], crypt)[0] == 1


# ---- the ACL check (fake DACL reader) ----
def _dacl(*aces, owner=acl.ADMINISTRATORS):
    return acl.Dacl(True, tuple(aces), owner)


def _ace(sid, mask=0x1200A9, allow=True, inherit_only=False):
    return acl.Ace(sid, allow, mask, inherit_only)


def test_key_acl_accepts_owner_admin_system_only():
    d = _dacl(_ace(acl.SYSTEM), _ace(acl.ADMINISTRATORS), _ace("S-1-5-21-1-2-3-1001"), owner="S-1-5-21-1-2-3-1001")
    assert key_acl.key_file_findings("k", reader=lambda p: d) == []


@pytest.mark.parametrize("sid", [acl.USERS, "S-1-1-0", "S-1-5-11", "S-1-5-21-9-9-9-1002"])
def test_key_acl_flags_any_other_reader(sid):
    d = _dacl(_ace(acl.SYSTEM), _ace(sid))
    found = key_acl.key_file_findings("k", reader=lambda p: d)
    assert len(found) == 1 and sid in found[0]


def test_key_acl_ignores_deny_write_only_and_inherit_only_entries():
    d = _dacl(_ace(acl.SYSTEM), _ace(acl.USERS, allow=False), _ace(acl.USERS, mask=0x2),  # deny; write-only
              _ace(acl.USERS, inherit_only=True))
    assert key_acl.key_file_findings("k", reader=lambda p: d) == []


def test_key_acl_null_dacl_and_unreadable_are_findings():
    assert key_acl.key_file_findings("k", reader=lambda p: acl.Dacl(False, None, None))
    def boom(_p):
        raise OSError(5, "denied")
    assert "could not be read" in key_acl.key_file_findings("k", reader=boom)[0]


def test_key_acl_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(key_acl.sys, "platform", "linux")
    assert key_acl.key_file_findings(Path("k")) == []


# ---- the rewrite must not change who can read the key (found on the owner's server) ----
def test_the_new_key_file_is_locked_down_before_it_replaces_the_old_one(tmp_path):
    f = tmp_path / "backup.key"
    old = bc.write_key_file(f)
    seen = []

    def lock(tmp):
        seen.append((Path(tmp).name, Path(tmp).exists(), bytes(bc.read_key_file(f)) == bytes(old)))

    bc.write_keyring_file(f, bc.read_key_file(f), protect=fake_dpapi()[0], lock_down=lock)
    assert seen == [("backup.key.new", True, True)]  # called on the temp file while the OLD file was still in place
    assert bc.is_sealed(f) and not (tmp_path / "backup.key.new").exists()


def test_a_failed_lock_down_leaves_the_old_key_untouched(tmp_path):
    f = tmp_path / "backup.key"
    old = bc.write_key_file(f)

    def refuse_lock(_tmp):
        raise OSError("icacls failed")

    with pytest.raises(OSError):
        bc.write_keyring_file(f, bc.read_key_file(f), protect=fake_dpapi()[0], lock_down=refuse_lock)
    assert not bc.is_sealed(f) and bytes(bc.read_key_file(f)) == bytes(old)
    assert not (tmp_path / "backup.key.new").exists()


def test_the_windows_lock_down_grants_only_administrators_and_system(tmp_path, monkeypatch):
    import subprocess

    calls = []
    monkeypatch.setattr(bc.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    _REAL_LOCK_DOWN(tmp_path / "k.new")
    assert calls == [["icacls", str(tmp_path / "k.new"), "/inheritance:r", "/grant:r", "*S-1-5-32-544:(F)", "*S-1-5-18:(R)"]]
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 5, "", "denied"))
    with pytest.raises(OSError, match="could not restrict"):
        _REAL_LOCK_DOWN(tmp_path / "k.new")


def test_seal_and_rotate_warn_when_the_rewritten_key_is_exposed(tmp_path, monkeypatch):
    crypt = fake_dpapi()
    f = tmp_path / "keys" / "backup.key"
    f.parent.mkdir()
    bc.write_key_file(f)
    monkeypatch.setattr(key_acl, "key_file_findings", lambda *a, **k: [f"{f}: account S-1-5-32-545 can read the backup key"])
    rc, out, _err = _run(["key", "seal", "--key-file", str(f)], crypt)
    assert rc == 0 and "WARNING" in out and "refuse to start" in out
    rc, out, _err = _run(["key", "rotate", "--key-file", str(f)], crypt)
    assert rc == 0 and "WARNING" in out


@pytest.mark.parametrize("action", ["seal", "rotate", "export"])
def test_seal_rotate_and_export_all_lock_the_rewritten_file_down_by_default(tmp_path, monkeypatch, action):
    """The tests above run with the real icacls replaced by a no-op. This pins that every rewrite still goes through
    the module's lock-down (what write_keyring_file uses when no ``lock_down`` is passed), on the temp file, before
    the swap."""
    seen = []
    monkeypatch.setattr(bc, "_lock_down_key_file", lambda tmp: seen.append((Path(tmp).name, Path(tmp).exists())))
    f = tmp_path / "keys" / "backup.key"
    f.parent.mkdir()
    bc.write_key_file(f)
    args, target = ["key", action, "--key-file", str(f)], f
    if action == "export":
        target = tmp_path / "offline" / "copy.json"
        target.parent.mkdir()
        args += ["--out", str(target)]
    rc, _out, err = _run(args, fake_dpapi())
    assert rc == 0, err
    assert seen == [(target.name + ".new", True)]
