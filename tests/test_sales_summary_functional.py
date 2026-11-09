"""The Sales tab's KPI summary (must equal Tax year) and the year list."""
from __future__ import annotations

from datetime import date

import pytest

from src import active_plan, sales_service, sales_tax_year
from src.sales_ledger import validate_sale_row


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def _sale(input_dir, **over):
    row = dict(sale_date="2026-06-10", account="Trust_taxable", tax_class="taxable", symbol="VTI", shares=10,
               proceeds=2000.0, fees=1.5, basis=1500.0, purchase_date="2025-01-02")
    row.update(over)
    return sales_service.add_sale(input_dir, row)


def _plan(input_dir):
    _sale(input_dir, proceeds=2500.0, basis=1000.0, purchase_date="2026-01-05", symbol="VXUS")   # short +1500
    _sale(input_dir, proceeds=400.0, basis=1000.0)                                              # long -600
    gone = _sale(input_dir, proceeds=9000.0, basis=1000.0, symbol="QQQ")
    sales_service.void_sale(input_dir, gone["sale_id"])
    row = validate_sale_row(dict(sale_date="2026-06-10", account="Roth_roth", tax_class="roth", symbol="SPY", shares=1, proceeds=900.0,
                                 basis=100.0, purchase_date="2020-01-01", source="manual"))
    row.pop("status")
    row["gain"] = 800.0                                  # a stored non-taxable gain (imports and older rows carry one)
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        store.sales.insert_sale(**row)
    _sale(input_dir, sale_date="2025-03-03", proceeds=100.0, basis=50.0)


def test_summary_matches_tax_year_totals(input_dir):
    _plan(input_dir)
    s = sales_service.sales_summary(input_dir, 2026)
    t = sales_tax_year.tax_year_summary(input_dir, 2026)["totals"]
    assert (s["count"], s["st_gain"], s["lt_gain"]) == (t["count"], t["st_gain"], t["lt_gain"])
    assert s["sales"] == 2 and s["fees"] == 3.0


def test_summary_taxable_only_off_includes_ira_sales(input_dir):
    _plan(input_dir)
    off = sales_service.sales_summary(input_dir, 2026, taxable_only=False)
    assert off["count"] == 3 and off["lt_gain"] == pytest.approx(-601.5 + 800.0)


def test_summary_all_years(input_dir):
    _plan(input_dir)
    assert sales_service.sales_summary(input_dir, None)["count"] == 3


def test_years_exclude_future_and_empty(input_dir):
    _plan(input_dir)
    _sale(input_dir, sale_date=f"{date.today().year + 1}-01-02", purchase_date="2020-01-01")
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        store.transactions.insert(txn_date="2024-05-01", account="Trust_taxable", type="buy", symbol="VTI", shares=1.0, price=1.0,
                                  amount=-1.0, source="manual")
    years = sales_service.sales_years(input_dir)
    assert years == [2024, 2025, 2026]
