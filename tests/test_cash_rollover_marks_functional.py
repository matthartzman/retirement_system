"""Rollover-mark route and its effect on the ledger and the withdrawal totals."""
from datetime import date

import pytest

from src import active_plan, cash_rollover_marks as crm, cash_view
from src.server import app, plan_routes
from tests.test_cash_view_unit import ACCT, make


@pytest.fixture()
def client(tmp_path, monkeypatch):
    ws = make(tmp_path / "ws")
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    monkeypatch.setattr(plan_routes, "_audit", lambda e, d=None: None)
    return app.test_client(), ws


def test_bad_body_and_unknown_row_are_400(client):
    c, _ = client
    assert c.post("/api/cash/rollover-mark", json={}).status_code == 400
    assert c.post("/api/cash/rollover-mark", json={"account": ACCT, "date": "2026-01-01", "amount": -1.0}).status_code == 400
    assert c.post("/api/cash/rollover-mark", json={"account": "Nobody", "date": "2026-01-01", "amount": -1.0}).status_code == 400


def test_mark_and_unmark_round_trip_through_the_ledger_view(client, monkeypatch):
    c, ws = client

    def crafted(store, accounts, *, marks=True):      # the fixture file has no outgoing cash row: supply one
        led = {a: [{"date": "2026-04-07", "class": "transfer_out", "amount": -355000.0, "counts": True, "in_kind": False,
                    "pair_status": "external_withdrawal", "source": "broker", "description": "", "cash_balance": None,
                    "partner_account": None, "needs_review": False}] for a in accounts}
        if marks:
            crm.apply(store, led)
        return led
    monkeypatch.setattr(cash_view, "_ledgers", crafted)
    body = {"account": ACCT, "date": "2026-04-07", "amount": -355000.0}
    ok = c.post("/api/cash/rollover-mark", json=body)
    assert ok.status_code == 200 and ok.get_json()["marked"] is True
    with active_plan.workspace_store(ws) as store:
        assert [x["pair_status"] for x in cash_view.ledger_view(store, ACCT)["rows"]] == [crm.STATUS]
    c.post("/api/cash/rollover-mark", json={**body, "marked": False})
    with active_plan.workspace_store(ws) as store:
        assert [x["pair_status"] for x in cash_view.ledger_view(store, ACCT)["rows"]] == ["external_withdrawal"]
