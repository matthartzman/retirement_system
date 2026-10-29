"""Plan step 2.2: the /api/sales/candidates routes (scratch workspace)."""
from __future__ import annotations

import pytest

from src import active_plan
from src.server import app, plan_routes

LOTS = [{"account": "Trust", "symbol": "VTI", "purchase_date": "2023-01-10", "shares": "10", "purchase_price": "100", "lot_type": "buy", "note": ""}]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(LOTS)
        store.sales.add_candidate(source="monarch", sale_date="2026-07-06", account="Trust", symbol="VTI",
                                  shares=4.0, price=250.0, amount=1000.0, monarch_id="m-1")
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: tmp_path / "input")
    return app.test_client()


def test_list_panel_confirm_undo_dismiss_flow(client):
    listed = client.get("/api/sales/candidates?state=unmatched").get_json()
    assert listed["success"] and listed["counts"]["unmatched"] == 1
    cid = listed["candidates"][0]["candidate_id"]
    p = client.get(f"/api/sales/candidates/{cid}/panel").get_json()
    assert p["success"] and p["suggested_trade_date"] == "2026-07-03" and p["allocation"] == {}
    lot = p["lots"][0]["lot_id"]
    bad = client.post(f"/api/sales/candidates/{cid}/confirm", json={"allocation": {lot: 3}, "tax_class": "taxable", "trade_date": "2026-07-03"})
    assert bad.status_code == 400 and "must equal" in bad.get_json()["error"]
    ok = client.post(f"/api/sales/candidates/{cid}/confirm", json={"allocation": {lot: 4}, "tax_class": "taxable", "trade_date": "2026-07-03"})
    assert ok.status_code == 200 and len(ok.get_json()["sale_ids"]) == 1
    assert len(client.get("/api/sales").get_json()["sales"]) == 1
    assert client.post(f"/api/sales/candidates/{cid}/undo").status_code == 200
    assert client.get("/api/sales").get_json()["sales"] == []
    assert client.post(f"/api/sales/candidates/{cid}/dismiss", json={"reason": "not_a_sale"}).status_code == 200
    assert client.post(f"/api/sales/candidates/{cid}/restore").status_code == 200


def test_unknown_candidate_is_a_400(client):
    assert client.get("/api/sales/candidates/99/panel").status_code == 400
    assert client.post("/api/sales/candidates/99/undo").status_code == 400
