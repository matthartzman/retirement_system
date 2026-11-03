"""Year-end checklist routes: GET the derived steps, POST a confirmation (audited), input checks."""
from datetime import date

import pytest

from src import cash_view, cash_year_close as cyc, year_end
from src.server import app, plan_routes
from tests.test_cash_view_unit import make


@pytest.fixture()
def client(tmp_path, monkeypatch):
    ws = make(tmp_path / "ws")
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    for mod in (year_end, cyc, cash_view):
        monkeypatch.setattr(mod, "today", lambda: date(2027, 1, 8))
    return app.test_client()


def by_id(resp):
    return {s["id"]: s for s in resp.get_json()["steps"]}


def test_checklist_defaults_to_the_year_that_just_ended_and_validates_year(client):
    assert client.get("/api/year-end?year=abc").status_code == 400
    r = client.get("/api/year-end")
    assert r.get_json()["success"] and r.get_json()["year"] == 2026 and r.get_json()["in_season"] is True
    assert len(by_id(r)) == 8


def test_closing_the_year_flips_the_close_step_and_confirmation_round_trips(client, monkeypatch):
    events = []
    monkeypatch.setattr(plan_routes, "_audit", lambda e, d=None: events.append((e, d)))
    assert by_id(client.get("/api/year-end?year=2026"))["close_cash_year"]["state"] == "open"
    assert client.post("/api/cash/year-close", json={"year": 2026, "action": "close", "straddles_seen": True}).status_code == 200
    assert by_id(client.get("/api/year-end?year=2026"))["close_cash_year"]["state"] == "done"
    r = client.post("/api/year-end/confirm", json={"year": 2026, "step": "personal_numbers", "confirmed": True})
    assert by_id(r)["personal_numbers"]["state"] == "done" and events[-1] == ("year_end_step_confirmed", {"year": 2026, "step": "personal_numbers"})
    r = client.post("/api/year-end/confirm", json={"year": 2026, "step": "personal_numbers", "confirmed": False})
    assert by_id(r)["personal_numbers"]["state"] == "open"


def test_derived_steps_cannot_be_confirmed_by_hand(client):
    assert client.post("/api/year-end/confirm", json={"year": 2026, "step": "close_cash_year"}).status_code == 400
    assert client.post("/api/year-end/confirm", json={"year": "2026", "step": "personal_numbers"}).status_code == 400
