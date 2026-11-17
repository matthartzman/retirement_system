"""User A against user B's plans (same-account launcher, no elevation): list, switch, rename, duplicate, delete,
download and overwrite attempts with B's real ids and with crafted ids. The worker's own registry and path
confinement are what stop A here; the elevated per-account run adds the Windows ACLs and stays the owner's."""
from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import quote
from pathlib import Path

import pytest

from test_multi_user_isolation_integration import Client, launch_gateway  # noqa: F401 - gateway is the module fixture

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

BOB_PLAN_NAME = "BobSentinelPlanName"
CRAFTED = ["0" * 32, "../x", r"..\x", "CON", "NUL", "demo", "x" * 100, "é", "a b", "%2e%2e", "plans/x"]


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    yield from launch_gateway(tmp_path_factory.mktemp("plans"), {"alice": "user", "bob": "user"})


def _mint(gateway, name: str) -> Client:
    c = Client(gateway["ready"]["local_port"])
    token, csrf = gateway["store"].create_session(gateway["users"][name][0], "active", time.time(), "127.0.0.1")
    c.cookie, c.csrf = f"__Host-rp_session={token}", csrf
    return c


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "tmp" not in p.parts and p.suffix in (".rpx", ".db", ".rpx-wal", ".db-wal"):
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def pair(gateway):
    alice, bob = _mint(gateway, "alice"), _mint(gateway, "bob")
    status, body = bob.json("POST", "/api/plans/create", {"name": BOB_PLAN_NAME, "from": "demo"})
    assert status == 200, body
    status, body = alice.json("POST", "/api/plans/create", {"name": "Alice what-if", "from": "blank"})
    assert status == 200, body
    return alice, bob, body["plan"]["plan_id"], _bob_plan_id(bob)


def _bob_plan_id(bob) -> str:
    _, body = bob.json("GET", "/api/plans")
    return next(p["plan_id"] for p in body["plans"] if p["name"] == BOB_PLAN_NAME)


def _bob_dir(gateway) -> Path:
    return gateway["data_root"] / "users" / str(gateway["users"]["bob"][0])


def test_alice_never_sees_bobs_plan_in_her_list_or_anywhere(gateway, pair):
    alice, _bob, _own, bob_id = pair
    status, _h, raw = alice.request("GET", "/api/plans")
    assert status == 200
    assert BOB_PLAN_NAME.encode() not in raw and bob_id.encode() not in raw


@pytest.mark.parametrize("path", ["/api/plans/switch", "/api/plans/rename", "/api/plans/duplicate", "/api/plans/delete"])
def test_alice_cannot_act_on_bobs_plan_id(gateway, pair, path):
    alice, bob, _own, bob_id = pair
    before = _tree_hash(_bob_dir(gateway))
    status, _h, raw = alice.request("POST", path, {"plan_id": bob_id, "name": "stolen", "confirm_name": BOB_PLAN_NAME})
    assert status in (400, 404) and b'"success": false' in raw.lower().replace(b'":false', b'": false')
    assert BOB_PLAN_NAME.encode() not in raw
    assert _tree_hash(_bob_dir(gateway)) == before
    _, body = bob.json("GET", "/api/plans")
    assert any(p["plan_id"] == bob_id and p["name"] == BOB_PLAN_NAME for p in body["plans"])


def test_alice_cannot_download_bobs_plan_by_id(gateway, pair):
    alice, _bob, _own, bob_id = pair
    status, _h, raw = alice.request("GET", f"/api/plan/download?plan_id={bob_id}")
    assert status == 404 and not raw.startswith(b"SQLite format 3")
    status, _h, raw = alice.request("GET", "/api/plan/download")  # her own active plan is fine
    assert status == 200 and raw.startswith(b"SQLite format 3") and BOB_PLAN_NAME.encode() not in raw


@pytest.mark.parametrize("bad", CRAFTED)
def test_crafted_ids_are_refused_the_same_way_and_touch_no_disk(gateway, pair, bad):
    alice, *_ = pair
    before = (_tree_hash(_bob_dir(gateway)), _tree_hash(gateway["data_root"] / "users" / str(gateway["users"]["alice"][0])))
    for method, path, body in (("POST", "/api/plans/switch", {"plan_id": bad}), ("POST", "/api/plans/rename", {"plan_id": bad, "name": "n"}),
                               ("POST", "/api/plans/duplicate", {"plan_id": bad}),
                               ("POST", "/api/plans/delete", {"plan_id": bad, "confirm_name": "n"}),
                               ("GET", "/api/plan/download?plan_id=" + quote(bad, safe=""), None)):
        status, _h, raw = alice.request(method, path, body)
        assert status in (400, 404), (path, bad, status)
        assert b"Traceback" not in raw
    after = (_tree_hash(_bob_dir(gateway)), _tree_hash(gateway["data_root"] / "users" / str(gateway["users"]["alice"][0])))
    assert after == before


def test_hostile_names_never_become_paths(gateway, pair):
    alice, bob, *_ = pair
    bob_before = _tree_hash(_bob_dir(gateway))
    for name in ("..\\..\\..\\users\\2\\plan", "../../bob/plan.rpx", "CON", "a" * 5000):
        status, body = alice.json("POST", "/api/plans/duplicate", {"plan_id": pair[2], "name": name})
        assert status == 200, body
    assert _tree_hash(_bob_dir(gateway)) == bob_before
    alice_plans = gateway["data_root"] / "users" / str(gateway["users"]["alice"][0]) / "plans"
    assert all(len(p.stem) == 32 and p.suffix == ".rpx" for p in alice_plans.glob("*.rpx"))


def test_uploading_with_bobs_file_or_plan_name_cannot_overwrite_him(gateway, pair):
    alice, _bob, _own, _bid = pair
    before = _tree_hash(_bob_dir(gateway))
    _, _h, content = alice.request("GET", "/api/plan/download")
    status, body = alice.json("POST", "/api/plan/upload", {
        "filename": f"..\\..\\{gateway['users']['bob'][0]}\\plan.rpx", "name": BOB_PLAN_NAME,
        "content_base64": base64.b64encode(content).decode(), "mode": "open"})
    assert status == 200, body
    assert _tree_hash(_bob_dir(gateway)) == before


def test_alices_delete_leaves_bobs_files_byte_identical(gateway, pair):
    alice, _bob, own, _bid = pair
    _, plans = alice.json("GET", "/api/plans")
    other = next(p for p in plans["plans"] if p["plan_id"] != own and p["kind"] != "demo")
    alice.json("POST", "/api/plans/switch", {"plan_id": other["plan_id"]})
    before = _tree_hash(_bob_dir(gateway))
    status, body = alice.json("POST", "/api/plans/delete", {"plan_id": own, "confirm_name": "Alice what-if"})
    assert status == 200, body
    assert _tree_hash(_bob_dir(gateway)) == before
    status, _h, _raw = alice.request("POST", "/api/plans/switch", {"plan_id": own})  # a deleted id is now unknown
    assert status in (400, 404)
