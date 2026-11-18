"""Owner and viewer share routes over the gateway (Phase 9, design 5.6 and 5.8): selection by session, one uniform
not-found, CSRF and Origin, the sponsor rule, admins, limits, headers. Controls C5, C6, C12, C25, C28-C30, C33, AC-13.

In process: the owner's worker is a fake that answers the snapshot route as a correct worker would.
"""
from __future__ import annotations

import pytest

from src.gateway.share_publish import SharePublisher
from src.gateway.share_routes import NOT_FOUND_BODY
from src.gateway.viewer_routes import NOT_AVAILABLE_BODY
from tests.gateway_rig import Rig
from tests.test_gateway_share_publish_functional import FakeSupervisor, FakeWorker

DAY = 86400.0


def _publisher(rig):
    rig.fake_worker = FakeWorker(rig.shares)
    return SharePublisher(rig.shares, FakeSupervisor(), clock=lambda: rig.now[0], call=rig.fake_worker,
                          min_seconds_between=0, audit=lambda event, **kw: rig.store.audit(
                              event, now=rig.now[0], actor=kw["actor"], target_user_id=kw.get("target_user_id"),
                              details=kw.get("details", "")))


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path, shared_views=True, publisher_factory=_publisher)


def _create(owner_browser, viewer_id, **kw):
    body = {"viewer_id": viewer_id, "title": "For my advisor", "money_view": "percent",
            "views": ["live", "trends", "projections"], "expires_in_days": 90, "expected_plan_id": "plan-a"}
    body.update(kw)
    return owner_browser.post("/api/share/create", json=body)


@pytest.fixture()
def two(rig):
    """Two owners, each with one viewer and one published share."""
    oa, a = rig.signed_in("olive")
    ob, b = rig.signed_in("otto")
    va = rig.add_viewer("vic", sponsor=a)
    vb = rig.add_viewer("val", sponsor=b)
    sa = _create(oa, va).get_json()
    sb = _create(ob, vb).get_json()
    assert sa["published"] and sb["published"], (sa, sb)
    gva = rig.browser(ip="203.0.113.61")
    gva.login("vic")
    rig.enrol(gva, va)
    gvb = rig.browser(ip="203.0.113.62")
    gvb.login("val")
    rig.enrol(gvb, vb)
    return {"oa": oa, "ob": ob, "a": a, "b": b, "va": va, "vb": vb, "sa": sa["id"], "sb": sb["id"], "gva": gva,
            "gvb": gvb}


def test_other_guests_share_id_gives_the_uniform_404(rig, two):
    t = two
    assert t["gva"].get(f"/api/viewer/shares/{t['sa']}").status_code == 200
    for path in (f"/api/viewer/shares/{t['sb']}", f"/api/viewer/shares/{t['sb']}/status"):
        r = t["gva"].get(path)
        assert r.status_code == 404 and r.get_data() == NOT_AVAILABLE_BODY.encode()
    assert [s["id"] for s in t["gva"].get("/api/viewer/shares").get_json()["shares"]] == [t["sa"]]


def test_owner_cannot_reach_another_owners_share(rig, two):
    t = two
    for method, path in (("GET", f"/api/share/{t['sb']}/preview"), ("GET", f"/api/share/{t['sb']}/views"),
                         ("POST", f"/api/share/{t['sb']}/publish"), ("POST", f"/api/share/{t['sb']}/revoke"),
                         ("POST", f"/api/share/{t['sb']}/enable"), ("POST", f"/api/share/{t['sb']}/expiry"),
                         ("POST", f"/api/share/{t['sb']}/scope")):
        r = t["oa"].request(method, path, json_body={"expires_in_days": 5, "money_view": "dollars", "views": ["trends"]}
                            if method == "POST" else None)
        assert r.status_code == 404 and r.get_data() == NOT_FOUND_BODY.encode(), (method, path)
    assert rig.shares.owner_get(t["b"], t["sb"])["state"] == "active"
    assert [s["id"] for s in t["oa"].get("/api/share/list").get_json()["shares"]] == [t["sa"]]


def test_not_available_responses_are_byte_identical(rig, two):
    t = two
    g = t["gva"]
    revoked = _create(t["oa"], t["va"], title="To revoke").get_json()["id"]
    t["oa"].post(f"/api/share/{revoked}/revoke")
    expiring = _create(t["oa"], t["va"], title="Short", expires_in_days=1).get_json()["id"]
    unpublished = rig.shares.create(t["a"], viewer_id=t["va"], title="Never published", money_view="percent",
                                    views=["trends"], expires_in_days=9, plan_id="plan-a", now=rig.now[0], actor=rig_cli())
    rig.advance(DAY + 1)
    g = rig.browser(ip="203.0.113.70")  # the earlier session went idle in the meantime
    _relogin(rig, g, "vic", t["va"])
    ids = ["0" * 32, "not-hex", "A" * 32, "a" * 31, t["sb"], revoked, expiring, unpublished, "%2e%2e", "x" * 200]
    bodies = set()
    for sid in ids:
        for suffix in ("", "/status"):
            r = g.get(f"/api/viewer/shares/{sid}{suffix}")
            assert r.status_code == 404, (sid, suffix)
            bodies.add(r.get_data())
            assert r.headers["Content-Type"].startswith("application/json")
    assert bodies == {NOT_AVAILABLE_BODY.encode()}
    assert g.get(f"/api/viewer/shares/{t['sa']}").status_code == 200  # the live one still works


def _relogin(rig, b, name, uid):
    assert b.login(name).status_code == 200
    assert b.post("/api/auth/totp/verify", json={"code": rig.code(uid)}).status_code == 200
    b.refresh_csrf()
    rig.advance(31)


def rig_cli():
    from tests.gateway_rig import CLI
    return CLI


def test_revoke_takes_effect_on_the_next_request(rig, two):
    t = two
    assert t["gva"].get(f"/api/viewer/shares/{t['sa']}").status_code == 200
    assert t["oa"].post(f"/api/share/{t['sa']}/revoke").status_code == 200
    assert t["gva"].get(f"/api/viewer/shares/{t['sa']}").status_code == 404
    assert t["gva"].get(f"/api/viewer/shares/{t['sa']}/status").status_code == 404
    assert t["gva"].get("/api/viewer/shares").get_json()["shares"] == []
    assert not rig.shares.body_path(t["sa"]).exists()


def test_expired_share_is_not_served(rig, two):
    t = two
    assert t["oa"].post(f"/api/share/{t['sa']}/expiry", json={"expires_in_days": 1}).status_code == 200
    rig.advance(DAY - 60)
    g = t["gva"]
    g.login("vic")
    g.post("/api/auth/totp/verify", json={"code": rig.code(t["va"])})
    g.refresh_csrf()
    assert g.get(f"/api/viewer/shares/{t['sa']}").status_code == 200
    rig.advance(120)
    assert g.get(f"/api/viewer/shares/{t['sa']}").status_code == 404
    # Renewal brings it back (the body was kept until housekeeping runs).
    t["oa"].login("olive")
    t["oa"].post("/api/auth/totp/verify", json={"code": rig.code(t["a"])})
    t["oa"].refresh_csrf()
    assert t["oa"].post(f"/api/share/{t['sa']}/expiry", json={"expires_in_days": 30}).status_code == 200
    assert g.get(f"/api/viewer/shares/{t['sa']}").status_code == 200


def test_query_and_headers_change_nothing(rig, two):
    t = two
    base = t["gva"].get(f"/api/viewer/shares/{t['sa']}").get_data()
    for q in ("?views=projections", "?money_view=dollars", "?scope=all", f"?share_id={t['sb']}", "?user=2"):
        assert t["gva"].get(f"/api/viewer/shares/{t['sa']}{q}").get_data() == base, q
    for h in ({"X-Forwarded-User": "otto"}, {"X-Gateway-Share-Publish": "1"}, {"X-Money-View": "dollars"}):
        assert t["gva"].get(f"/api/viewer/shares/{t['sa']}", headers=h).get_data() == base
    assert t["gva"].get(f"/api/viewer/shares?owner={t['b']}").get_json()["shares"][0]["id"] == t["sa"]


def test_viewer_and_owner_responses_carry_no_store_and_csp(rig, two):
    t = two
    for b, path in ((t["gva"], "/api/viewer/shares"), (t["gva"], f"/api/viewer/shares/{t['sa']}"),
                    (t["gva"], f"/api/viewer/shares/{t['sb']}"), (t["gva"], "/gateway/viewer"),
                    (t["oa"], "/api/share/list"), (t["oa"], f"/api/share/{t['sa']}/preview"), (t["oa"], "/api/share/x"),
                    (t["gva"], "/api/plans")):
        r = b.get(path)
        assert r.headers["Cache-Control"] == "no-store", path
        assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Referrer-Policy"] == "no-referrer", path
        assert "default-src 'self'" in r.headers["Content-Security-Policy"], path
        assert r.headers["X-Content-Type-Options"] == "nosniff", path


def test_owner_writes_need_csrf_and_origin(rig, two):
    t = two
    for kw in ({"csrf": False}, {"origin": "https://evil.example"}, {"origin": False},
               {"headers": {"Sec-Fetch-Site": "cross-site"}}):
        r = t["oa"].post(f"/api/share/{t['sa']}/revoke", **kw)
        assert r.status_code == 403, kw
        r = t["oa"].post("/api/share/create", json={"viewer_id": t["va"], "title": "x", "expected_plan_id": "plan-a"}, **kw)
        assert r.status_code == 403, kw
    r = t["oa"].request("POST", f"/api/share/{t['sa']}/revoke", body=b"viewer_id=1",
                        content_type="application/x-www-form-urlencoded")
    assert r.status_code == 403
    assert rig.shares.owner_get(t["a"], t["sa"])["state"] == "active"


def test_owner_cannot_grant_or_list_viewers_they_do_not_sponsor(rig, two):
    t = two
    viewers = t["oa"].get("/api/share/viewers").get_json()["viewers"]
    assert [v["id"] for v in viewers] == [t["va"]]
    for vid in (t["vb"], t["b"], t["a"], 99999, "1", None, True):
        r = _create(t["oa"], vid)
        assert r.status_code == 404 and r.get_json()["error"] == "That viewer was not found.", vid
    assert len(t["oa"].get("/api/share/list").get_json()["shares"]) == 1


def test_admin_cannot_read_or_create_shares(rig, two):
    t = two
    admin, _ = rig.signed_in("root", role="admin")
    for path in (f"/api/share/{t['sa']}/preview", f"/api/share/{t['sb']}/views"):
        assert admin.get(path).status_code == 404
    assert admin.get("/api/share/list").get_json()["shares"] == []
    assert _create(admin, t["va"]).status_code == 404  # an admin sponsors no one here
    users = admin.get("/api/auth/admin/console/users").get_json()["users"]
    by_id = {u["id"]: u for u in users}
    assert by_id[t["a"]]["shares_owned"] == 1 and by_id[t["va"]]["shares_received"] == 1
    text = str(users)
    assert "For my advisor" not in text and t["sa"] not in text  # counts only: no titles, no ids
    assert not any(r.rule.startswith("/api/auth/admin") and "share" in r.rule for r in rig.app.url_map.iter_rules())


def test_limits_refuse_with_409(tmp_path):
    rig = Rig(tmp_path, shared_views=True, publisher_factory=_publisher)
    oa, a = rig.signed_in("olive")
    va = rig.add_viewer("vic", sponsor=a)
    for i in range(10):
        assert _create(oa, va, title=f"S{i}").status_code == 200
    r = _create(oa, va, title="Eleventh")
    assert r.status_code == 409 and "at most 10" in r.get_json()["error"]
    for i in range(4):
        rig.add_viewer(f"v{i}x", sponsor=a)
    with pytest.raises(ValueError):
        rig.add_viewer("sixth", sponsor=a)
    sid = oa.get("/api/share/list").get_json()["shares"][0]["id"]
    rig.publisher._min_between = 60.0
    rig.publisher._last.clear()
    assert oa.post(f"/api/share/{sid}/publish").status_code == 200
    r = oa.post(f"/api/share/{sid}/publish")
    assert r.status_code == 409 and "less than a minute" in r.get_json()["message"]


def test_viewer_body_cap_is_the_gateway_cap(rig, two):
    t = two
    big = b"x" * (32 * 1024 + 1)
    for listener in ("funnel",):
        refusal, limit = rig.funnel.preflight("GET", f"/api/viewer/shares/{t['sa']}",
                                               {"Host": "node.example.ts.net:8443", "X-Forwarded-For": "203.0.113.61",
                                                "Cookie": "; ".join(f"{k}={v}" for k, v in t["gva"].cookies.items())})
        assert refusal is None and limit == 32 * 1024, listener
        refusal, limit = rig.funnel.preflight("POST", "/api/plans/upload",
                                               {"Host": "node.example.ts.net:8443", "X-Forwarded-For": "203.0.113.61",
                                                "Origin": "https://node.example.ts.net:8443",
                                                "X-CSRF-Token": t["gva"].csrf, "Content-Type": "application/json",
                                                "Cookie": "; ".join(f"{k}={v}" for k, v in t["gva"].cookies.items())})
        assert refusal is not None and refusal.status_code == 404  # refused before any body is read
    assert len(big) > 32 * 1024
    assert rig.upstream.calls == []


def test_flag_off_owner_routes_answer_404(tmp_path):
    rig = Rig(tmp_path)
    oa, a = rig.signed_in("olive")
    for method, path in (("GET", "/api/share/list"), ("GET", "/api/share/viewers"), ("POST", "/api/share/create"),
                         ("GET", "/gateway/sharing"), ("GET", "/gateway/sharing/static/sharing.js")):
        assert oa.request(method, path, json_body={} if method == "POST" else None).status_code == 404, path
    assert rig.upstream.calls == []
