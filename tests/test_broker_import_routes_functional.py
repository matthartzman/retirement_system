"""/api/sales/broker/* routes and the ledger Edit / Back to queue routes (scratch workspace, synthetic file)."""
from __future__ import annotations

import pytest

from src import active_plan
from src.server import app, plan_routes
from tests.broker_activity_fixtures import FILE_NAME, VANGUARD_FILE_NAME, history_csv, vanguard_csv

ACCT = "Member_1_HSA"
HOLDINGS = [{"account": ACCT, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90",
             "lot_type": "buy", "note": ""}]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: tmp_path / "input")
    return app.test_client()


def body(**over):
    return {"broker": "fidelity", "content": history_csv(), "file_name": FILE_NAME, "account": ACCT, **over}


def test_preview_commit_requeue_revert_flow(client):
    pv = client.post("/api/sales/broker/preview", json=body()).get_json()
    assert pv["success"] and pv["counts"]["orders_ready"] == 2
    out = client.post("/api/sales/broker/commit", json=body(confirm_method="fifo")).get_json()
    assert out["success"] and len(out["confirmed"]) == 2
    sales = client.get("/api/sales").get_json()["sales"]
    assert {s["source"] for s in sales} == {"broker"}
    rq = client.post(f"/api/sales/{sales[0]['sale_id']}/requeue")
    assert rq.status_code == 200 and rq.get_json()["candidate_id"] in out["confirmed"]
    refused = client.post(f"/api/sales/broker/imports/{out['import_id']}/revert")
    assert refused.status_code == 400 and "confirmed" in refused.get_json()["error"]
    for cid in out["confirmed"]:
        if cid != rq.get_json()["candidate_id"]:
            assert client.post(f"/api/sales/candidates/{cid}/undo").status_code == 200
    ok = client.post(f"/api/sales/broker/imports/{out['import_id']}/revert")
    assert ok.status_code == 200
    assert client.get("/api/sales/broker/imports").get_json()["imports"][0]["status"] == "reverted"


def test_broker_is_detected_and_a_multi_account_file_takes_an_account_map(client):
    b = {"content": vanguard_csv(), "file_name": VANGUARD_FILE_NAME}  # no broker: recognized from the header
    pv = client.post("/api/sales/broker/preview", json=b).get_json()
    assert pv["success"] and pv["needs_account"] and pv["broker"] == "vanguard" and len(pv["hints"]) == 2
    amap = {"vanguard:1111": "Member_2_IRA", "vanguard:2222": "Member_2_Roth"}
    pv = client.post("/api/sales/broker/preview", json={**b, "accounts": amap}).get_json()
    assert pv["success"] and not pv["needs_account"] and len(pv["parts"]) == 2
    refused = client.post("/api/sales/broker/commit", json={**b, "accounts": {"vanguard:1111": "Member_2_IRA"}})
    assert refused.status_code == 400
    out = client.post("/api/sales/broker/commit", json={**b, "accounts": amap}).get_json()
    assert out["success"] and len(out["import_ids"]) == 2 and out["rows_new"] == 11
    names = {i["account"] for i in client.get("/api/sales/broker/imports").get_json()["imports"]}
    assert names == set(amap.values())
    unknown = client.post("/api/sales/broker/preview", json={"content": "a,b\n1,2\n"}).get_json()
    assert unknown["errors"] and "not recognized" in unknown["errors"][0]["error"]


def test_income_route_needs_account_and_year(client):
    assert client.get("/api/sales/broker/income?year=2026").status_code == 400
    assert client.get(f"/api/sales/broker/income?account={ACCT}&year=x").status_code == 400
    r = client.get(f"/api/sales/broker/income?account={ACCT}&year=2026").get_json()
    assert r["success"] and r["totals"]["broker"] == 0


def test_edit_manual_sale_voids_old_row(client):
    row = {"sale_date": "2026-06-10", "account": "Member_1_Trust", "tax_class": "taxable", "symbol": "VTI", "shares": 10,
           "proceeds": 2000, "basis": 1500, "purchase_date": "2024-01-02"}
    added = client.post("/api/sales", json=row)
    assert added.status_code == 200, added.get_json()
    sid = added.get_json()["sale"]["sale_id"]
    r = client.post(f"/api/sales/{sid}/replace", json={**row, "basis": "1600", "shares": "10"})
    assert r.status_code == 200 and r.get_json()["sale"]["gain"] == 400
    voided = client.get("/api/sales?include_voided=1").get_json()["sales"]
    assert sum(1 for s in voided if s["status"] == "voided") >= 1
    bad = client.post(f"/api/sales/{sid}/replace", json=row)
    assert bad.status_code == 400
