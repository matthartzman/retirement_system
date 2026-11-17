"""Machine-scope DPAPI (``CryptProtectData`` with ``CRYPTPROTECT_LOCAL_MACHINE``) for the per-user server worker.

Why machine scope: user-scope DPAPI keys (and so Windows Credential Manager) hang off the account's password, and a
password rotation through ``NetUserChangePassword`` with no logon session open does not reliably re-key them; the
elevated tests measured the stored credential vanishing in about half the rotations
(``documentation/future/multi-user-server-monarch-secrets-design.md``, "What the elevated runs measured"). A
machine-scope key does not depend on any account's password, so a rotation cannot orphan it.

What it does NOT give you: any local account on this machine can call the same API and decrypt a blob it can read.
The protection is therefore the file ACL on the worker's own ``app.db`` (the gateway lays it out so only that
account and the gateway can open it), plus the per-secret ``entropy`` that ties a blob to its name. Do not use this
on a machine where the worker's data folder is readable by other accounts.

Imports nothing from the rest of the application; Windows only.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes as w

CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4


class DpapiUnavailable(RuntimeError):
    """DPAPI cannot be used here (not Windows, or the call failed)."""


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", w.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_BLOB, object]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _call(name: str, data: bytes, entropy: bytes) -> bytes:
    if sys.platform != "win32":
        raise DpapiUnavailable("machine-scope DPAPI needs Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    fn = getattr(crypt32, name)
    fn.argtypes = [ctypes.POINTER(_BLOB), ctypes.c_void_p, ctypes.POINTER(_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                   w.DWORD, ctypes.POINTER(_BLOB)]
    src, keep_src = _blob(data)
    ent, keep_ent = _blob(entropy)
    out = _BLOB()
    flags = CRYPTPROTECT_UI_FORBIDDEN | (CRYPTPROTECT_LOCAL_MACHINE if name == "CryptProtectData" else 0)
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, flags, ctypes.byref(out)):
        raise DpapiUnavailable(f"{name} failed (Windows error {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)
        del keep_src, keep_ent


def protect(data: bytes, entropy: bytes) -> bytes:
    return _call("CryptProtectData", data, entropy)


def unprotect(blob: bytes, entropy: bytes) -> bytes:
    return _call("CryptUnprotectData", blob, entropy)
