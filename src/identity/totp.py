"""Time-based one-time passwords (RFC 6238 over RFC 4226), recovery codes and sealed secrets. Stdlib only.

Secrets are sealed with a key held in the OS credential store (``secrets_store``), never in ``identity.db``,
so a copied database does not yield working second factors. The seal is encrypt-then-MAC built from HMAC-SHA256
(a counter-mode keystream plus a tag bound to the person), which needs no third-party package.
Nothing here logs or returns a secret except ``new_secret`` (shown once during enrolment).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import os
import secrets
import struct
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # accept the previous, current and next step (clock drift)
KEY_SECRET_NAME = "identity.totp.key"
RECOVERY_COUNT = 8
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
_SEAL_VERSION = b"\x01"


class SealError(ValueError):
    """A sealed secret failed its integrity check (wrong key, wrong person, or tampered)."""


def new_secret() -> str:
    """A 160-bit secret as unpadded base32 (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _decode(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(secret: bytes, counter: int, digits: int = DIGITS) -> str:
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits)


def totp_at(secret_b32: str, at: float, digits: int = DIGITS, step: int = STEP_SECONDS) -> str:
    return hotp(_decode(secret_b32), int(at // step), digits)


def match_step(secret_b32: str, code: str, at: float, window: int = WINDOW, step: int = STEP_SECONDS) -> int | None:
    """The time step whose code equals ``code`` (within the drift window), else None. Constant-time compare."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    secret = _decode(secret_b32)
    now_step = int(at // step)
    found = None
    for s in range(now_step - window, now_step + window + 1):
        if hmac.compare_digest(hotp(secret, s), code) and found is None:
            found = s
    return found


def provisioning_uri(secret_b32: str, account: str, issuer: str = "Financial Insights") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")


# ---- sealed storage ----
def _subkey(key: bytes, label: bytes) -> bytes:
    return hmac.new(key, b"identity-totp|" + label, hashlib.sha256).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + struct.pack(">I", counter), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def seal(plaintext: bytes, key: bytes, user_id: int) -> bytes:
    nonce = secrets.token_bytes(16)
    ct = bytes(a ^ b for a, b in zip(plaintext, _keystream(_subkey(key, b"enc"), nonce, len(plaintext))))
    tag = hmac.new(_subkey(key, b"mac"), struct.pack(">q", user_id) + nonce + ct, hashlib.sha256).digest()
    return _SEAL_VERSION + nonce + ct + tag


def unseal(blob: bytes, key: bytes, user_id: int) -> bytes:
    blob = bytes(blob)
    if len(blob) < 1 + 16 + 32 or blob[:1] != _SEAL_VERSION:
        raise SealError("unreadable second-factor secret")
    nonce, ct, tag = blob[1:17], blob[17:-32], blob[-32:]
    want = hmac.new(_subkey(key, b"mac"), struct.pack(">q", user_id) + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, want):
        raise SealError("second-factor secret failed its integrity check")
    return bytes(a ^ b for a, b in zip(ct, _keystream(_subkey(key, b"enc"), nonce, len(ct))))


# ---- recovery codes ----
def new_recovery_codes(count: int = RECOVERY_COUNT) -> list[str]:
    return ["".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(5)) + "-"
            + "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(5)) for _ in range(count)]


def normalize_recovery(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "").replace("-", "")


def hash_recovery(code: str, key: bytes) -> str:
    return hmac.new(_subkey(key, b"recovery"), normalize_recovery(code).encode(), hashlib.sha256).hexdigest()


def looks_like_recovery(code: str) -> bool:
    n = normalize_recovery(code)
    return len(n) == 10 and all(c in _RECOVERY_ALPHABET for c in n)


_KEY_THREAD_LOCK = threading.Lock()


@contextlib.contextmanager
def _key_creation_lock():
    """Serialise first-use key creation across threads AND processes (the Admin app, Financial Insights and the
    gateway can all start at once): an OS file lock in the user's temp folder, plus a thread lock."""
    path = Path(tempfile.gettempdir()) / "retirement_identity_totp_key.lock"
    with _KEY_THREAD_LOCK:
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)  # a lock handle, not data
        try:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415

                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def default_key() -> bytes:
    """The sealing key from the OS credential store, created on first use. Raises ``SecretStoreUnavailable``
    when there is no credential store (callers fail closed: no second factor can be checked or enrolled).

    X-8: creation is atomic. The get-then-set used to let two starters each mint a key, the later write orphaning
    every secret sealed with the first; now the check, the mint and the write happen under one lock, and the value is
    read back so every caller returns what is actually stored."""
    from src import secrets_store

    value = secrets_store.get_secret(KEY_SECRET_NAME)
    if not value:
        with _key_creation_lock():
            value = secrets_store.get_secret(KEY_SECRET_NAME)  # someone may have created it while we waited
            if not value:
                secrets_store.set_secret(KEY_SECRET_NAME, secrets.token_hex(32))
                value = secrets_store.get_secret(KEY_SECRET_NAME)
    return bytes.fromhex(value)


def now() -> float:
    return time.time()
