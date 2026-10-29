"""Plan step 1.4, server side: manual sale entry, CSV import (preview then commit) and the ledger list."""
from __future__ import annotations

import pytest

from src import active_plan, sales_service
from src.sales_ledger import ValidationError

CSV_HEADER = "sale_date,account,tax_class,symbol,shares,proceeds,fees,basis,purchase_date\n"


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def _row(**over):
    row = dict(sale_date="2026-06-10", account="Trust", tax_class="taxable", symbol="vti", shares=10,
               proceeds=2000.0, fees=5.0, basis=1500.0, purchase_date="2025-01-02")
    row.update(over)
    return row


def test_add_sale_records_a_manual_confirmed_row_with_derived_fields(input_dir):
    sale = sales_service.add_sale(input_dir, _row())
    assert sale["source"] == "manual" and sale["status"] == "confirmed"
    assert sale["gain"] == pytest.approx(495.0) and sale["holding_period"] == "long" and sale["symbol"] == "VTI"
    assert [s["sale_id"] for s in sales_service.list_sales(input_dir)["sales"]] == [sale["sale_id"]]


def test_add_sale_rejects_bad_row_and_writes_nothing(input_dir):
    with pytest.raises(ValidationError):
        sales_service.add_sale(input_dir, _row(shares=0))
    assert sales_service.list_sales(input_dir)["sales"] == []


def test_add_sale_ignores_a_caller_supplied_source(input_dir):
    assert sales_service.add_sale(input_dir, _row(source="1099b"))["source"] == "manual"


def test_list_filters_by_year_and_totals_taxable_gain_by_term(input_dir):
    sales_service.add_sale(input_dir, _row())  # long, +495
    sales_service.add_sale(input_dir, _row(purchase_date="2026-01-02", proceeds=1000.0))  # short, -505
    sales_service.add_sale(input_dir, _row(tax_class="roth", purchase_date=None))  # no gain
    sales_service.add_sale(input_dir, _row(sale_date="2025-03-01"))
    out = sales_service.list_sales(input_dir, year=2026)
    assert len(out["sales"]) == 3
    assert out["totals"] == {"count": 3, "short_gain": pytest.approx(-505.0), "long_gain": pytest.approx(495.0)}


def test_void_and_unvoid(input_dir):
    sid = sales_service.add_sale(input_dir, _row())["sale_id"]
    sales_service.void_sale(input_dir, sid)
    assert sales_service.list_sales(input_dir)["sales"] == []
    assert [s["status"] for s in sales_service.list_sales(input_dir, include_voided=True)["sales"]] == ["voided"]
    sales_service.unvoid_sale(input_dir, sid)
    assert len(sales_service.list_sales(input_dir)["sales"]) == 1


def test_void_unknown_sale_is_a_service_error(input_dir):
    with pytest.raises(ValidationError):
        sales_service.void_sale(input_dir, 999)


def test_csv_preview_reports_will_write_duplicates_and_errors_without_writing(input_dir):
    sales_service.add_sale(input_dir, _row())
    text = (CSV_HEADER
            + "2026-06-10,Trust,taxable,VTI,10,2000,5,1500,2025-01-02\n"      # duplicate of the ledger row
            + "2026-07-01,Trust,taxable,VXUS,5,500,0,400,2024-01-02\n"        # new
            + "2026-07-01,Trust,taxable,VXUS,5,500,0,400,2024-01-02\n"        # duplicate within the file
            + "2026-07-02,Trust,taxable,BND,0,500,0,400,2024-01-02\n")        # bad shares
    p = sales_service.preview_csv(input_dir, text)
    assert p["received"] == 4 and len(p["will_write"]) == 1 and p["will_write"][0]["symbol"] == "VXUS"
    assert len(p["duplicates"]) == 2
    assert len(p["errors"]) == 1 and p["errors"][0]["line"] == 5 and "shares" in p["errors"][0]["error"]
    assert len(sales_service.list_sales(input_dir)["sales"]) == 1


def test_csv_preview_missing_required_column(input_dir):
    p = sales_service.preview_csv(input_dir, "sale_date,account\n2026-01-01,Trust\n")
    assert p["will_write"] == [] and "missing required column" in p["errors"][0]["error"]


def test_csv_commit_writes_valid_rows_as_csv_source_and_is_idempotent(input_dir):
    text = CSV_HEADER + "2026-07-01,Trust,taxable,VXUS,5,500,0,400,2024-01-02\n"
    first = sales_service.commit_csv(input_dir, text)
    assert first["written"] == 1
    rows = sales_service.list_sales(input_dir)["sales"]
    assert rows[0]["source"] == "manual" and rows[0]["gain"] == pytest.approx(100.0)
    assert sales_service.commit_csv(input_dir, text)["written"] == 0
    assert len(sales_service.list_sales(input_dir)["sales"]) == 1


def test_csv_commit_with_any_error_writes_nothing(input_dir):
    text = CSV_HEADER + "2026-07-01,Trust,taxable,VXUS,5,500,0,400,2024-01-02\n2026-07-02,Trust,taxable,BND,x,1,0,1,2024-01-02\n"
    with pytest.raises(ValidationError):
        sales_service.commit_csv(input_dir, text)
    assert sales_service.list_sales(input_dir)["sales"] == []
