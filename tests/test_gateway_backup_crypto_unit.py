"""Encrypted backup archive format: round trip, wrong key, corruption, truncation, reordering."""
from __future__ import annotations

import io
import os
import struct

import pytest

from src.gateway import backup_crypto as bc

pytestmark = pytest.mark.unit


def _encrypt(master: bytes, payload: bytes) -> bytes:
    sink = io.BytesIO()
    w = bc.EncryptingWriter(sink, master)
    w.write(payload)
    w.finish()
    return sink.getvalue()


def _decrypt(master, blob: bytes) -> bytes:
    r = bc.DecryptingReader(io.BytesIO(blob), master)
    out = r.read()
    r.verify_to_end()
    return out


def test_round_trip_small_empty_and_multi_chunk():
    key = bc.generate_key()
    for size in (0, 1, bc.CHUNK_SIZE, bc.CHUNK_SIZE + 1, 2 * bc.CHUNK_SIZE + 17):
        data = os.urandom(size)
        assert _decrypt(key, _encrypt(key, data)) == data


def test_ciphertext_does_not_contain_the_plaintext():
    key = bc.generate_key()
    blob = _encrypt(key, b"SECRET-PLAN-CONTENT" * 50)
    assert b"SECRET-PLAN-CONTENT" not in blob


def test_wrong_key_is_reported_as_wrong_key_not_corruption():
    blob = _encrypt(bc.generate_key(), b"x" * 100)
    with pytest.raises(bc.WrongKeyError):
        bc.DecryptingReader(io.BytesIO(blob), bc.generate_key())
    with pytest.raises(bc.WrongKeyError):
        bc.DecryptingReader(io.BytesIO(blob), None)


def test_flipped_byte_in_any_chunk_fails_loudly():
    key = bc.generate_key()
    blob = bytearray(_encrypt(key, os.urandom(bc.CHUNK_SIZE + 500)))
    for pos in (len(blob) - 5, bc._HEADER.size + 10, len(blob) // 2):
        bad = bytearray(blob)
        bad[pos] ^= 0x01
        with pytest.raises(bc.CorruptBackupError):
            _decrypt(key, bytes(bad))


def test_truncated_archive_fails_even_at_a_chunk_boundary():
    key = bc.generate_key()
    blob = _encrypt(key, os.urandom(bc.CHUNK_SIZE * 2 + 5))
    h = bc._HEADER.size
    first_chunk_end = h + 4 + struct.unpack(">I", blob[h:h + 4])[0]
    for cut in (len(blob) - 1, first_chunk_end, h + 2, 3):
        with pytest.raises(bc.CorruptBackupError):
            _decrypt(key, blob[:cut])


def test_chunk_reordering_and_trailing_data_fail():
    key = bc.generate_key()
    blob = _encrypt(key, os.urandom(bc.CHUNK_SIZE * 2 + 5))
    with pytest.raises(bc.CorruptBackupError):
        _decrypt(key, blob + b"\x00")
    h = bc._HEADER.size
    n1 = struct.unpack(">I", blob[h:h + 4])[0]
    c1 = blob[h:h + 4 + n1]
    n2 = struct.unpack(">I", blob[h + 4 + n1:h + 8 + n1])[0]
    c2 = blob[h + 4 + n1:h + 8 + n1 + n2]
    rest = blob[h + 8 + n1 + n2:]
    with pytest.raises(bc.CorruptBackupError):
        _decrypt(key, blob[:h] + c2 + c1 + rest)


def test_not_an_archive():
    with pytest.raises(bc.CorruptBackupError):
        bc.DecryptingReader(io.BytesIO(b"hello world, definitely not a backup archive"), bc.generate_key())


def test_key_file_is_created_once_and_read_back(tmp_path):
    path = tmp_path / "keys" / "backup.key"
    key = bc.write_key_file(path)
    assert bc.read_key_file(path) == key and len(key) == bc.KEY_BYTES
    with pytest.raises(FileExistsError):
        bc.write_key_file(path)
    path.write_text("not base64 !!", encoding="utf-8")
    with pytest.raises(bc.WrongKeyError):
        bc.read_key_file(path)
    with pytest.raises(bc.WrongKeyError):
        bc.read_key_file(tmp_path / "missing.key")
