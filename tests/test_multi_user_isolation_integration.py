"""The isolation gate: two users behind a real gateway process, each with their own real worker process.

``tests/conftest.py`` builds one workspace per session, so two users cannot share one test process; like
``tests/e2e/fixtures.js`` this starts the gateway (and through it the workers) as subprocesses with a temp
data root, the same-account launcher and no elevation. It shows that user A cannot read or change user B's
plan through the gateway, through a guessed worker port without the token, with a forged Host or Origin,
or with client-supplied credential headers, and that logout and gateway exit stop the workers.

Opt-in per-account mode (elevated, installed build): see ``tests/isolation_per_account.py`` and
``tools/run_isolation_on_installed_build.ps1``.

Slow-ish (two worker starts, about 5-15 s) and Windows-sensitive: run it once per change, not in a loop.
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import isolation_per_account as ipa
from src.gateway import totp
from src.gateway.store import Actor, GatewayStore

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[1]
PW = "isolation gate password 1"
PUBLIC_ORIGIN = "https://node.example.ts.net:8443"
PUBLIC_HOST = "node.example.ts.net:8443"
HOME = ("Other Assets", "Home", "value_as_of_plan_start")
SHARED_KEY_ENV = "RETIREMENT_SYSTEM_FMP_API_KEY"
SHARED_KEY = "gate-shared-provider-key-5f1c0e"  # synthetic sentinel, not a real key
ALICE_ACCOUNT = "Alice Sentinel Savings"
ALICE_MERCHANT = "AliceSentinelMerchant"


def _pid_alive(pid: int) -> bool:
    if sys.platform != "win32":  # POSIX: signal 0 probes the process without touching it
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        try:  # a killed child that nobody has reaped yet is a zombie: gone for our purposes
            return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except (OSError, IndexError):
            return True
    try:
        from src.gateway import winapi  # noqa: PLC0415
        import ctypes  # noqa: PLC0415

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000 | 0x00100000, False, int(pid))
        if not h:
            return False
        try:
            return winapi.process_exit_code(h) is None
        finally:
            k.CloseHandle(ctypes.c_void_p(h))
    except OSError:
        return False


class Client:
    """A browser stand-in on one gateway listener: keeps the session cookie and CSRF token."""

    def __init__(self, port: int, listener: str = "local") -> None:
        self.port, self.listener = port, listener
        self.cookie = ""
        self.csrf = ""

    @property
    def origin(self) -> str:
        return PUBLIC_ORIGIN if self.listener == "funnel" else f"http://127.0.0.1:{self.port}"

    def request(self, method: str, path: str, body=None, headers: dict | None = None, *, origin=True,
                csrf=True) -> tuple[int, dict, bytes]:
        hdrs = {"Host": PUBLIC_HOST if self.listener == "funnel" else f"127.0.0.1:{self.port}"}
        if self.listener == "funnel":
            hdrs["X-Forwarded-For"] = "203.0.113.9"
        data = b""
        if body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        if method not in ("GET", "HEAD"):
            if origin:
                hdrs["Origin"] = self.origin if origin is True else origin
            if csrf and self.csrf:
                hdrs["X-CSRF-Token"] = self.csrf
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        hdrs.update(headers or {})
        hdrs["Content-Length"] = str(len(data))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for k, v in hdrs.items():
                conn.putheader(k, v)
            conn.endheaders(data)
            resp = conn.getresponse()
            raw = resp.read()
            rh = {k.lower(): v for k, v in resp.getheaders()}
        finally:
            conn.close()
        set_cookie = rh.get("set-cookie", "")
        if set_cookie:
            pair = set_cookie.split(";", 1)[0]
            self.cookie = "" if "Max-Age=0" in set_cookie else pair
        return resp.status, rh, raw

    def json(self, method: str, path: str, body=None, **kw) -> tuple[int, dict]:
        status, _h, raw = self.request(method, path, body, **kw)
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, {"_raw": raw[:300].decode("utf-8", "replace")}

    def sign_in(self, username: str, secret: str, step_offset: int = 0) -> None:
        """``step_offset`` 1 for a user's second sign-in within one 30 s step (codes are single-use;
        the gateway accepts the next step's code too)."""
        status, body = self.json("POST", "/api/auth/login", {"username": username, "password": PW})
        assert status == 200 and body.get("next") == "totp", body
        self.csrf = body["csrf_token"]
        code = totp.code_at(secret, int(time.time() // 30) + step_offset)
        status, body = self.json("POST", "/api/auth/totp/verify", {"code": code})
        assert status == 200, body
        status, body = self.json("GET", "/api/auth/session")
        assert status == 200 and body["authenticated"] is True, body
        self.csrf = body["csrf_token"]


def _enrolled_user(store: GatewayStore, username: str, role: str = "user") -> tuple[int, str]:
    actor = Actor(None, "isolation-test")
    now = time.time()
    uid = store.create_user(username, username.title(), role, PW, now=now, actor=actor, must_change=False)
    secret = store.begin_totp_enrolment(uid, now - 3600)
    assert store.confirm_totp(uid, totp.code_at(secret, int((now - 3600) // 30)), now - 3600)
    return uid, secret


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    yield from launch_gateway(tmp_path_factory.mktemp("isolation"), {"alice": "user", "bob": "user"})


def launch_gateway(base: Path, roles: dict[str, str], extra_args: tuple[str, ...] = ()):
    """Start the gateway (and through it the workers) with these enrolled users; yields the info dict, then stops it.

    Default: same-account launcher, source tree, temp data root. With ``RETIREMENT_ISOLATION_LAUNCHER=per-account``
    (elevated only, see ``tests/isolation_per_account.py``) it runs the INSTALLED copy with per-account workers
    under a throwaway ``C:\rpwtest_*`` root, and cleans up the accounts, profiles and folders afterwards."""
    per = ipa.per_account_config()
    box = None
    if per:
        pre = ipa.leftover_accounts()
        assert not pre, f"throwaway accounts from an earlier run are still there: {pre}"
        ipa.sweep_profiles()  # profiles an earlier killed run left loaded (their accounts are already gone)
        from src.gateway import acl, winapi  # noqa: PLC0415

        box = ipa.new_box()
        me = winapi.current_user_sid()
        base, data_root = box / "gateway", box / "data"
        for d in (base, data_root):
            d.mkdir()
            acl.lock_gateway_only(d, gateway_sid=me)
        (data_root / "users").mkdir()
        acl.lock_gateway_only(data_root / "users", gateway_sid=me)
        python, cwd = per["python"], per["install_dir"]
    else:
        data_root = base / "data"
        python, cwd = sys.executable, ROOT
    db = base / "gateway.db"
    store = GatewayStore(db, scrypt_n=2**12)
    users = {name: _enrolled_user(store, name, role) for name, role in roles.items()}
    ready_file = base / "ready.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    env[SHARED_KEY_ENV] = SHARED_KEY  # the gateway holds the shared provider key; workers get it by --pass-env only
    if per:
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # keep the installed folder clean
    cmd = ipa.gateway_command(python, db, data_root, ready_file, public_origin=PUBLIC_ORIGIN,
                              shared_key_env=SHARED_KEY_ENV, per_account=per, extra_args=extra_args)
    log = (base / "gateway.log").open("w", encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if per else 0  # so Ctrl+Break reaches only the gateway
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    try:
        deadline = time.time() + (120 if per else 60)
        while not ready_file.is_file():
            if proc.poll() is not None or time.time() > deadline:
                log.close()
                pytest.fail("gateway did not start:\n" + (base / "gateway.log").read_text(encoding="utf-8")[-3000:])
            time.sleep(0.1)
        ready = json.loads(ready_file.read_text(encoding="utf-8"))
        assert ready["workers"] is True
        info = {"proc": proc, "ready": ready, "users": users, "data_root": data_root, "base": base, "store": store,
                "log": base / "gateway.log", "per_account": bool(per)}
        yield info
    finally:
        if per and proc.poll() is None:
            # A clean stop lets the gateway unload the worker accounts' profiles; a kill leaves them loaded by Windows.
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                proc.wait(timeout=40)
            except (OSError, subprocess.TimeoutExpired):
                pass
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        if box is not None:
            ipa.cleanup(box, store, data_root)


@pytest.fixture(scope="module")
def signed_in(gateway):
    port = gateway["ready"]["local_port"]
    clients = {}
    for name, (_uid, secret) in gateway["users"].items():
        c = Client(port)
        c.sign_in(name, secret)
        clients[name] = c
    return clients


def _port_info(gateway, user: str) -> dict:
    uid = gateway["users"][user][0]
    path = gateway["data_root"] / "users" / str(uid) / "local_state" / "worker.port.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _home_row(client: Client) -> dict:
    status, body = client.json("GET", "/api/config/rows")
    assert status == 200, body
    return next(r for r in body["rows"] if (r["section"], r["subsection"], r["label"]) == HOME)


def test_each_user_reaches_their_own_worker(gateway, signed_in):
    for name in ("alice", "bob"):
        status, body = signed_in[name].json("GET", "/api/ping")
        assert status == 200 and body.get("remote_mode") is True, body
    a, b = _port_info(gateway, "alice"), _port_info(gateway, "bob")
    assert a["port"] != b["port"] and a["pid"] != b["pid"]
    uid_a, uid_b = gateway["users"]["alice"][0], gateway["users"]["bob"][0]
    assert (gateway["data_root"] / "users" / str(uid_a) / "plan.rpx").is_file()
    assert (gateway["data_root"] / "users" / str(uid_b) / "plan.rpx").is_file()


def test_a_plan_edit_by_one_user_is_invisible_to_the_other(signed_in):
    alice, bob = signed_in["alice"], signed_in["bob"]
    before_b = _home_row(bob)["value"]
    row = _home_row(alice)
    status, body = alice.json("POST", "/api/config/rows",
                              {"updates": [{"row_index": row["row_index"], "value": "$1,234,567"}], "sync": True})
    assert status == 200 and body.get("updated") == 1, body
    assert _home_row(alice)["value"] == "$1,234,567"
    assert _home_row(bob)["value"] == before_b != "$1,234,567"


def test_a_guessed_worker_port_without_the_token_is_refused(gateway, signed_in):
    b = _port_info(gateway, "bob")
    for headers in ({}, {"X-API-Token": "guessed-token"}, {"Authorization": "Bearer guessed-token"},
                    {"Host": "evil.example", "X-API-Token": "guessed-token"}):
        conn = http.client.HTTPConnection("127.0.0.1", b["port"], timeout=30)
        try:
            conn.request("GET", "/api/config/rows", headers=headers)
            resp = conn.getresponse()
            body = resp.read()
        finally:
            conn.close()
        assert resp.status in (401, 403, 421), (headers, resp.status)
        assert b"Home" not in body
    # A state-changing call straight at the port, with a forged Origin, changes nothing.
    conn = http.client.HTTPConnection("127.0.0.1", b["port"], timeout=30)
    try:
        conn.request("POST", "/api/config/rows", body=json.dumps({"updates": [], "sync": True}),
                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{b['port']}"})
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    assert resp.status == 401


def test_forged_host_and_origin_are_refused_at_the_gateway(gateway, signed_in):
    alice = signed_in["alice"]
    status, _h, _b = alice.request("GET", "/api/config/rows", headers={"Host": "127.0.0.1:1"})
    assert status == 200  # any loopback Host is the local listener's own; the worker Host is rewritten
    status, _h, _b = alice.request("GET", "/api/config/rows", headers={"Host": "evil.example"})
    assert status == 421
    b = _port_info(gateway, "bob")
    status, body = alice.json("POST", "/api/config/rows", {"updates": [], "sync": True},
                              origin=f"http://127.0.0.1:{b['port']}")
    assert status == 403, body
    status, body = alice.json("POST", "/api/config/rows", {"updates": [], "sync": True}, origin="https://evil.example")
    assert status == 403, body


def test_client_credential_headers_never_reach_a_worker_or_switch_the_user(gateway, signed_in):
    port = gateway["ready"]["funnel_port"]
    alice = Client(port, "funnel")
    alice.sign_in("alice", gateway["users"]["alice"][1], step_offset=1)
    bob_cookie = signed_in["bob"].cookie
    hostile = {"X-API-Token": "client-chosen", "Authorization": "Bearer client-chosen",
               "X-Forwarded-Host": f"127.0.0.1:{_port_info(gateway, 'bob')['port']}", "X-Forwarded-Proto": "http",
               "Forwarded": "for=127.0.0.1;host=127.0.0.1", "X-Real-IP": "127.0.0.1", "X-Gateway-User": "bob"}
    # If any client credential reached the worker it would refuse the request (wrong token), and a
    # switched user would show Bob's value instead of the one Alice saved.
    row = _home_row(alice)
    status, _h, raw = alice.request("GET", "/api/config/rows", headers=hostile)
    assert status == 200, raw[:300]
    rows = json.loads(raw)["rows"]
    assert next(r for r in rows if (r["section"], r["subsection"], r["label"]) == HOME)["value"] == row["value"]
    # Bob's cookie carried alongside Alice's: refused outright rather than one of them being picked.
    try:
        status, _h, raw = alice.request("GET", "/api/config/rows", headers={"Cookie": f"{alice.cookie}; {bob_cookie}"})
        assert status == 400 and b"Home" not in raw, (status, raw[:200])
    finally:
        status, body = alice.json("POST", "/api/auth/logout", {})
        assert status == 200, body


def test_the_event_stream_route_and_the_synchronous_build_are_blocked(signed_in):
    alice = signed_in["alice"]
    status, body = alice.json("GET", "/api/build/events/abc123")
    assert status == 403, body
    status, body = alice.json("POST", "/api/build", {})
    assert status == 403, body
    status, body = alice.json("GET", "/api/build/progress/queued-0000000000000000")
    assert status == 404, body


def test_worker_responses_set_no_cookie_and_build_status_reports_running_state(signed_in):
    status, headers, raw = signed_in["bob"].request("GET", "/api/build/status")
    assert status == 200 and "set-cookie" not in headers
    assert json.loads(raw)["build_running"] is False


def _upload(client: Client, kind: str, text: str) -> tuple[int, dict]:
    import base64  # noqa: PLC0415

    return client.json("POST", "/api/monarch/upload", {"kind": kind, "filename": f"{kind}.csv",
                                                        "content_base64": base64.b64encode(text.encode()).decode()})


def _workspace_bytes(gateway, user: str) -> bytes:
    """Every file under the user's workspace, concatenated (plan.rpx and app.db are SQLite: text is stored as is)."""
    root = gateway["data_root"] / "users" / str(gateway["users"][user][0])
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


def test_one_users_monarch_upload_is_invisible_to_the_other(gateway, signed_in):
    alice, bob = signed_in["alice"], signed_in["bob"]
    status, body = _upload(alice, "transactions",
                           f"Date,Merchant,Category,Account,Amount,Id\n2026-08-01,{ALICE_MERCHANT},Groceries,"
                           f"{ALICE_ACCOUNT},-12.34,gate-tx-1\n")
    assert status == 200 and body["added"] == 1, body
    status, body = _upload(alice, "balances", f"Date,Balance,Account\n2026-08-03,100.00,{ALICE_ACCOUNT}\n"
                                              f"2026-08-04,101.00,{ALICE_ACCOUNT}\n")
    assert status == 200 and body["status"] == "ok", body
    _s, _h, alice_view = alice.request("GET", "/api/reconcile")
    _s, _h, bob_view = bob.request("GET", "/api/reconcile")
    assert ALICE_ACCOUNT.encode() in alice_view
    assert ALICE_ACCOUNT.encode() not in bob_view
    assert ALICE_MERCHANT.encode() in _workspace_bytes(gateway, "alice")
    bob_files = _workspace_bytes(gateway, "bob")
    assert ALICE_MERCHANT.encode() not in bob_files and ALICE_ACCOUNT.encode() not in bob_files


def test_the_secret_store_ui_is_refused_and_a_same_account_worker_stores_nothing(gateway, signed_in):
    if gateway["per_account"]:
        return  # premise is a same-account worker; per-account workers have their own secret store (elevated suite)
    for name in ("alice", "bob"):
        status, body = signed_in[name].json("POST", "/api/secrets", {"name": "fmp_api_key", "value": "user-key"})
        assert status == 403, body
        status, body = signed_in[name].json("GET", "/api/status")
        assert status == 200 and body.get("encryption", {}).get("store_active") is not True, body.get("encryption")


def test_the_monarch_connector_never_signs_in_on_a_same_account_worker(gateway, signed_in):
    """--monarch-connector is on, but these workers share the gateway's credential store: no tokens may go there."""
    if gateway["per_account"]:
        return  # premise is a same-account worker; a per-account worker may use the connector
    for name in ("alice", "bob"):
        status, body = signed_in[name].json("GET", "/api/monarch/connector")
        assert status == 200 and body["available"] is False and body["connected"] is False, body
        if sys.platform == "win32":  # elsewhere the reason is "no credential store backend"; unavailable is the contract
            assert "own Windows account" in body["reason"], body
        status, body = signed_in[name].json("POST", "/api/monarch/connector/start", {})
        assert status == 403 and "authorize_url" not in body, body


def test_the_shared_provider_key_reaches_workers_but_never_a_response_or_a_workspace(gateway, signed_in):
    import hashlib  # noqa: PLC0415

    needles = (SHARED_KEY.encode(), hashlib.sha256(SHARED_KEY.encode()).hexdigest()[:12].encode())
    for name in ("alice", "bob"):
        client = signed_in[name]
        seen = b""
        for method, path, body in (("GET", "/api/status", None), ("GET", "/api/runtime", None),
                                   ("GET", "/api/ping", None),
                                   ("POST", "/api/prices/test-symbol", {"symbol": "VTI"})):
            status, _h, raw = client.request(method, path, body)
            seen += raw
            assert all(n not in raw for n in needles), (name, path)
        assert SHARED_KEY_ENV.encode() in seen, "the worker did not receive the shared key by --pass-env"
        assert all(n not in _workspace_bytes(gateway, name) for n in needles), name


def test_logout_stops_the_users_worker_and_gateway_exit_stops_the_rest(gateway, signed_in):
    alice_pid, bob_pid = _port_info(gateway, "alice")["pid"], _port_info(gateway, "bob")["pid"]
    assert _pid_alive(alice_pid) and _pid_alive(bob_pid)
    status, body = signed_in["alice"].json("POST", "/api/auth/logout", {})  # her last session
    assert status == 200, body
    deadline = time.time() + 30
    while time.time() < deadline and _pid_alive(alice_pid):
        time.sleep(0.5)
    assert not _pid_alive(alice_pid), "alice's worker still runs after she signed out"
    assert _pid_alive(bob_pid)
    gateway["proc"].terminate()  # TerminateProcess: no clean-up code runs, only the kill-on-close jobs
    gateway["proc"].wait(timeout=20)
    deadline = time.time() + 15
    while time.time() < deadline and _pid_alive(bob_pid):
        time.sleep(0.5)
    assert not _pid_alive(bob_pid), "bob's worker outlived the gateway"
