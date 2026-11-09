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


def test_holding_period_check_counts_backfilled_lots(tmp_path):
    from src import transactions
    (tmp_path / "input").mkdir()
    acct = "Matt_Trust"
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all([{"Account": "Trust", "Role": "Investment", "Mapped Investment Account": acct}])
        store.dataset("holdings").replace_all([{"account": acct, "symbol": "ITOT", "purchase_date": "", "shares": "20", "purchase_price": "90", "lot_type": "buy", "note": ""}])
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
        real = store.transactions.insert(txn_date="2025-01-02", account=acct, type="buy", symbol="ITOT", shares=10.0, price=95.0, amount=-950.0, source="manual")
    inp = tmp_path / "input"
    lots = {l["txn_id"]: l["source"] for l in sales_service.open_lots(inp, acct, "ITOT", "2026-09-01")["lots"]}
    opening = next(i for i, src in lots.items() if src == "backfill")
    rows = [dict(sale_date="2026-09-01", account=acct, symbol="ITOT", shares=5, proceeds=500.0, fees=0.0, basis=450.0, purchase_date="2025-01-01", txn_lot=opening),
            dict(sale_date="2026-09-02", account=acct, symbol="ITOT", shares=5, proceeds=500.0, fees=0.0, basis=475.0, purchase_date="2025-01-02", txn_lot=real)]
    sales_service.add_sales(inp, rows)
    assert sales_service.holding_period_check(inp, 2026) == {"lots": 1, "sales": 1}
    assert sales_service.holding_period_check(inp, 2025) == {"lots": 0, "sales": 0}
    flags = {l["txn_id"]: l["source"] for l in sales_service.open_lots(inp, acct, "ITOT", "2026-09-01")["lots"]}
    with active_plan.workspace_store(tmp_path) as store:
        payload = transactions.open_lots(store, account=acct, symbol="ITOT")
    assert sorted(l["date_not_on_file"] for l in payload) == [False, True]
    assert all(l["wash_adjustment"] is None and l["tacked_date"] is None for l in payload)
    assert flags
