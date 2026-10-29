"""Plan step 1.4: the /api/sales routes (against a scratch workspace, not the shared test plan)."""
from __future__ import annotations

import pytest

from src import active_plan
from src.server import app, plan_routes

CSV = ("sale_date,account,tax_class,symbol,shares,proceeds,fees,basis,purchase_date\n"
       "2026-07-01,Trust,taxable,VXUS,5,500,0,400,2024-01-02\n")
ROW = dict(sale_date="2026-06-10", account="Trust", tax_class="taxable", symbol="vti", shares=10,
           proceeds=2000, fees=5, basis=1500, purchase_date="2025-01-02")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: tmp_path / "input")
    return app.test_client()


def test_add_list_void_roundtrip(client):
    r = client.post("/api/sales", json=ROW)
    assert r.status_code == 200 and r.get_json()["sale"]["gain"] == pytest.approx(495.0)
    sale_id = r.get_json()["sale"]["sale_id"]
    listed = client.get("/api/sales?year=2026").get_json()
    assert listed["success"] and len(listed["sales"]) == 1 and listed["totals"]["long_gain"] == pytest.approx(495.0)
    assert client.post(f"/api/sales/{sale_id}/void").status_code == 200
    assert client.get("/api/sales").get_json()["sales"] == []
    assert len(client.get("/api/sales?include_voided=1").get_json()["sales"]) == 1
    assert client.post(f"/api/sales/{sale_id}/unvoid").status_code == 200
    assert len(client.get("/api/sales").get_json()["sales"]) == 1


def test_bad_row_is_a_400_with_the_reason(client):
    r = client.post("/api/sales", json={**ROW, "shares": 0})
    assert r.status_code == 400 and not r.get_json()["success"] and "shares" in r.get_json()["error"]


def test_bad_year_is_a_400(client):
    assert client.get("/api/sales?year=abc").status_code == 400


def test_void_unknown_sale_is_a_400(client):
    assert client.post("/api/sales/999/void").status_code == 400


def test_csv_preview_then_commit(client):
    p = client.post("/api/sales/import/preview", json={"content": CSV}).get_json()
    assert p["success"] and p["received"] == 1 and len(p["will_write"]) == 1
    assert client.get("/api/sales").get_json()["sales"] == []
    c = client.post("/api/sales/import/commit", json={"content": CSV})
    assert c.status_code == 200 and c.get_json()["written"] == 1
    assert client.post("/api/sales/import/commit", json={"content": CSV}).get_json()["written"] == 0


def test_csv_commit_with_errors_is_a_400(client):
    r = client.post("/api/sales/import/commit", json={"content": CSV + "bad,row\n"})
    assert r.status_code == 400 and client.get("/api/sales").get_json()["sales"] == []


def test_tax_year_summary_carryforward_and_wash_routes(client):
    loss = {**ROW, "proceeds": 1000, "basis": 1400}
    assert client.post("/api/sales", json=loss).status_code == 200
    out = client.get("/api/sales/tax-year?year=2026").get_json()
    assert out["success"] and out["netting"]["net_lt"] == pytest.approx(-405.0) and out["wash"]["count"] == 0
    r = client.post("/api/sales/carryforward", json={"year": 2026, "carryforward_short": 100, "carryforward_long": 200})
    assert r.status_code == 200 and r.get_json()["carryforward_long"] == 200.0
    out = client.get("/api/sales/tax-year?year=2026").get_json()
    assert out["carryforward_in"] == {"short": 100.0, "long": 200.0, "entered": True}
    r = client.post("/api/sales/wash/refresh")
    assert r.status_code == 200 and r.get_json() == {"success": True, "flagged": 0, "updated": 0}


def test_tax_year_routes_reject_bad_input(client):
    assert client.get("/api/sales/tax-year").status_code == 400
    assert client.get("/api/sales/tax-year?year=abc").status_code == 400
    r = client.post("/api/sales/carryforward", json={"year": 2026, "carryforward_short": -1, "carryforward_long": 0})
    assert r.status_code == 400 and "zero or more" in r.get_json()["error"]
