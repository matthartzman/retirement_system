"""Financial Insights guests are view-only (security review F-01) and never see server error detail (F-05).

Contract: every POST route is classified owner-only or guest-writable. Functional: percent and dollar guests are refused
the owner-only writes and the balances database is unchanged; the owner's local listener still writes.
"""
from __future__ import annotations

import sqlite3

import pytest

from financial_trends_reporter import balance_store
from financial_trends_reporter.access_routes import GUEST_WRITABLE_POST, OWNER_ONLY_POST, READ_ONLY_REFUSED
from tests.test_trends_access_gate_functional import Rig

_BODIES = {
    "/api/account": {"account_key": "Brokerage", "type": "Loan", "app_account": "HACKED"},
    "/api/account-prefs": {"items": [{"account_key": "Brokerage", "include": False}]},
    "/api/passthrough-decision": {"key": "a|b", "decision": "approve"},
    "/api/run-now": {},
    "/api/run-cancel": {},
}


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path, test_routes=True)


def _post_rules(rig) -> set[str]:
    return {r.rule for r in rig.app.routes if "POST" in r.methods and r.rule.startswith("/api/")}


def test_every_post_route_is_owner_only_or_guest_writable(rig):
    rules = _post_rules(rig)
    assert not OWNER_ONLY_POST & GUEST_WRITABLE_POST
    assert rules - OWNER_ONLY_POST - GUEST_WRITABLE_POST == set(), "a new POST route must be classified owner-only or guest-writable"
    assert (OWNER_ONLY_POST | GUEST_WRITABLE_POST) - rules == set(), "a classified POST rule no longer exists"


@pytest.mark.parametrize("money_view", ["percent", "dollars"])
def test_guests_are_refused_every_owner_only_write_and_nothing_changes(rig, tmp_path, money_view):
    uid = rig.add("ann", money_view=money_view)
    rig.store.set_grant(uid, "insights", money_view=money_view, views=None, now=rig.now[0], bump=False)
    _, token = rig.signin()
    before = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    for rule in sorted(OWNER_ONLY_POST):
        resp = rig.call(rig.remote, "POST", rule, _BODIES[rule], cookie=token)
        assert resp.status_code == 403, rule
        assert resp.get_json()["error"] in (READ_ONLY_REFUSED, "Something went wrong. Try again later.")
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == before  # no balances db, decisions file or run
    assert rig.call(rig.remote, "PUT", "/api/account", _BODIES["/api/account"], cookie=token).status_code in (403, 404, 405)


def test_owner_local_listener_can_still_write(rig):
    resp = rig.call(rig.local, "POST", "/api/passthrough-decision", _BODIES["/api/passthrough-decision"])
    assert resp.status_code == 200


def test_guest_writable_routes_stay_open(rig):
    rig.add("ann", money_view="dollars")
    _, token = rig.signin()
    assert rig.call(rig.remote, "POST", "/api/ping", {"idle_ms": 0}, cookie=token).status_code == 200
    assert rig.call(rig.remote, "POST", "/api/view", {"view": "trends"}, cookie=token).status_code == 200
    assert rig.call(rig.remote, "POST", "/api/signout", {}, cookie=token).status_code == 200


def test_dollar_guest_account_write_leaves_database_unchanged(rig, tmp_path):
    db = tmp_path / balance_store.DB_FILENAME  # beside log.jsonl, where the app looks
    rows = [("2026-11-20", "Brokerage", "Brokerage", 1000.0)]
    balance_store.import_balance_rows(db, rows, "t")
    rig.add("ann", money_view="dollars")
    _, token = rig.signin()
    def dump():
        with sqlite3.connect(db) as c:
            return c.execute("SELECT * FROM accounts").fetchall()
    before = dump()
    assert rig.call(rig.remote, "POST", "/api/account", _BODIES["/api/account"], cookie=token).status_code == 403
    assert dump() == before


@pytest.mark.parametrize("money_view", ["percent", "dollars"])
def test_remote_500_is_generic_with_an_error_id(rig, money_view, caplog):
    rig.add("ann", money_view=money_view)
    _, token = rig.signin()
    resp = rig.call(rig.remote, "GET", "/api/test-money-raises", cookie=token)
    body = resp.get_json()
    text = resp.get_data(as_text=True)
    assert resp.status_code == 500
    assert "RuntimeError" not in text and "$1,234" not in text and "failed on" not in text
    if money_view == "dollars":
        assert body["error_id"] and body["error"] == "Something went wrong. Try again later."


def test_owner_local_500_stays_verbose(rig):
    resp = rig.call(rig.local, "GET", "/api/test-money-raises")
    assert resp.status_code == 500 and "RuntimeError" in resp.get_data(as_text=True)
