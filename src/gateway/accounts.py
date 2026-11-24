"""One Windows account per gateway user: create, grant and deny logon rights, disable, delete, rotate.

``NullAccountManager`` (same-account launcher: CI and development) does nothing. ``WindowsAccountManager``
creates a standard local account ``<prefix><user id>`` with a random password when an admin creates a
user, grants ``SeBatchLogonRight`` (the worker logs on as a batch job) and the deny-interactive,
deny-remote-desktop and deny-network rights, and locks the user's data folder to that account and the
gateway. The password exists only in memory and, DPAPI-protected for the gateway's account, in
``gateway.db``; it is never printed, logged or returned. Every call here needs an elevated gateway (the
service runs as LocalSystem); see ``documentation/future/multi-user-server-supervisor-design.md``.
"""
from __future__ import annotations

import ctypes
import logging
import secrets
import socket
import string
import time
from ctypes import wintypes as w
from pathlib import Path
from typing import Callable

from . import acl, winapi

LOG = logging.getLogger("retirement.gateway.accounts")
DEFAULT_PREFIX = "rpw_"
WORKER_RIGHTS = ("SeBatchLogonRight", "SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight",
                 "SeDenyNetworkLogonRight")
PASSWORD_LENGTH = 32
_NERR_USER_EXISTS = 2224
_NERR_USER_NOT_FOUND = 2221
_UF_SCRIPT = 0x0001
_UF_ACCOUNTDISABLE = 0x0002
_UF_NORMAL_ACCOUNT = 0x0200
_UF_DONT_EXPIRE_PASSWD = 0x10000
_USER_PRIV_USER = 1


class NullAccountManager:
    """Same-account mode: no Windows accounts; the worker runs as the gateway's own account."""

    def ensure(self, user_id: int, workspace: Path) -> None:
        return None

    def disable(self, user_id: int, disabled: bool) -> None:
        return None

    def remove(self, user_id: int, workspace: Path) -> None:
        return None

    def housekeeping(self, known_user_ids: set[int]) -> None:
        return None


def new_password() -> str:
    """32 random characters with every class present (meets any local complexity policy)."""
    alphabet = string.ascii_letters + string.digits + "!#$%&()*+,-.:;<=>?@[]^_{|}~"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(PASSWORD_LENGTH))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
                and any(not c.isalnum() for c in pw)):
            return pw


# ---- ctypes: NetUser*, LSA, DeleteProfile --------------------------------------------------------

class _USER_INFO_1(ctypes.Structure):
    _fields_ = [("name", w.LPWSTR), ("password", w.LPWSTR), ("password_age", w.DWORD), ("priv", w.DWORD),
                ("home_dir", w.LPWSTR), ("comment", w.LPWSTR), ("flags", w.DWORD), ("script_path", w.LPWSTR)]


class _USER_INFO_1003(ctypes.Structure):
    _fields_ = [("password", w.LPWSTR)]


class _USER_INFO_1008(ctypes.Structure):
    _fields_ = [("flags", w.DWORD)]


class _LSA_UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", w.USHORT), ("MaximumLength", w.USHORT), ("Buffer", w.LPWSTR)]


class _LSA_OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Length", w.ULONG), ("RootDirectory", w.HANDLE), ("ObjectName", ctypes.c_void_p),
                ("Attributes", w.ULONG), ("SecurityDescriptor", ctypes.c_void_p),
                ("SecurityQualityOfService", ctypes.c_void_p)]


def _netapi():
    n = ctypes.WinDLL("netapi32", use_last_error=True)
    n.NetUserAdd.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p, ctypes.POINTER(w.DWORD)]
    n.NetUserDel.argtypes = [w.LPCWSTR, w.LPCWSTR]
    n.NetUserGetInfo.argtypes = [w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    n.NetUserSetInfo.argtypes = [w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_void_p, ctypes.POINTER(w.DWORD)]
    n.NetUserChangePassword.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR]
    n.NetApiBufferFree.argtypes = [ctypes.c_void_p]
    for fn in (n.NetUserAdd, n.NetUserDel, n.NetUserGetInfo, n.NetUserSetInfo, n.NetUserChangePassword):
        fn.restype = w.DWORD
    return n


def _net_error(what: str, code: int) -> OSError:
    return OSError(code, f"{what} failed (error {code})", None, code)


def net_user_add(name: str, password: str, comment: str) -> bool:
    """Create a standard local account. False when it already exists."""
    info = _USER_INFO_1(name, password, 0, _USER_PRIV_USER, None, comment,
                        _UF_SCRIPT | _UF_NORMAL_ACCOUNT | _UF_DONT_EXPIRE_PASSWD, None)
    err = w.DWORD()
    rc = _netapi().NetUserAdd(None, 1, ctypes.byref(info), ctypes.byref(err))
    if rc == _NERR_USER_EXISTS:
        return False
    if rc:
        raise _net_error("NetUserAdd", rc)
    return True


def _user_flags(name: str) -> int:
    n = _netapi()
    buf = ctypes.c_void_p()
    rc = n.NetUserGetInfo(None, name, 1, ctypes.byref(buf))
    if rc:
        raise _net_error("NetUserGetInfo", rc)
    try:
        return int(ctypes.cast(buf, ctypes.POINTER(_USER_INFO_1)).contents.flags)
    finally:
        n.NetApiBufferFree(buf)


def net_user_set_disabled(name: str, disabled: bool) -> None:
    flags = _user_flags(name)
    flags = (flags | _UF_ACCOUNTDISABLE) if disabled else (flags & ~_UF_ACCOUNTDISABLE)
    info, err = _USER_INFO_1008(flags), w.DWORD()
    rc = _netapi().NetUserSetInfo(None, name, 1008, ctypes.byref(info), ctypes.byref(err))
    if rc:
        raise _net_error("NetUserSetInfo(1008)", rc)


def net_user_is_disabled(name: str) -> bool:
    return bool(_user_flags(name) & _UF_ACCOUNTDISABLE)


def net_user_reset_password(name: str, password: str) -> None:
    """An administrative reset. Only for an account with nothing to lose (just created): a reset orphans
    the account's DPAPI master keys and so its Credential Manager entries."""
    info, err = _USER_INFO_1003(password), w.DWORD()
    rc = _netapi().NetUserSetInfo(None, name, 1003, ctypes.byref(info), ctypes.byref(err))
    if rc:
        raise _net_error("NetUserSetInfo(1003)", rc)


def net_user_change_password(name: str, old: str, new: str) -> None:
    """A password *change* with the old password, which keeps the account's DPAPI keys usable."""
    # The machine's own name, not None (None means the caller's logon domain, which for LocalSystem is
    # not necessarily this machine's account database).
    rc = _netapi().NetUserChangePassword(socket.gethostname(), name, old, new)
    if rc:
        raise _net_error("NetUserChangePassword", rc)


def net_user_delete(name: str) -> bool:
    rc = _netapi().NetUserDel(None, name)
    if rc == _NERR_USER_NOT_FOUND:
        return False
    if rc:
        raise _net_error("NetUserDel", rc)
    return True


def _advapi():
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.LsaOpenPolicy.argtypes = [ctypes.c_void_p, ctypes.POINTER(_LSA_OBJECT_ATTRIBUTES), w.DWORD,
                                ctypes.POINTER(w.HANDLE)]
    a.LsaAddAccountRights.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.POINTER(_LSA_UNICODE_STRING), w.ULONG]
    a.LsaRemoveAccountRights.argtypes = [w.HANDLE, ctypes.c_void_p, w.BOOLEAN, ctypes.c_void_p, w.ULONG]
    a.LsaEnumerateAccountRights.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                            ctypes.POINTER(w.ULONG)]
    a.LsaFreeMemory.argtypes = [ctypes.c_void_p]
    a.LsaClose.argtypes = [w.HANDLE]
    a.LsaNtStatusToWinError.argtypes = [w.ULONG]
    a.LsaNtStatusToWinError.restype = w.ULONG
    a.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    for fn in (a.LsaOpenPolicy, a.LsaAddAccountRights, a.LsaRemoveAccountRights, a.LsaEnumerateAccountRights):
        fn.restype = w.ULONG
    return a


class _Lsa:
    def __init__(self) -> None:
        self.a = _advapi()
        self.handle = w.HANDLE()
        attrs = _LSA_OBJECT_ATTRIBUTES()
        attrs.Length = ctypes.sizeof(attrs)
        status = self.a.LsaOpenPolicy(None, ctypes.byref(attrs), 0x00000010 | 0x00000800, ctypes.byref(self.handle))
        self._check("LsaOpenPolicy", status)

    def _check(self, what: str, status: int) -> None:
        if status:
            code = int(self.a.LsaNtStatusToWinError(status))
            raise OSError(code, f"{what} failed (error {code})", None, code)

    def __enter__(self) -> "_Lsa":
        return self

    def __exit__(self, *exc) -> None:
        self.a.LsaClose(self.handle)

    def _sid(self, sid: str):
        psid = ctypes.c_void_p()
        if not self.a.ConvertStringSidToSidW(sid, ctypes.byref(psid)):
            raise OSError(ctypes.get_last_error(), "ConvertStringSidToSidW failed")
        return psid

    def add(self, sid: str, rights: tuple[str, ...]) -> None:
        arr = (_LSA_UNICODE_STRING * len(rights))()
        for i, r in enumerate(rights):
            arr[i] = _LSA_UNICODE_STRING(len(r) * 2, len(r) * 2 + 2, r)
        psid = self._sid(sid)
        try:
            self._check("LsaAddAccountRights", self.a.LsaAddAccountRights(self.handle, psid, arr, len(rights)))
        finally:
            ctypes.windll.kernel32.LocalFree(psid)

    def remove_all(self, sid: str) -> None:
        psid = self._sid(sid)
        try:
            status = self.a.LsaRemoveAccountRights(self.handle, psid, True, None, 0)
            if status and int(self.a.LsaNtStatusToWinError(status)) != 2:  # ERROR_FILE_NOT_FOUND: had none
                self._check("LsaRemoveAccountRights", status)
        finally:
            ctypes.windll.kernel32.LocalFree(psid)

    def rights(self, sid: str) -> set[str]:
        psid = self._sid(sid)
        buf, count = ctypes.c_void_p(), w.ULONG()
        try:
            status = self.a.LsaEnumerateAccountRights(self.handle, psid, ctypes.byref(buf), ctypes.byref(count))
            if status and int(self.a.LsaNtStatusToWinError(status)) == 2:
                return set()
            self._check("LsaEnumerateAccountRights", status)
            arr = ctypes.cast(buf, ctypes.POINTER(_LSA_UNICODE_STRING))
            return {ctypes.wstring_at(arr[i].Buffer, arr[i].Length // 2) for i in range(count.value)}
        finally:
            if buf:
                self.a.LsaFreeMemory(buf)
            ctypes.windll.kernel32.LocalFree(psid)


def grant_worker_rights(sid: str) -> None:
    with _Lsa() as lsa:
        lsa.add(sid, WORKER_RIGHTS)


def account_rights(sid: str) -> set[str]:
    with _Lsa() as lsa:
        return lsa.rights(sid)


def remove_all_rights(sid: str) -> None:
    with _Lsa() as lsa:
        lsa.remove_all(sid)


def delete_profile(sid: str) -> bool:
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    userenv.DeleteProfileW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR]
    if userenv.DeleteProfileW(sid, None, None):
        return True
    code = ctypes.get_last_error()
    if code in (2, 3):  # no profile was ever created
        return False
    raise OSError(code, f"DeleteProfileW failed (error {code})", None, code)


# ---- the manager ---------------------------------------------------------------------------------

class WindowsAccountManager:
    def __init__(self, store, data_root: Path, *, prefix: str = DEFAULT_PREFIX, rotate_days: float = 90.0,
                 gateway_sid: str | None = None, clock: Callable[[], float] = time.time) -> None:
        if not winapi.IS_WINDOWS:
            raise OSError("per-user Windows accounts need Windows")
        if not prefix or len(prefix) > 12 or not all(c.isalnum() or c in "_-" for c in prefix):
            raise ValueError("account prefix must be 1-12 letters, digits, '_' or '-'")
        self.store = store
        self.data_root = Path(data_root)
        self.prefix = prefix
        self.rotate_seconds = float(rotate_days) * 86400
        self.gateway_sid = gateway_sid or winapi.current_user_sid()
        self._clock = clock

    def account_name(self, user_id: int) -> str:
        name = f"{self.prefix}{int(user_id)}"
        if len(name) > 20:
            raise ValueError("account name longer than 20 characters")
        return name

    def ensure(self, user_id: int, workspace: Path) -> None:
        row = self.store.get_worker_account(user_id)
        if row is not None and row["state"] != "removing":
            if not row["sid"] or winapi.lookup_account_sid(row["account_name"]) != row["sid"]:
                raise RuntimeError(f"worker account {row['account_name']} is missing; run account housekeeping")
            return
        if row is not None:
            raise RuntimeError("this user's previous worker account is still being removed")
        name = self.account_name(user_id)
        password = new_password()
        created = net_user_add(name, password, "Retirement planner worker (managed by the gateway)")
        if not created:
            # Left over from an interrupted create (the row was never stored): nothing in it to keep.
            LOG.warning("worker account %s already existed; resetting its password", name)
            net_user_reset_password(name, password)
        sid = winapi.lookup_account_sid(name)
        if not sid:
            raise RuntimeError(f"worker account {name} was created but has no SID")
        grant_worker_rights(sid)
        self.store.put_worker_account(user_id, name, sid, winapi.dpapi_protect(password.encode("utf-8")), self._clock())
        del password
        workspace.mkdir(parents=True, exist_ok=True)
        # A brand-new account cannot have a running worker, so resetting whatever is already in the folder is safe.
        acl.lock_user_folder(workspace, account_sid=sid, gateway_sid=self.gateway_sid, worker_stopped=True)
        LOG.info("worker account %s created for user %s", name, user_id)

    def credentials(self, user_id: int) -> tuple[str, str]:
        row = self.store.get_worker_account(user_id)
        if row is None:
            raise RuntimeError("this user has no worker account")
        if row["state"] != "active":
            raise RuntimeError("this user's worker account is not active")
        return row["account_name"], winapi.dpapi_unprotect(bytes(row["secret"])).decode("utf-8")

    def sid(self, user_id: int) -> str | None:
        row = self.store.get_worker_account(user_id)
        return row["sid"] if row else None

    def disable(self, user_id: int, disabled: bool) -> None:
        row = self.store.get_worker_account(user_id)
        if row is None:
            return
        net_user_set_disabled(row["account_name"], disabled)
        self.store.update_worker_account(user_id, state="disabled" if disabled else "active")

    def remove(self, user_id: int, workspace: Path) -> None:
        """Delete the account, its rights and its profile (the worker must already be stopped)."""
        row = self.store.get_worker_account(user_id)
        if row is None:
            return
        self.store.update_worker_account(user_id, state="removing")
        name, sid = row["account_name"], row["sid"]
        if sid:
            remove_all_rights(sid)
        net_user_delete(name)
        if sid:
            delete_profile(sid)
        self.store.delete_worker_account(user_id)
        LOG.info("worker account %s for user %s removed", name, user_id)

    def rotate(self, user_id: int) -> None:
        row = self.store.get_worker_account(user_id)
        if row is None or row["state"] != "active":
            return
        old = winapi.dpapi_unprotect(bytes(row["secret"])).decode("utf-8")
        new = new_password()
        net_user_change_password(row["account_name"], old, new)
        self.store.update_worker_account(user_id, secret=winapi.dpapi_protect(new.encode("utf-8")),
                                         rotated_at=self._clock())
        del old, new
        LOG.info("worker account password for user %s rotated", user_id)

    def housekeeping(self, known_user_ids: set[int]) -> None:
        """Retry removal of accounts whose gateway user is gone; rotate passwords that are due."""
        now = self._clock()
        for row in self.store.list_worker_accounts():
            uid = int(row["user_id"])
            try:
                if uid not in known_user_ids or row["state"] == "removing":
                    self.remove(uid, self.data_root / "users" / str(uid))
                elif row["state"] == "active" and self.rotate_seconds and now - row["rotated_at"] > self.rotate_seconds:
                    self.rotate(uid)
            except OSError:
                LOG.warning("worker account housekeeping failed for user %s", uid, exc_info=True)
