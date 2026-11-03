"""Verify-account route and the gate state carried on GET /api/cash."""
from datetime import date

import pytest

from src import cash_verified_accounts as cva, cash_view, cash_year_close as cyc
from src.server import app, plan_routes
from tests.test_cash_view_unit import ACCT, make


@pytest.fixture()
def client(tmp_path, monkeypatch):
    ws = make(tmp_path / "ws")
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    for mod in (cyc, cash_view, cva):
        monkeypatch.setattr(mod, "today", lambda: date(2027, 1, 8))
    return app.test_client()


def gate(client):
    return client.get("/api/cash?year=2027").get_json()["accounts"][0]["floor_gate"]


def test_verify_needs_a_closed_year_then_round_trips_and_is_audited(client, monkeypatch):
    events = []
    monkeypatch.setattr(plan_routes, "_audit", lambda e, d=None: events.append((e, d)))
    assert gate(client) == {"verified": False, "eligible": False, "reason": "not verified against a closed year"}
    bad = client.post("/api/cash/verify-account", json={"account": ACCT})
    assert bad.status_code == 400 and "closed year" in bad.get_json()["error"] and events == []
    assert client.post("/api/cash/year-close", json={"year": 2026, "action": "close", "straddles_seen": True}).status_code == 200
    ok = client.post("/api/cash/verify-account", json={"account": ACCT})
    assert ok.status_code == 200 and ok.get_json()["verified"] is True
    assert events[-1] == ("cash_account_verified", {"account": ACCT}) and gate(client)["verified"] is True
    off = client.post("/api/cash/verify-account", json={"account": ACCT, "verified": False})
    assert off.get_json()["verified"] is False and events[-1][0] == "cash_account_unverified"


def test_verify_rejects_missing_or_unknown_accounts(client):
    assert client.post("/api/cash/verify-account", json={}).status_code == 400
    assert client.post("/api/cash/verify-account", json={"account": "Nobody"}).status_code == 400
