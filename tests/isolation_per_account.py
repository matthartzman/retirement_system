"""Opt-in per-account mode for the isolation gate (security review condition 6).

Default (PR CI, unelevated): the three isolation modules start the gateway with the same-account launcher from
the source tree. With ``RETIREMENT_ISOLATION_LAUNCHER=per-account`` they instead start it with
``--launcher per-account`` from an INSTALLED copy (``RETIREMENT_ISOLATION_INSTALL_DIR`` and
``RETIREMENT_ISOLATION_PYTHON``), so every user's worker is a real ``rpwtest_<n>`` Windows account.

It changes the machine, so it also needs ``RETIREMENT_ELEVATED_TESTS=1`` in an elevated shell (the gateway must
be LocalSystem: use ``tools/run_isolation_on_installed_build.ps1``). Everything throwaway lives under
``C:\\rpwtest_<hex>``; the owner's real data and state folders are never used (guarded below).
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest

LAUNCHER_ENV = "RETIREMENT_ISOLATION_LAUNCHER"
INSTALL_ENV = "RETIREMENT_ISOLATION_INSTALL_DIR"
PYTHON_ENV = "RETIREMENT_ISOLATION_PYTHON"
PREFIX = "rpwtest_"
# Never place throwaway data under these (the owner's real server).
PROTECTED = (Path("C:/RetirementPlanner/data"), Path("C:/RetirementPlanner/state"))


class PerAccountConfigError(Exception):
    pass


def per_account_requested(environ=None) -> bool:
    return (environ if environ is not None else os.environ).get(LAUNCHER_ENV, "").strip().lower() == "per-account"


def elevated_allowed(environ=None) -> bool:
    env = environ if environ is not None else os.environ
    if env.get("RETIREMENT_ELEVATED_TESTS") != "1" or os.name != "nt":
        return False
    import ctypes  # noqa: PLC0415
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def per_account_config(environ=None) -> dict | None:
    """None for the default mode. For per-account: ``{"install_dir", "python"}``, or skips when not elevated, or
    raises PerAccountConfigError for a bad install dir / python (so a typo is loud, not a silent same-account run)."""
    env = environ if environ is not None else os.environ
    if not per_account_requested(env):
        value = env.get(LAUNCHER_ENV, "").strip()
        if value and value.lower() != "same-account":
            raise PerAccountConfigError(f"{LAUNCHER_ENV} must be 'per-account' or unset, not {value!r}")
        return None
    if not elevated_allowed(env):
        pytest.skip("per-account isolation: needs RETIREMENT_ELEVATED_TESTS=1 in an elevated shell "
                    "(see tools/run_isolation_on_installed_build.ps1)")
    install, python = env.get(INSTALL_ENV, "").strip(), env.get(PYTHON_ENV, "").strip()
    if not install or not python:
        raise PerAccountConfigError(f"per-account mode needs {INSTALL_ENV} and {PYTHON_ENV}")
    install_dir, py = Path(install), Path(python)
    if not (install_dir / "src" / "gateway").is_dir():
        raise PerAccountConfigError(f"{INSTALL_ENV}={install}: no src/gateway there")
    if not py.is_file():
        raise PerAccountConfigError(f"{PYTHON_ENV}={python}: not a file")
    return {"install_dir": install_dir, "python": py}


def assert_throwaway(path: Path) -> None:
    p = path.resolve()
    for guarded in PROTECTED:
        if p == guarded.resolve() or guarded.resolve() in p.parents:
            raise PerAccountConfigError(f"refusing to use {p}: inside the owner's real server folders")


def gateway_command(python, db: Path, data_root: Path, ready_file: Path, *, public_origin: str, shared_key_env: str,
                    per_account: dict | None) -> list[str]:
    """The gateway command line; ``per_account`` adds the launcher, account prefix, install dir and worker Python."""
    cmd = [str(python), "-m", "src.gateway", "--db", str(db), "--local-port", "0", "--funnel-port", "0",
           "--public-origin", public_origin, "--no-tailscale-check", "--data-root", str(data_root), "--provision", "demo",
           "--ready-file", str(ready_file), "--build-concurrency", "1", "--pass-env", shared_key_env,
           "--monarch-connector",
           "--worker-env", "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1",
           "--worker-env", "RETIREMENT_SYSTEM_FROZEN_TODAY=2026-08-04"]
    if per_account:
        cmd += ["--launcher", "per-account", "--account-prefix", PREFIX,
                "--install-dir", str(per_account["install_dir"]), "--python", str(per_account["python"])]
    return cmd


def new_box() -> Path:
    base = Path(f"C:\\rpwtest_{secrets.token_hex(3)}")
    assert_throwaway(base)
    base.mkdir()
    return base


def local_users() -> list[str]:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-LocalUser).Name"], capture_output=True,
                         text=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def leftover_accounts() -> list[str]:
    return [n for n in local_users() if n.lower().startswith(PREFIX)]


def force_rmtree(path: Path) -> None:
    if not path.exists():
        return
    subprocess.run(["takeown", "/F", str(path), "/R", "/D", "Y"], capture_output=True)
    subprocess.run(["icacls", str(path), "/grant", "*S-1-5-32-544:F", "/T", "/C", "/Q"], capture_output=True)
    shutil.rmtree(path, ignore_errors=True)


_LIST_SIDS = r"""
Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like 'C:\Users\rpwtest_*' } | ForEach-Object { $_.SID }
"""
_REMOVE = r"""
Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like 'C:\Users\rpwtest_*' } | ForEach-Object {
    try { Remove-CimInstance -InputObject $_ -ErrorAction Stop; "removed $($_.LocalPath)" }
    catch { "remove $($_.LocalPath) failed: $($_.Exception.Message)" }
}
"""


def _enable_privileges(*names: str) -> None:
    """Switch on privileges the token holds but has disabled (``reg unload`` does not, and gets 'Access is denied')."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes as w  # noqa: PLC0415

    class LUID(ctypes.Structure):
        _fields_ = [("Low", w.DWORD), ("High", w.LONG)]

    class LAA(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", w.DWORD)]

    class TP(ctypes.Structure):
        _fields_ = [("Count", w.DWORD), ("Privileges", LAA * 1)]

    k, a = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("advapi32", use_last_error=True)
    k.GetCurrentProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    a.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    a.LookupPrivilegeValueW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.POINTER(LUID)]
    a.AdjustTokenPrivileges.argtypes = [w.HANDLE, w.BOOL, ctypes.POINTER(TP), w.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    tok = w.HANDLE()
    if not a.OpenProcessToken(k.GetCurrentProcess(), 0x20 | 0x8, ctypes.byref(tok)):  # ADJUST_PRIVILEGES | QUERY
        return
    try:
        for name in names:
            tp = TP()
            tp.Count = 1
            tp.Privileges[0].Attributes = 2  # SE_PRIVILEGE_ENABLED
            if a.LookupPrivilegeValueW(None, name, ctypes.byref(tp.Privileges[0].Luid)):
                a.AdjustTokenPrivileges(tok, False, ctypes.byref(tp), 0, None, None)
    finally:
        k.CloseHandle(tok)


def unload_hive(sid: str) -> list[str]:
    """RegUnLoadKey for a leaked profile hive and its _Classes hive; one result line each."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes as w  # noqa: PLC0415

    _enable_privileges("SeRestorePrivilege", "SeBackupPrivilege")
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.RegUnLoadKeyW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    a.RegUnLoadKeyW.restype = w.LONG
    hku = ctypes.c_void_p(0x80000003)  # HKEY_USERS
    return [f"RegUnLoadKey {sub}: {a.RegUnLoadKeyW(hku, sub)}" for sub in (sid, f"{sid}_Classes")]


def sweep_profiles() -> None:
    """Unload and delete every ``C:\\Users\\rpwtest_*`` profile. The tests end the gateway with TerminateProcess, so
    the worker accounts' registry hives stay loaded (the gateway never ran its own unload) and DeleteProfile cannot
    remove them until they are unloaded. Retried because the dead workers' handles close a moment after the kill."""
    dest = os.environ.get(DIAG_ENV, "").strip()
    for attempt in range(4):
        sids = subprocess.run(["powershell", "-NoProfile", "-Command", _LIST_SIDS], capture_output=True,
                              text=True).stdout.split()
        lines = [line for sid in sids for line in unload_hive(sid)]
        out = subprocess.run(["powershell", "-NoProfile", "-Command", _REMOVE], capture_output=True, text=True)
        if dest:  # what the unload and Remove-CimInstance said, for the owner to read after a failed run
            try:
                Path(dest).mkdir(parents=True, exist_ok=True)
                with (Path(dest) / "profile_sweep.txt").open("a", encoding="utf-8") as fh:
                    fh.write(f"--- attempt {attempt}\n" + "\n".join(lines) + f"\n{out.stdout}{out.stderr}\n")
            except OSError:
                pass
        if not any(p.name.lower().startswith(PREFIX) for p in Path("C:\\Users").iterdir()):
            return
        time.sleep(2)


DIAG_ENV = "RETIREMENT_ISOLATION_DIAG_DIR"


def save_diagnostics(box: Path, data_root: Path, environ=None) -> None:
    """Copy the gateway log and every worker's logs (small text files only) to ``RETIREMENT_ISOLATION_DIAG_DIR``
    before teardown deletes them, so a SYSTEM run that fails can be read by the owner. Best effort."""
    dest = (environ if environ is not None else os.environ).get(DIAG_ENV, "").strip()
    if not dest:
        return
    out = Path(dest) / box.name
    try:
        out.mkdir(parents=True, exist_ok=True)
        for src in [*box.glob("gateway/*.log"), *data_root.glob("users/*/local_state/logs/*.log")]:
            if src.is_file() and src.stat().st_size < 2_000_000:
                rel = src.relative_to(box)
                target = out / "__".join(rel.parts)
                shutil.copyfile(src, target)
    except OSError:
        pass


def cleanup(box: Path, store, data_root: Path) -> None:
    """Remove the throwaway accounts the gateway created, their profiles and folders, then assert none are left."""
    from src.gateway import accounts  # noqa: PLC0415

    save_diagnostics(box, data_root)
    sweep_profiles()  # unload the hives the killed gateway left loaded, so account removal can delete the profiles
    mgr = accounts.WindowsAccountManager(store, data_root, prefix=PREFIX, rotate_days=0)
    for row in store.list_worker_accounts():
        try:
            mgr.remove(int(row["user_id"]), data_root / "users" / str(row["user_id"]))
        except OSError:
            pass
    force_rmtree(box)
    sweep_profiles()
    for p in Path("C:\\Users").iterdir():
        if p.name.lower().startswith(PREFIX):
            force_rmtree(p)
    leftovers = leftover_accounts()
    profiles = [p.name for p in Path("C:\\Users").iterdir() if p.name.lower().startswith(PREFIX)]
    assert not leftovers, f"throwaway accounts left behind: {leftovers}"
    assert not profiles, f"throwaway profiles left behind: {profiles}"
    assert not box.exists(), f"{box} was not removed"
