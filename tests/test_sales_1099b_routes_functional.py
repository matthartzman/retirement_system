"""Plan step 5.2: /api/sales/1099b/preview and /apply (scratch workspace, synthetic statement)."""
from __future__ import annotations

import base64

import pytest

import broker_1099b_synthetic as syn
from src import active_plan
from src.server import app, plan_routes

BASE = dict(symbol="ABCD", account="Trust", tax_class="taxable", shares=10.0, fees=0.0, source="manual",
            sale_date="2025-09-10", purchase_date="2025-03-04", holding_period="short", proceeds=1490.0, basis=1400.0, gain=90.0)
SYMBOLS = ["ABCD", "WXYZ", "QRST", "LMNO", "PQRS"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.sales.insert_sale(**BASE)
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: tmp_path / "input")
    from src import broker_1099b
    monkeypatch.setattr(broker_1099b, "_master_symbols", lambda: set(SYMBOLS))
    return app.test_client()


def body(**over):
    return {"broker": "etrade", "account": "Trust", "content": syn.build_statement(), **over}


def test_preview_then_apply_then_replace_flow(client):
    pv = client.post("/api/sales/1099b/preview", json=body()).get_json()
    assert pv["success"] and pv["can_apply"] and pv["report"]["totals"]["changed"] == 1
    assert "status,symbol" in pv["report_csv"]
    ok = client.post("/api/sales/1099b/apply", json=body())
    assert ok.status_code == 200 and ok.get_json()["corrected"] == 1 and ok.get_json()["added"] == 6
    again = client.post("/api/sales/1099b/apply", json=body())
    assert again.status_code == 400 and "already" in again.get_json()["error"]
    sales = client.get("/api/sales").get_json()["sales"]
    assert any(s["official_proceeds"] == 1500.0 for s in sales)


def test_pdf_upload_as_base64_reports_a_clean_error_or_parses(client):
    r = client.post("/api/sales/1099b/preview", json={"broker": "etrade", "account": "Trust", "pdf_base64": base64.b64encode(b"nope").decode()})
    assert r.status_code == 400 and r.get_json()["error"]


def test_bad_inputs_are_400(client):
    assert client.post("/api/sales/1099b/preview", json=body(account="")).status_code == 400
    assert client.post("/api/sales/1099b/preview", json=body(broker="nosuch")).status_code == 400
    assert client.post("/api/sales/1099b/preview", json={"broker": "etrade", "account": "Trust"}).status_code == 400
    assert client.post("/api/sales/1099b/preview", json=body(pdf_base64="!!!")).status_code == 400


def test_control_total_gap_is_refused_by_apply(client):
    bad = syn.totals()
    bad[("short", True)] = (1.0,) + bad[("short", True)][1:]
    r = client.post("/api/sales/1099b/apply", json=body(content=syn.build_statement(summary=bad)))
    assert r.status_code == 400 and "control" in r.get_json()["error"].lower()
