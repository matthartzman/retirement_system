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


def _run_as(box, uid: int, argv: list[str], timeout: float = 60.0, env: dict | None = None) -> int:
    proc = PerAccountLauncher(box["mgr"]).launch(LaunchSpec(uid, argv, Path("C:\\Windows\\System32"), env or {},
                                                            256 * 2**20, 8))
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


def _process_session(pid: int) -> int | None:
    sid = ctypes.c_ulong()
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    return int(sid.value) if k.ProcessIdToSessionId(ctypes.c_ulong(pid), ctypes.byref(sid)) else None


def _app_copy(box) -> Path:
    """A copy of ``src`` in the throwaway folder, which the worker accounts can read. The repository itself may sit
    in a folder only its owner can read (a per-user ACL), and the probe imports ``src.secrets_store``."""
    app = box["base"] / "app"
    if not app.exists():
        shutil.copytree(ROOT / "src", app / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return app


# Runs the real ``src.secrets_store`` as a dedicated worker would (remote mode plus the per-account launcher's flag).
# The result file always gets written: a traceback instead of the value if anything raised, because the child has no
# stderr to read.
_CRED_PROBE = chr(10).join([
    "import sys",
    "try:",
    "    sys.path.insert(0, sys.argv[1])",
    "    from src import secrets_store as s",
    "    if sys.argv[2] == 'set': s.set_secret('elevated-probe', sys.argv[4])",
    "    result = s.encryption_status()['mode'] + ' ' + s.get_secret('elevated-probe')",
    "except BaseException:",
    "    import traceback",
    "    result = 'PROBE FAILED ' + traceback.format_exc().replace(chr(10), ' | ')",
    "open(sys.argv[3], 'w', encoding='utf-8').write(result)",
])


def test_a_stored_credential_survives_repeated_password_rotation_and_goes_with_the_user(box):
    """The question Phase 3 left open. Measured on this machine (see the monarch-secrets design note): Windows
    Credential Manager lost a stored entry in about half of the rotations, so a dedicated worker keeps its secrets
    under machine-scope DPAPI in its own app.db (``src/secrets_store.py``). This runs the real store as the worker
    account, rotates the password several times with no logon session open, and requires the secret every time.

    Run it as SYSTEM in session 0, like the gateway service (``tools/run_elevated_tests_as_system.ps1``): a worker
    started from an interactive admin shell by CreateProcessWithTokenW cannot initialise user32, so ctypes and
    keyring fail there for a reason that has nothing to do with secrets."""
    assert _process_session(os.getpid()) == 0, (
        "run this test as SYSTEM (session 0), like the gateway service: powershell -ExecutionPolicy Bypass -File "
        "tools/run_elevated_tests_as_system.ps1 -Filter credential. From an interactive session the worker cannot "
        "initialise user32 and fails for a reason unrelated to secrets.")
    mgr, uid = box["mgr"], 907
    ws = _ws(box, uid)
    mgr.ensure(uid, ws)
    value = "probe-" + secrets.token_hex(4)
    env = {"RETIREMENT_SYSTEM_REMOTE_MODE": "1", "RETIREMENT_SYSTEM_WORKSPACE_ROOT": str(ws)}
    out = ws / "cred.txt"
    argv = [box["python"], "-E", "-s", "-c", _CRED_PROBE, str(_app_copy(box))]
    expected = f"machine-dpapi {value}"

    def run(*extra) -> str:
        out.unlink(missing_ok=True)
        assert _run_as(box, uid, argv + [extra[0], str(out), *extra[1:]], env=env) == 0
        return out.read_text(encoding="utf-8")

    assert run("set", value) == expected
    profile = Path("C:/Users") / mgr.account_name(uid)
    for n in range(1, 5):
        mgr.rotate(uid)
        assert run("get") == expected, f"the secret did not survive password rotation number {n}"
    sup = _supervisor(box)
    try:
        sup.user_deleted(uid)
    finally:
        sup.shutdown()
    assert not profile.exists(), "the profile outlived the user"
    assert not ws.exists(), "the workspace (and the secrets in its app.db) outlived the user"
