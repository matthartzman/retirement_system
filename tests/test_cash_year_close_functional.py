"""Cash-year close routes: GET status, POST close / reopen with audit, permission and input checks."""
from datetime import date

import pytest

from src import cash_view, cash_year_close as cyc
from src.server import app, plan_routes
from tests.test_cash_view_unit import make


@pytest.fixture()
def client(tmp_path, monkeypatch):
    ws = make(tmp_path / "ws")
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    monkeypatch.setattr(cyc, "today", lambda: date(2027, 1, 8))
    monkeypatch.setattr(cash_view, "today", lambda: date(2027, 1, 8))
    return app.test_client()


def test_status_reports_blockers_or_allows_and_validates_year(client):
    assert client.get("/api/cash/year-close?year=abc").status_code == 400
    st = client.get("/api/cash/year-close?year=2026").get_json()
    assert st["success"] and st["year"] == 2026 and st["closed"] is False and "allowed" in st


def test_close_and_reopen_round_trip_through_the_view(client, monkeypatch):
    events = []
    monkeypatch.setattr(plan_routes, "_audit", lambda e, d=None: events.append((e, d)))
    bad = client.post("/api/cash/year-close", json={"year": "2026", "action": "close"})
    assert bad.status_code == 400
    assert client.post("/api/cash/year-close", json={"year": 2026, "action": "nope"}).status_code == 400
    r = client.post("/api/cash/year-close", json={"year": 2026, "action": "close", "note": "ok", "straddles_seen": True})
    assert r.get_json()["closed"] is True and r.get_json()["note"] == "ok" and events == [("cash_year_closed", {"year": 2026})]
    assert client.get("/api/cash?year=2026").get_json()["comparison"]["closed"] is True
    assert client.post("/api/cash/year-close", json={"year": 2026, "action": "close"}).status_code == 400
    assert client.post("/api/cash/year-close", json={"year": 2026, "action": "reopen"}).get_json()["closed"] is False
    assert events[-1] == ("cash_year_reopened", {"year": 2026})
