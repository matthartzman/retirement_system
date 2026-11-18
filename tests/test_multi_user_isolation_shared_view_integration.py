"""Isolation gate for shared views (Phase 9): two owners and two viewers behind a real gateway (``--insights
--shared-views``), with each owner's real worker. Controls C3, C5, C6, C12, C23 and abuse cases AC-1 to AC-6, AC-10,
AC-12, through the real HTTP path (security review section 7; design section 10).

Shows: no worker, workspace or Windows account for a viewer, whatever it asks for; id guessing and replay across
sessions get the uniform not-found; planner, ``/insights/``, admin and owner routes are refused to viewers; nobody
enumerates another party's shares or viewers; a revoke takes effect on the next request; the snapshot route cannot be
reached from a browser; a published percent record is leak-free. Slow (two worker starts): run it once.
"""
from __future__ import annotations

import json
import time

import pytest

from financial_trends_reporter import percent_view
from src.gateway import totp
from src.gateway.store import Actor
from src.gateway.viewer_routes import NOT_AVAILABLE_BODY
from tests.test_multi_user_isolation_integration import PW, Client, launch_gateway

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.slow]

REFUSED_TO_VIEWERS = [
    ("GET", "/"), ("GET", "/static/dashboard.html"), ("GET", "/api/plans"), ("POST", "/api/plans/delete"),
    ("POST", "/api/build/start"), ("GET", "/api/plan/rows"), ("GET", "/insights/"), ("GET", "/insights/api/history"),
    ("GET", "/insights/api/whoami"), ("POST", "/insights/api/share-snapshot"), ("GET", "/gateway/admin"),
    ("GET", "/api/auth/admin/users"), ("GET", "/api/auth/admin/console/users"), ("GET", "/gateway/sharing"),
    ("GET", "/api/share/list"), ("POST", "/api/share/create"), ("GET", "/API/plans"), ("GET", "/api//plans"),
    ("GET", "/%61pi/plans"), ("GET", "/insights/../api/plans"),
]


def _viewer(store, name: str, sponsor: int) -> tuple[int, str]:
    actor = Actor(None, "isolation-test")
    now = time.time()
    vid = store.create_viewer(name, name.title(), PW, sponsor_user_id=sponsor, now=now, actor=actor, must_change=False)
    secret = store.begin_totp_enrolment(vid, now - 3600)
    assert store.confirm_totp(vid, totp.code_at(secret, int((now - 3600) // 30)), now - 3600)
    return vid, secret


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    yield from launch_gateway(tmp_path_factory.mktemp("isolation_shared_views"), {"alice": "user", "bob": "user"},
                              extra_args=("--insights", "--shared-views"))


@pytest.fixture(scope="module")
def world(gateway):
    port, store = gateway["ready"]["local_port"], gateway["store"]
    a, b = gateway["users"]["alice"][0], gateway["users"]["bob"][0]
    viewers = {"vic": _viewer(store, "vic", a), "val": _viewer(store, "val", b)}
    clients = {}
    for name, (_uid, secret) in list(gateway["users"].items()) + list(viewers.items()):
        c = Client(port)
        c.sign_in(name, secret)
        clients[name] = c
    shares = {}
    for owner, viewer, mv in (("alice", "vic", "percent"), ("bob", "val", "dollars")):
        c = clients[owner]
        assert c.json("POST", "/insights/api/run-now", {})[0] == 200  # FI history, and with it the percent basis
        status, who = c.json("GET", "/insights/api/whoami")
        assert status == 200, who
        t0 = time.time()
        status, body = c.json("POST", "/api/share/create", {
            "viewer_id": viewers[viewer][0], "title": f"For {viewer}", "money_view": mv,
            "views": ["live", "trends", "projections"], "expires_in_days": 90, "expected_plan_id": who["plan"]["id"]})
        assert status == 200 and body.get("published"), body
        shares[owner] = body["id"]
        print(f"measured: {owner} {mv} publish {time.time() - t0:.2f} s")
    return {"clients": clients, "viewers": viewers, "shares": shares, "a": a, "b": b}


def _users_dirs(gateway) -> set[str]:
    return {p.name for p in (gateway["data_root"] / "users").iterdir()}


def test_id_guessing_and_replay_across_sessions(gateway, world):
    vic, val = world["clients"]["vic"], world["clients"]["val"]
    sa, sb = world["shares"]["alice"], world["shares"]["bob"]
    status, _h, raw = vic.request("GET", f"/api/viewer/shares/{sa}")
    assert status == 200 and json.loads(raw)["share_id"] == sa
    for sid in (sb, "0" * 32, sa[:-1] + ("0" if sa[-1] != "0" else "1"), "../" + sa, sa.upper()):
        status, _h, raw = vic.request("GET", f"/api/viewer/shares/{sid}")
        assert status == 404 and raw == NOT_AVAILABLE_BODY.encode(), sid
    status, _h, raw = val.request("GET", f"/api/viewer/shares/{sa}")
    assert status == 404 and raw == NOT_AVAILABLE_BODY.encode()
    # The same URL with no session, or with a cookie replayed after sign-out, gets nothing.
    anon = Client(gateway["ready"]["local_port"])
    assert anon.request("GET", f"/api/viewer/shares/{sa}")[0] == 401
    replay = Client(gateway["ready"]["local_port"])
    replay.sign_in("vic", world["viewers"]["vic"][1], step_offset=1)
    stolen = replay.cookie
    assert replay.json("POST", "/api/auth/logout", {})[0] == 200
    replay.cookie = stolen
    assert replay.request("GET", f"/api/viewer/shares/{sa}")[0] == 401


def test_planner_insights_admin_and_owner_routes_are_refused_for_a_viewer(gateway, world):
    before = _users_dirs(gateway)
    for name in ("vic", "val"):
        c = world["clients"][name]
        for method, path in REFUSED_TO_VIEWERS:
            status, headers, raw = c.request(method, path, {} if method == "POST" else None)
            assert status in (302, 404), (name, method, path, status)
            if status == 302:
                assert headers["location"] == "/gateway/viewer", (name, path)
            assert headers.get("cache-control") == "no-store", (name, path)
    assert _users_dirs(gateway) == before


def test_no_worker_or_workspace_for_a_viewer(gateway, world):
    dirs = _users_dirs(gateway)
    for _name, (vid, _s) in world["viewers"].items():
        assert str(vid) not in dirs
        assert gateway["store"].get_worker_account(vid) is None
    assert {str(world["a"]), str(world["b"])} <= dirs
    assert gateway["store"].member_ids() == {world["a"], world["b"]}
    log = gateway["log"].read_text(encoding="utf-8", errors="replace")
    for _name, (vid, _s) in world["viewers"].items():
        assert f"worker for user {vid} " not in log  # the supervisor logs every start, stop and failure this way


def test_nobody_enumerates_other_shares_or_viewers(world):
    c = world["clients"]
    shares_vic = c["vic"].json("GET", "/api/viewer/shares")[1]["shares"]
    assert [s["id"] for s in shares_vic] == [world["shares"]["alice"]]
    alice_list = c["alice"].json("GET", "/api/share/list")[1]["shares"]
    assert [s["id"] for s in alice_list] == [world["shares"]["alice"]]
    viewers = c["alice"].json("GET", "/api/share/viewers")[1]["viewers"]
    assert [v["id"] for v in viewers] == [world["viewers"]["vic"][0]]
    status, body = c["alice"].json("POST", "/api/share/create", {
        "viewer_id": world["viewers"]["val"][0], "title": "x", "expected_plan_id": "p"})
    assert status == 404 and body["error"] == "That viewer was not found."
    for path in (f"/api/share/{world['shares']['bob']}/preview", f"/api/share/{world['shares']['bob']}/views"):
        status, _h, raw = c["alice"].request("GET", path)
        assert status == 404


def test_the_snapshot_route_cannot_be_reached_from_a_browser(world):
    alice = world["clients"]["alice"]
    for path in ("/insights/api/share-snapshot", "/insights/api/share%2Dsnapshot", "/insights/api/SHARE-SNAPSHOT"):
        status, _h, _raw = alice.request("POST", path, {"share_id": "a" * 32}, headers={"X-Gateway-Share-Publish": "1"})
        assert status in (400, 404), path


def test_published_records_are_leak_free_and_measured(world):
    vic, val = world["clients"]["vic"], world["clients"]["val"]
    status, _h, raw = vic.request("GET", f"/api/viewer/shares/{world['shares']['alice']}")
    doc = json.loads(raw)
    assert status == 200 and doc["money_view"] == "percent"
    assert set(doc["views"]) == {"live", "trends", "projections"}
    assert percent_view.find_money_leaks(doc["views"]) == []
    status, _h, raw2 = val.request("GET", f"/api/viewer/shares/{world['shares']['bob']}")
    assert status == 200 and json.loads(raw2)["money_view"] == "dollars"
    print(f"measured: percent record {len(raw)} bytes, dollars record {len(raw2)} bytes")
    t0 = time.time()
    for _ in range(5):
        vic.request("GET", f"/api/viewer/shares/{world['shares']['alice']}")
    print(f"measured: guest record fetch {(time.time() - t0) / 5 * 1000:.0f} ms")


def test_revocation_takes_effect_on_the_next_request(world):
    alice, vic = world["clients"]["alice"], world["clients"]["vic"]
    sid = world["shares"]["alice"]
    assert vic.request("GET", f"/api/viewer/shares/{sid}/status")[0] == 200
    assert alice.json("POST", f"/api/share/{sid}/revoke", {})[0] == 200
    status, _h, raw = vic.request("GET", f"/api/viewer/shares/{sid}")
    assert status == 404 and raw == NOT_AVAILABLE_BODY.encode()
    assert vic.json("GET", "/api/viewer/shares")[1]["shares"] == []
