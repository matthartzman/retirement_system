"""WP9.1: the schema-driven csv_exchange core (src/csv_exchange/core.py)."""
from __future__ import annotations

import pytest

from src.csv_exchange import (
    DATASETS,
    FLAT_DATASET_FILES,
    PLAN_CSV_FILES,
    ImportRejected,
    ParsedDataset,
    commit,
    current_rows,
    dataset_for_file,
    export_dataset,
    parse,
    preview,
    validate,
)
from src.stores import PlanStore, ValidationError

HOLDINGS = (
    "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
    "Brokerage,VTI,2020-01-02,10,150.25,,\n"
    "IRA,BND,2021-03-04,5.5,80,,first\n"
)
LIABILITIES = (
    "liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year,payoff_month,carry_zero,notes\n"
    "L1,mortgage,Home,250000,3.25%,1500,2020,2050,,,\n"
    "L2,auto,Car,12000,4.9%,400,2023,2027,,,\n"
)
PLAN_HEADER = "section,subsection,label,value,units,notes\n"
SCHEMA = {
    ("Household", "", "retirement_year"): {"type": "year", "required": "TRUE", "min": "", "max": ""},
    ("Cashflow", "Earned Income", "salary"): {"type": "currency", "required": "", "min": "0", "max": ""},
}


@pytest.fixture
def store():
    s = PlanStore.open(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------- registry
def test_registry_declares_every_flat_dataset_and_the_plan_set():
    assert set(FLAT_DATASET_FILES) <= set(DATASETS)
    assert DATASETS["plan_rows"].files == PLAN_CSV_FILES
    for name in ("monarch_transactions", "cma", "correlation", "security_master"):
        assert name in DATASETS
    assert not DATASETS["cma"].writable and DATASETS["holdings"].writable
    assert dataset_for_file("CLIENT_HOLDINGS.csv").name == "holdings"
    assert dataset_for_file("client_policy.csv").name == "plan_rows"
    assert dataset_for_file("nope.csv") is None


# ------------------------------------------------------------------------------- parse
def test_parse_flat_keeps_cells_as_written_and_fills_missing_columns():
    p = parse("account,symbol,shares,market_value\n Brokerage ,VTI,10.50,1\n,,,\n", "holdings")
    assert p.errors == []
    assert len(p.rows) == 1
    row = p.rows[0]
    assert row["account"] == " Brokerage " and row["shares"] == "10.50"
    assert row["purchase_price"] == "" and row["market_value"] == "1"


def test_parse_reports_missing_required_columns_and_empty_text():
    assert any("symbol" in i.message for i in parse("account,shares\nA,1\n", "holdings").errors)
    assert parse("", "holdings").errors


def test_parse_plan_rows_multi_file_collapses_duplicates():
    texts = {
        "client_data.csv": PLAN_HEADER + "Household,,retirement_year,2030,,\n",
        "client_household.csv": PLAN_HEADER + "Household,,retirement_year,2031,,\nHousehold,,state,CA,,\n",
    }
    p = parse(texts, "plan_rows")
    assert [r["value"] for r in p.rows] == ["2031", "CA"]
    assert any("duplicate" in w.message for w in p.warnings)
    assert parse("foo,bar\n1,2\n", "plan_rows").errors  # not a plan CSV


def test_parse_monarch_maps_columns_and_drops_run_id():
    text = "id,date,merchant,amount,account,category,run_id\nm1,2026-01-05,Shop,-12.50,Chk,Food,r9\n"
    p = parse(text, "monarch_transactions")
    assert p.errors == []
    row = p.rows[0]
    assert row["Monarch Id"] == "m1" and row["Amount"] == "-12.50" and "run_id" not in row


# ---------------------------------------------------------------------------- validate
def test_validate_flat_numeric_and_required_cells():
    p = parse("account,symbol,shares,purchase_price\nA,VTI,ten,$1,000.00\nB,,1,\n", "holdings")
    issues = validate(p)
    msgs = [(i.row, i.column) for i in issues if i.level == "error"]
    assert (1, "shares") in msgs and (2, "symbol") in msgs
    assert (1, "purchase_price") not in msgs  # "$1,000.00" is a number


def test_validate_plan_rows_against_schema_fields():
    p = parse(PLAN_HEADER + "Household,,retirement_year,soon,,\n"
              "Cashflow,Earned Income,salary,-5,,\nOther,,unknown,1,,\n", "plan_rows")
    issues = validate(p, schema=SCHEMA)
    errors = {(i.row, i.column) for i in issues if i.level == "error"}
    assert errors == {(1, "value"), (2, "value")}
    warnings = [i for i in issues if i.level == "warning"]
    assert len(warnings) == 1 and "1 row(s)" in warnings[0].message and "Other /  / unknown" in warnings[0].message
    assert validate(p, schema=SCHEMA) == issues  # idempotent


def test_validate_plan_rows_uses_the_shipped_catalog_by_default():
    p = parse(PLAN_HEADER + "Nowhere,,not_a_field,1,,\n", "plan_rows")
    assert [i.level for i in validate(p)] == ["warning"]


# ------------------------------------------------------------------------ preview/diff
def test_preview_counts_added_changed_removed_unchanged_without_writing(store):
    commit(store, parse(LIABILITIES, "liabilities"))
    incoming = parse(
        "liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year,payoff_month,carry_zero,notes\n"
        "L1,mortgage,Home,249000,3.25%,1500,2020,2050,,,\n"
        "L3,heloc,Line,0,8%,0,2026,2030,,,\n", "liabilities")
    before = store.liabilities.rows()
    rep = preview(store, incoming)
    assert store.liabilities.rows() == before
    d = rep["diff"]
    assert (d["added"], d["changed"], d["removed"], d["unchanged"]) == (1, 1, 1, 0)
    assert d["samples"]["changed"][0]["fields"] == ["balance"]
    assert d["samples"]["changed"][0]["before"]["balance"] == "250000"
    assert d["samples"]["removed"][0]["liability_id"] == "L2"
    assert rep["will_write"] and rep["rows_current"] == 2 and rep["rows_after"] == 2


def test_preview_unchanged_and_keyless_dataset(store):
    commit(store, parse(HOLDINGS, "holdings"))
    rep = preview(store, parse(HOLDINGS, "holdings"))
    assert rep["diff"]["unchanged"] == 2 and rep["diff"]["added"] == 0
    edited = HOLDINGS.replace("5.5", "6")
    d = preview(store, parse(edited, "holdings"))["diff"]
    assert (d["added"], d["removed"], d["changed"], d["unchanged"]) == (1, 1, 0, 1)


def test_preview_reports_errors_and_will_not_write(store):
    rep = preview(store, parse("account,symbol,shares\nA,VTI,x\n", "holdings"))
    assert rep["errors"] and rep["will_write"] is False


def test_preview_reference_dataset_is_read_only():
    from src.stores.ref_access import reference

    ref = reference()
    text = export_dataset(ref, "security_master")
    rep = preview(ref, parse(text, "security_master"))
    assert rep["writable"] is False and rep["will_write"] is False
    assert rep["diff"]["unchanged"] == rep["rows_current"] > 0
    with pytest.raises(ImportRejected):
        commit(ref, parse(text, "security_master"))


def test_monarch_upsert_preview_and_commit(store):
    commit(store, parse("Date,Amount,Monarch Id,Merchant\n2026-01-01,-1,m1,A\n2026-01-02,-2,,Cash\n",
                        "ytd_transactions"))
    incoming = parse("id,date,amount,merchant\nm1,2026-01-01,-1.50,A\nm2,2026-01-03,-3,B\n",
                     "monarch_transactions")
    d = preview(store, incoming)["diff"]
    assert (d["added"], d["changed"], d["removed"], d["unchanged"]) == (1, 1, 0, 1)
    assert commit(store, incoming) == {"monarch_transactions": 3}
    rows = store.dataset("ytd_transactions").rows()
    assert [(r["Monarch Id"], r["Amount"]) for r in rows] == [("m1", "-1.50"), ("", "-2"), ("m2", "-3")]


# ------------------------------------------------------------------------------ commit
def test_commit_is_one_transaction_and_rolls_back_everything(store):
    commit(store, [parse(HOLDINGS, "holdings"), parse(LIABILITIES, "liabilities")])
    holdings_before = store.holdings.rows()
    liabilities_before = store.liabilities.rows()
    good = parse(HOLDINGS.replace("VTI", "VXUS"), "holdings")
    bad = parse(LIABILITIES, "liabilities")
    bad.rows[0]["balance"] = 5  # not text: the store refuses it mid-commit
    with pytest.raises(ValidationError):
        commit(store, [good, bad])
    assert store.holdings.rows() == holdings_before
    assert store.liabilities.rows() == liabilities_before


def test_commit_refuses_invalid_input_before_writing(store):
    commit(store, parse(HOLDINGS, "holdings"))
    before = store.holdings.rows()
    with pytest.raises(ImportRejected) as exc:
        commit(store, [parse(LIABILITIES, "liabilities"), parse("account,symbol,shares\nA,VTI,x\n", "holdings")])
    assert exc.value.issues
    assert store.holdings.rows() == before and store.liabilities.rows() == []


def test_commit_plan_rows_replaces_rows_with_per_section_order(store):
    store.insert_row("Old", label="gone", value="1")
    p = parse(PLAN_HEADER + "Household,,retirement_year,2030,,\nCashflow,Earned Income,salary,100000,,\n"
              "Household,,state,CA,,a note\n", "plan_rows")
    assert commit(store, p, schema=SCHEMA) == {"plan_rows": 3}
    assert store.section_order() == ["Household", "Cashflow"]
    assert [(r["label"], r["sort_order"]) for r in store.rows("Household")] == [("retirement_year", 0), ("state", 1)]
    assert store.rows("Old") == []


# ------------------------------------------------------------------------------ export
@pytest.mark.parametrize("name,text", [("holdings", HOLDINGS), ("liabilities", LIABILITIES)])
def test_export_round_trip_flat(store, name, text):
    commit(store, parse(text, name))
    out = export_dataset(store, name)
    assert out == text
    rep = preview(store, parse(out, name))
    assert rep["diff"]["unchanged"] == 2 and rep["diff"]["added"] == rep["diff"]["removed"] == 0


def test_export_round_trip_plan_rows(store):
    text = (PLAN_HEADER + "Household,,retirement_year,2030,,\nCashflow,Earned Income,salary,\"100,000\",USD,"
            "\"notes, with comma\"\nHousehold,,state,CA,,\n")
    commit(store, parse(text, "plan_rows"), schema=SCHEMA)
    out = export_dataset(store, "plan_rows")
    again = parse(out, "plan_rows")
    assert again.rows == current_rows(store, "plan_rows")
    assert again.rows[2]["value"] == "100,000" and again.rows[2]["notes"] == "notes, with comma"
    d = preview(store, again, schema=SCHEMA)["diff"]
    assert d["unchanged"] == 3 and d["changed"] == d["added"] == d["removed"] == 0


def test_export_round_trip_reference_cma():
    from src.stores.ref_access import reference

    ref = reference()
    text = export_dataset(ref, "cma")
    p = parse(text, "cma")
    assert validate(p) == []
    assert p.rows == current_rows(ref, "cma")


def test_export_import_only_shape_is_refused(store):
    with pytest.raises(KeyError):
        export_dataset(store, "monarch_transactions")


def test_parsed_dataset_spec_lookup():
    with pytest.raises(KeyError):
        ParsedDataset("nope", [], []).spec


def test_fixture_plan_round_trips_through_export_and_commit_unchanged(tmp_path):
    """The frozen sample plan: every plan dataset exported, re-imported into an empty plan in
    one commit, comes back byte-for-byte (so no number can move)."""
    from tests import plan_fixture as pf

    plan = pf.make_plan(tmp_path)
    names = ["plan_rows", *FLAT_DATASET_FILES]
    with PlanStore.open(plan.plan_db) as src, PlanStore.open(":memory:") as dst:
        parsed = [parse(export_dataset(src, n), n) for n in names]
        for p in parsed:
            rep = preview(src, p)
            d = rep["diff"]
            assert rep["errors"] == [] and d["changed"] == d["added"] == d["removed"] == 0, p.name
        commit(dst, parsed)
        assert dst.sectioned_data() == src.sectioned_data()
        for n in FLAT_DATASET_FILES:
            assert dst.dataset(n).rows() == src.dataset(n).rows(), n
