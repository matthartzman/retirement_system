"""A Financial Insights grant that lists its tabs is refused every data route of the tabs it leaves out.

Finding F1 of the Phase 9 shared-view security review: the tab limit used to hide tabs in the page only, so a guest
granted Trends could still read the Snapshot, Realized and Projections data by URL. The remote gate now refuses those
routes (``access_routes.VIEW_ROUTES``); the owner's local listener and worker mode are unchanged.
"""
from __future__ import annotations

import pytest

from financial_trends_reporter.access_routes import INSIGHTS_VIEWS, TAB_FREE_ROUTES, VIEW_REFUSED, VIEW_ROUTES
from financial_trends_reporter.passthrough_decisions import decisions_path_for_log
from tests.test_trends_access_gate_functional import Rig

# A body each tab-owned POST route accepts, so a refusal comes from the gate and an allowed call reaches the route.
_POST_BODIES = {
    "/api/account-prefs": {"items": []},
    "/api/passthrough-decision": {"key": "a|b", "decision": "approve"},
}


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def _methods(rig) -> dict[str, str]:
    """Rule -> the method to call it with (GET where the route has one)."""
    return {r.rule: ("GET" if "GET" in r.methods else sorted(r.methods)[0]) for r in rig.app.routes}


def _guest(rig, views, money_view="dollars", name="ann"):
    uid = rig.add(name, money_view=money_view)
    rig.store.set_grant(uid, "insights", money_view=money_view, views=views, now=rig.now[0], bump=False)
    resp, token = rig.signin(name)
    assert resp.status_code == 200 and token
    return token


def _call(rig, listener, rule, methods, token=None):
    method = methods[rule]
    return rig.call(listener, method, rule, _POST_BODIES.get(rule) if method == "POST" else None, cookie=token)


def _refused(resp) -> bool:
    return resp.status_code == 403 and (resp.get_json() or {}).get("error") == VIEW_REFUSED


def test_every_api_rule_is_classified_exactly_once(rig):
    rules = {r.rule for r in rig.app.routes if r.rule.startswith("/api/")}
    assert not set(VIEW_ROUTES) & TAB_FREE_ROUTES
    assert rules - set(VIEW_ROUTES) - TAB_FREE_ROUTES == set(), "a new /api/ route needs a tab or a TAB_FREE_ROUTES entry"
    assert (set(VIEW_ROUTES) | TAB_FREE_ROUTES) - rules == set(), "a classified rule no longer exists"
    assert set(VIEW_ROUTES.values()) == set(INSIGHTS_VIEWS)


@pytest.mark.parametrize("tab", INSIGHTS_VIEWS)
def test_a_one_tab_grant_reaches_only_that_tabs_routes(rig, tab):
    token = _guest(rig, [tab])
    methods = _methods(rig)
    for rule, owner in sorted(VIEW_ROUTES.items()):
        resp = _call(rig, rig.remote, rule, methods, token)
        assert _refused(resp) == (owner != tab), f"{rule} ({owner} tab) for a {tab}-only grant: {resp.status_code}"


def test_the_f1_reproduction_is_refused(rig):
    # Before the fix: 403 on the /api/view report, but 200 on each of these.
    token = _guest(rig, ["trends"])
    assert rig.call(rig.remote, "POST", "/api/view", {"view": "projections"}, cookie=token).status_code == 403
    for path in ("/api/projections", "/api/live-snapshot", "/api/live-snapshot?refresh=1", "/api/realized"):
        assert _refused(rig.call(rig.remote, "GET", path, cookie=token)), path
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200


def test_other_spellings_of_a_refused_route_get_no_data(rig):
    token = _guest(rig, ["trends"])
    assert rig.call(rig.remote, "HEAD", "/api/projections", cookie=token).status_code == 403
    for path in ("/api/projections/", "/API/projections", "/api//projections"):
        assert rig.call(rig.remote, "GET", path, cookie=token).status_code in (403, 404), path


def test_a_grant_without_a_tab_list_reaches_every_tab(rig):
    token = _guest(rig, None)
    methods = _methods(rig)
    for rule in sorted(VIEW_ROUTES):
        assert not _refused(_call(rig, rig.remote, rule, methods, token)), rule


def test_tab_free_routes_stay_open_to_a_limited_grant(rig):
    token = _guest(rig, ["projections"])
    methods = _methods(rig)
    for rule in sorted(TAB_FREE_ROUTES - {"/api/signin", "/api/signout", "/api/exit"}):
        assert not _refused(_call(rig, rig.remote, rule, methods, token)), rule


def test_a_refused_write_changes_nothing_and_is_not_logged(rig, tmp_path):
    token = _guest(rig, ["projections"])
    resp = rig.call(rig.remote, "POST", "/api/passthrough-decision", _POST_BODIES["/api/passthrough-decision"], cookie=token)
    assert _refused(resp)
    assert not decisions_path_for_log(tmp_path / "log.jsonl").exists()
    assert "passthrough decision" not in [e["event"] for e in rig.store.read_events(person="Ann")]


def test_a_percent_guest_is_refused_the_same_routes(tmp_path):
    rig = Rig(tmp_path, percent_basis=lambda: 1000.0)
    token = _guest(rig, ["trends"], money_view="percent")
    for path in ("/api/projections", "/api/live-snapshot", "/api/realized"):
        # The percent view replaces every error body with its generic text; the status stays the gate's.
        assert rig.call(rig.remote, "GET", path, cookie=token).status_code == 403, path
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200


def test_the_owner_on_the_local_listener_is_never_tab_limited(rig):
    methods = _methods(rig)
    for rule in sorted(VIEW_ROUTES):
        assert not _refused(_call(rig, rig.local, rule, methods)), rule
