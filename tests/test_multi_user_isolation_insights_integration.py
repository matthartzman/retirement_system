"""Isolation gate for Financial Insight: two users and an admin behind a real gateway (``--insights``), each with a real worker.

Same stack as ``test_multi_user_isolation_integration.py`` (gateway subprocess, same-account launcher, temp data root).
Shows that ``/insights/`` is served by the signed-in user's own worker only: nobody sees another user's balances, accounts
or history, an admin sees only their own, the page and its API refuse a signed-out caller, routes outside the FI
allow-list stay refused, and an **Update** leaves the plan file untouched.

Design: documentation/future/multi-user-insights-design.md (section 5 and 8). Slow (three worker starts): run it once.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from tests.test_multi_user_isolation_integration import (
    ALICE_ACCOUNT, ROOT, Client, _upload, _workspace_bytes, launch_gateway,
)

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.slow]

FI_VIEWS = ("/insights/api/balances", "/insights/api/accounts", "/insights/api/history", "/insights/api/flows",
            "/insights/api/liquid-change", "/insights/api/app-accounts", "/insights/api/whoami")


def _tree_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True,
                          text=True, check=False).stdout


@pytest.fixture(scope="module")
def tree_before():
    return _tree_status()


@pytest.fixture(scope="module")
def gateway(tmp_path_factory, tree_before):
    roles = {"alice": "user", "bob": "user", "root": "admin"}
    yield from launch_gateway(tmp_path_factory.mktemp("isolation_insights"), roles, extra_args=("--insights",))


@pytest.fixture(scope="module")
def signed_in(gateway):
    port = gateway["ready"]["local_port"]
    clients = {}
    for name, (_uid, secret) in gateway["users"].items():
        c = Client(port)
        c.sign_in(name, secret)
        clients[name] = c
    return clients


def _plan_hash(gateway, user: str) -> str:
    root = gateway["data_root"] / "users" / str(gateway["users"][user][0])
    return hashlib.sha256((root / "plan.rpx").read_bytes()).hexdigest()


def _fi_bytes(client: Client) -> bytes:
    out = b""
    for path in FI_VIEWS:
        status, _h, raw = client.request("GET", path)
        assert status == 200, (path, status, raw[:200])
        out += raw
    return out


def test_the_session_offers_insights_and_the_page_is_served_by_the_users_own_worker(signed_in):
    for name, client in signed_in.items():
        status, body = client.json("GET", "/api/auth/session")
        assert status == 200 and body["insights"] is True, (name, body)
        status, headers, raw = client.request("GET", "/insights/")
        assert status == 200 and b"Financial Insight" in raw, (name, status)
        status, body = client.json("GET", "/insights/api/whoami")
        assert status == 200 and body["listener"] == "worker", (name, body)


def test_one_users_balances_never_appear_in_another_users_financial_insight(gateway, signed_in):
    alice, bob, root = signed_in["alice"], signed_in["bob"], signed_in["root"]
    status, body = _upload(alice, "balances", f"Date,Balance,Account\n2026-08-03,100.00,{ALICE_ACCOUNT}\n"
                                              f"2026-08-04,101.00,{ALICE_ACCOUNT}\n")
    assert status == 200 and body["status"] == "ok", body
    assert ALICE_ACCOUNT.encode() in _fi_bytes(alice), "alice's own FI should show her uploaded account"
    for other in (bob, root):
        assert ALICE_ACCOUNT.encode() not in _fi_bytes(other)
    assert ALICE_ACCOUNT.encode() not in _workspace_bytes(gateway, "bob")


def test_no_request_parameter_or_header_selects_another_user(signed_in):
    bob = signed_in["bob"]
    for suffix in ("?user=alice", "?user_id=1", "?plan_id=alice", "?path=../1/plan.rpx"):
        status, _h, raw = bob.request("GET", "/insights/api/balances" + suffix)
        assert ALICE_ACCOUNT.encode() not in raw, suffix
    status, _h, raw = bob.request("GET", "/insights/api/balances",
                                  headers={"X-Retirement-User": "alice", "X-Forwarded-User": "alice"})
    assert ALICE_ACCOUNT.encode() not in raw


def test_update_leaves_the_plan_file_unchanged_and_history_stays_private(gateway, signed_in):
    alice, bob = signed_in["alice"], signed_in["bob"]
    before = _plan_hash(gateway, "alice")
    status, body = alice.json("POST", "/insights/api/run-now", {})
    assert status in (200, 409, 500, 502), (status, body)  # price providers are off in this rig: the run may report an error
    assert _plan_hash(gateway, "alice") == before, "Financial Insight changed the plan file"
    status, _h, bob_history = bob.request("GET", "/insights/api/history")
    assert status == 200 and ALICE_ACCOUNT.encode() not in bob_history
    assert ALICE_ACCOUNT.encode() not in _workspace_bytes(gateway, "bob")


def test_signed_out_callers_and_refused_routes_get_nothing(gateway, signed_in):
    anonymous = Client(gateway["ready"]["local_port"])
    status, _h, _raw = anonymous.request("GET", "/insights/api/balances")
    assert status == 401
    status, headers, _raw = anonymous.request("GET", "/insights/")
    assert status == 302 and "/login" in headers.get("location", "")
    alice = signed_in["alice"]
    for method, path in (("POST", "/insights/api/exit"), ("GET", "/insights/api/config/rows"),
                         ("POST", "/insights/api/plans/switch")):
        status, _h, raw = alice.request(method, path, {} if method == "POST" else None)
        assert status in (403, 404), (path, status)
        assert ALICE_ACCOUNT.encode() not in raw


def test_errors_do_not_leak_paths(signed_in):
    status, _h, raw = signed_in["alice"].request("GET", "/insights/api/spending?from=not-a-date&to=also-bad")
    text = raw.decode("utf-8", "replace")
    assert "\\Users\\" not in text and "Traceback" not in text and "isolation_insights" not in text, text[:300]


def test_financial_insight_writes_nothing_into_the_install_folder(tree_before, signed_in):
    _fi_bytes(signed_in["alice"])  # make sure FI has run before comparing
    assert _tree_status() == tree_before, "a worker wrote into the source tree"


def test_a_worker_with_financial_insight_loaded_stays_within_its_memory_cap(gateway, signed_in):
    psutil = pytest.importorskip("psutil")
    for name in ("alice", "bob", "root"):
        _fi_bytes(signed_in[name])
        uid = gateway["users"][name][0]
        info = json.loads((gateway["data_root"] / "users" / str(uid) / "local_state" / "worker.port.json").read_text("utf-8"))
        proc = psutil.Process(info["pid"])
        rss = proc.memory_info().rss + sum(c.memory_info().rss for c in proc.children(recursive=True))
        print(f"worker {name}: {rss / 2**20:.0f} MB with Financial Insight loaded")
        assert rss < 1792 * 2**20  # the supervisor's default per-worker cap (--worker-memory-mb)
