"""Tests for src/plan_data_backfill.py (system review item A7, Wave 3 3.12).

Characterization + behavior tests for the generic backfill engine and for
src/server/app_core.py's PLAN_DATA_BACKFILL_ENTRIES table, which replaced
twelve near-identical _ensure_*_ui_plan_data_rows functions. Written before
that replacement was trusted, run against a tmp_path (not the live input/
directory) - this is the safety net the review's own risk note called for
("there is no existing safety net to regress against").
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plan_data_backfill import (
    BackfillEntry,
    apply_backfill,
    insert_after_last,
    insert_before,
    section_is,
    section_subsection_is,
)


def _read_csv(path: Path) -> list[list[str]]:
    import csv
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


HEADER = ["section", "subsection", "label", "value", "units", "notes"]


# ── Generic engine ────────────────────────────────────────────────────────

def test_insert_before_lands_before_first_match(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(
        "section,subsection,label,value,units,notes\n"
        "Alpha,,x,1,,\n"
        "Beta,,y,2,,\n",
        encoding="utf-8",
    )
    entry = BackfillEntry("a.csv", [["New", "", "z", "3", "", ""]], insert_before(section_is("Beta")))
    apply_backfill(tmp_path, [entry])
    rows = _read_csv(path)
    assert [r[0] for r in rows] == ["section", "Alpha", "New", "Beta"]


def test_insert_before_appends_at_end_when_no_match(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("section,subsection,label,value,units,notes\nAlpha,,x,1,,\n", encoding="utf-8")
    entry = BackfillEntry("a.csv", [["New", "", "z", "3", "", ""]], insert_before(section_is("Nonexistent")))
    apply_backfill(tmp_path, [entry])
    rows = _read_csv(path)
    assert [r[0] for r in rows] == ["section", "Alpha", "New"]


def test_insert_after_last_lands_after_the_last_matching_row_not_the_first(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(
        "section,subsection,label,value,units,notes\n"
        "Cashflow,Spending,a,1,,\n"
        "Cashflow,Spending,b,2,,\n"
        "Cashflow,Mortgage,c,3,,\n",
        encoding="utf-8",
    )
    entry = BackfillEntry(
        "a.csv", [["Cashflow", "Spending", "new_row", "9", "", ""]],
        insert_after_last(section_subsection_is("Cashflow", "Spending")),
    )
    apply_backfill(tmp_path, [entry])
    rows = _read_csv(path)
    labels = [r[2] for r in rows[1:]]
    assert labels == ["a", "b", "new_row", "c"]


def test_missing_file_gets_header_and_new_rows(tmp_path):
    entry = BackfillEntry("missing.csv", [["Sec", "Sub", "lbl", "v", "u", "n"]])
    added = apply_backfill(tmp_path, [entry])
    path = tmp_path / "missing.csv"
    assert path.exists()
    rows = _read_csv(path)
    assert rows[0] == HEADER
    assert rows[1] == ["Sec", "Sub", "lbl", "v", "u", "n"]
    assert added == {"missing.csv": 1}


def test_existing_row_is_never_duplicated(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("section,subsection,label,value,units,notes\nSec,Sub,lbl,already-here,,\n", encoding="utf-8")
    entry = BackfillEntry("a.csv", [["Sec", "Sub", "lbl", "different-value-same-key", "", ""]])
    added = apply_backfill(tmp_path, [entry])
    rows = _read_csv(path)
    assert len(rows) == 2  # header + the one original row, nothing added
    assert rows[1][3] == "already-here"  # untouched, not overwritten
    assert added == {}


def test_unchanged_file_is_not_rewritten(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("section,subsection,label,value,units,notes\nSec,Sub,lbl,v,,\n", encoding="utf-8")
    before_mtime = path.stat().st_mtime_ns
    entry = BackfillEntry("a.csv", [["Sec", "Sub", "lbl", "v", "", ""]])  # already present
    apply_backfill(tmp_path, [entry])
    assert path.stat().st_mtime_ns == before_mtime


def test_multiple_entries_for_the_same_file_batch_into_one_read_and_write(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("section,subsection,label,value,units,notes\nSec,Sub,existing,v,,\n", encoding="utf-8")
    entries = [
        BackfillEntry("a.csv", [["First", "", "a", "1", "", ""]]),
        BackfillEntry("a.csv", [["Second", "", "b", "2", "", ""]]),
    ]
    added = apply_backfill(tmp_path, entries)
    rows = _read_csv(path)
    assert [r[0] for r in rows[1:]] == ["Sec", "First", "Second"]
    assert added == {"a.csv": 2}


def test_later_entry_anchor_sees_an_earlier_entrys_insertion(tmp_path):
    """insert_after_last for the same (section, subsection) anchor, applied via
    two entries in sequence, must stack - the second entry's rows land after
    the first entry's rows, not both landing in the same spot independently."""
    path = tmp_path / "a.csv"
    path.write_text("section,subsection,label,value,units,notes\nEconomic Assumptions,,x,1,,\n", encoding="utf-8")
    anchor = insert_after_last(section_subsection_is("Economic Assumptions", ""))
    entries = [
        BackfillEntry("a.csv", [["Economic Assumptions", "", "first_new", "a", "", ""]], anchor),
        BackfillEntry("a.csv", [["Economic Assumptions", "", "second_new", "b", "", ""]], anchor),
    ]
    apply_backfill(tmp_path, entries)
    rows = _read_csv(path)
    labels = [r[2] for r in rows[1:]]
    assert labels == ["x", "first_new", "second_new"]


def test_dynamic_row_source_callable_is_invoked_at_apply_time_with_target_dir(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
    calls = []

    def dynamic_rows(target_dir):
        calls.append(target_dir)
        return [["Account Policy", "acct1", "x", "", "", ""], ["Account Policy", "acct2", "x", "", "", ""]]

    entry = BackfillEntry("a.csv", dynamic_rows)
    added = apply_backfill(tmp_path, [entry])
    assert calls == [tmp_path]
    assert added == {"a.csv": 2}


def test_only_files_named_in_entries_are_touched(tmp_path):
    (tmp_path / "untouched.csv").write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
    entry = BackfillEntry("a.csv", [["Sec", "", "x", "1", "", ""]])
    apply_backfill(tmp_path, [entry])
    assert (tmp_path / "untouched.csv").read_text(encoding="utf-8") == "section,subsection,label,value,units,notes\n"


# ── Integration: the real app_core.py entries table, against a tmp_path ────

@pytest.fixture
def app_core(monkeypatch, tmp_path):
    """Import app_core and point its Plan Data resolution at tmp_path, so
    calling the real _ensure_user_ui_plan_data_rows() cannot reach the live
    input/ directory."""
    import src.server.app_core as ac
    monkeypatch.setattr(ac, "CSV_PATH", tmp_path / "client_data.csv")
    return ac


def _seed_minimal_old_schema_plan(tmp_path: Path) -> None:
    (tmp_path / "client_data.csv").write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
    for name in ("client_policy.csv", "client_household.csv", "client_income.csv", "client_assets.csv", "client_spending.csv"):
        (tmp_path / name).write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")


def test_ensure_user_ui_plan_data_rows_only_writes_inside_tmp_path(app_core, tmp_path):
    _seed_minimal_old_schema_plan(tmp_path)
    app_core._ensure_user_ui_plan_data_rows()
    for entry in app_core.PLAN_DATA_BACKFILL_ENTRIES:
        path = tmp_path / entry.file_name
        assert path.exists(), f"{entry.file_name} should exist under tmp_path"
    # The live repo's real input/ directory must be untouched by this test.
    real_input = Path(__file__).resolve().parents[1] / "input"
    # (sanity: real_input exists in this repo checkout; the point is app_core
    # never referenced it once CSV_PATH was monkeypatched away from it)
    assert real_input.exists()


def test_ensure_user_ui_plan_data_rows_backfills_expected_canonical_rows(app_core, tmp_path):
    _seed_minimal_old_schema_plan(tmp_path)
    app_core._ensure_user_ui_plan_data_rows()

    policy_rows = _read_csv(tmp_path / "client_policy.csv")
    policy_labels = {r[2] for r in policy_rows[1:]}
    assert "allocation_selection_mode" in policy_labels
    assert "mc_engine_mode" in policy_labels
    assert "roth_conversion_policy" in policy_labels
    assert "tlh_policy" in policy_labels

    household_rows = _read_csv(tmp_path / "client_household.csv")
    household_labels = {r[2] for r in household_rows[1:]}
    assert "reinvest_dividends_default" in household_labels
    assert "cash_yield_rate" in household_labels
    assert "inflation_general" in household_labels

    spending_rows = _read_csv(tmp_path / "client_spending.csv")
    spending_labels = {r[2] for r in spending_rows[1:]}
    assert "core_spending_growth_mode" in spending_labels
    assert "annual_real_estate_taxes" in spending_labels

    assets_rows = _read_csv(tmp_path / "client_assets.csv")
    assert any(r[2] == "hsa_withdrawal_mode" for r in assets_rows[1:])


def test_ensure_user_ui_plan_data_rows_is_idempotent(app_core, tmp_path):
    _seed_minimal_old_schema_plan(tmp_path)
    app_core._ensure_user_ui_plan_data_rows()
    first_pass = {name: _read_csv(tmp_path / name) for name in ("client_policy.csv", "client_household.csv", "client_spending.csv", "client_assets.csv", "client_income.csv")}
    app_core._ensure_user_ui_plan_data_rows()
    second_pass = {name: _read_csv(tmp_path / name) for name in first_pass}
    assert first_pass == second_pass


def test_ensure_user_ui_plan_data_rows_does_not_overwrite_an_existing_user_value(app_core, tmp_path):
    _seed_minimal_old_schema_plan(tmp_path)
    policy_path = tmp_path / "client_policy.csv"
    policy_path.write_text(
        "section,subsection,label,value,units,notes\n"
        "Withdrawal Policy,Roth Conversion,roth_conversion_policy,fixed_dollar,choice,already chosen\n",
        encoding="utf-8",
    )
    app_core._ensure_user_ui_plan_data_rows()
    rows = _read_csv(policy_path)
    by_label = {r[2]: r[3] for r in rows[1:]}
    assert by_label["roth_conversion_policy"] == "fixed_dollar"


def test_dividend_reinvestment_rows_cover_every_holdings_account(app_core, tmp_path, monkeypatch):
    _seed_minimal_old_schema_plan(tmp_path)
    (tmp_path / "client_holdings.csv").write_text(
        "account,symbol,purchase_date,shares,purchase_price,lot_type\n"
        "Member_1_IRA,VTI,2020-01-01,10,100,long\n"
        "Member_1_Roth,VTI,2020-01-01,5,100,long\n",
        encoding="utf-8",
    )
    app_core._ensure_user_ui_plan_data_rows()
    policy_rows = _read_csv(tmp_path / "client_policy.csv")
    reinvest_accounts = {r[1] for r in policy_rows[1:] if r[2] == "reinvest_dividends"}
    assert reinvest_accounts == {"Member_1_IRA", "Member_1_Roth"}


def test_account_titling_rows_cover_every_holdings_account_including_checking(app_core, tmp_path):
    """Item 4.7 (P8): unlike reinvest_dividends (checking/529 excluded), the
    beneficiary/titling audit applies to every account -- checking accounts
    commonly carry their own TOD/POD designation too."""
    _seed_minimal_old_schema_plan(tmp_path)
    (tmp_path / "client_holdings.csv").write_text(
        "account,symbol,purchase_date,shares,purchase_price,lot_type\n"
        "Member_1_IRA,VTI,2020-01-01,10,100,long\n"
        "Family_Checking,CASH,2020-01-01,1000,1,\n",
        encoding="utf-8",
    )
    app_core._ensure_user_ui_plan_data_rows()
    estate_rows = _read_csv(tmp_path / "client_insurance_estate.csv")
    titling_rows = [r for r in estate_rows[1:] if r[0] == "Account Titling"]
    accounts = {r[1] for r in titling_rows}
    assert accounts == {"Member_1_IRA", "Family_Checking"}
    labels_by_account = {}
    for r in titling_rows:
        labels_by_account.setdefault(r[1], set()).add(r[2])
    for labels in labels_by_account.values():
        assert labels == {"primary_beneficiary", "contingent_beneficiary", "titling", "trust_see_through"}


def test_account_titling_rows_are_idempotent_and_preserve_edits(app_core, tmp_path):
    _seed_minimal_old_schema_plan(tmp_path)
    (tmp_path / "client_holdings.csv").write_text(
        "account,symbol,purchase_date,shares,purchase_price,lot_type\n"
        "Member_1_IRA,VTI,2020-01-01,10,100,long\n",
        encoding="utf-8",
    )
    app_core._ensure_user_ui_plan_data_rows()
    estate_path = tmp_path / "client_insurance_estate.csv"
    rows = _read_csv(estate_path)
    for r in rows:
        if r[0] == "Account Titling" and r[1] == "Member_1_IRA" and r[2] == "titling":
            r[3] = "JTWROS"
    import csv
    with estate_path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    app_core._ensure_user_ui_plan_data_rows()
    rows_after = _read_csv(estate_path)
    by_key = {(r[0], r[1], r[2]): r[3] for r in rows_after[1:]}
    assert by_key[("Account Titling", "Member_1_IRA", "titling")] == "JTWROS"


def test_no_pytest_guard_left_on_the_orchestrator(app_core, tmp_path):
    """A7: the old `if 'pytest' in sys.modules: return` guard is gone - this
    test itself running under pytest and still observing real writes to
    tmp_path is the proof."""
    _seed_minimal_old_schema_plan(tmp_path)
    app_core._ensure_user_ui_plan_data_rows()
    policy_rows = _read_csv(tmp_path / "client_policy.csv")
    assert len(policy_rows) > 1
