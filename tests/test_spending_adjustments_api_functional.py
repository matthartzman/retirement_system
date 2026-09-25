"""#335: /api/spending-adjustments reads and replaces the Cashflow /
Spending Adjustments adj_N_* rows in client_spending.csv."""
import csv

import pytest

import src.server.plan_routes as plan_routes
from src.server import app
from src.spending_adjustments import Adjustment, load_adjustments


@pytest.fixture
def spending_csv(tmp_path, monkeypatch):
    path = tmp_path / "client_spending.csv"
    path.write_text(
        "section,subsection,label,value,units,notes\n"
        "Cashflow,Spending,annual_spending_base_year,90000,USD,\n"
        "Cashflow,Mortgage,monthly_payment,2000,USD,\n", encoding="utf-8")
    monkeypatch.setattr(plan_routes, "_client_section_path", lambda *a, **k: path)
    monkeypatch.setattr(plan_routes, "_audit", lambda *a, **k: None)
    return path


def _sectioned(path):
    out: dict = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0] == "Cashflow":
                out.setdefault(r[1], {})[r[2]] = r[3]
    return out


def test_add_edit_delete_round_trip(spending_csv):
    client = app.test_client()
    assert client.get("/api/spending-adjustments").get_json()["adjustments"] == []

    rows = [{"category": "dining", "start_year": "2035", "end_year": "", "change_pct": "-20"},
            {"category": "ALL:Travel", "start_year": "2038", "end_year": "2045", "change_pct": "-50"}]
    resp = client.post("/api/spending-adjustments", json={"adjustments": rows})
    assert resp.status_code == 200 and resp.get_json()["count"] == 2
    assert client.get("/api/spending-adjustments").get_json()["adjustments"] == rows
    assert load_adjustments(_sectioned(spending_csv)) == [
        Adjustment("dining", 2035, None, -0.20), Adjustment("ALL:Travel", 2038, 2045, -0.50)]
    # Other rows untouched.
    assert _sectioned(spending_csv)["Mortgage"]["monthly_payment"] == "2000"

    # Edit + delete: post the shortened list; stale adj_2_* rows are removed.
    client.post("/api/spending-adjustments", json={"adjustments": [dict(rows[0], change_pct="-25")]})
    section = _sectioned(spending_csv)["Spending Adjustments"]
    assert section["adj_1_change_pct"] == "-25"
    assert not any(k.startswith("adj_2_") for k in section)

    client.post("/api/spending-adjustments", json={"adjustments": []})
    assert "Spending Adjustments" not in _sectioned(spending_csv)


@pytest.mark.parametrize("bad", [
    {"category": "", "start_year": "2030", "change_pct": "-10"},
    {"category": "dining", "start_year": "20x0", "change_pct": "-10"},
    {"category": "dining", "start_year": "2030", "end_year": "2029", "change_pct": "-10"},
    {"category": "dining", "start_year": "2030", "change_pct": "-100"},
    {"category": "ALL:Business", "start_year": "2030", "change_pct": "-10"},
])
def test_invalid_rows_are_rejected(spending_csv, bad):
    resp = app.test_client().post("/api/spending-adjustments", json={"adjustments": [bad]})
    assert resp.status_code == 400
    assert "Spending Adjustments" not in _sectioned(spending_csv)
