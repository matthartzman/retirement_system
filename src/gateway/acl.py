"""Folder permissions for the multi-user server: apply them, and check them loudly.

Phase 0 found that a standard account could read any folder created under ``C:\\`` (inherited read for
Users), so being a separate account protects nothing by itself. Layout (see the design note):

* data root, ``data/users/``, the ``gateway.db`` folder and backups: SYSTEM, Administrators and the
  gateway account only, inheritance removed;
* ``data/users/<id>/``: the same plus that user's worker account (modify);
* the install folder and runtime: the same plus Users read and execute, no write for anyone else.

``setup`` applies these with ``icacls`` (no secret is ever on a command line); ``check`` reads every DACL
and reports each folder a worker could read or write that it should not. Run as
``python -m src.gateway.acl setup|check ...``; ``check`` exits 1 when it finds anything.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes as w
from dataclasses import dataclass
from pathlib import Path

from . import fsguard

SYSTEM = "S-1-5-18"
ADMINISTRATORS = "S-1-5-32-544"
USERS = "S-1-5-32-545"
OWNER_RIGHTS = "S-1-3-4"
TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
# Groups every worker account's token carries (or may carry): a grant to one of them reaches all workers.
BROAD_SIDS = {
    "S-1-1-0": "Everyone", USERS: "Users", "S-1-5-11": "Authenticated Users", "S-1-5-4": "INTERACTIVE",
    "S-1-5-3": "BATCH", "S-1-5-113": "Local account", "S-1-5-32-546": "Guests", "S-1-5-32-559": "Performance Log Users",
    "S-1-5-32-558": "Performance Monitor Users", "S-1-5-2": "NETWORK", "S-1-5-7": "ANONYMOUS LOGON",
    "S-1-15-2-1": "ALL APPLICATION PACKAGES", "S-1-3-0": "CREATOR OWNER", "S-1-5-14": "Remote Interactive",
}
_READ_BITS = 0x0001 | 0x0020 | 0x80000000 | 0x10000000 | 0x20000000  # read data, execute, GENERIC_READ/ALL/EXECUTE
_WRITE_BITS = (0x0002 | 0x0004 | 0x0040 | 0x00010000 | 0x00040000 | 0x00080000 | 0x40000000 | 0x10000000
               | 0x0010 | 0x0100)  # write/append data, delete child, DELETE, WRITE_DAC/OWNER, GENERIC_WRITE/ALL, EA, attrs
MAX_WALK = 20000


class AclError(RuntimeError):
    pass


@dataclass(frozen=True)
class Ace:
    sid: str
    allow: bool
    mask: int
    inherit_only: bool

    @property
    def reads(self) -> bool:
        return bool(self.mask & _READ_BITS)

    @property
    def writes(self) -> bool:
        return bool(self.mask & _WRITE_BITS)


@dataclass(frozen=True)
class Dacl:
    protected: bool
    aces: tuple[Ace, ...] | None  # None: a NULL DACL (everyone has full access)
    owner: str | None = None  # SID of the object's owner

    def effective(self, allowed: set[str]) -> tuple[Ace, ...]:
        """The ACEs that matter: OWNER RIGHTS only grants to whoever owns the object, so while the owner is
        one of the ``allowed`` SIDs it widens nothing (CI runners add such an ACE). Owned by anyone else, it
        reaches that account and is kept."""
        return tuple(a for a in self.aces or () if not (a.sid == OWNER_RIGHTS and self.owner in allowed))


# ---- reading -------------------------------------------------------------------------------------

def read_dacl(path: Path) -> Dacl:
    if os.name != "nt":
        raise AclError("ACL checks need Windows")
    from . import winapi  # noqa: PLC0415

    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.GetNamedSecurityInfoW.argtypes = [w.LPCWSTR, ctypes.c_int, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    a.GetNamedSecurityInfoW.restype = w.DWORD
    a.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)]
    a.GetAce.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    dacl, sd, owner_sid = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    rc = a.GetNamedSecurityInfoW(str(path), 1, 0x4 | 0x1, ctypes.byref(owner_sid), None, ctypes.byref(dacl), None, ctypes.byref(sd))
    if rc:
        raise OSError(rc, f"GetNamedSecurityInfoW failed for a folder (error {rc})", None, rc)
    try:
        control, rev = w.WORD(), w.DWORD()
        a.GetSecurityDescriptorControl(sd, ctypes.byref(control), ctypes.byref(rev))
        protected = bool(control.value & 0x1000)  # SE_DACL_PROTECTED
        owner = winapi.sid_to_string(owner_sid) if owner_sid.value else None
        if not dacl.value:
            return Dacl(protected, None, owner)
        count = ctypes.c_uint16.from_address(dacl.value + 4).value  # ACL.AceCount
        aces = []
        for i in range(count):
            pace = ctypes.c_void_p()
            if not a.GetAce(dacl, i, ctypes.byref(pace)):
                raise OSError(ctypes.get_last_error(), "GetAce failed")
            ace_type = ctypes.c_ubyte.from_address(pace.value).value
            flags = ctypes.c_ubyte.from_address(pace.value + 1).value
            if ace_type not in (0, 1):  # only plain allow/deny ACEs carry a SID at offset 8
                continue
            mask = ctypes.c_uint32.from_address(pace.value + 4).value
            sid = winapi.sid_to_string(ctypes.c_void_p(pace.value + 8))
            aces.append(Ace(sid, ace_type == 0, mask, bool(flags & 0x08)))
        return Dacl(protected, tuple(aces), owner)
    finally:
        ctypes.windll.kernel32.LocalFree(sd)


# ---- applying ------------------------------------------------------------------------------------

_REFUSED_ROOTS_ENV = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "USERPROFILE", "PUBLIC")


def _guard(path: Path) -> Path:
    """Refuse to rewrite the ACL of a drive root, a system or profile folder, or a git working copy
    (the owner's real data lives in one)."""
    p = Path(path).resolve()
    if p.parent == p:
        raise AclError("refusing to change the permissions of a drive root")
    for name in _REFUSED_ROOTS_ENV:
        value = os.environ.get(name)
        if value and Path(value).resolve() == p:
            raise AclError("refusing to change the permissions of a system or profile folder")
    if p.parent.resolve() == Path(os.environ.get("SYSTEMDRIVE", "C:") + "\\Users").resolve():
        raise AclError("refusing to change the permissions of a user profile")
    for candidate in (p, *p.parents):
        if (candidate / ".git").exists():
            raise AclError("refusing to change the permissions inside a git working copy")
    return p


def _icacls(*args: str) -> None:
    proc = subprocess.run(["icacls", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise AclError(f"icacls failed ({proc.returncode}): {(proc.stdout + proc.stderr).strip()[-400:]}")


def _lock(path: Path, grants: list[str]) -> None:
    p = _guard(path)
    p.mkdir(parents=True, exist_ok=True)
    if any(p.iterdir()):
        fsguard.remove_reparse_points(p)  # icacls /T follows links a worker may have planted
        _icacls(str(p / "*"), "/reset", "/T", "/C", "/Q")  # children inherit from the folder only
    _icacls(str(p), "/inheritance:r", "/grant:r", *grants, "/C", "/Q")


def _core(gateway_sid: str, rights: str = "F") -> list[str]:
    sids = dict.fromkeys([SYSTEM, ADMINISTRATORS, gateway_sid])
    return [f"*{s}:(OI)(CI){rights}" for s in sids]


def lock_gateway_only(path: Path, *, gateway_sid: str) -> None:
    """Data root, ``data/users/``, the ``gateway.db`` folder, backups."""
    _lock(path, _core(gateway_sid))


def lock_user_folder(path: Path, *, account_sid: str, gateway_sid: str) -> None:
    _lock(path, _core(gateway_sid) + [f"*{account_sid}:(OI)(CI)M"])


def lock_install_readonly(path: Path, *, gateway_sid: str) -> None:
    _lock(path, _core(gateway_sid) + [f"*{USERS}:(OI)(CI)RX"])


# ---- checking ------------------------------------------------------------------------------------

def _label(sid: str, workers: dict[str, str]) -> str:
    return workers.get(sid) or BROAD_SIDS.get(sid) or sid


def check_private(path: Path, *, allowed: set[str], workers: dict[str, str], what: str, walk: bool = False) -> list[str]:
    """Findings when anyone outside ``allowed`` (SIDs) can read or write ``path`` (and, with ``walk``,
    anything below it)."""
    findings: list[str] = []
    if not path.exists():
        return [f"{what}: missing ({path})"]
    entries = [path]
    if walk:
        for i, child in enumerate(path.rglob("*")):
            if i >= MAX_WALK:
                findings.append(f"{what}: more than {MAX_WALK} entries, the rest were not checked")
                break
            entries.append(child)
    for entry in entries:
        try:
            dacl = read_dacl(entry)
        except OSError as exc:
            findings.append(f"{what}: cannot read permissions of {entry} ({exc.errno})")
            continue
        where = what if entry == path else f"{what} [{entry.relative_to(path)}]"
        if dacl.aces is None:
            findings.append(f"{where}: has no access list at all (everyone has full access)")
            continue
        if entry == path and entry.is_dir() and not dacl.protected:  # files inherit from their folder
            findings.append(f"{what}: still inherits permissions from its parent folder")
        for ace in dacl.effective(allowed):
            if ace.allow and ace.sid not in allowed and (ace.reads or ace.writes):
                findings.append(f"{where}: {_label(ace.sid, workers)} has access")
    return findings


def check_readonly(path: Path, *, writers: set[str], workers: dict[str, str], what: str) -> list[str]:
    """Findings when anyone outside ``writers`` can write ``path`` (reading is allowed: the install)."""
    findings: list[str] = []
    if not path.exists():
        return [f"{what}: missing ({path})"]
    try:
        dacl = read_dacl(path)
    except OSError as exc:
        return [f"{what}: cannot read permissions ({exc.errno})"]
    if dacl.aces is None:
        return [f"{what}: has no access list at all (everyone can write)"]
    for ace in dacl.effective(writers):
        if ace.allow and ace.sid not in writers and ace.writes:
            findings.append(f"{what}: {_label(ace.sid, workers)} can write")
    return findings


def check_not_readable_by_workers(path: Path, *, workers: dict[str, str], what: str) -> list[str]:
    """For folders the setup must not touch (the owner's working copy): report any worker reach."""
    if not path.exists():
        return []
    try:
        dacl = read_dacl(path)
    except OSError as exc:
        return [f"{what}: cannot read permissions ({exc.errno})"]
    if dacl.aces is None:
        return [f"{what}: readable by every account (no access list)"]
    reach = set(BROAD_SIDS) | set(workers)
    return [f"{what}: {_label(a.sid, workers)} can read it" for a in dacl.aces if a.allow and a.sid in reach and a.reads]


def check_layout(*, data_root: Path, gateway_sid: str, workers: dict[int, tuple[str, str]],
                 install_dir: Path | None = None, gateway_db: Path | None = None, backup_dir: Path | None = None,
                 forbid: list[Path] | None = None) -> list[str]:
    """Every finding for the whole layout. ``workers`` maps user id to (account name, SID)."""
    core = {SYSTEM, ADMINISTRATORS, gateway_sid, TRUSTED_INSTALLER}
    names = {sid: f"worker account {name}" for name, sid in workers.values()}
    findings = check_private(data_root, allowed=core, workers=names, what="data root")
    users_dir = data_root / "users"
    findings += check_private(users_dir, allowed=core, workers=names, what="data/users")
    if users_dir.is_dir():
        for child in sorted(users_dir.iterdir()):
            if not child.is_dir():
                continue
            owner = workers.get(int(child.name)) if child.name.isdigit() else None
            allowed = core | ({owner[1]} if owner else set())
            findings += check_private(child, allowed=allowed, workers=names, what=f"data/users/{child.name}", walk=True)
    if gateway_db is not None:
        findings += check_private(gateway_db.parent, allowed=core, workers=names, what="gateway.db folder")
        if gateway_db.exists():
            findings += check_private(gateway_db, allowed=core, workers=names, what="gateway.db")
    if backup_dir is not None:
        findings += check_private(backup_dir, allowed=core, workers=names, what="backups")
    if install_dir is not None:
        findings += check_readonly(install_dir, writers=core, workers=names, what="install folder")
    for path in forbid or []:
        findings += check_not_readable_by_workers(path, workers=names, what=f"protected folder {path}")
    return findings


# ---- CLI -----------------------------------------------------------------------------------------

def _workers_from_db(db: Path | None) -> dict[int, tuple[str, str]]:
    if db is None or not db.exists():
        return {}
    from .store import GatewayStore  # noqa: PLC0415

    return {int(r["user_id"]): (r["account_name"], r["sid"]) for r in GatewayStore(db).list_worker_accounts() if r["sid"]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.gateway.acl", description=__doc__.split("\n\n")[0])
    p.add_argument("command", choices=("setup", "check"))
    p.add_argument("--data-root", required=True, type=Path)
    p.add_argument("--gateway-db", type=Path, help="gateway.db (also the source of the worker account list)")
    p.add_argument("--install-dir", type=Path, help="the read-only install folder (code and runtime)")
    p.add_argument("--backup-dir", type=Path)
    p.add_argument("--gateway-sid", help="the gateway's account SID (default: the account running this command)")
    p.add_argument("--forbid", type=Path, action="append", default=[],
                   help="a folder worker accounts must not be able to read; checked only, never changed")
    args = p.parse_args(argv)
    from . import winapi  # noqa: PLC0415

    gateway_sid = args.gateway_sid or winapi.current_user_sid()
    workers = _workers_from_db(args.gateway_db)
    if args.command == "setup":
        try:
            lock_gateway_only(args.data_root, gateway_sid=gateway_sid)
            lock_gateway_only(args.data_root / "users", gateway_sid=gateway_sid)
            for uid, (_name, sid) in sorted(workers.items()):
                lock_user_folder(args.data_root / "users" / str(uid), account_sid=sid, gateway_sid=gateway_sid)
            if args.gateway_db is not None:
                lock_gateway_only(args.gateway_db.parent, gateway_sid=gateway_sid)
            if args.backup_dir is not None:
                lock_gateway_only(args.backup_dir, gateway_sid=gateway_sid)
            if args.install_dir is not None:
                lock_install_readonly(args.install_dir, gateway_sid=gateway_sid)
        except AclError as exc:
            print(f"setup stopped: {exc}", file=sys.stderr)
            return 2
        print("permissions applied; checking")
    findings = check_layout(data_root=args.data_root, gateway_sid=gateway_sid, workers=workers,
                            install_dir=args.install_dir, gateway_db=args.gateway_db, backup_dir=args.backup_dir,
                            forbid=args.forbid)
    if findings:
        print(f"FAILED: {len(findings)} permission problem(s):", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK: no worker account can read or write anything it should not")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
