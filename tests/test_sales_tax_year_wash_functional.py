"""Tax year with wash sales: the loss used in netting is net of what is disallowed; the cards say where each share of it goes."""
from __future__ import annotations

import pytest

from src import active_plan, sales_service, sales_tax_year
from src.server import app, plan_routes

LOSS_ACCT = "Matt_Trust"


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all([
            {"account": "Spouse_Trust", "symbol": "VTI", "purchase_date": "2026-06-15", "shares": "10", "purchase_price": "90", "lot_type": "buy", "note": ""},
            {"account": "Member_1_Roth", "symbol": "VTI", "purchase_date": "2026-06-20", "shares": "10", "purchase_price": "91", "lot_type": "buy", "note": ""}])
    return tmp_path / "input"


def _loss(input_dir, **over):
    row = dict(sale_date="2026-06-10", account=LOSS_ACCT, tax_class="taxable", symbol="VTI", shares=20, proceeds=1000.0, fees=0.0, basis=1400.0,
               purchase_date="2025-01-02")
    row.update(over)
    return sales_service.add_sale(input_dir, row)


def test_netting_uses_loss_net_of_disallowed(input_dir):
    _loss(input_dir)                                                        # -400 long; 20 shares sold, 20 replacement shares
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert out["wash"]["disallowed"] == pytest.approx(400.0)
    assert out["wash"]["deferred"] == pytest.approx(200.0) and out["wash"]["lost_permanently"] == pytest.approx(200.0)   # Roth half
    assert out["wash"]["sales"] == 1
    assert out["totals"]["lt_gain"] == pytest.approx(-400.0)                # realized stays as recorded
    assert out["netting"]["net_lt"] == pytest.approx(0.0)                   # the whole loss is disallowed


def test_partial_disallowance_leaves_the_rest_deductible(input_dir):
    _loss(input_dir, shares=40, proceeds=2000.0, basis=2800.0)               # -800, 40 sold, 20 replaced: half
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert out["wash"]["disallowed"] == pytest.approx(400.0)
    assert out["netting"]["net_lt"] == pytest.approx(-400.0)


def test_review_not_wash_restores_the_whole_loss_and_estimated_tax_moves_only_when_flagged(input_dir):
    _loss(input_dir, shares=20)
    flagged = sales_tax_year.tax_year_summary(input_dir, 2026)
    sales_tax_year.set_wash_review(input_dir, f"{LOSS_ACCT}|VTI|2026-06-10", "not_wash", reason="not substantially identical")
    cleared = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert flagged["wash"]["disallowed"] > 0 and cleared["wash"]["disallowed"] == 0
    assert cleared["netting"]["net_lt"] == pytest.approx(-400.0) and flagged["netting"]["net_lt"] == pytest.approx(0.0)
    if flagged.get("realized_tax", {}).get("available") and cleared.get("realized_tax", {}).get("available"):
        assert flagged["realized_tax"]["total"] >= cleared["realized_tax"]["total"]


def test_wash_cards_name_both_sides_and_where_the_loss_goes(input_dir, monkeypatch):
    _loss(input_dir)
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: input_dir)
    out = app.test_client().get("/api/sales/wash?year=2026").get_json()
    assert out["success"] and len(out["cards"]) == 1
    c = out["cards"][0]
    assert c["sale_key"] == f"{LOSS_ACCT}|VTI|2026-06-10" and c["loss"] == pytest.approx(400.0) and c["deductible"] == pytest.approx(0.0)
    where = {m["account"]: m["where"] for m in c["matches"]}
    assert where["Spouse_Trust"].startswith("adds $200.00 to the cost of this lot")
    assert where["Member_1_Roth"] == "lost permanently"
    assert "_" not in c["account"] and all("_" not in m["label"] for m in c["matches"])      # friendly names, not ids
    sales_tax_year.set_wash_review(input_dir, c["sale_key"], "wash")
    again = app.test_client().get("/api/sales/wash?year=2026").get_json()
    assert again["cards"] == [] and again["reviewed"][0]["outcome"] == "wash"
