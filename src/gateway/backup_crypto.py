"""Authenticated, chunked encryption for backup archives (AES-256-GCM, per-archive HKDF key).

Layout: ``RPBK`` | version | key id (8) | salt (16) | nonce prefix (4) | chunk size (u32), then repeated
``ciphertext length (u32) | ciphertext``. Each chunk is bound to its position and to "last chunk or not", so
reordering, dropping, duplicating, truncating or flipping any byte fails authentication.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import struct
import sys
import time
from pathlib import Path
from typing import BinaryIO, Callable, Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"RPBK"
VERSION = 1
CHUNK_SIZE = 1024 * 1024
KEY_BYTES = 32
_HEADER = struct.Struct(">4sB8s16s4sI")
_LEN = struct.Struct(">I")
_HKDF_INFO = b"retirement-planner gateway backup v1"


class BackupCryptoError(Exception):
    """Base class: the archive cannot be trusted or read."""


class WrongKeyError(BackupCryptoError):
    """The archive was written with a different key (or no key is available)."""


class CorruptBackupError(BackupCryptoError):
    """The archive is damaged, truncated or has been tampered with."""


def key_id(master: bytes) -> bytes:
    return hashlib.sha256(b"key id:" + master).digest()[:8]


def generate_key() -> bytes:
    return os.urandom(KEY_BYTES)


def write_key_file(path: Path, master: bytes | None = None) -> bytes:
    """Create ``path`` (never overwriting) holding a base64 key; returns the key."""
    master = master or generate_key()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(base64.b64encode(master) + b"\n")
    return master


class KeyRing(bytes):
    """The CURRENT key (as bytes, so every existing ``master: bytes`` caller encrypts with it) plus every older key by
    ``key_id``: a rotation does not orphan archives written under a previous key (SEC-08)."""

    keys: dict[bytes, bytes]

    def __new__(cls, current: bytes, older: Iterable[bytes] = ()) -> "KeyRing":
        ring = super().__new__(cls, current)
        ring.keys = {key_id(k): bytes(k) for k in (*older, current)}
        return ring

    @property
    def current_id(self) -> bytes:
        return key_id(bytes(self))

    def for_archive(self, kid: bytes) -> bytes | None:
        return self.keys.get(kid)


Protect = Callable[[bytes], bytes]
SEAL_MAGIC = b"RPSEAL1\n"  # a key file that holds a DPAPI blob of the key ring JSON
_RING_FORMAT = "rp-backup-keyring"


def default_protect() -> tuple[Protect, Protect] | None:
    """(protect, unprotect) through machine-scope DPAPI on Windows; None elsewhere (the plain-file fallback)."""
    if sys.platform != "win32":
        return None
    from . import winapi  # noqa: PLC0415

    return winapi.dpapi_protect_machine, winapi.dpapi_unprotect


def keyring_to_bytes(ring: KeyRing) -> bytes:
    entries = [{"id": kid.hex(), "key": base64.b64encode(k).decode("ascii")} for kid, k in ring.keys.items()]
    return json.dumps({"format": _RING_FORMAT, "version": 1, "current": ring.current_id.hex(), "keys": entries,
                       "written": int(time.time())}, indent=1).encode("utf-8")


def _ring_from_json(raw: bytes) -> KeyRing:
    try:
        doc = json.loads(raw.decode("utf-8"))
        if doc.get("format") != _RING_FORMAT:
            raise ValueError("format")
        keys = {bytes.fromhex(e["id"]): base64.b64decode(e["key"], validate=True) for e in doc["keys"]}
        current = keys[bytes.fromhex(doc["current"])]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise WrongKeyError(f"the backup key file is not a valid key ring ({type(exc).__name__})") from None
    if any(len(k) != KEY_BYTES or key_id(k) != kid for kid, k in keys.items()):
        raise WrongKeyError("the backup key ring holds a key of the wrong size or id")
    return KeyRing(current, [k for kid, k in keys.items() if k != current])


def is_sealed(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(len(SEAL_MAGIC)) == SEAL_MAGIC
    except OSError:
        return False


def read_key_file(path: Path, *, unprotect: Protect | None = None) -> KeyRing:
    """Read a key file in any of its three forms: the original single base64 key, a plain key-ring JSON, or a key
    ring sealed with DPAPI (``unprotect`` defaults to Windows DPAPI). Returns the ring (bytes: the current key)."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise WrongKeyError(f"the backup key file cannot be read ({type(exc).__name__})") from None
    if raw.startswith(SEAL_MAGIC):
        un = unprotect or (default_protect() or (None, None))[1]
        if un is None:
            raise WrongKeyError("the backup key file is sealed with Windows DPAPI and can only be opened on Windows")
        try:
            return _ring_from_json(un(base64.b64decode(raw[len(SEAL_MAGIC):].strip(), validate=True)))
        except WrongKeyError:
            raise
        except Exception as exc:  # noqa: BLE001 - DPAPI refusals are OSError, bad base64 is ValueError
            raise WrongKeyError(f"the sealed backup key file cannot be opened here ({type(exc).__name__})") from None
    if raw.lstrip().startswith(b"{"):
        return _ring_from_json(raw)
    try:
        master = base64.b64decode(raw.strip(), validate=True)
    except ValueError as exc:
        raise WrongKeyError(f"the backup key file cannot be read ({type(exc).__name__})") from None
    if len(master) != KEY_BYTES:
        raise WrongKeyError("the backup key file does not hold a 32-byte key")
    return KeyRing(master)


def _lock_down_key_file(path: Path) -> None:
    """Windows: ``0o600`` means nothing, and a new file takes its permissions from the folder, not from the file it
    replaces. Give the new key file exactly Administrators (full) and SYSTEM (read), inheritance removed, BEFORE it
    replaces the old one. Raises on failure: an exposed key must not replace a protected one."""
    if sys.platform != "win32":
        return
    import subprocess  # noqa: PLC0415

    proc = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", "*S-1-5-32-544:(F)", "*S-1-5-18:(R)"],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise OSError(f"could not restrict the new key file's permissions: {(proc.stdout + proc.stderr).strip()[-200:]}")


def write_keyring_file(path: Path, ring: KeyRing, *, protect: Protect | None = None,
                       lock_down: Callable[[Path], None] | None = None) -> None:
    """Replace ``path`` atomically with the ring (sealed when ``protect`` is given). The temp file is created exclusive
    and 0600 in the same folder, so a crash leaves the old key file intact. On Windows it is locked down to
    Administrators and SYSTEM before the swap (a new file would otherwise inherit the folder's entries)."""
    path = Path(path)
    payload = keyring_to_bytes(ring)
    data = SEAL_MAGIC + base64.b64encode(protect(payload)) + b"\n" if protect else payload + b"\n"
    tmp = path.with_name(path.name + ".new")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        (lock_down or _lock_down_key_file)(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def rotate_keyring(ring: KeyRing) -> KeyRing:
    """A new current key; every earlier key is kept so older archives still open."""
    return KeyRing(generate_key(), list(ring.keys.values()))


def _data_key(master: bytes, salt: bytes) -> AESGCM:
    return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=_HKDF_INFO).derive(master))


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + struct.pack(">Q", index)


def _aad(header: bytes, index: int, final: bool) -> bytes:
    return header + struct.pack(">QB", index, 1 if final else 0)


class EncryptingWriter(io.RawIOBase):
    """A write-only file object: bytes in, an encrypted archive stream out to ``sink``."""

    def __init__(self, sink: BinaryIO, master: bytes) -> None:
        super().__init__()
        self._sink = sink
        salt, prefix = os.urandom(16), os.urandom(4)
        self._header = _HEADER.pack(MAGIC, VERSION, key_id(master), salt, prefix, CHUNK_SIZE)
        self._aes = _data_key(master, salt)
        self._prefix = prefix
        self._buf = bytearray()
        self._index = 0
        self._done = False
        sink.write(self._header)

    def writable(self) -> bool:
        return True

    def _emit(self, data: bytes, final: bool) -> None:
        ct = self._aes.encrypt(_nonce(self._prefix, self._index), data, _aad(self._header, self._index, final))
        self._sink.write(_LEN.pack(len(ct)))
        self._sink.write(ct)
        self._index += 1

    def write(self, data) -> int:  # noqa: ANN001
        if self._done:
            raise ValueError("archive already finished")
        self._buf += data
        while len(self._buf) > CHUNK_SIZE:  # keep >=1 byte back so the last chunk can carry the final flag
            self._emit(bytes(self._buf[:CHUNK_SIZE]), False)
            del self._buf[:CHUNK_SIZE]
        return len(data)

    def finish(self) -> None:
        if not self._done:
            self._emit(bytes(self._buf), True)
            self._buf.clear()
            self._done = True


class DecryptingReader(io.RawIOBase):
    """A read-only file object over an encrypted archive; raises the typed errors as it goes."""

    def __init__(self, source: BinaryIO, master: bytes | None) -> None:
        super().__init__()
        self._src = source
        raw = source.read(_HEADER.size)
        if len(raw) < _HEADER.size:
            raise CorruptBackupError("the file is too short to be a backup archive")
        magic, version, kid, salt, prefix, chunk = _HEADER.unpack(raw)
        if magic != MAGIC or version != VERSION or chunk != CHUNK_SIZE:
            raise CorruptBackupError("not a backup archive of a supported version")
        key = master.for_archive(kid) if isinstance(master, KeyRing) else master
        if key is None or kid != key_id(key):
            raise WrongKeyError("this archive was written with a different key")
        self._header, self._prefix = raw, prefix
        self._aes = _data_key(key, salt)
        self._index = 0
        self._plain = b""
        self._pos = 0
        self._final_seen = False

    def readable(self) -> bool:
        return True

    def _next_chunk(self) -> bool:
        if self._final_seen:
            if self._src.read(1):
                raise CorruptBackupError("unexpected data after the last chunk")
            return False
        raw = self._src.read(_LEN.size)
        if len(raw) < _LEN.size:
            raise CorruptBackupError("the archive is truncated")
        (n,) = _LEN.unpack(raw)
        if n < 16 or n > CHUNK_SIZE + 16:
            raise CorruptBackupError("the archive is damaged (bad chunk length)")
        ct = self._src.read(n)
        if len(ct) < n:
            raise CorruptBackupError("the archive is truncated")
        for final in (False, True):  # the writer's flag is authenticated, so exactly one can succeed
            try:
                self._plain = self._aes.decrypt(_nonce(self._prefix, self._index), ct,
                                                _aad(self._header, self._index, final))
            except InvalidTag:
                continue
            self._final_seen = final
            self._index += 1
            self._pos = 0
            return True
        raise CorruptBackupError("the archive failed its integrity check (damaged or altered)")

    def readinto(self, b) -> int:  # noqa: ANN001
        want = len(b)
        while self._pos >= len(self._plain):
            if not self._next_chunk():
                return 0
        n = min(want, len(self._plain) - self._pos)
        b[:n] = self._plain[self._pos:self._pos + n]
        self._pos += n
        return n

    def verify_to_end(self) -> None:
        while self.read(CHUNK_SIZE):
            pass
        if not self._final_seen:
            raise CorruptBackupError("the archive is truncated")
