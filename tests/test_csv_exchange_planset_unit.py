"""WP9.2: plan-set import/export (zip, legacy names, round trip)."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from src.csv_exchange import (
    PLAN_CSV_FILES,
    ImportRejected,
    current_rows,
    export_dataset,
    export_plan_set,
    import_plan_set,
    split_plan_rows,
)
from src.stores import PlanStore

HOLDINGS = ("account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
            "Brokerage,VTI,2020-01-02,10,150.25,,\nIRA,BND,2021-03-04,5.5,80,,first\n")
LIABILITIES = ("liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year,notes\n"
               "L1,mortgage,Home,250000,3.25%,1500,2020,2050,\n")
SPENDING_BUDGET = "kind,key,annual_budget\ncategory,groceries,12000\n"
ROWS = [
    ("Household", "", "retirement_year", "2030", "year", ""),
    ("Household", "", "state", "TX", "", "note, with comma"),
    ("Cashflow", "Earned Income", "salary", "150000", "$", ""),
    ("Positions", "", "VTI", "10", "", 'quoted "x"'),
    ("Scenarios", "", "base", "1", "", ""),
    ("Estate Planning", "", "trust", "yes", "", ""),
]


@pytest.fixture
def stores():
    a, b = PlanStore.open(":memory:"), PlanStore.open(":memory:")
    yield a, b
    a.close()
    b.close()


def _seed(store):
    from src.csv_exchange import commit, parse
    with store.transaction():
        order: dict[str, int] = {}
        for sec, sub, label, value, units, notes in ROWS:
            n = order.get(sec, 0)
            order[sec] = n + 1
            store.insert_row(sec, subsection=sub, label=label, value=value, units=units, notes=notes, sort_order=n)
    commit(store, [parse(HOLDINGS, "holdings"), parse(LIABILITIES, "liabilities"),
                   parse(SPENDING_BUDGET, "spending_budget")])


def _zip_names(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.namelist()


def test_split_plan_rows_uses_primary_part_files_and_keeps_order():
    rows = [dict(zip(("section", "subsection", "label", "value", "units", "notes"), r)) for r in ROWS]
    files = split_plan_rows(rows)
    assert list(files) == [f for f in PLAN_CSV_FILES if f in files]
    assert "Estate Planning" in files["client_insurance_estate.csv"]
    assert files["client_household.csv"].splitlines()[0] == "section,subsection,label,value,units,notes"
    assert "Scenarios" in files["client_policy.csv"] and "client_business.csv" not in files


def test_export_zip_has_manifest_plan_files_and_flat_datasets(stores):
    src, _ = stores
    _seed(src)
    data = export_plan_set(src)
    names = _zip_names(data)
    assert "manifest.json" in names and "client_household.csv" in names
    assert "client_holdings.csv" in names or any("holdings" in n for n in names)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["datasets"]["plan_rows"]["rows"] == len(ROWS)
    assert manifest["datasets"]["holdings"]["rows"] == 2
    assert export_plan_set(src) == data   # reproducible


def test_round_trip_into_empty_plan_is_identical(stores):
    src, dst = stores
    _seed(src)
    result = import_plan_set(dst, export_plan_set(src))
    assert result["errors"] == 0 and result["committed"]["plan_rows"] == len(ROWS)
    key = lambda r: (r["section"], r["subsection"], r["label"])  # noqa: E731
    assert sorted(current_rows(dst, "plan_rows"), key=key) == sorted(current_rows(src, "plan_rows"), key=key)
    for name in ("holdings", "liabilities", "spending_budget"):
        assert export_dataset(dst, name) == export_dataset(src, name)
    assert import_plan_set(dst, export_plan_set(src), dry_run=True)["datasets"]["plan_rows"]["diff"]["added"] == 0


def test_import_accepts_legacy_names_folders_and_text_mapping(stores):
    src, dst = stores
    _seed(src)
    files = {"Old Plan/INPUT/" + k.upper().replace(".CSV", ".csv"): v
             for k, v in __import__("src.csv_exchange.plan_set", fromlist=["x"]).export_plan_set_files(src).items()
             if k != "manifest.json"}
    files["notes.txt"] = "ignore me"
    result = import_plan_set(dst, files)
    assert result["ignored"] == ["notes.txt"]
    assert result["committed"]["plan_rows"] == len(ROWS) and result["committed"]["holdings"] == 2


def test_dry_run_writes_nothing_and_errors_reject_everything(stores):
    src, dst = stores
    _seed(src)
    pre = import_plan_set(dst, export_plan_set(src), dry_run=True)
    assert pre["committed"] is None and current_rows(dst, "plan_rows") == []
    bad = {"client_household.csv": "section,subsection,label,value,units,notes\nHousehold,,x,1,,\n",
           "client_holdings.csv": "symbol\nVTI\n"}   # missing required columns
    with pytest.raises(ImportRejected):
        import_plan_set(dst, bad)
    assert current_rows(dst, "plan_rows") == []      # all-or-nothing


def test_not_a_zip_is_rejected(stores):
    with pytest.raises(ImportRejected):
        import_plan_set(stores[1], b"definitely not a zip")
