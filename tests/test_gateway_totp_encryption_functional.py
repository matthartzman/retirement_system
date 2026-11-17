"""P7-O1: TOTP secrets are encrypted at rest in gateway.db (DPAPI scheme), migrated in place, and stay encrypted in backups."""
from __future__ import annotations

import sqlite3

import pytest

from src.gateway import backup_store as bs
from src.gateway import totp
from src.gateway.secret_box import PREFIX, DpapiSecretBox, PlaintextSecretBox
from src.gateway.store import Actor, GatewayStore
from tests.gateway_rig import Rig

CLI = Actor(None, "test")
KEY = bytes(range(32))


class XorBox:
    """A reversible stand-in, so the logic is testable off Windows; the DPAPI box is tested separately."""

    def protect(self, secret: str) -> str:
        return PREFIX + bytes(b ^ 0x5A for b in secret.encode()).hex()

    def unprotect(self, stored: str) -> str | None:
        if not stored.startswith(PREFIX):
            return stored  # legacy plaintext
        return bytes(b ^ 0x5A for b in bytes.fromhex(stored[len(PREFIX):])).decode()


class BrokenBox(XorBox):
    """What a rebuilt machine sees: the blobs do not open."""

    def unprotect(self, stored: str) -> str | None:
        return None if stored.startswith(PREFIX) else stored


def _store(tmp_path, box, name="g.db"):
    return GatewayStore(tmp_path / name, scrypt_n=2**4, secret_box=box)


def _raw(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT user_id, secret FROM totp_secrets").fetchall()
    finally:
        con.close()


def _enrol(store, now=1_000_000.0, username="ann"):
    uid = store.create_user(username, username, "user", "a long enough password", now=now, actor=CLI)
    secret = store.begin_totp_enrolment(uid, now)
    assert store.confirm_totp(uid, totp.code_at(secret, int(now // 30)), now)
    return uid, secret


def test_new_secret_is_stored_sealed_and_still_verifies(tmp_path):
    s = _store(tmp_path, XorBox())
    uid, secret = _enrol(s)
    ((_, stored),) = _raw(s.path)
    assert stored.startswith(PREFIX) and secret not in stored
    assert s._totp_secret(uid) == secret
    assert s.verify_totp(uid, totp.code_at(secret, int(1_000_030 // 30) + 1), 1_000_030)


def test_pending_enrolment_returns_the_same_secret_twice(tmp_path):
    s = _store(tmp_path, XorBox())
    uid = s.create_user("ann", "Ann", "user", "a long enough password", now=1.0, actor=CLI)
    assert s.begin_totp_enrolment(uid, 1.0) == s.begin_totp_enrolment(uid, 2.0)


def _legacy_store(tmp_path):
    """gateway.db as the old code left it: an enrolled user with a clear-text secret."""
    s = _store(tmp_path, PlaintextSecretBox())
    uid, secret = _enrol(s)
    assert _raw(s.path) == [(uid, secret)]
    return s, uid, secret


def test_migration_encrypts_legacy_rows_in_place_and_is_idempotent(tmp_path):
    legacy, uid, secret = _legacy_store(tmp_path)
    s = _store(tmp_path, XorBox())
    assert s.protect_totp_secrets() == 1
    ((_, stored),) = _raw(s.path)
    assert stored.startswith(PREFIX) and secret not in stored
    assert s.protect_totp_secrets() == 0
    assert _raw(s.path) == [(uid, stored)]  # untouched the second time
    assert s.verify_totp(uid, totp.code_at(secret, int(1_000_060 // 30)), 1_000_060)


def test_no_clear_text_secret_is_left_in_the_database_file_or_its_wal(tmp_path):
    legacy, _uid, secret = _legacy_store(tmp_path)
    s = _store(tmp_path, XorBox())
    s.protect_totp_secrets()
    for suffix in ("", "-wal", "-shm"):
        p = tmp_path / f"g.db{suffix}"
        if p.exists():
            assert secret.encode() not in p.read_bytes(), p.name


def test_unreadable_blobs_fail_closed_and_are_reported(tmp_path):
    s = _store(tmp_path, XorBox())
    uid, secret = _enrol(s)
    moved = _store(tmp_path, BrokenBox(), name="g.db")  # same file, new machine
    assert moved.unreadable_totp_users() == [uid]
    assert moved.verify_totp(uid, totp.code_at(secret, int(1_000_060 // 30)), 1_000_060) is False
    assert moved.totp_status(uid) == "enrolled"  # an admin reset is the way out
    moved.reset_totp(uid, now=2.0, actor=CLI)
    assert moved.unreadable_totp_users() == []


def test_an_unreadable_pending_secret_is_replaced_not_returned(tmp_path):
    s = _store(tmp_path, XorBox())
    uid = s.create_user("ann", "Ann", "user", "a long enough password", now=1.0, actor=CLI)
    old = s.begin_totp_enrolment(uid, 1.0)
    moved = _store(tmp_path, BrokenBox())
    new = moved.begin_totp_enrolment(uid, 2.0)
    assert new != old and totp.verify(new, totp.code_at(new, 5), 5 * 30, None) == 5


def test_the_rig_signs_in_with_the_default_box(tmp_path):
    rig = Rig(tmp_path)
    b, uid = rig.signed_in()
    assert _raw(rig.store.path)[0][1].startswith(PREFIX if DpapiSecretBox.available() else "")
    assert b.get("/api/auth/session").get_json()["authenticated"] is True


def test_backups_carry_only_the_sealed_form(tmp_path):
    s = _store(tmp_path, XorBox())
    uid, secret = _enrol(s)
    (tmp_path / "data").mkdir()
    path, report = bs.write_archive(tmp_path / "a.rpbk", KEY, data_root=tmp_path / "data", user_ids=[],
                                    gateway_db=s.path, now=1_000_000.0)
    assert "gateway.db" in report.get("members", ["gateway.db"])
    out = bs.restore_gateway_db(path, KEY, tmp_path / "restored.db")
    ((_, stored),) = _raw(out)
    assert stored.startswith(PREFIX) and secret not in stored
    assert secret.encode() not in out.read_bytes()
    restored = _store(tmp_path, XorBox(), name="restored.db")
    assert restored.verify_totp(uid, totp.code_at(secret, int(1_000_060 // 30)), 1_000_060)


@pytest.mark.skipif(not DpapiSecretBox.available(), reason="DPAPI needs Windows")
def test_dpapi_box_round_trips_and_does_not_hold_the_secret():
    box = DpapiSecretBox()
    sealed = box.protect("JBSWY3DPEHPK3PXP")
    assert sealed.startswith(PREFIX) and "JBSWY3DPEHPK3PXP" not in sealed
    assert box.unprotect(sealed) == "JBSWY3DPEHPK3PXP"
    assert box.unprotect(PREFIX + "AAAA") is None  # garbage is unreadable, not an exception
    assert box.unprotect("JBSWY3DPEHPK3PXP") == "JBSWY3DPEHPK3PXP"  # legacy plaintext passes through


def test_startup_seals_legacy_rows_and_warns_about_unreadable_ones(tmp_path, caplog):
    from src.gateway import server

    legacy, uid, secret = _legacy_store(tmp_path)
    store = _store(tmp_path, XorBox())
    server.protect_totp_at_startup(store)
    assert _raw(store.path)[0][1].startswith(PREFIX)
    moved = _store(tmp_path, BrokenBox())
    with caplog.at_level("WARNING"):
        server.protect_totp_at_startup(moved)
    assert "reset" in caplog.text and str(uid) in caplog.text
