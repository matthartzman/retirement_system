"""The gateway's share publisher (Phase 9, design 5.4-5.5): worker output is untrusted, bodies are bound to rows,
races leave nothing wider, the snapshot route is the gateway's alone. Controls C14, C15, C19, C20, C22, C23, C24, C33.

Most tests answer for the worker with a fake; one renders a real record through FI in worker mode, in process.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from src.gateway.build_queue import BuildQueue
from src.gateway.proxy import WorkerProxy
from src.gateway.share_publish import PUBLISH_HEADER, SNAPSHOT_PATH, SharePublisher, validate_record
from src.gateway.supervisor import Endpoint
from src.gateway.upstream import Identity, upstream_headers
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest
from tests.gateway_rig import CLI, Rig

SCOPES = {sc: {"from": "2026-01-01", "to": "2026-11-18"} for sc in ("week", "month", "3m", "6m", "ytd", "1y", "all")}


class FakeSupervisor:
    def __init__(self) -> None:
        self.asked: list[int] = []

    def endpoint(self, uid):
        self.asked.append(uid)
        return Endpoint(uid, 40000 + uid, 1, "tok")


def record(row, **over):
    views = {}
    for tab in row["views"]:
        if tab == "trends":
            views[tab] = {"/api/history": [{"as_of_date": "2026-11-18", "net_worth": {"total": 0.5}}],
                          "/api/spending?scope=ytd": {"total": 0.01}}
        elif tab == "live":
            views[tab] = {"/api/live-snapshot?scope=week": {"total": 0.2}, "/api/realized?tax_year=2026": {"gain": 0.01}}
        else:
            views[tab] = {"/api/projections": {"rows": [{"year": 2030, "total": 1.5}]}}
    doc = {"schema": "shared_view/1", "share_id": row["id"], "scope_rev": row["scope_rev"],
           "generated_at": "2026-11-18T12:00:00Z", "plan": {"id": row["plan_id"], "name": "Main plan"},
           "money_view": row["money_view"], "basis_date": "2026-11-18", "scopes": copy.deepcopy(SCOPES), "views": views}
    doc.update(over)
    return doc


class FakeWorker:
    """Answers the snapshot route from the row it is asked about (what a correct worker would return)."""

    def __init__(self, shares) -> None:
        self.shares = shares
        self.calls: list[dict] = []
        self.mutate = None
        self.status = 200
        self.ctype = "application/json"
        self.raw: bytes | None = None

    def __call__(self, ep, method, path, *, body, timeout, max_bytes, headers):
        ask = json.loads(body)
        self.calls.append({"ep": ep, "method": method, "path": path, "ask": ask, "headers": headers,
                           "max_bytes": max_bytes})
        row = dict(self.shares.owner_get(ep.user_id, ask["share_id"]))
        doc = record(row)
        if self.mutate:
            doc = self.mutate(doc) or doc
        data = self.raw if self.raw is not None else json.dumps(doc).encode()
        return self.status, self.ctype, data[:max_bytes]


@pytest.fixture()
def env(tmp_path):
    rig = Rig(tmp_path, shared_views=True)
    owner = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner)
    worker = FakeWorker(rig.shares)
    sup = FakeSupervisor()
    audit = []
    pub = SharePublisher(rig.shares, sup, clock=lambda: rig.now[0], call=worker, min_seconds_between=0,
                         audit=lambda event, **kw: audit.append((event, kw)))
    sid = rig.shares.create(owner, viewer_id=vid, title="For Vic", money_view="percent",
                            views=["live", "trends", "projections"], expires_in_days=90, plan_id="plan-a",
                            now=rig.now[0], actor=CLI)
    return rig, owner, vid, sid, pub, worker, sup, audit


def _viewer(rig, vid):
    b = rig.browser(ip="203.0.113.60")
    assert b.login("vic").status_code == 200
    rig.enrol(b, vid)
    return b


def test_publish_stores_a_body_bound_to_its_row_and_the_viewer_gets_it(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    res = pub.publish(owner, sid, actor=CLI)
    assert res.ok, res.code
    call = worker.calls[0]
    assert call["path"] == SNAPSHOT_PATH and call["headers"] == {PUBLISH_HEADER: "1"}
    assert call["ask"] == {"share_id": sid, "scope_rev": 1, "money_view": "percent",
                           "views": ["live", "trends", "projections"], "expected_plan_id": "plan-a"}
    assert call["max_bytes"] == pub.max_bytes + 1 and sup.asked == [owner]  # the owner's own worker, nobody else's
    row = rig.shares.owner_get(owner, sid)
    data = rig.shares.body_path(sid).read_bytes()
    assert row["snapshot_sha256"] == hashlib.sha256(data).hexdigest() and row["snapshot_bytes"] == len(data)
    assert row["published_rev"] == 1
    b = _viewer(rig, vid)
    r = b.get(f"/api/viewer/shares/{sid}")
    assert r.status_code == 200 and r.get_data() == data
    assert [s["id"] for s in b.get("/api/viewer/shares").get_json()["shares"]] == [sid]
    assert ("share_published", audit[0][1]) == audit[0] and "bytes" in audit[0][1]["details"]
    assert not list(rig.shares.dir.glob("*.tmp"))


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(extra=1),                                             # an unknown top-level key
    lambda d: d.pop("scopes"),                                               # a missing one
    lambda d: d.update(schema="shared_view/2"),
    lambda d: d.update(share_id="f" * 32),                                   # someone else's id
    lambda d: d.update(scope_rev=d["scope_rev"] + 1),
    lambda d: d.update(money_view="dollars"),
    lambda d: d["plan"].update(id="plan-b"),
    lambda d: d["views"].update(accounts={"/api/accounts": {}}),             # a tab that does not exist
    lambda d: d["views"]["trends"].update({"/api/spending/transactions": []}),  # a never-included route
    lambda d: d["views"]["trends"].update({"/api/spending?scope=custom": {}}),
    lambda d: d["views"]["projections"].update({"/api/whoami": {}}),
    lambda d: d.update(views=[]),
    lambda d: d["scopes"].update(custom={}),
])
def test_output_outside_the_schema_or_scope_is_refused(env, mutate):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    worker.mutate = mutate
    res = pub.publish(owner, sid, actor=CLI)
    assert not res.ok and res.code == "invalid"
    assert not rig.shares.body_path(sid).exists()
    assert rig.shares.owner_get(owner, sid)["published_at"] is None
    assert audit[-1][0] == "share_publish_failed" and "reason invalid" in audit[-1][1]["details"]


def test_more_tabs_than_granted_are_refused(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    rig.shares.set_scope(owner, sid, money_view="percent", views=["trends"], now=rig.now[0], actor=CLI)

    def widen(d):
        d["views"]["projections"] = {"/api/projections": {"rows": []}}
    worker.mutate = widen
    assert pub.publish(owner, sid, actor=CLI).code == "invalid"


def test_non_200_non_json_and_garbage_are_refused(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    for status, ctype, raw in ((500, "application/json", b"{}"), (200, "text/html", None), (200, "application/json", b"{"),
                               (200, "application/json", b"[]")):
        worker.status, worker.ctype, worker.raw = status, ctype, raw
        assert pub.publish(owner, sid, actor=CLI).code == "invalid", (status, ctype, raw)
    assert not rig.shares.body_path(sid).exists()


def test_oversized_output_is_refused(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    pub.max_bytes = 2000

    def big(d):
        d["views"]["projections"]["/api/projections"] = {"rows": [{"year": 2030, "note": "x" * 500}] * 20}
    worker.mutate = big
    res = pub.publish(owner, sid, actor=CLI)
    assert res.code == "too_large"
    assert worker.calls[-1]["max_bytes"] == 2001  # the cap plus one byte, never a silently truncated body
    assert not rig.shares.body_path(sid).exists()
    assert validate_record(200, "application/json", json.dumps(record(rig.shares.owner_get(owner, sid))).encode(),
                           rig.shares.owner_get(owner, sid), 10**6)


def test_gateway_rechecks_for_money_leaks(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env

    def leak(d):
        d["views"]["trends"]["/api/history"][0]["net_worth"]["total"] = 1234567.0  # an unscaled amount
    worker.mutate = leak
    assert pub.publish(owner, sid, actor=CLI).code == "money_leak"

    def dollar_text(d):
        d["views"]["projections"]["/api/projections"]["note"] = "You have $1,234,567"
    worker.mutate = dollar_text
    assert pub.publish(owner, sid, actor=CLI).code == "money_leak"
    assert not rig.shares.body_path(sid).exists()
    # A dollars share is not checked for amounts: they are the point of it.
    rig.shares.set_scope(owner, sid, money_view="dollars", views=["trends"], now=rig.now[0], actor=CLI)
    worker.mutate = leak
    assert pub.publish(owner, sid, actor=CLI).ok


def test_strings_are_normalised(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    hostile = "Bro‮kerage\u0000 <script>alert(1)</script>​ Á"

    def names(d):
        d["plan"]["name"] = hostile
        d["views"]["trends"]["/api/history"][0]["account"] = hostile * 50
    worker.mutate = names
    assert pub.publish(owner, sid, actor=CLI).ok
    doc = json.loads(rig.shares.body_path(sid).read_bytes())
    name = doc["plan"]["name"]
    assert "‮" not in name and "\u0000" not in name and "​" not in name
    assert "Á" in name  # NFC: A + combining acute became one character
    assert "<script>" in name  # markup is kept as text; the page renders text only (C24, 9c)
    assert len(doc["views"]["trends"]["/api/history"][0]["account"]) <= 200


def test_body_not_matching_its_row_is_never_served(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    assert pub.publish(owner, sid, actor=CLI).ok
    b = _viewer(rig, vid)
    path = rig.shares.body_path(sid)
    good = path.read_bytes()
    assert b.get(f"/api/viewer/shares/{sid}").status_code == 200
    miss = b.get("/api/viewer/shares/" + "e" * 32).get_data()
    tampered = [good.replace(b"Main plan", b"Main plaN"),                        # one byte: digest
                good + b" ",                                                       # size
                json.dumps({**json.loads(good), "scope_rev": 2}).encode()]         # embedded revision
    for data in tampered:
        path.write_bytes(data)
        r = b.get(f"/api/viewer/shares/{sid}")
        assert r.status_code == 404 and r.get_data() == miss
    path.unlink()
    assert b.get(f"/api/viewer/shares/{sid}").get_data() == miss
    events = [e["event"] for e in rig.store.read_audit(50)]
    assert events.count("share_integrity_failed") == 4
    # A body published for another share is not served under this one, even byte for byte.
    other = rig.shares.create(owner, viewer_id=vid, title="Other", money_view="percent", views=["trends"],
                              expires_in_days=9, plan_id="plan-a", now=rig.now[0], actor=CLI)
    assert pub.publish(owner, other, actor=CLI).ok
    path.write_bytes(rig.shares.body_path(other).read_bytes())
    assert b.get(f"/api/viewer/shares/{sid}").status_code == 404


def test_revoke_during_publish_leaves_nothing(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    pub.after_store = lambda share_id: rig.shares.revoke(owner, share_id, now=rig.now[0], actor=CLI)
    res = pub.publish(owner, sid, actor=CLI)
    assert not res.ok and res.code == "lost_race"
    assert not rig.shares.body_path(sid).exists()
    row = rig.shares.owner_get(owner, sid)
    assert row["state"] == "revoked" and row["published_at"] is None
    pub.after_store = None
    assert pub.publish(owner, sid, actor=CLI).code == "not_found"  # a revoked share is never published again


def test_scope_change_during_publish_discards_the_wider_result(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    assert pub.publish(owner, sid, actor=CLI).ok  # all three tabs are live
    pub.after_store = lambda share_id: rig.shares.set_scope(owner, share_id, money_view="percent", views=["trends"],
                                                            now=rig.now[0], actor=CLI)
    res = pub.publish(owner, sid, actor=CLI)
    assert res.code == "lost_race"
    assert not rig.shares.body_path(sid).exists()  # neither the old wide body nor the new wide one survives
    row = rig.shares.owner_get(owner, sid)
    assert row["scope_rev"] == 2 and row["published_at"] is None and row["views"] == ["trends"]
    b = _viewer(rig, vid)
    assert b.get(f"/api/viewer/shares/{sid}").status_code == 404
    pub.after_store = None
    assert pub.publish(owner, sid, actor=CLI).ok
    assert list(json.loads(b.get(f"/api/viewer/shares/{sid}").get_data())["views"]) == ["trends"]


def test_plan_switched_in_another_tab_is_not_published(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    worker.status, worker.raw = 409, json.dumps({"success": False, "error": "plan_not_active"}).encode()
    res = pub.publish(owner, sid, actor=CLI)
    assert res.code == "plan_not_active" and "Open this view's plan" in res.message
    assert not rig.shares.body_path(sid).exists()
    worker.status, worker.raw = 410, json.dumps({"success": False, "error": "plan_missing"}).encode()
    assert pub.publish(owner, sid, actor=CLI).code == "plan_missing"
    assert rig.shares.owner_get(owner, sid)["state"] == "revoked"  # decision 7


def test_publish_is_scoped_to_the_owner_and_rate_limited(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    other = rig.add_user("otto")
    assert pub.publish(other, sid, actor=CLI).code == "not_found"
    assert pub.publish(owner, "../" + sid, actor=CLI).code == "not_found"
    assert worker.calls == []
    slow = SharePublisher(rig.shares, FakeSupervisor(), clock=lambda: rig.now[0], call=worker,
                          audit=lambda *a, **k: None)
    assert slow.publish(owner, sid, actor=CLI).ok
    assert slow.publish(owner, sid, actor=CLI).code == "too_soon"
    rig.advance(61)
    assert slow.publish(owner, sid, actor=CLI).ok


def test_browser_cannot_call_the_snapshot_route():
    class Sup:
        def __init__(self):
            self.calls = []

        def endpoint(self, uid):
            self.calls.append(uid)
            raise AssertionError("must not be reached")
    sup = Sup()
    proxy = WorkerProxy(sup, BuildQueue(1))
    for path in ("/insights/api/share-snapshot", "/insights/api/share-snapshot/", "/insights/api/SHARE-SNAPSHOT",
                 "/insights/api/share%2Dsnapshot", "/insights/api/share%252Dsnapshot", "/insights/api/share-snapshot.json"):
        for method in ("POST", "GET"):
            req = LocalRequest(method, path, HeaderMap({"Host": "x", PUBLISH_HEADER: "1"}), b"{}", environ={})
            assert proxy.forward(req, Identity(3, "olive", "Olive", "user")).status_code in (400, 404), path
    assert sup.calls == []
    # The gateway-only header never survives the proxy's header contract.
    out = upstream_headers({PUBLISH_HEADER: "1", "x-gateway-share-publish": "1", "Accept": "*/*"}, worker_port=1,
                           worker_token="t", body_length=0)
    assert not any(k.lower() == PUBLISH_HEADER.lower() for k in out)


def test_a_real_worker_record_passes_validation_and_is_served(tmp_path, monkeypatch):
    """End to end in process: FI in worker mode renders, the gateway checks, stores and serves it."""
    from financial_trends_reporter import worker_mode
    from financial_trends_reporter.main import create_app
    from src import market_data, plan_registry, platform_runtime
    from tests.test_insights_worker_mode_functional import ROWS, _clear_balances, _put_balances

    monkeypatch.setattr(market_data, "quote_details", lambda symbols, *a, **k: {})
    monkeypatch.setattr(market_data, "daily_closes", lambda *a, **k: {})
    monkeypatch.setattr(worker_mode, "SYNC_MIN_INTERVAL_SECONDS", 0.0)
    _clear_balances()
    _put_balances(ROWS)
    try:
        fi = worker_mode.WorkerListenerApp(create_app(platform_runtime.workspace_root(), mode="worker"))

        def call(ep, method, path, *, body, timeout, max_bytes, headers):
            assert path.startswith("/insights/")
            resp = fi.handle_http(method, path[len("/insights"):], {"Host": "127.0.0.1:1", **headers,
                                                                    "Content-Type": "application/json"}, body)
            return resp.status_code, resp.headers.get("Content-Type", ""), resp.get_data()[:max_bytes]

        rig = Rig(tmp_path, shared_views=True)
        owner = rig.add_user("olive")
        vid = rig.add_viewer("vic", sponsor=owner)
        pub = SharePublisher(rig.shares, FakeSupervisor(), clock=lambda: rig.now[0], call=call,
                             audit=lambda *a, **k: None)
        plan = plan_registry.active_plan_id()
        for mv in ("percent", "dollars"):
            sid = rig.shares.create(owner, viewer_id=vid, title=f"Real {mv}", money_view=mv,
                                    views=["live", "trends", "projections"], expires_in_days=90, plan_id=plan,
                                    now=rig.now[0], actor=CLI)
            res = pub.publish(owner, sid, actor=CLI)
            assert res.ok, res.code
            print(f"measured: {mv} record {res.nbytes} bytes")
            doc = json.loads(rig.shares.body_path(sid).read_bytes())
            assert set(doc["views"]) == {"live", "trends", "projections"}
        other = rig.shares.create(owner, viewer_id=vid, title="Other plan", money_view="dollars", views=["trends"],
                                  expires_in_days=90, plan_id="not-this-plan", now=rig.now[0], actor=CLI)
        assert pub.publish(owner, other, actor=CLI).code == "plan_missing"
    finally:
        _clear_balances()


def test_validate_record_never_mutates_its_input(env):
    rig, owner, vid, sid, pub, worker, sup, audit = env
    row = rig.shares.owner_get(owner, sid)
    doc = record(row)
    before = copy.deepcopy(doc)
    validate_record(200, "application/json; charset=utf-8", json.dumps(doc).encode(), row, 10**6)
    assert doc == before
