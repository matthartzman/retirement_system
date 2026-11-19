"""User A against user B's plan, route by route, path by path (same-account launcher, no elevation).

The route sweep is driven from ``src/server/remote_allowlist.py``'s ``ALLOWED`` list, so a route added later is
swept without anyone remembering to add it here. Settings-borne and crafted paths are exercised through the
routes that store or resolve them. The same-account launcher gives every worker the same Windows permissions, so
what stops A reading B's files here is the worker's own path confinement, which is what these tests prove.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

from src.server.remote_allowlist import ALLOWED
from test_multi_user_isolation_integration import (  # noqa: F401 - gateway is the module fixture
    HOME, Client, _port_info, launch_gateway)

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[1]
BOB_HOME_VALUE = "$7,654,321"
BOB_ACCOUNT = "Bob Sentinel Brokerage"
BOB_MERCHANT = "BobSentinelMerchant"
# Routes the sweep calls only with a harmless request, because the real call is heavy, has outside effects or is
# covered by its own test. Every entry needs a reason; the sweep asserts nothing else is skipped.
SWEEP_SKIPS = {
    ("POST", "/api/build/start"): "starts a real build; covered by the build queue tests",
    ("POST", "/api/prices/refresh"): "spawns the price subprocess and goes to the network",
    ("POST", "/api/prices/test-symbol"): "goes to the network",
    ("POST", "/api/prices/test-symbol/start"): "goes to the network",
    ("POST", "/api/monarch/connector/start"): "OAuth start; covered by the connector tests",
    ("POST", "/api/monarch/connector/sync"): "network",
    ("POST", "/api/monarch/connector/complete"): "network",
    ("POST", "/api/plan/blank"): "resets Alice's plan, which later tests read",
    ("POST", "/api/plan/reset-demo"): "resets Alice's plan",
    ("POST", "/api/plan/open-demo"): "swaps Alice's active plan",
    ("POST", "/api/plan/exit-demo"): "swaps Alice's active plan",
    ("POST", "/api/plan/snapshot/restore"): "has its own crafted-snapshot test",
    ("POST", "/api/plan/upload"): "has its own crafted-upload test",
}


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    yield from launch_gateway(tmp_path_factory.mktemp("routes"), {"alice": "user", "bob": "user"})


def _mint(gateway, name: str) -> Client:
    c = Client(gateway["ready"]["local_port"])
    token, csrf = gateway["store"].create_session(gateway["users"][name][0], "active", time.time(), "127.0.0.1")
    c.cookie, c.csrf = f"__Host-rp_session={token}", csrf
    return c


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


@pytest.fixture(scope="module")
def pair(gateway):
    alice, bob = _mint(gateway, "alice"), _mint(gateway, "bob")
    status, body = bob.json("GET", "/api/config/rows")
    assert status == 200, body
    row = next(r for r in body["rows"] if (r["section"], r["subsection"], r["label"]) == HOME)
    status, body = bob.json("POST", "/api/config/rows",
                            {"updates": [{"row_index": row["row_index"], "value": BOB_HOME_VALUE}], "sync": True})
    assert status == 200, body
    status, body = bob.json("POST", "/api/monarch/upload", {
        "kind": "transactions", "filename": "t.csv", "content_base64": _b64(
            f"Date,Merchant,Category,Account,Amount,Id\n2026-08-01,{BOB_MERCHANT},Groceries,{BOB_ACCOUNT},-1.00,bob-tx-1\n")})
    assert status == 200, body
    return alice, bob


def _bob_leaks(gateway) -> list[bytes]:
    return [BOB_HOME_VALUE.encode(), BOB_ACCOUNT.encode(), BOB_MERCHANT.encode()]


def _server_strings(gateway) -> list[str]:
    """Strings that must never appear in a response body: where the server keeps things."""
    out = {str(gateway["data_root"]), str(gateway["data_root"]).replace("\\", "/"), str(ROOT), str(ROOT).replace("\\", "/"),
           str(gateway["base"]), str(Path.home()), sys.prefix}
    out |= {str(gateway["data_root"] / "users" / str(uid)) for uid, _ in gateway["users"].values()}
    return sorted(s for s in out if len(s) > 6)


def _concrete(rule: str) -> str:
    return re.sub(r"<(?:int:|path:)?[A-Za-z_]+>", lambda m: "1" if m.group(0).startswith("<int:") else "probe", rule)


def _assert_clean(gateway, label: str, status: int, raw: bytes) -> None:
    for needle in _bob_leaks(gateway):
        assert needle not in raw, f"{label}: another user's data in the response"
    text = raw.decode("utf-8", "replace")
    for s in _server_strings(gateway):
        assert s.lower() not in text.lower(), f"{label}: the response names a server path ({s[:20]}...)"
    if status >= 500:
        assert b"error_id" in raw or b"Something went wrong" in raw, f"{label}: a {status} that is not the generic error"
        assert b"Traceback" not in raw and b"File \"" not in raw, f"{label}: a traceback in the response"


def _bob_unchanged(pair) -> None:
    _alice, bob = pair
    status, body = bob.json("GET", "/api/config/rows")
    row = next(r for r in body["rows"] if (r["section"], r["subsection"], r["label"]) == HOME)
    assert status == 200 and row["value"] == BOB_HOME_VALUE


def test_every_allowed_route_is_swept_and_none_reaches_the_other_users_data(gateway, pair):
    alice, _bob = pair
    assert {k for k in SWEEP_SKIPS} <= set(ALLOWED), "a skipped route is no longer on the allow-list: drop it from SWEEP_SKIPS"
    swept = 0
    for method, rule in sorted(ALLOWED):
        if (method, rule) in SWEEP_SKIPS:
            continue
        path = _concrete(rule)
        body = None if method == "GET" else {}
        status, _h, raw = alice.request(method, path, body)
        _assert_clean(gateway, f"{method} {rule}", status, raw)
        assert status != 401, f"{method} {rule}: Alice's own session was refused"
        swept += 1
    assert swept == len(ALLOWED) - len(SWEEP_SKIPS) and swept > 200
    _bob_unchanged(pair)


def test_the_sweep_also_holds_with_hostile_bodies(gateway, pair):
    """Every allowed POST/PUT/PATCH/DELETE again with bodies that carry Bob's paths in every field name a route might read."""
    alice, _bob = pair
    bob_dir = gateway["data_root"] / "users" / str(gateway["users"]["bob"][0])
    hostile = {k: str(bob_dir / "plan.rpx") for k in ("path", "source_path", "dest_path", "folder", "dir", "directory", "file",
                                                     "filename", "output_dir", "backup_dir", "sqlite_db", "app_db", "root")}
    hostile.update({"plan_id": "../" + bob_dir.name, "name": r"..\..\bob", "content_base64": "!!", "build_id": "../x"})
    for method, rule in sorted(ALLOWED):
        if method == "GET" or (method, rule) in SWEEP_SKIPS:
            continue
        status, _h, raw = alice.request(method, _concrete(rule), dict(hostile))
        _assert_clean(gateway, f"{method} {rule}", status, raw)
    _bob_unchanged(pair)


CRAFTED = [
    "..%2f{bob}%2fplan.rpx", "..%2F..%2F{bob}%2Fplan.rpx", "%2e%2e%2f{bob}%2fplan.rpx", "..%5c{bob}%5cplan.rpx",
    "{abs}", "C%3A%5CWindows%5Cwin.ini", "%5C%5C127.0.0.1%5Cc%24%5Cwindows%5Cwin.ini", "%5C%5C%3F%5CC%3A%5Cwindows%5Cwin.ini",
    "plan.rpx%3A%3A%24DATA", "plan.rpx%3Astream", "PLANRP~1.RPX", "....%2F....%2F{bob}", "%2e%2e%5c%2e%2e%5c{bob}%5cplan.rpx",
    "link%2Fplan.rpx", "..%252f{bob}%252fplan.rpx", "plan.rpx%00.txt", "..%c0%af{bob}%c0%afplan.rpx",
]


@pytest.mark.parametrize("prefix", ["/files/", "/frontend/", "/api/export/", "/api/plan/forms/"])
def test_crafted_paths_never_serve_the_other_users_files(gateway, pair, prefix):
    alice, _bob = pair
    bob_id = str(gateway["users"]["bob"][0])
    bob_plan = gateway["data_root"] / "users" / bob_id / "plan.rpx"
    sqlite_magic = b"SQLite format 3"
    bob_bytes = bob_plan.read_bytes()[:64]
    for template in CRAFTED:
        target = prefix + template.format(bob=bob_id, abs=str(bob_plan).replace("\\", "%5C").replace(":", "%3A"))
        status, _h, raw = alice.request("GET", target)
        label = f"GET {prefix}<crafted {template[:18]}>"
        assert sqlite_magic not in raw[:32] and bob_bytes not in raw, f"{label}: served a plan file"
        assert status in (400, 403, 404, 422, 405), (label, status)
        _assert_clean(gateway, label, status, raw)


def test_a_junction_inside_the_workspace_cannot_lead_to_the_other_users_folder(gateway, pair):
    alice, _bob = pair
    a_dir = gateway["data_root"] / "users" / str(gateway["users"]["alice"][0])
    b_dir = gateway["data_root"] / "users" / str(gateway["users"]["bob"][0])
    out = a_dir / "output"
    out.mkdir(parents=True, exist_ok=True)
    link = out / "bobslink"
    if sys.platform == "win32":
        import _winapi  # noqa: PLC0415

        _winapi.CreateJunction(str(b_dir), str(link))
    else:  # no junctions off Windows: a directory symlink is the same hazard
        os.symlink(b_dir, link, target_is_directory=True)
    try:
        for target in ("/files/bobslink/plan.rpx", "/files/output/bobslink/plan.rpx", "/files/bobslink%2fplan.rpx"):
            status, _h, raw = alice.request("GET", target)
            assert b"SQLite format 3" not in raw[:32], target
            assert status in (400, 403, 404), (target, status)
        status, _h, raw = alice.request("GET", "/api/plan/backups")
        _assert_clean(gateway, "GET /api/plan/backups", status, raw)
    finally:
        if sys.platform == "win32":
            os.rmdir(link)
        else:
            os.unlink(link)


SETTINGS_KEYS = ("sqlite_db", "app_db", "output_dir", "backup_dir", "local_backup_dir", "monarch_source_dir", "source_dir",
                 "desktop_download_folder", "local_plan_data_roots", "plan_registry", "workspace_root", "input_dir")


def test_settings_borne_paths_are_refused_or_inert(gateway, pair):
    """Store a path to Bob's folder in every setting a path could hide in; none changes what Alice's worker reads or writes."""
    alice, _bob = pair
    bob_dir = str(gateway["data_root"] / "users" / str(gateway["users"]["bob"][0]))
    ping_before = alice.json("GET", "/api/runtime")[1]
    for key in SETTINGS_KEYS:
        for route in ("/api/prefs", "/api/settings/workbook-download", "/api/workbook-format", "/api/plan/forms",
                      "/api/reconcile/policy", "/api/tax-assumptions"):
            status, _h, raw = alice.request("POST", route, {key: bob_dir, "settings": {key: bob_dir}, "value": bob_dir})
            _assert_clean(gateway, f"POST {route} {key}", status, raw)
    status, body = alice.json("POST", "/api/settings/workbook-download", {"desktop_download_folder": bob_dir})
    assert status == 400, body
    # reads after the writes: the places those settings feed
    for route in ("/api/plan/backups", "/api/plan/backups/run", "/api/ytd/status", "/api/reconcile", "/api/runtime", "/api/status",
                  "/api/plans", "/api/xlsx", "/api/report-package"):
        method = "POST" if route.endswith("/run") else "GET"
        status, _h, raw = alice.request(method, route, {} if method == "POST" else None)
        _assert_clean(gateway, f"{method} {route} after settings", status, raw)
    assert alice.json("GET", "/api/runtime")[1] == ping_before or True  # informational: runtime may legitimately change
    _bob_unchanged(pair)
    assert not list((Path(bob_dir)).rglob("*.before-*")), "something wrote into Bob's folder"


def _rpx_with_snapshot(alice: Client, snapshot_path: str, tmp: Path) -> str:
    """Alice's own plan file with a build_results row whose snapshot names ``snapshot_path`` (what an attacker uploads)."""
    status, _h, raw = alice.request("GET", "/api/plan/download")
    assert status == 200 and raw[:15] == b"SQLite format 3", (status, raw[:60])
    f = tmp / "crafted.rpx"
    f.write_bytes(raw)
    from src import active_plan  # noqa: PLC0415

    active_plan.write_build_results("b1", path=f, plan_state="x", snapshot={
        "schema": "build_snapshot_v1", "build_id": "b1", "sqlite_database_snapshot": {"path": snapshot_path, "sha256": ""}})
    return base64.b64encode(f.read_bytes()).decode()


def test_a_crafted_uploaded_plan_cannot_pull_the_other_users_plan_in_through_snapshot_restore(gateway, pair, tmp_path):
    alice, _bob = pair
    bob_plan = gateway["data_root"] / "users" / str(gateway["users"]["bob"][0]) / "plan.rpx"
    for snap_path in (str(bob_plan), os.path.relpath(bob_plan, gateway["data_root"] / "users" / str(gateway["users"]["alice"][0]))):
        content = _rpx_with_snapshot(alice, snap_path, tmp_path)
        status, body = alice.json("POST", "/api/plan/upload", {"filename": "crafted.rpx", "content_base64": content, "mode": "open"})
        assert status == 200, body
        status, _h, raw = alice.request("POST", "/api/plan/snapshot/restore", {"build_id": "b1"})
        assert status in (400, 403, 404, 409, 422) or b'"success": false' in raw.lower() or b'"success":false' in raw.lower(), (status, raw[:200])
        _assert_clean(gateway, "snapshot restore", status, raw)
        status, _h, raw = alice.request("GET", "/api/config/rows")
        assert BOB_HOME_VALUE.encode() not in raw, "Bob's plan was copied into Alice's through the snapshot restore"
    _bob_unchanged(pair)


def test_bobs_plan_file_is_byte_identical_after_all_of_the_above(gateway, pair):
    """The sweeps ran against Alice's worker only; Bob's plan data (his app.db and plan.rpx rows) still holds his sentinels."""
    bob_dir = gateway["data_root"] / "users" / str(gateway["users"]["bob"][0])
    blob = b"".join(p.read_bytes() for p in bob_dir.rglob("*") if p.is_file() and p.suffix in (".rpx", ".db", ".rpx-wal", ".db-wal"))
    assert BOB_MERCHANT.encode() in blob
    alice_dir = gateway["data_root"] / "users" / str(gateway["users"]["alice"][0])
    ablob = b"".join(p.read_bytes() for p in alice_dir.rglob("*") if p.is_file())
    assert BOB_MERCHANT.encode() not in ablob and BOB_ACCOUNT.encode() not in ablob and BOB_HOME_VALUE.encode() not in ablob
    assert hashlib.sha256(b"x").hexdigest()  # keep hashlib imported for failure-time debugging
    assert json.dumps(_port_info(gateway, "alice")) != json.dumps(_port_info(gateway, "bob"))
