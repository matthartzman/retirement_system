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
    assert len(by_id(r)) == 13


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


def test_route_carries_the_five_tax_filing_steps_with_derived_states(client):
    steps = by_id(client.get("/api/year-end?year=2026"))
    tax = ["clear_sales_queue", "resolve_log_drift", "run_wash_check", "tie_1099b", "confirm_carryforward"]
    assert all(k in steps for k in tax)
    assert all(steps[k]["link"] == "sales_ledger" and steps[k]["hash"].startswith("#sales_ledger?") for k in tax)
    assert steps["clear_sales_queue"]["state"] == "done" and steps["tie_1099b"]["state"] == "done"
    assert steps["run_wash_check"]["state"] == "done"          # the broker import ran the automatic scan
    assert steps["confirm_carryforward"]["state"] == "open"


def test_wash_step_reopens_when_the_inputs_change_without_a_rescan(client, tmp_path):
    from src import active_plan
    with active_plan.workspace_store(tmp_path / "ws", write=True) as store:
        rows = store.dataset("holdings").rows()
        store.dataset("holdings").replace_all(rows + [{"account": "Joint_taxable", "symbol": "VTI", "purchase_date": "2026-06-12",
                                                       "shares": "1", "purchase_price": "100", "lot_type": "buy", "note": ""}])
    s = by_id(client.get("/api/year-end?year=2026"))["run_wash_check"]
    assert s["state"] == "open" and "since the ledger changed" in s["detail"]


def test_a_failing_gather_falls_back_to_the_safe_default(client, monkeypatch, caplog):
    from src import transactions
    monkeypatch.setattr(transactions, "started", lambda store: (_ for _ in ()).throw(RuntimeError("boom")))
    r = client.get("/api/year-end?year=2026")
    assert r.status_code == 200 and by_id(r)["resolve_log_drift"]["state"] == "done"
    assert "boom" in caplog.text


def test_derived_steps_cannot_be_confirmed_by_hand(client):
    assert client.post("/api/year-end/confirm", json={"year": 2026, "step": "close_cash_year"}).status_code == 400
    assert client.post("/api/year-end/confirm", json={"year": "2026", "step": "personal_numbers"}).status_code == 400
