"""The worker's share-snapshot route (Phase 9, design 5.3-5.4): projection by construction, the desktop's percent
pipeline, the leak check, no error text, the active-plan rule. Controls C18, C19, C21, C22 (worker side), C23.

Runs FI in worker mode over the conftest workspace (the same set-up as test_insights_worker_mode_functional.py).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from financial_trends_reporter import percent_view, projections, share_snapshot, worker_mode
from financial_trends_reporter.main import create_app
from financial_trends_reporter.share_snapshot import PUBLISH_HEADER, route_plan, scope_ranges
from src import plan_registry, platform_runtime
from tests.test_insights_worker_mode_functional import ROWS, _put_balances, call, worker, ws  # noqa: F401

SID = "0123456789abcdef0123456789abcdef"
ALL = ["live", "trends", "projections"]
NEVER = ("/api/spending/transactions", "/api/accounts", "/api/app-accounts", "/api/run-status", "/api/whoami",
         "/api/account", "/api/account-prefs", "/api/passthrough-decision", "/api/run-now")


# Quotes and closes would go to the network; the snapshot's logic does not depend on them.
VOLATILE = ("as_of", "quotes_age_seconds")


@pytest.fixture(autouse=True)
def _no_market_data(monkeypatch):
    from src import market_data  # noqa: PLC0415

    monkeypatch.setattr(market_data, "quote_details", lambda symbols, *a, **k: {})
    monkeypatch.setattr(market_data, "daily_closes", lambda *a, **k: {})


def _steady(obj):
    """Drop the fields of a live snapshot that change from one call to the next."""
    if isinstance(obj, dict):
        return {k: _steady(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [_steady(v) for v in obj]
    return obj


def snap(app, views=ALL, money_view="dollars", plan_id=None, header=True, rev=1):
    body = {"share_id": SID, "scope_rev": rev, "money_view": money_view, "views": list(views),
            "expected_plan_id": plan_id if plan_id is not None else plan_registry.active_plan_id()}
    hdrs = {"Host": "127.0.0.1:1", "Content-Type": "application/json"}
    if header:
        hdrs[PUBLISH_HEADER] = "1"
    resp = app.handle_http("POST", "/api/share-snapshot", hdrs, json.dumps(body).encode())
    try:
        return resp.status_code, json.loads(resp.get_data())
    except ValueError:
        return resp.status_code, resp.get_data()


def _plan_sha() -> str:
    return hashlib.sha256(plan_registry.active_plan_file().read_bytes()).hexdigest()


def test_record_holds_only_the_granted_views(worker):
    status, rec = snap(worker, views=["trends"])
    assert status == 200, rec
    assert set(rec) == share_snapshot.TOP_LEVEL_KEYS
    assert rec["schema"] == "shared_view/1" and rec["share_id"] == SID and rec["scope_rev"] == 1
    assert list(rec["views"]) == ["trends"]
    expected = route_plan(["trends"], rec["scopes"], date.fromisoformat(rec["scopes"]["all"]["to"]))
    assert set(rec["views"]["trends"]) == {k for k, _t in expected["trends"]}
    assert set(rec["scopes"]) == set(share_snapshot.SCOPES)
    status, rec = snap(worker, views=["projections"])
    assert list(rec["views"]) == ["projections"] and list(rec["views"]["projections"]) == ["/api/projections"]
    status, rec = snap(worker, views=["live"])
    keys = set(rec["views"]["live"])
    assert all(k.startswith(("/api/live-snapshot?scope=", "/api/realized?tax_year=")) for k in keys)


def test_transactions_and_settings_are_never_included(worker):
    _put_balances(ROWS)
    for mv in ("dollars", "percent"):
        status, rec = snap(worker, money_view=mv)
        assert status == 200, rec
        for panel in rec["views"].values():
            for key in panel:
                assert key.split("?", 1)[0] not in NEVER, key


def test_percent_record_equals_the_desktop_percent_bodies(worker, ws):
    _put_balances(ROWS)
    status, rec = snap(worker, money_view="percent")
    assert status == 200, rec
    app = create_app(ws, mode="worker")
    # The desktop basis (main.py): balances, history and the plan's annuity values. Recompute it the same way.
    from financial_trends_reporter import plan_annuity_values  # noqa: PLC0415
    from financial_trends_reporter.main import read_history  # noqa: PLC0415

    db = worker_mode.insights_dir() / "monarch_balances.sqlite3"
    k = percent_view.scale_basis(db, read_history(worker_mode.log_path()), plan_annuity_values.account_values(ws, db))
    assert k and k > 0
    plan = route_plan(ALL, rec["scopes"], date.fromisoformat(rec["basis_date"]))
    checked = 0
    for view, items in plan.items():
        for key, target in items:
            stored = rec["views"][view][key]
            if stored == {"available": False}:
                continue
            code, dollars = call(worker_mode.WorkerListenerApp(app), "GET", target)
            assert code == 200
            desktop = json.loads(json.dumps(percent_view.percent_body(key.split("?", 1)[0], dollars, k)))
            assert _steady(stored) == _steady(desktop), key
            checked += 1
    assert checked >= 10
    assert percent_view.find_money_leaks(rec["views"]) == []


def test_leak_fails_the_publish(worker, monkeypatch):
    _put_balances(ROWS)
    monkeypatch.setattr(share_snapshot.percent_view, "percent_body", lambda route, payload, k: payload)  # unscaled
    status, body = snap(worker, money_view="percent")
    assert status == 422 and body == {"success": False, "error": "money_leak"}


def test_percent_without_a_basis_is_refused(worker):
    status, body = snap(worker, money_view="percent")  # no balances imported in this workspace
    assert status == 409 and body["error"] == "no_basis"


def test_a_failing_route_is_marked_unavailable_without_its_error_text(worker, monkeypatch, ws):
    secret = f"boom at {ws} line 42"

    def broken(_ws):
        raise RuntimeError(secret)
    monkeypatch.setattr(projections, "load", broken)
    status, rec = snap(worker, views=["projections"])
    assert status == 200
    assert rec["views"]["projections"]["/api/projections"] == {"available": False}
    text = json.dumps(rec)
    assert "boom" not in text and "RuntimeError" not in text and "line 42" not in text


def test_record_holds_no_server_path(worker, ws):
    _put_balances(ROWS)
    status, rec = snap(worker, money_view="dollars")
    assert status == 200
    text = json.dumps(rec)
    for needle in (str(ws), str(platform_runtime.workspace_root()), str(ws).replace("\\", "\\\\")):
        assert needle not in text


def test_other_active_plan_is_refused(worker):
    before = _plan_sha()
    status, body = snap(worker, plan_id="some-other-plan-id")
    assert status == 410 and body["error"] == "plan_missing"  # not registered at all
    assert _plan_sha() == before


def test_only_the_gateway_header_reaches_the_route(worker):
    status, body = snap(worker, header=False)
    assert status == 404
    bad = {"share_id": "not-hex", "scope_rev": 1, "money_view": "dollars", "views": ["trends"],
           "expected_plan_id": plan_registry.active_plan_id()}
    resp = worker.handle_http("POST", "/api/share-snapshot", {"Host": "127.0.0.1:1", PUBLISH_HEADER: "1",
                                                               "Content-Type": "application/json"},
                              json.dumps(bad).encode())
    assert resp.status_code == 400
    for views in ([], ["accounts"], ["trends", "trends"]):
        assert snap(worker, views=views)[0] == 400


def test_plan_file_is_unchanged_by_a_snapshot(worker):
    _put_balances(ROWS)
    before = _plan_sha()
    for mv in ("dollars", "percent"):
        assert snap(worker, money_view=mv)[0] == 200
    assert _plan_sha() == before


@pytest.mark.parametrize("anchor,expected", [
    ("2026-03-31", {"month": "2026-02-28", "week": "2026-03-24", "ytd": "2026-01-01", "1y": "2025-03-31"}),
    ("2024-02-29", {"1y": "2023-02-28", "3m": "2023-11-29", "6m": "2023-08-29"}),
])
def test_scope_ranges_follow_the_page(anchor, expected):
    r = scope_ranges(date.fromisoformat(anchor))
    for sc, start in expected.items():
        assert r[sc] == {"from": start, "to": anchor}
    assert r["all"]["from"] == "2025-02-01"
