"""Plan step 3a.3, server side: the tax-year summary, carryforward entry and wash-flag refresh of the Sales Ledger page."""
from __future__ import annotations

import pytest

from src import active_plan, sales_service, sales_tax_year
from src.realized_tax import net_realized_by_year
from src.sales_ledger import ValidationError


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def _sale(input_dir, **over):
    row = dict(sale_date="2026-06-10", account="Trust_taxable", tax_class="taxable", symbol="VTI", shares=10,
               proceeds=2000.0, fees=0.0, basis=1500.0, purchase_date="2025-01-02")
    row.update(over)
    return sales_service.add_sale(input_dir, row)


def test_through_year_extends_the_chain_so_losses_keep_being_used():
    sales = [{"tax_year": 2025, "term": "long", "gain": -8000.0}]
    by_year = net_realized_by_year(sales, {}, through_year=2027)
    assert sorted(by_year) == [2025, 2026, 2027]
    assert [by_year[y]["ordinary_offset"] for y in (2025, 2026, 2027)] == [3000.0, 3000.0, 2000.0]
    assert by_year[2027]["carryforward_lt"] == 0.0


def test_empty_ledger_summary_is_all_zero(input_dir):
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert out["year"] == 2026 and out["filing"] == "MFJ" and out["limit"] == 3000.0
    assert all(v == 0.0 for v in out["netting"].values())
    assert out["carryforward_in"] == {"short": 0.0, "long": 0.0, "entered": False}
    assert out["wash"] == {"count": 0, "flagged_loss": 0.0, "rows": []}


def test_summary_nets_the_year_and_ignores_voided_and_non_taxable(input_dir):
    _sale(input_dir, proceeds=2500.0, basis=1000.0, purchase_date="2026-01-05", symbol="VXUS")  # +1,500 short
    _sale(input_dir, proceeds=400.0, basis=1000.0)  # -600 long
    voided = _sale(input_dir, proceeds=9000.0, basis=1000.0, symbol="QQQ")
    sales_service.void_sale(input_dir, voided["sale_id"])
    _sale(input_dir, account="Roth_roth", tax_class="roth", proceeds=9000.0, basis=1.0, symbol="SPY")
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert (out["netting"]["net_st"], out["netting"]["net_lt"]) == (1500.0, -600.0)
    assert (out["netting"]["gain_to_tax_ordinary"], out["netting"]["gain_to_tax_ltcg"]) == (900.0, 0.0)
    assert out["totals"] == {"count": 2, "st_gain": 1500.0, "lt_gain": -600.0}


def test_prior_year_loss_carries_in_until_the_user_enters_the_real_figure(input_dir):
    _sale(input_dir, sale_date="2025-06-10", proceeds=2000.0, basis=10000.0, purchase_date="2020-01-01")  # -8,000 long
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert out["carryforward_in"] == {"short": 0.0, "long": 5000.0, "entered": False}
    assert out["netting"]["ordinary_offset"] == 3000.0 and out["netting"]["carryforward_lt"] == 2000.0
    sales_tax_year.set_carryforward(input_dir, 2026, short=250.0, long=1000.0)
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert out["carryforward_in"] == {"short": 250.0, "long": 1000.0, "entered": True}
    assert out["carryforward_out"] == {"short": 0.0, "long": 0.0}
    assert out["netting"]["ordinary_offset"] == 1250.0


def test_a_year_with_no_sales_still_uses_up_the_carryforward(input_dir):
    _sale(input_dir, sale_date="2024-06-10", proceeds=2000.0, basis=10000.0, purchase_date="2020-01-01")  # -8,000
    out = sales_tax_year.tax_year_summary(input_dir, 2026)  # 2024 and 2025 each used 3,000, leaving 2,000 for 2026
    assert out["carryforward_in"]["long"] == 2000.0 and out["carryforward_out"]["long"] == 0.0
    assert out["netting"]["ordinary_offset"] == 2000.0


def test_mfs_filing_halves_the_limit(input_dir):
    _sale(input_dir, proceeds=100.0, basis=9100.0)  # -9,000 long
    out = sales_tax_year.tax_year_summary(input_dir, 2026, filing="MFS")
    assert out["limit"] == 1500.0 and out["netting"]["ordinary_offset"] == 1500.0
    assert out["carryforward_out"]["long"] == 7500.0


def test_filing_status_comes_from_the_plan_when_not_given(input_dir, monkeypatch):
    monkeypatch.setattr(active_plan, "peek_plan_data_for_input_dir",
                        lambda d: {"Household": {"": {"filing_status": "mfs"}}})
    assert sales_tax_year.tax_year_summary(input_dir, 2026)["filing"] == "MFS"


@pytest.mark.parametrize("short,long", [(-1, 0), (0, -5), ("x", 0), (float("nan"), 0)])
def test_set_carryforward_rejects_bad_figures(input_dir, short, long):
    with pytest.raises(ValidationError):
        sales_tax_year.set_carryforward(input_dir, 2026, short=short, long=long)
    assert sales_tax_year.tax_year_summary(input_dir, 2026)["carryforward_in"]["entered"] is False


def test_set_carryforward_rejects_a_bad_year(input_dir):
    with pytest.raises(ValidationError):
        sales_tax_year.set_carryforward(input_dir, 1800, short=0, long=0)


def test_wash_refresh_flags_a_loss_with_an_ira_repurchase_and_is_idempotent(input_dir):
    sale = _sale(input_dir, proceeds=1000.0, basis=1400.0)  # -400
    active_plan.write_dataset_rows_for_input_dir(input_dir, "holdings", [
        {"account": "Spouse_ira", "symbol": "VTI", "purchase_date": "2026-06-20", "shares": "10",
         "purchase_price": "100", "lot_type": "reinvest", "note": ""},
        {"account": "Cash_checking", "symbol": "CASH", "purchase_date": "2026-06-11", "shares": "500",
         "purchase_price": "1", "lot_type": "buy", "note": ""},
    ])
    assert sales_tax_year.refresh_wash_flags(input_dir) == {"flagged": 1, "updated": 1}
    row = [s for s in sales_service.list_sales(input_dir)["sales"] if s["sale_id"] == sale["sale_id"]][0]
    assert row["wash_flag"] == "possible" and "no basis add-back" in row["wash_note"]
    assert sales_tax_year.refresh_wash_flags(input_dir) == {"flagged": 1, "updated": 0}
    wash = sales_tax_year.tax_year_summary(input_dir, 2026)["wash"]
    assert wash["count"] == 1 and wash["flagged_loss"] == 400.0 and wash["rows"][0]["sale_id"] == sale["sale_id"]


def test_wash_refresh_clears_a_flag_when_the_repurchase_is_gone(input_dir):
    _sale(input_dir, proceeds=1000.0, basis=1400.0)
    active_plan.write_dataset_rows_for_input_dir(input_dir, "holdings", [
        {"account": "Joint_taxable", "symbol": "VTI", "purchase_date": "2026-06-12", "shares": "1",
         "purchase_price": "100", "lot_type": "buy", "note": ""}])
    sales_tax_year.refresh_wash_flags(input_dir)
    active_plan.write_dataset_rows_for_input_dir(input_dir, "holdings", [])
    assert sales_tax_year.refresh_wash_flags(input_dir) == {"flagged": 0, "updated": 1}
    assert sales_tax_year.tax_year_summary(input_dir, 2026)["wash"]["count"] == 0


def test_entering_a_carryforward_keeps_the_state_rate_override(input_dir):
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        store.sales.set_adjustment(2026, state_rate_override=0.04)
    sales_tax_year.set_carryforward(input_dir, 2026, short=1.0, long=2.0)
    with active_plan.workspace_store(input_dir.parent) as store:
        assert store.sales.adjustment(2026)["state_rate_override"] == 0.04
