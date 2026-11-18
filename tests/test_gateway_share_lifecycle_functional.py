"""Share lifecycle (Phase 9, design 7): revoke, scope change, expiry and the sweep, owner disabled or deleted, viewer
deleted, plan deleted, the flag off, and what the audit holds. Controls C12, C13, C32, C35-C37. In process.
"""
from __future__ import annotations

import json
import re

import pytest

from src.gateway.build_queue import BuildQueue
from src.gateway.proxy import WorkerProxy
from src.gateway.share_publish import plan_delete_hook
from src.gateway.upstream import Identity
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest, Response
from tests.gateway_rig import CLI, Rig
from tests.test_gateway_admin_console_functional import Recorder
from tests.test_gateway_share_routes_functional import _create, _publisher, _relogin

DAY = 86400.0
API = "/api/auth/admin/console"


@pytest.fixture()
def rig(tmp_path):
    r = Rig(tmp_path, shared_views=True, publisher_factory=_publisher, lifecycle=Recorder())
    return r


def _setup(rig):
    ob, owner = rig.signed_in("olive")
    vid = rig.add_viewer("vic", sponsor=owner)
    sid = _create(ob, vid).get_json()["id"]
    g = rig.browser(ip="203.0.113.81")
    _relogin_first(rig, g, "vic", vid)
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 200
    return ob, owner, vid, sid, g


def _relogin_first(rig, b, name, uid):
    assert b.login(name).status_code == 200
    rig.enrol(b, uid)


def test_revoke_deletes_the_body(rig):
    ob, owner, vid, sid, g = _setup(rig)
    path = rig.shares.body_path(sid)
    assert path.exists()
    assert ob.post(f"/api/share/{sid}/revoke").status_code == 200
    assert not path.exists()
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 404
    assert ob.post(f"/api/share/{sid}/publish").status_code == 404  # never published again
    assert ob.post(f"/api/share/{sid}/enable").status_code == 404


def test_scope_change_deletes_the_old_body_before_republishing(rig):
    ob, owner, vid, sid, g = _setup(rig)
    deleted_first = []
    real_delete = rig.shares.delete_body

    def spy_delete(share_id):
        deleted_first.append(rig.shares.body_path(share_id).exists())
        real_delete(share_id)
    rig.shares.delete_body = spy_delete
    rig.publisher.after_store = lambda share_id: deleted_first.append("stored")
    r = ob.post(f"/api/share/{sid}/scope", json={"money_view": "percent", "views": ["projections"]})
    assert r.status_code == 200 and r.get_json()["published"]
    assert deleted_first[0] is True and deleted_first.index("stored") > 0  # the old body went before the new render
    doc = json.loads(g.get(f"/api/viewer/shares/{sid}").get_data())
    assert list(doc["views"]) == ["projections"] and doc["scope_rev"] == 2
    # A failed republish leaves nothing to serve, never the wider old body.
    rig.fake_worker.status = 500
    r = ob.post(f"/api/share/{sid}/scope", json={"money_view": "percent", "views": ["trends"]})
    assert r.status_code == 200 and r.get_json()["published"] is False
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 404
    assert not rig.shares.body_path(sid).exists()


def test_sweep_removes_orphans(rig):
    ob, owner, vid, sid, g = _setup(rig)
    keep = rig.shares.body_path(sid)
    revoked = _create(ob, vid, title="Revoked").get_json()["id"]
    rev_body = rig.shares.body_path(revoked).read_bytes()
    ob.post(f"/api/share/{revoked}/revoke")
    rig.shares.body_path(revoked).write_bytes(rev_body)  # a delete that failed earlier
    short = _create(ob, vid, title="Short", expires_in_days=1).get_json()["id"]
    unpublished = rig.shares.create(owner, viewer_id=vid, title="Never", money_view="percent", views=["trends"],
                                    expires_in_days=9, plan_id="plan-a", now=rig.now[0], actor=CLI)
    rig.shares.body_path(unpublished).write_bytes(b"{}")
    (rig.shares.dir / ("f" * 32 + ".json")).write_bytes(b"{}")          # no row at all
    (rig.shares.dir / (sid + ".json.tmp")).write_bytes(b"partial")      # a write that never finished
    (rig.shares.dir / "notes.txt").write_bytes(b"junk")
    rig.advance(DAY + 1)
    report = rig.shares.housekeeping(rig.now[0], CLI)
    assert keep.exists()
    left = sorted(p.name for p in rig.shares.dir.iterdir())
    assert left == [sid + ".json"]
    assert report["expired"] == 1 and report["bodies_deleted"] == 6
    again = rig.shares.housekeeping(rig.now[0] + 60, CLI)
    assert again["expired"] == 0  # share_expired is audited once
    events = [e for e in rig.store.read_audit(200) if e["event"] == "share_expired"]
    assert len(events) == 1 and short in events[0]["details"]
    # 90 days on, revoked and expired rows are purged with their access log.
    rig.advance(91 * DAY)
    rig.shares.housekeeping(rig.now[0], CLI)
    assert rig.shares.owner_get(owner, revoked) is None and rig.shares.owner_get(owner, short) is None
    assert rig.shares.owner_get(owner, sid) is not None or rig.shares.owner_list(owner, rig.now[0]) == []


def test_disabled_owner_serves_nothing(rig):
    admin, _ = rig.signed_in("root", role="admin")
    ob, owner, vid, sid, g = _setup(rig)
    assert admin.post(API + "/users/disable", json={"id": owner}).status_code == 200
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 404
    assert g.get("/api/viewer/shares").get_json()["shares"] == []
    assert rig.shares.body_path(sid).exists()  # kept while the owner is unusable
    assert admin.post(API + "/users/enable", json={"id": owner}).status_code == 200
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 200
    # An owner whose access has expired serves nothing either.
    rig.store.set_profile(owner, expires_at=rig.now[0] + 10, now=rig.now[0], actor=CLI)
    rig.advance(11)
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 404


def test_deleting_the_owner_removes_shares_viewers_and_bodies(rig):
    admin, _ = rig.signed_in("root", role="admin")
    ob, owner, vid, sid, g = _setup(rig)
    other_owner = rig.add_user("otto")
    other_viewer = rig.add_viewer("val", sponsor=other_owner)
    rig.app_recorder = None
    path = rig.shares.body_path(sid)
    r = admin.post(API + "/users/delete", json={"id": owner, "confirm_username": "olive"})
    assert r.status_code == 200
    assert rig.store.get_user(vid) is None and rig.store.get_user(other_viewer) is not None
    assert rig.shares.owner_get(owner, sid) is None and not path.exists()
    assert g.get("/api/viewer/shares").status_code == 401  # the viewer's session went with the account
    events = [e["event"] for e in rig.store.read_audit(50)]
    assert "viewer deleted" in events and "user deleted" in events


def test_viewer_deleted_or_disabled_gets_nothing(rig):
    admin, _ = rig.signed_in("root", role="admin")
    ob, owner, vid, sid, g = _setup(rig)
    assert admin.post(API + "/users/disable", json={"id": vid}).status_code == 200
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 401
    assert admin.post(API + "/users/delete", json={"id": vid, "confirm_username": "vic"}).status_code == 200
    assert rig.shares.owner_get(owner, sid) is None  # the share cascaded with its grantee


def test_deleting_the_plan_revokes_its_shares(rig):
    ob, owner, vid, sid, g = _setup(rig)
    other_plan = _create(ob, vid, title="Plan B", expected_plan_id="plan-b").get_json()["id"]
    hook = plan_delete_hook(rig.shares, CLI, clock=lambda: rig.now[0])

    class Sup:
        def endpoint(self, uid):
            raise AssertionError("not reached")
    proxy = WorkerProxy(Sup(), BuildQueue(1))
    proxy._send = lambda req, uid, path, **kw: Response(json.dumps({"success": True}), status=200,
                                                        content_type="application/json")
    proxy.after_forward = hook
    ident = Identity(owner, "olive", "Olive", "user")
    body = json.dumps({"plan_id": "plan-a", "confirm_name": "Main"}).encode()
    # A failed delete changes nothing; another user's delete of a plan with the same id changes nothing.
    proxy._send = lambda req, uid, path, **kw: Response("{}", status=400, content_type="application/json")
    proxy.forward(LocalRequest("POST", "/api/plans/delete", HeaderMap({"Host": "x"}), body, environ={}), ident)
    proxy.forward(LocalRequest("POST", "/api/plans/delete", HeaderMap({"Host": "x"}), body, environ={}),
                  Identity(owner + 50, "x", "X", "user"))
    assert rig.shares.owner_get(owner, sid)["state"] == "active"
    proxy._send = lambda req, uid, path, **kw: Response("{}", status=200, content_type="application/json")
    proxy.forward(LocalRequest("POST", "/api/plans/delete", HeaderMap({"Host": "x"}), body, environ={}), ident)
    row = rig.shares.owner_get(owner, sid)
    assert row["state"] == "revoked" and row["state_reason"] == "plan deleted"
    assert not rig.shares.body_path(sid).exists()
    assert rig.shares.owner_get(owner, other_plan)["state"] == "active"
    assert g.get(f"/api/viewer/shares/{sid}").status_code == 404


SHARE_DETAILS = re.compile(r"^share [0-9a-f]{32}( rev \d+)?( bytes \d+)?( reason [a-z_ ]+)?( days \d+)?$")


def test_audit_and_access_log_hold_ids_only(rig):
    ob, owner, vid, sid, g = _setup(rig)
    title = "Secret title 98765"
    sid2 = _create(ob, vid, title=title).get_json()["id"]
    g.get(f"/api/viewer/shares/{sid2}")
    g.get(f"/api/viewer/shares/{sid2}")
    ob.post(f"/api/share/{sid2}/expiry", json={"expires_in_days": 30})
    ob.post(f"/api/share/{sid2}/scope", json={"money_view": "dollars", "views": ["trends"]})
    rig.fake_worker.status = 500
    ob.post(f"/api/share/{sid2}/publish")
    ob.post(f"/api/share/{sid2}/revoke")
    share_events = [e for e in rig.store.read_audit(500) if e["event"].startswith("share_")]
    names = {e["event"] for e in share_events}
    assert {"share_created", "share_published", "share_viewed", "share_scope_changed", "share_publish_failed",
            "share_revoked", "share_expiry_changed"} <= names
    for e in share_events:
        assert SHARE_DETAILS.match(e["details"]), e
        assert title not in json.dumps(e)
    viewed = [e for e in share_events if e["event"] == "share_viewed" and sid2 in e["details"]]
    assert len(viewed) == 1  # once per session and share
    log = ob.get(f"/api/share/{sid}/views").get_json()["views"]
    assert log and set(log[0]) == {"at", "viewer"} and log[0]["viewer"] == "Vic"
    rows = rig.store._read("SELECT * FROM share_access_log")
    assert all(set(r.keys()) == {"id", "share_id", "viewer_user_id", "at"} for r in rows)
    assert len([r for r in rows if r["share_id"] == sid2]) == 1  # at most one row per 10 minutes


def test_flag_off_serves_nothing(tmp_path):
    on = Rig(tmp_path, shared_views=True, publisher_factory=_publisher)
    ob, owner, vid, sid, g = _setup(on)
    body = on.shares.body_path(sid).read_bytes()
    off = Rig.__new__(Rig)  # the same database and folder, with the flag off
    off.__init__(tmp_path, shared_views=False, shares=on.shares)
    off.now = on.now
    g_off = off.browser(ip="203.0.113.91")
    _relogin(off, g_off, "vic", vid)
    o_off = off.browser(ip="203.0.113.92")
    _relogin(off, o_off, "olive", owner)
    for b, path in ((g_off, "/api/viewer/shares"), (g_off, f"/api/viewer/shares/{sid}"),
                    (g_off, f"/api/viewer/shares/{sid}/status"), (g_off, "/gateway/viewer"),
                    (o_off, "/api/share/list"), (o_off, f"/api/share/{sid}/preview"), (o_off, "/gateway/sharing")):
        assert b.get(path).status_code == 404, path
    assert o_off.post(f"/api/share/{sid}/publish").status_code == 404
    assert on.shares.body_path(sid).read_bytes() == body  # rows and bodies are kept
    assert off.upstream.calls == []
    # Turning it on again restores the previous state.
    again = Rig.__new__(Rig)
    again.__init__(tmp_path, shared_views=True, shares=on.shares)
    again.now = on.now
    g_on = again.browser(ip="203.0.113.93")
    _relogin(again, g_on, "vic", vid)
    assert g_on.get(f"/api/viewer/shares/{sid}").get_data() == body
