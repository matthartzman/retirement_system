"""Two-factor sign-in in the identity store: RFC 6238 vectors, sealed secrets, replay, recovery codes, lockout."""
from __future__ import annotations

import base64
import sqlite3

import pytest

from src.identity import IdentityStore
from src.identity import totp as totp_lib

PW = "correct horse"
KEY = bytes(range(32))
T0 = 1_000_000.0


def _store(tmp_path, key=KEY):
    return IdentityStore(tmp_path / "identity.db", scrypt_n=2**4, totp_key=lambda: key)


def _enrol(store, uid, now=T0):
    secret = store.begin_enrolment(uid, now=now)
    codes = store.confirm_enrolment(uid, totp_lib.totp_at(secret, now), now=now)
    assert codes
    return secret, codes


def test_rfc_6238_sha1_vectors():
    secret = b"12345678901234567890"
    for t, want in [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                    (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")]:
        assert totp_lib.hotp(secret, t // 30, 8) == want
    b32 = base64.b32encode(secret).decode()
    assert totp_lib.totp_at(b32, 59) == "287082"
    assert totp_lib.match_step(b32, "287082", 59) == 1


def test_drift_window_is_one_step_either_side():
    b32 = base64.b32encode(b"12345678901234567890").decode()
    code = totp_lib.totp_at(b32, 3000)
    assert totp_lib.match_step(b32, code, 3000 + 30) == 100
    assert totp_lib.match_step(b32, code, 3000 - 30) == 100
    assert totp_lib.match_step(b32, code, 3000 + 90) is None
    assert totp_lib.match_step(b32, "12345", 3000) is None and totp_lib.match_step(b32, "abcdef", 3000) is None


def test_sealed_secret_is_bound_to_key_and_person_and_detects_tampering():
    blob = totp_lib.seal(b"JBSWY3DPEHPK3PXP", KEY, 7)
    assert b"JBSWY3DP" not in blob
    assert totp_lib.unseal(blob, KEY, 7) == b"JBSWY3DPEHPK3PXP"
    with pytest.raises(totp_lib.SealError):
        totp_lib.unseal(blob, bytes(32), 7)
    with pytest.raises(totp_lib.SealError):
        totp_lib.unseal(blob, KEY, 8)
    flipped = bytearray(blob)
    flipped[20] ^= 1
    with pytest.raises(totp_lib.SealError):
        totp_lib.unseal(bytes(flipped), KEY, 7)


def test_database_holds_no_readable_secret_or_recovery_code(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    secret, codes = _enrol(store, uid)
    row = sqlite3.connect(store.path).execute("SELECT secret, recovery_codes FROM totp").fetchone()
    assert secret.encode() not in bytes(row[0])
    assert not any(c in row[1] or totp_lib.normalize_recovery(c) in row[1] for c in codes)
    other = _store(tmp_path, key=bytes(32))  # a copied database with the wrong key yields no working factor
    assert other.verify_login("ann", PW, T0 + 60, code=totp_lib.totp_at(secret, T0 + 60)).reason == "bad_code"


def test_enrolment_needs_a_working_code_and_drops_the_secret_after_five_misses(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    secret = store.begin_enrolment(uid, now=T0)
    assert store.confirm_enrolment(uid, "000000" if totp_lib.totp_at(secret, T0) != "000000" else "111111", now=T0) is None
    assert not store.totp_enrolled(uid)
    for _ in range(4):
        store.confirm_enrolment(uid, "abcdef", now=T0)
    with pytest.raises(ValueError):  # pending secret dropped: even the right code is refused until a restart
        store.confirm_enrolment(uid, totp_lib.totp_at(secret, T0), now=T0)
    secret = store.begin_enrolment(uid, now=T0)
    with pytest.raises(ValueError):  # expired
        store.confirm_enrolment(uid, totp_lib.totp_at(secret, T0 + 700), now=T0 + 700)


def test_signin_asks_for_a_code_then_accepts_one_fresh_code(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW, must_change=False)
    secret, _ = _enrol(store, uid)
    assert store.verify_login("ann", PW, T0 + 60).reason == "totp"
    assert store.verify_login("ann", PW, T0 + 60, code="").reason == "totp"
    ok = store.verify_login("ann", PW, T0 + 60, code=totp_lib.totp_at(secret, T0 + 60))
    assert ok.ok and not ok.needs_enrolment


def test_a_code_cannot_be_replayed_not_even_the_enrolment_code(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    secret, _ = _enrol(store, uid)
    assert store.verify_login("ann", PW, T0 + 1, code=totp_lib.totp_at(secret, T0)).reason == "bad_code"  # enrollment code
    code = totp_lib.totp_at(secret, T0 + 30)
    assert store.verify_login("ann", PW, T0 + 30, code=code).ok
    assert store.verify_login("ann", PW, T0 + 31, code=code).reason == "bad_code"
    assert store.verify_login("ann", PW, T0 + 61, code=totp_lib.totp_at(secret, T0 + 60)).ok
    # an older step than the last accepted is refused even though it is inside the drift window
    assert store.verify_login("ann", PW, T0 + 62, code=totp_lib.totp_at(secret, T0 + 30)).reason == "bad_code"


def test_recovery_code_works_once_and_regeneration_replaces_the_set(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    secret, codes = _enrol(store, uid)
    assert len(codes) == 8 and store.recovery_codes_left(uid) == 8
    assert store.verify_login("ann", PW, T0 + 60, code=codes[0].lower()).ok  # case and dash do not matter
    assert store.recovery_codes_left(uid) == 7
    assert store.verify_login("ann", PW, T0 + 61, code=codes[0]).reason == "bad_code"
    assert store.regenerate_recovery_codes(uid, codes[1], now=T0 + 90) is None  # a recovery code cannot mint more
    new = store.regenerate_recovery_codes(uid, totp_lib.totp_at(secret, T0 + 120), now=T0 + 120)
    assert new and store.recovery_codes_left(uid) == 8
    assert store.verify_login("ann", PW, T0 + 130, code=codes[2]).reason == "bad_code"
    assert store.verify_login("ann", PW, T0 + 131, code=new[0]).ok


def test_wrong_codes_share_the_password_lockout_and_a_right_password_does_not_clear_it(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW)
    secret, _ = _enrol(store, uid)
    for i in range(4):
        assert store.verify_login("ann", PW, T0 + 60 + i, code="000000").reason == "bad_code"
        assert store.verify_login("ann", PW, T0 + 60 + i).reason == "totp"  # re-sending the password resets nothing
    assert store.verify_login("ann", PW, T0 + 70, code="000000").reason == "locked"
    assert store.verify_login("ann", PW, T0 + 71, code=totp_lib.totp_at(secret, T0 + 71)).reason == "locked"
    later = T0 + 70 + 16 * 60
    assert store.verify_login("ann", PW, later, code=totp_lib.totp_at(secret, later)).ok


def test_a_wrong_code_feeds_the_global_throttle(tmp_path):
    store = _store(tmp_path)
    for name in ("a", "b", "c", "d", "e"):
        uid = store.add_user(name, name, PW)
        _enrol(store, uid)
        for i in range(5):
            store.verify_login(name, PW, T0 + 60 + i, code="000000")
    assert store.global_delay(T0 + 70) > 0


def test_requirement_defaults_on_is_optional_per_person_and_existing_people_are_prompted(tmp_path):
    store = _store(tmp_path)
    new = store.add_user("Ann", "ann", PW, must_change=False)
    opt = store.add_user("Bob", "bob", PW, must_change=False, totp_required=False)
    assert store.verify_login("ann", PW, T0).needs_enrolment
    assert not store.verify_login("bob", PW, T0).needs_enrolment
    store.set_totp_required(opt, True)
    assert store.verify_login("bob", PW, T0).needs_enrolment
    _enrol(store, new)
    assert not store.verify_login("ann", PW, T0 + 60, code=totp_lib.totp_at(store_secret(store, new), T0 + 60)).needs_enrolment
    # a database from before this column gains it with every existing person required
    legacy = tmp_path / "old.db"
    conn = sqlite3.connect(legacy)
    conn.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, display_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,"
                       " pw_hash BLOB NOT NULL, pw_salt BLOB NOT NULL, scrypt_n INTEGER NOT NULL, must_change INTEGER NOT NULL DEFAULT 1,"
                       " created_at REAL NOT NULL, updated_at REAL NOT NULL, failed_count INTEGER NOT NULL DEFAULT 0,"
                       " locked_until REAL NOT NULL DEFAULT 0, last_signin_at REAL, role TEXT NOT NULL DEFAULT 'user',"
                       " status TEXT NOT NULL DEFAULT 'active', expires_at REAL, session_epoch INTEGER NOT NULL DEFAULT 0,"
                       " notes TEXT NOT NULL DEFAULT '');"
                       "INSERT INTO users(display_name, username, pw_hash, pw_salt, scrypt_n, created_at, updated_at)"
                       " VALUES ('Old','old',x'00',x'00',16,0,0); PRAGMA user_version = 3;")
    conn.commit()
    conn.close()
    assert IdentityStore(legacy, scrypt_n=2**4, totp_key=lambda: KEY).list_users()[0]["totp_required"] is True


def store_secret(store, uid):
    from src.identity import totp as t
    blob = sqlite3.connect(store.path).execute("SELECT secret FROM totp WHERE user_id=?", (uid,)).fetchone()[0]
    return t.unseal(bytes(blob), KEY, uid).decode()


def test_admin_reset_removes_the_factor_ends_sessions_and_requires_enrolment_again(tmp_path):
    store = _store(tmp_path)
    uid = store.add_user("Ann", "ann", PW, must_change=False)
    _enrol(store, uid)
    epoch = store.session_epoch(uid)
    assert store.reset_totp(uid) is True
    assert store.session_epoch(uid) == epoch + 1 and not store.totp_enrolled(uid)
    assert store.verify_login("ann", PW, T0 + 60).needs_enrolment
    assert store.reset_totp(uid) is False


def test_credential_store_failure_is_raised_not_swallowed(tmp_path):
    from src.secrets_store import SecretStoreUnavailable

    def broken():
        raise SecretStoreUnavailable("no credential store")

    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4, totp_key=broken)
    uid = store.add_user("Ann", "ann", PW)
    with pytest.raises(SecretStoreUnavailable):
        store.begin_enrolment(uid, now=T0)
    assert store.verify_login("ann", PW, T0).needs_enrolment  # people without a factor can still reach the enrollment page
