"""#335: /api/spending-adjustments reads and replaces the Cashflow /
Spending Adjustments adj_N_* rows of the plan (plan_rows; WP4.4b)."""
import pytest

import src.server.app_core as app_core
from src.server import app
from src.spending_adjustments import Adjustment, load_adjustments
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    return plan


def _cashflow(ws):
    return ws.store_data()["Cashflow"]


def test_add_edit_delete_round_trip(ws):
    client = app.test_client()
    mortgage = dict(_cashflow(ws)["Mortgage"])
    assert client.get("/api/spending-adjustments").get_json()["adjustments"] == []

    rows = [{"category": "dining", "start_year": "2035", "end_year": "", "change_pct": "-20"},
            {"category": "ALL:Travel", "start_year": "2038", "end_year": "2045", "change_pct": "-50"}]
    resp = client.post("/api/spending-adjustments", json={"adjustments": rows}, headers=HEADERS)
    assert resp.status_code == 200 and resp.get_json()["count"] == 2
    assert client.get("/api/spending-adjustments").get_json()["adjustments"] == rows
    assert load_adjustments(_cashflow(ws)) == [
        Adjustment("dining", 2035, None, -0.20), Adjustment("ALL:Travel", 2038, 2045, -0.50)]
    # Other rows untouched.
    assert _cashflow(ws)["Mortgage"] == mortgage

    # Edit + delete: post the shortened list; stale adj_2_* rows are removed. The edited row keeps its id.
    with ws.store(readonly=True) as store:
        row_id = next(r["row_id"] for r in store.rows("Cashflow") if r["label"] == "adj_1_change_pct")
    client.post("/api/spending-adjustments", json={"adjustments": [dict(rows[0], change_pct="-25")]}, headers=HEADERS)
    section = _cashflow(ws)["Spending Adjustments"]
    assert section["adj_1_change_pct"] == "-25"
    assert not any(k.startswith("adj_2_") for k in section)
    with ws.store(readonly=True) as store:
        assert store.get_row(row_id)["value"] == "-25"

    client.post("/api/spending-adjustments", json={"adjustments": []}, headers=HEADERS)
    assert "Spending Adjustments" not in _cashflow(ws)


@pytest.mark.parametrize("bad", [
    {"category": "", "start_year": "2030", "change_pct": "-10"},
    {"category": "dining", "start_year": "20x0", "change_pct": "-10"},
    {"category": "dining", "start_year": "2030", "end_year": "2029", "change_pct": "-10"},
    {"category": "dining", "start_year": "2030", "change_pct": "-100"},
    {"category": "ALL:Business", "start_year": "2030", "change_pct": "-10"},
])
def test_invalid_rows_are_rejected(ws, bad):
    resp = app.test_client().post("/api/spending-adjustments", json={"adjustments": [bad]}, headers=HEADERS)
    assert resp.status_code == 400
    assert "Spending Adjustments" not in _cashflow(ws)
