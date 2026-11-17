"""Per-user Windows accounts on this machine. ELEVATED and machine-changing: skipped unless
``RETIREMENT_ELEVATED_TESTS=1`` in an elevated shell, and run only with the owner's approval.

Creates throwaway accounts ``rpwtest_<n>`` and a throwaway folder ``C:\\rpwtest_<hex>`` (with a copy of
this Python runtime, because the owner's Python under their profile is unreadable to other accounts),
and removes all of it afterwards, then checks the removal. It never touches the owner's data folder or
its permissions. Covers the checks Phase 0 left open:

* batch logon still works with the deny-interactive, deny-remote-desktop and deny-network rights set,
  and interactive logon is refused;
* a worker started as another account is inside its Job Object, and closing the job kills it;
* one account cannot read another's folder or the gateway's folder;
* deleting a user's account while its worker runs (worker, account, profile and folder all go);
* password rotation (a change, not a reset) and a fresh launch with the new password.
"""
from __future__ import annotations

import ctypes
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.gateway import accounts, acl, winapi
from src.gateway.build_queue import BuildQueue
from src.gateway.launchers import LaunchSpec, PerAccountLauncher
from src.gateway.store import GatewayStore
from src.gateway.supervisor import Supervisor, SupervisorConfig, call_worker

pytestmark = [pytest.mark.elevated, pytest.mark.integration]
ROOT = Path(__file__).resolve().parents[1]
PREFIX = "rpwtest_"


def _alive(pid: int) -> bool:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x1000 | 0x00100000, False, int(pid))
    if not h:
        return False
    try:
        return winapi.process_exit_code(h) is None
    finally:
        k.CloseHandle(ctypes.c_void_p(h))


def _force_rmtree(path: Path) -> None:
    if not path.exists():
        return
    subprocess.run(["takeown", "/F", str(path), "/R", "/D", "Y"], capture_output=True)
    subprocess.run(["icacls", str(path), "/grant", "*S-1-5-32-544:F", "/T", "/C", "/Q"], capture_output=True)
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="module")
def box():
    base = Path(f"C:\\rpwtest_{secrets.token_hex(3)}")
    base.mkdir()
    me = winapi.current_user_sid()
    acl.lock_install_readonly(base, gateway_sid=me)  # Users may read and run the runtime copy, not write
    runtime = base / "py"
    rc = subprocess.run(["robocopy", sys.base_prefix, str(runtime), "/E", "/XD", "__pycache__", "/NFL", "/NDL", "/NJH",
                         "/NJS", "/NP", "/MT:16"], capture_output=True).returncode
    assert rc < 8, f"robocopy failed with {rc}"
    data = base / "data"
    gw = base / "gateway"
    data.mkdir()
    gw.mkdir()
    acl.lock_gateway_only(data, gateway_sid=me)
    acl.lock_gateway_only(data / "users", gateway_sid=me)
    acl.lock_gateway_only(gw, gateway_sid=me)
    store = GatewayStore(gw / "gateway.db", scrypt_n=2**4)
    mgr = accounts.WindowsAccountManager(store, data, prefix=PREFIX, rotate_days=0)
    info = {"base": base, "python": str(runtime / "python.exe"), "data": data, "gw": gw, "store": store, "mgr": mgr,
            "me": me}
    try:
        yield info
    finally:
        for row in store.list_worker_accounts():
            try:
                mgr.remove(int(row["user_id"]), data / "users" / str(row["user_id"]))
            except OSError:
                pass
        _force_rmtree(base)
        leftovers = [n for n in _local_users() if n.lower().startswith(PREFIX)]
        profiles = [p.name for p in Path("C:\\Users").iterdir() if p.name.lower().startswith(PREFIX)]
        for p in profiles:
            _force_rmtree(Path("C:\\Users") / p)
        assert not leftovers, f"throwaway accounts left behind: {leftovers}"
        assert not base.exists(), f"{base} was not removed"


def _local_users() -> list[str]:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-LocalUser).Name"], capture_output=True,
                         text=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _ws(box, uid: int) -> Path:
    return box["data"] / "users" / str(uid)


def test_batch_logon_works_with_the_deny_rights_and_interactive_logon_is_refused(box):
    mgr = box["mgr"]
    mgr.ensure(901, _ws(box, 901))
    sid = mgr.sid(901)
    assert set(accounts.WORKER_RIGHTS) <= accounts.account_rights(sid)
    name, pw = mgr.credentials(901)
    tok = winapi.logon(name, pw, winapi.LOGON32_LOGON_BATCH)
    winapi.close_handle(tok)
    with pytest.raises(OSError) as exc:
        winapi.logon(name, pw, winapi.LOGON32_LOGON_INTERACTIVE)
    assert exc.value.winerror == winapi.ERROR_LOGON_TYPE_NOT_GRANTED
    del pw
    assert acl.check_layout(data_root=box["data"], gateway_sid=box["me"],
                            workers={901: (name, sid)}, gateway_db=box["gw"] / "gateway.db") == []


def _run_as(box, uid: int, argv: list[str], timeout: float = 60.0, env: dict | None = None,
            memory: int | None = 256 * 2**20, procs: int | None = 8) -> int:
    proc = PerAccountLauncher(box["mgr"]).launch(LaunchSpec(uid, argv, Path("C:\\Windows\\System32"), env or {},
                                                            memory, procs))
    box['last_method'] = proc.method
    try:
        deadline = time.time() + timeout
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        return proc.poll()
    finally:
        proc.kill()


def test_one_account_cannot_read_another_accounts_or_the_gateways_folder(box):
    mgr = box["mgr"]
    for uid in (902, 903):
        mgr.ensure(uid, _ws(box, uid))
    secret_a = _ws(box, 902) / "plan.rpx"
    secret_a.write_text("account A's plan", encoding="utf-8")
    (box["gw"] / "probe.txt").write_text("gateway only", encoding="utf-8")
    out_b = _ws(box, 903) / "probe.txt"
    probe = chr(10).join([
        "import sys",
        "out = []",
        "for target in sys.argv[1:3]:",
        "    try: out.append('READ ' + open(target, encoding='utf-8').read())",
        "    except PermissionError: out.append('DENIED')",
        "open(sys.argv[3], 'w', encoding='utf-8').write(chr(10).join(out))",
    ])
    code = _run_as(box, 903, [box["python"], "-E", "-s", "-c", probe, str(secret_a), str(box["gw"] / "probe.txt"),
                              str(out_b)])
    assert code == 0, code
    assert out_b.read_text(encoding="utf-8").splitlines() == ["DENIED", "DENIED"]


def _supervisor(box) -> Supervisor:
    cfg = SupervisorConfig(data_root=box["data"], install_dir=ROOT, python=box["python"], provision="demo",
                           start_timeout=120, extra_env={"RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS": "1"})
    return Supervisor(cfg, PerAccountLauncher(box["mgr"]), accounts=box["mgr"], build_queue=BuildQueue(1))


def test_a_worker_runs_as_its_own_account_inside_its_job_and_dies_with_it(box):
    sup = _supervisor(box)
    try:
        ep = sup.endpoint(904)
        assert call_worker(ep, "GET", "/api/ping")[0] == 200
        assert winapi.process_user_sid(ep.pid) == box["mgr"].sid(904)
        proc = sup._slots[904].process
        assert proc.method.startswith("per-account") and proc.job.active_processes() >= 1
        sup.stop(904, "test")
        deadline = time.time() + 15
        while time.time() < deadline and _alive(ep.pid):
            time.sleep(0.2)
        assert not _alive(ep.pid)
    finally:
        sup.shutdown()


def test_password_rotation_keeps_the_account_usable(box):
    mgr = box["mgr"]
    mgr.ensure(905, _ws(box, 905))
    before = mgr.credentials(905)[1]
    mgr.rotate(905)
    assert mgr.credentials(905)[1] != before
    del before
    sup = _supervisor(box)
    try:
        ep = sup.endpoint(905)
        assert call_worker(ep, "GET", "/api/ping")[0] == 200
    finally:
        sup.shutdown()


def test_deleting_a_user_while_its_worker_runs_removes_everything(box):
    sup = _supervisor(box)
    try:
        ep = sup.endpoint(906)
        name = box["mgr"].account_name(906)
        sid = box["mgr"].sid(906)
        sup.user_deleted(906)
        deadline = time.time() + 15
        while time.time() < deadline and _alive(ep.pid):
            time.sleep(0.2)
        assert not _alive(ep.pid)
        assert winapi.lookup_account_sid(name) is None
        assert not _ws(box, 906).exists()
        assert box["store"].get_worker_account(906) is None
        assert not (Path("C:\\Users") / name).exists()
        assert accounts.account_rights(sid) == set()
    finally:
        sup.shutdown()


_CRED_PROBE = chr(10).join([
    "import sys, keyring",
    "sys.path.insert(0, sys.argv[1])",
    "from src import secrets_store as s",
    "backend = keyring.get_keyring()",
    "s._remote_mode_guard(backend)  # remote mode plus the per-account launcher's flag: must accept",
    "if sys.argv[2] == 'set': keyring.set_password(s.SERVICE_NAME, 'elevated-probe', sys.argv[4])",
    "got = keyring.get_password(s.SERVICE_NAME, 'elevated-probe') or ''",
    "open(sys.argv[3], 'w', encoding='utf-8').write(type(backend).__name__ + ' ' + got)",
])


def test_a_stored_credential_survives_password_rotation_and_goes_with_the_user(box):
    """The question Phase 3 left open: NetUserChangePassword (a change, not a reset) should keep the DPAPI master
    keys, so a Credential Manager entry the worker account stored is still readable after rotation; deleting the
    user (NetUserDel + DeleteProfileW) removes it with the profile."""
    mgr, uid = box["mgr"], 907
    ws = _ws(box, uid)
    mgr.ensure(uid, ws)
    value = "probe-" + secrets.token_hex(4)
    env = {"RETIREMENT_SYSTEM_REMOTE_MODE": "1"}
    out = ws / "cred.txt"
    argv = [box["python"], "-E", "-s", "-c", _CRED_PROBE, str(ROOT)]
    assert _run_as(box, uid, argv + ["set", str(out), value], env=env) == 0
    assert out.read_text(encoding="utf-8") == f"WinVaultKeyring {value}"
    profile = Path("C:\\Users") / mgr.account_name(uid)
    mgr.rotate(uid)
    out.unlink()
    assert _run_as(box, uid, argv + ["get", str(out)], env=env) == 0
    assert out.read_text(encoding="utf-8") == f"WinVaultKeyring {value}", "the credential did not survive rotation"
    sup = _supervisor(box)
    try:
        sup.user_deleted(uid)
    finally:
        sup.shutdown()
    assert not profile.exists(), "the profile (and its Credential Manager vault) outlived the user"


# Each stage runs in its own process as the worker account and appends one flushed line per step to a file, so a
# process killed by the loader (0xC0000142) still leaves the last step it reached. The child has no stdio, so the
# file is the only channel.
_STAGE_HEADER = chr(10).join([
    "import sys, os, traceback",
    "def note(msg):",
    "    with open(sys.argv[1], 'a', encoding='utf-8') as f:",
    "        f.write(msg + chr(10)); f.flush(); os.fsync(f.fileno())",
    "note('start')",
    "try:",
])


def _stage(body: str) -> str:
    lines = [("    " + ln) for ln in body.splitlines()]
    tail = ["except BaseException:", "    note('EXC ' + traceback.format_exc().replace(chr(10), ' | '))", "note('end')"]
    return chr(10).join([_STAGE_HEADER, *lines, *tail])


_DIAG_STAGES = {
    "0 bare python": "note('ok')",
    "1 window station and desktop": chr(10).join([
        "import ctypes, ctypes.wintypes as w",
        "u = ctypes.WinDLL('user32', use_last_error=True)",
        "u.GetProcessWindowStation.restype = ctypes.c_void_p",
        "u.GetUserObjectInformationW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]",
        "buf = ctypes.create_unicode_buffer(256); n = w.DWORD()",
        "ok = u.GetUserObjectInformationW(u.GetProcessWindowStation(), 2, buf, 512, ctypes.byref(n))",
        "note('window station ok=%s name=%r' % (ok, buf.value))",
    ]),
    "2 import platform; platform.uname()": "import platform; note(str(platform.uname()))",
    "3 import keyring": "import keyring; note('keyring ' + keyring.__file__)",
    "4 keyring.get_keyring()": "import keyring; note(type(keyring.get_keyring()).__name__)",
    "5 WinVault set and get": chr(10).join([
        "import keyring",
        "keyring.set_password('RetirementSystemDiag', 'u', 'v'); note('set ok')",
        "note('get ' + str(keyring.get_password('RetirementSystemDiag', 'u')))",
        "keyring.delete_password('RetirementSystemDiag', 'u'); note('delete ok')",
    ]),
}


def test_diagnose_worker_credential_manager_stages(box):
    """Diagnostic, not a gate: runs each step of the credential probe in its own process as a worker account and
    reports the exit code and what each reached. Output goes to the terminal (use -s) and to
    ``%TEMP%\rpw_cred_diag.txt`` for pasting back."""
    uid = 908
    ws = _ws(box, uid)
    box["mgr"].ensure(uid, ws)
    report = []
    for label, body in _DIAG_STAGES.items():
        out = ws / "stage.txt"
        out.unlink(missing_ok=True)
        code = _run_as(box, uid, [box["python"], "-E", "-s", "-c", _stage(body), str(out)],
                       env={"RETIREMENT_SYSTEM_REMOTE_MODE": "1"})
        seen = out.read_text(encoding="utf-8") if out.exists() else "(no file written)"
        report.append(f"[{label}] exit={code} hex={(code or 0) & 0xFFFFFFFF:#010x}{chr(10)}{seen}")
    text = (chr(10) * 2).join(report)
    Path(os.environ.get("TEMP", r"C:\Windows\Temp"), "rpw_cred_diag.txt").write_text(text, encoding="utf-8")
    print(chr(10) + text)


def test_diagnose_worker_dll_load_failures(box):
    """Diagnostic, not a gate: which of the job limits, the runtime copy's ACLs or the DLLs themselves makes
    ``import _ctypes`` fail for a worker account. Output: terminal (-s) and ``%TEMP%\rpw_dll_diag.txt``."""
    uid = 909
    ws = _ws(box, uid)
    box["mgr"].ensure(uid, ws)
    out = ws / "stage.txt"
    mib = 2**20
    report = []

    def run(label, body, memory, procs):
        out.unlink(missing_ok=True)
        code = _run_as(box, uid, [box["python"], "-E", "-s", "-c", _stage(body), str(out)], env={}, memory=memory,
                       procs=procs)
        seen = out.read_text(encoding="utf-8") if out.exists() else "(no file written)"
        report.append(f"[{label}] exit={(code or 0) & 0xFFFFFFFF:#010x} via {box.get('last_method')}" + chr(10)
                      + seen.replace(chr(10), " / "))

    for memory, procs in ((None, None), (256 * mib, 8), (1024 * mib, 8), (256 * mib, None)):
        run(f"import _ctypes, memory={memory and memory // mib}MiB procs={procs}", "import _ctypes; note('ok')",
            memory, procs)
    for mod in ("_wmi", "sqlite3", "_ssl", "_socket", "_overlapped", "_decimal"):
        run(f"import {mod} (no limits)", f"import {mod}; note('ok')", None, None)
    py = Path(box["python"]).parent
    for target in (py / "DLLs", py / "DLLs" / "_ctypes.pyd", py / "python312.dll", py / "vcruntime140_1.dll", py):
        r = subprocess.run(["icacls", str(target)], capture_output=True, text=True)
        report.append(f"[icacls {target}]" + chr(10) + r.stdout.strip())
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'} "
                        "-MaxEvents 4 | ForEach-Object { $_.Message }"], capture_output=True, text=True)
    report.append("[recent Application Error events]" + chr(10) + r.stdout.strip())
    text = (chr(10) * 2).join(report)
    Path(os.environ.get("TEMP", r"C:\Windows\Temp"), "rpw_dll_diag.txt").write_text(text, encoding="utf-8")
    print(chr(10) + text)
