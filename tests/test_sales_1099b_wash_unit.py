"""1099-B wash tie: a line with column 1g sets the sale's review to 'broker reported'; cross-account amounts are listed apart."""
from __future__ import annotations

import pytest

import broker_1099b_synthetic as syn
from src import active_plan, sales_tax_year
from src.server import app, plan_routes

SYMBOLS = ["ABCD", "WXYZ", "QRST", "LMNO", "PQRS"]
KEY = "Trust|WXYZ|2025-10-15"                     # the synthetic statement's 60.00 wash line


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: tmp_path / "input")
    from src import broker_1099b
    monkeypatch.setattr(broker_1099b, "_master_symbols", lambda: set(SYMBOLS))
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path


def _apply(client):
    r = client.post("/api/sales/1099b/apply", json={"broker": "etrade", "account": "Trust", "content": syn.build_statement()})
    assert r.status_code == 200, r.get_json()


def _reviews(ws):
    with active_plan.workspace_store(ws) as store:
        return store.sales.reviews()


def test_apply_sets_broker_reported(ws):
    _apply(app.test_client())
    rv = _reviews(ws)[KEY]
    assert rv["outcome"] == "broker_reported" and rv["broker_amount"] == pytest.approx(60.0)


def test_user_outcome_not_overwritten(ws):
    sales_tax_year.set_wash_review(ws / "input", KEY, "not_wash", reason="not substantially identical")
    _apply(app.test_client())
    assert _reviews(ws)[KEY]["outcome"] == "not_wash"


def test_cross_account_amount_listed_separately(ws):
    with active_plan.workspace_store(ws, write=True) as store:
        store.dataset("holdings").replace_all([{"account": "Spouse_Roth", "symbol": "WXYZ", "purchase_date": "2025-10-20", "shares": "8", "purchase_price": "50",
                                                "lot_type": "buy", "note": ""}])
    c = app.test_client()
    _apply(c)
    tie = c.get("/api/sales/1099b/wash?year=2025").get_json()["tie"]
    assert [x["sale_key"] for x in tie["cross_account"]] == [KEY]
    assert tie["cross_account"][0]["label"] == "Spouse Roth" and tie["cross_account"][0]["amount"] > 0
    assert all(x["sale_key"] != KEY or x["computed"] == 0.0 for x in tie["same_account"])


def test_broker_amount_replaces_computed_without_double_count(ws):
    c = app.test_client()
    _apply(c)
    with active_plan.workspace_store(ws, write=True) as store:
        store.dataset("holdings").replace_all([{"account": "Trust", "symbol": "WXYZ", "purchase_date": "2025-10-20", "shares": "8", "purchase_price": "50",
                                                "lot_type": "buy", "note": ""}])
    out = sales_tax_year.tax_year_summary(ws / "input", 2025)
    assert out["wash"]["disallowed"] == pytest.approx(40.0)        # the broker's 60, capped at the 40 loss: not added to our own figure
