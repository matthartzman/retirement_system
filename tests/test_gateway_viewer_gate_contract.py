"""The viewer boundary (Phase 9, controls C1-C4 and C34): a viewer session is answered only by the gateway.

Walks every gateway route, every planner and Financial Insight rule, and spelling variants, as an active viewer:
only ``VIEWER_ALLOWED`` answers, and neither the upstream nor the supervisor is ever called. The second and third
layers (the proxy and the supervisor refusals) and Phase 8's scheduler selection are checked on their own, without
the gate in front of them. In process, with fakes: no worker is started.
"""
from __future__ import annotations

import json
import re
import types

import pytest

from financial_trends_reporter import worker_allowlist
from src.gateway import insights_schedule as sched
from src.gateway import viewer_routes
from src.gateway.build_queue import BuildQueue
from src.gateway.proxy import WorkerProxy
from src.gateway.supervisor import Supervisor, SupervisorConfig, WorkerUnavailable
from src.gateway.upstream import Identity
from src.gateway.viewer_routes import NOT_AVAILABLE_BODY, VIEWER_ALLOWED, VIEWER_HOME
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest
from src.server import remote_allowlist
from tests.gateway_rig import Rig

# The design's table (multi-user-shared-view-design.md, 5.6), typed out again on purpose. A change to the module's
# table must be made here too, which is the point: the table is reviewed line by line, not derived.
REVIEWED = frozenset({
    ("GET", "/login"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/session"),
    ("POST", "/api/auth/totp/enrol/start"),
    ("POST", "/api/auth/totp/enrol/confirm"),
    ("POST", "/api/auth/totp/verify"),
    ("GET", "/gateway/enrol"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/password"),
    ("GET", "/gateway/account"),
    ("GET", "/gateway/static/<name>"),
    ("GET", "/gateway/viewer"),
    ("GET", "/gateway/viewer/static/<name>"),
    ("GET", "/api/viewer/shares"),
    ("GET", "/api/viewer/shares/<share_id>"),
    ("GET", "/api/viewer/shares/<share_id>/status"),
})

# Paths a curious or hostile guest might try, beyond the route maps: other spellings of planner, FI, admin and owner
# paths (encoded, case-changed, doubled slashes, trailing slashes, dot segments).
EXTRA_PATHS = [
    "/", "/index.html", "/static/dashboard.html", "/api/plans", "/api/plans/delete", "/api/build/start",
    "/api/build/events/x", "/api/plan/rows", "/insights", "/insights/", "/insights/api/history",
    "/insights/api/share-snapshot", "/insights/api/projections", "/gateway/admin", "/gateway/admin/static/users.js",
    "/gateway/administrator", "/api/auth/admin/users", "/api/auth/admin/console/users", "/gateway/users",
    "/gateway/sharing", "/gateway/sharing/static/sharing.js", "/api/share/list", "/api/share/create",
    "/api/share/viewers", "/API/plans", "/Api/Plans", "/api//plans", "/api/plans/", "//api/plans", "/%61pi/plans",
    "/api/%2e%2e/plans", "/gateway/viewer/../admin", "/gateway/Viewer", "/gateway/viewer/", "/gateway/viewerx",
    "/api/viewer/shares/", "/api/viewer/sharesx", "/api/viewer/shares/../../plans", "/api/viewer",
    "/api/viewer/other", "/INSIGHTS/", "/insights/../api/plans", "/gateway/static/../app.py",
    "/gateway/viewer/static/../../app.py", "/gateway/viewer/static/", "/api/auth/admin", "/favicon.ico",
]
METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")


def _concrete(rule: str) -> str:
    return re.sub(r"<(?:int:|path:)?[^>]+>", lambda m: "1" if m.group(0).startswith("<int:") else "x", rule)


class RecordingSupervisor:
    """Stands in for the supervisor behind a real WorkerProxy: any call is a failure of the boundary."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def endpoint(self, uid):
        self.calls.append(("endpoint", uid))
        raise WorkerUnavailable("no workers in this test")

    def touch(self, uid):
        self.calls.append(("touch", uid))

    def port_owner_ok(self, ep):  # pragma: no cover - never reached
        return True

    def mark_dead(self, *a):  # pragma: no cover
        self.calls.append(("mark_dead", 0))


class CountingProxy(WorkerProxy):
    def __init__(self, sup) -> None:
        super().__init__(sup, BuildQueue(1))
        self.forwarded: list[tuple[str, str]] = []

    def forward(self, req, identity):
        self.forwarded.append((req.method, req.path))
        return super().forward(req, identity)


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path, shared_views=True)


@pytest.fixture()
def proxied(tmp_path):
    """A rig whose upstream is a real WorkerProxy over a recording supervisor."""
    sup = RecordingSupervisor()
    proxy = CountingProxy(sup)
    r = Rig(tmp_path, upstream=proxy, shared_views=True)
    r.sup, r.proxy = sup, proxy
    return r


def _all_targets(rig) -> list[tuple[str, str]]:
    """(method, path) pairs: every gateway route, every planner and FI rule, the extra spellings, in every method."""
    paths: set[str] = set(EXTRA_PATHS)
    for rule in rig.app.url_map.iter_rules():
        paths.add(_concrete(rule.rule))
    for _method, rule in remote_allowlist.ALLOWED:
        paths.add(_concrete(rule))
    for _method, rule in worker_allowlist.ALLOWED:
        paths.add("/insights" + _concrete(rule))
    return [(m, p) for p in sorted(paths) for m in METHODS]


def _allowed_by_table(rig, method: str, path: str) -> bool:
    route, _kw = rig.app._match(path, method)
    return route is not None and (("GET" if method == "HEAD" else method), route.rule) in VIEWER_ALLOWED


def _assert_refused(resp, method: str, path: str) -> None:
    assert resp.status_code in (302, 404), (method, path, resp.status_code)
    if method == "GET" and path.startswith("/gateway/static/") and resp.status_code == 404:
        return  # public for everyone before any session check; a name that is not a file is the router's own 404
    if resp.status_code == 302:
        assert resp.headers["Location"] == VIEWER_HOME, (method, path)
    else:
        assert json.loads(resp.get_data(as_text=True)) == json.loads(NOT_AVAILABLE_BODY), (method, path)
        assert resp.get_data() == NOT_AVAILABLE_BODY.encode(), (method, path)


# ---- C4: the table itself ----
def test_viewer_table_is_exactly_the_reviewed_set(rig):
    assert isinstance(VIEWER_ALLOWED, frozenset)
    assert VIEWER_ALLOWED == REVIEWED
    registered = {(m, r.rule) for r in rig.app.url_map.iter_rules() for m in r.methods}
    assert VIEWER_ALLOWED <= registered, sorted(VIEWER_ALLOWED - registered)
    # Derived from no other table: the module holds no reference to the planner, FI or gateway gate modules.
    for value in vars(viewer_routes).values():
        if isinstance(value, types.ModuleType):
            assert value.__name__ not in ("src.server.remote_allowlist", "financial_trends_reporter.worker_allowlist",
                                          "src.gateway.app"), value.__name__
    planner = {(m, r) for m, r in remote_allowlist.ALLOWED}
    assert not (VIEWER_ALLOWED & planner)
    assert not any(rule.startswith(("/insights", "/gateway/admin", "/api/auth/admin", "/gateway/users", "/api/share",
                                    "/gateway/sharing")) for _m, rule in VIEWER_ALLOWED)


# ---- C1: the gate branch ----
def test_every_route_outside_the_table_is_refused_for_a_viewer(rig):
    owner, owner_id = rig.signed_in("olive")
    viewer, _vid = rig.signed_in_viewer("vic", sponsor=owner_id)
    checked = 0
    for method, path in _all_targets(rig):
        if _allowed_by_table(rig, method, path):
            continue
        resp = viewer.request(method, path, json_body={"id": 1, "title": "x"} if method != "GET" else None)
        _assert_refused(resp, method, path)
        checked += 1
    assert checked > 400  # the sweep really covered the planner and FI tables
    assert rig.upstream.calls == []
    # The same walk as the member still reaches the upstream (the sweep is not vacuous).
    assert owner.get("/api/plans").status_code == 200 and rig.upstream.calls


def test_no_upstream_call_for_any_viewer_request(proxied):
    _owner, owner_id = proxied.signed_in("olive")
    viewer, _vid = proxied.signed_in_viewer("vic", sponsor=owner_id)
    for method, path in _all_targets(proxied):
        viewer.request(method, path, json_body={} if method != "GET" else None)
    # Every table route too, background poll or not.
    for method, rule in sorted(VIEWER_ALLOWED):
        viewer.request(method, _concrete(rule), json_body={} if method != "GET" else None,
                       headers={"X-Background-Poll": "1"})
    assert proxied.proxy.forwarded == []
    assert proxied.sup.calls == []


def test_unknown_kind_is_treated_as_a_viewer(rig, monkeypatch):
    _owner, owner_id = rig.signed_in("olive")
    member, _mid = rig.signed_in("mel")
    real = rig.store.get_session
    for odd in ("guest", "Member", "member ", "", None, "MISSING"):
        def fake(token, now, _odd=odd):
            sess = real(token, now)
            if sess is not None:
                if _odd == "MISSING":
                    sess.pop("kind", None)
                else:
                    sess["kind"] = _odd
            return sess
        monkeypatch.setattr(rig.store, "get_session", fake)
        for method, path in (("GET", "/api/plans"), ("GET", "/"), ("POST", "/api/plans/delete"),
                             ("GET", "/insights/api/history"), ("GET", "/gateway/admin")):
            _assert_refused(member.request(method, path, json_body={} if method != "GET" else None), method, path)
    assert rig.upstream.calls == []
    monkeypatch.setattr(rig.store, "get_session", real)
    assert member.get("/api/plans").status_code == 200  # an exact 'member' is still forwarded


def test_pending_and_must_change_viewers_never_reach_the_upstream(rig):
    _owner, owner_id = rig.signed_in("olive")
    rig.add_viewer("val", sponsor=owner_id)
    pending = rig.browser(ip="203.0.113.40")
    assert pending.login("val").status_code == 200
    for method, path in (("GET", "/api/plans"), ("GET", "/"), ("GET", "/api/viewer/shares")):
        assert pending.request(method, path).status_code in (302, 401)
    assert rig.upstream.calls == []


# ---- C2: the proxy refusal ----
def _req(path="/api/plans", method="GET") -> LocalRequest:
    return LocalRequest(method, path, HeaderMap({"Host": "x"}), b"", environ={})


def test_proxy_refuses_a_viewer_identity():
    sup = RecordingSupervisor()
    audited: list[tuple[str, int, str]] = []
    proxy = WorkerProxy(sup, BuildQueue(1), audit=lambda event, uid, details: audited.append((event, uid, details)))
    for kind in ("viewer", "guest", "", "Member"):
        resp = proxy.forward(_req(), Identity(7, "vic", "Vic", "user", kind))
        assert resp.status_code == 503
        assert "viewer" not in resp.get_data(as_text=True).lower()
    assert sup.calls == []
    assert [a[0] for a in audited] == ["viewer_forward_refused"] * 4 and all(a[1] == 7 for a in audited)
    # The default identity is a member and is still forwarded (to the supervisor, which then answers 503 here).
    proxy.forward(_req(), Identity(8, "mel", "Mel", "user"))
    assert sup.calls and sup.calls[0] == ("endpoint", 8)


# ---- C3: the supervisor refusal ----
class RecordingLauncher:
    def __init__(self) -> None:
        self.launched: list[int] = []

    def launch(self, spec):  # pragma: no cover - must never run for a viewer
        self.launched.append(spec.user_id)
        raise RuntimeError("no processes in this test")


class RecordingAccounts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def ensure(self, uid, workspace):
        self.calls.append(("ensure", uid))

    def disable(self, uid, disabled):
        self.calls.append(("disable", uid))

    def remove(self, uid, workspace):
        self.calls.append(("remove", uid))

    def housekeeping(self, known):
        self.calls.append(("housekeeping", len(known)))


def test_supervisor_never_provisions_a_viewer(tmp_path):
    rig = Rig(tmp_path, shared_views=True)
    owner_id = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner_id)
    launcher, accounts = RecordingLauncher(), RecordingAccounts()
    sup = Supervisor(SupervisorConfig(data_root=tmp_path / "data"), launcher, accounts=accounts,
                     is_member=rig.store.is_member)
    with pytest.raises(WorkerUnavailable):
        sup.endpoint(vid)
    with pytest.raises(PermissionError):
        sup.user_created(vid)
    with pytest.raises(PermissionError):
        sup._start(sup._slot(vid))
    sup.user_disabled(vid, True)
    sup.signed_out(vid, 0)
    for unknown in (999, vid + 1000):  # no such row: not a member either
        with pytest.raises(WorkerUnavailable):
            sup.endpoint(unknown)
    assert launcher.launched == [] and accounts.calls == []
    assert not (tmp_path / "data" / "users" / str(vid)).exists()
    # A member is still provisioned.
    sup.user_created(owner_id)
    assert ("ensure", owner_id) in accounts.calls and (tmp_path / "data" / "users" / str(owner_id)).is_dir()


# ---- C34 (selection): Phase 8's scheduler ----
def test_insights_scheduler_never_selects_a_viewer(tmp_path):
    rig = Rig(tmp_path, shared_views=True)
    owner_id = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner_id)
    s = sched.InsightsScheduler(supervisor=RecordingSupervisor(), list_users=rig.store.list_users,
                                session_count=lambda u, n: 0, cutoff=sched.parse_cutoff("17:30"),
                                audit=lambda *a: None, clock=lambda: rig.now[0])
    assert s.eligible_users(rig.now[0]) == [owner_id]
    assert vid not in s.eligible_users(rig.now[0])
    # Fail closed on rows without a kind, or with any kind other than exactly 'member'.
    odd = [{"id": 5, "disabled": False, "expired": False}, {"id": 6, "disabled": False, "expired": False, "kind": "x"},
           {"id": 7, "disabled": False, "expired": False, "kind": "member"}]
    s2 = sched.InsightsScheduler(supervisor=RecordingSupervisor(), list_users=lambda now: odd,
                                 session_count=lambda u, n: 0, cutoff=sched.parse_cutoff("17:30"),
                                 audit=lambda *a: None, clock=lambda: rig.now[0])
    assert s2.eligible_users(rig.now[0]) == [7]
