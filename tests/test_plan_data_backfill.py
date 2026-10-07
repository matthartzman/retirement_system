"""Tests for src/plan_data_backfill.py (system review item A7, Wave 3 3.12; plan rows WP4.4c).

The generic engine against a PlanStore, and src/server/app_core.py's PLAN_DATA_BACKFILL_ENTRIES
table through the real ``_ensure_user_ui_plan_data_rows`` on a plan built by ``make_plan``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plan_data_backfill import (
    BackfillEntry,
    after_last,
    apply_backfill,
    before_first,
    label_is,
    pending_rows,
    subsection_is,
)
from src.stores import PlanStore
from tests.plan_fixture import make_plan


@pytest.fixture
def store(tmp_path):
    s = PlanStore.open(tmp_path / "unit.rpx", create=True)
    yield s
    s.close()


def _seed(store, rows):
    for section, sub, label, value in rows:
        store.insert_row(section, subsection=sub, label=label, value=value)


def _labels(store, section):
    return [r["label"] for r in store.rows(section)]


# -- Generic engine --------------------------------------------------------

def test_before_first_lands_before_first_match(store):
    _seed(store, [("Alpha", "", "x", "1"), ("Alpha", "S", "y", "2"), ("Alpha", "S", "y2", "2")])
    apply_backfill(store, [BackfillEntry([["Alpha", "", "z", "3", "", ""]], before_first(subsection_is("S")))])
    assert _labels(store, "Alpha") == ["x", "z", "y", "y2"]


def test_no_anchor_and_no_match_append_at_the_end_of_the_section(store):
    _seed(store, [("Alpha", "", "x", "1")])
    apply_backfill(store, [
        BackfillEntry([["Alpha", "", "a", "3", "", ""]]),
        BackfillEntry([["Alpha", "", "b", "3", "", ""]], before_first(label_is("nope"))),
        BackfillEntry([["Alpha", "", "c", "3", "", ""]], after_last(subsection_is("nope"))),
    ])
    assert _labels(store, "Alpha") == ["x", "a", "b", "c"]


def test_after_last_lands_after_the_last_matching_row_not_the_first(store):
    _seed(store, [("Cashflow", "Spending", "a", "1"), ("Cashflow", "Spending", "b", "2"), ("Cashflow", "Mortgage", "c", "3")])
    apply_backfill(store, [BackfillEntry([["Cashflow", "Spending", "new_row", "9", "", ""]], after_last(subsection_is("Spending")))])
    assert _labels(store, "Cashflow") == ["a", "b", "new_row", "c"]


def test_new_section_is_created_and_row_fields_are_kept(store):
    added = apply_backfill(store, [BackfillEntry([["Sec", "Sub", "lbl", "v", "u", "n"]])])
    assert added == 1
    (row,) = store.rows("Sec")
    assert (row["subsection"], row["label"], row["value"], row["units"], row["notes"]) == ("Sub", "lbl", "v", "u", "n")


def test_existing_row_is_never_duplicated_or_overwritten(store):
    _seed(store, [("Sec", "Sub", "lbl", "already-here")])
    revision = store.revision()
    entry = BackfillEntry([["Sec", "Sub", "lbl", "different-value-same-key", "", ""]])
    assert pending_rows(store, [entry]) == []
    assert apply_backfill(store, [entry]) == 0
    assert [r["value"] for r in store.rows("Sec")] == ["already-here"]
    assert store.revision() == revision  # an unchanged plan is not written


def test_a_key_added_by_an_earlier_entry_is_not_added_again(store):
    row = [["Sec", "", "dup", "1", "", ""]]
    assert apply_backfill(store, [BackfillEntry(row), BackfillEntry(row)]) == 1


def test_one_entry_spanning_sections_inserts_each_section_as_a_group(store):
    _seed(store, [("Model Constants", "A", "a1", "1"), ("Withdrawal Policy", "B", "b1", "1")])
    apply_backfill(store, [BackfillEntry([
        ["Model Constants", "A", "m1", "", "", ""], ["Withdrawal Policy", "B", "w1", "", "", ""],
        ["Model Constants", "A", "m2", "", "", ""]])])
    assert _labels(store, "Model Constants") == ["a1", "m1", "m2"]
    assert _labels(store, "Withdrawal Policy") == ["b1", "w1"]


def test_later_entry_anchor_sees_an_earlier_entrys_insertion(store):
    _seed(store, [("Economic Assumptions", "", "x", "1"), ("Economic Assumptions", "Z", "tail", "1")])
    anchor = after_last(subsection_is(""))
    apply_backfill(store, [
        BackfillEntry([["Economic Assumptions", "", "first_new", "a", "", ""]], anchor),
        BackfillEntry([["Economic Assumptions", "", "second_new", "b", "", ""]], anchor),
    ])
    assert _labels(store, "Economic Assumptions") == ["x", "first_new", "second_new", "tail"]


def test_dynamic_row_source_callable_is_invoked_with_source_dir(store, tmp_path):
    calls = []

    def dynamic_rows(source_dir):
        calls.append(source_dir)
        return [["Account Policy", "acct1", "x", "", "", ""], ["Account Policy", "acct2", "x", "", "", ""]]

    assert apply_backfill(store, [BackfillEntry(dynamic_rows)], tmp_path) == 2
    assert calls == [tmp_path]


# -- Integration: the real app_core entries table, on a plan_rows plan ------

@pytest.fixture
def ws(tmp_path, monkeypatch):
    import src.server.app_core as ac
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    return plan


def _strip_backfilled(ws):
    """Remove every canonical row from the plan and from its CSV working copy, so the backfill has
    work to do (a plan from before these controls existed)."""
    import src.server.app_core as ac
    keys = {(r[0], r[1], r[2]) for e in ac.PLAN_DATA_BACKFILL_ENTRIES if not callable(e.rows) for r in e.rows}
    with ac._edit_active_plan() as edit:
        for row in edit.store.all_rows():
            if (row["section"], row["subsection"], row["label"]) in keys:
                edit.store.delete_row(row["row_id"])
    return keys


def _values(ws):
    with ws.store(readonly=True) as store:
        return {(r["section"], r["subsection"], r["label"]): r["value"] for r in store.all_rows()}


def test_ensure_rows_backfills_expected_canonical_rows_and_writes_the_csv_copy(ws):
    import src.server.app_core as ac
    keys = _strip_backfilled(ws)
    assert not keys & set(_values(ws))
    ac._ensure_user_ui_plan_data_rows()
    values = _values(ws)
    assert keys <= set(values)
    labels = {k[2] for k in values}
    for label in ("allocation_selection_mode", "mc_engine_mode", "roth_conversion_policy", "tlh_policy",
                  "reinvest_dividends_default", "cash_yield_rate", "inflation_general",
                  "core_spending_growth_mode", "annual_real_estate_taxes", "hsa_withdrawal_mode"):
        assert label in labels
    # the CSV working copy (kept until 4.5) holds them too, so a CSV writer cannot drop them
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(ws.input_dir.glob("client_*.csv")))
    assert "allocation_selection_mode" in text and "tlh_policy" in text


def test_ensure_rows_is_idempotent_and_leaves_row_ids_alone(ws):
    import src.server.app_core as ac
    _strip_backfilled(ws)
    ac._ensure_user_ui_plan_data_rows()
    with ws.store(readonly=True) as store:
        first = store.all_rows()
        revision = store.revision()
    ac._ensure_user_ui_plan_data_rows()
    with ws.store(readonly=True) as store:
        assert store.all_rows() == first
        assert store.revision() == revision


def test_ensure_rows_does_not_overwrite_an_existing_user_value(ws):
    import src.server.app_core as ac
    _strip_backfilled(ws)
    with ac._edit_active_plan() as edit:
        edit.store.insert_row("Withdrawal Policy", subsection="Roth Conversion", label="roth_conversion_policy",
                              value="fixed_dollar", units="choice", notes="already chosen")
    ac._ensure_user_ui_plan_data_rows()
    assert _values(ws)[("Withdrawal Policy", "Roth Conversion", "roth_conversion_policy")] == "fixed_dollar"


def test_ensure_rows_skips_a_plan_with_no_rows(tmp_path, monkeypatch):
    import src.server.app_core as ac
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    ac._ensure_user_ui_plan_data_rows()
    assert not (tmp_path / "input").exists() or not list((tmp_path / "input").glob("client_*.csv"))


def test_ensure_rows_does_not_fail_when_the_csv_copy_cannot_be_read(ws):
    import src.server.app_core as ac
    _strip_backfilled(ws)
    (ws.input_dir / "client_policy.csv").write_text('section,subsection,label,value,units,notes\n"unterminated', encoding="utf-8")
    ac._ensure_user_ui_plan_data_rows()  # no exception


def test_dividend_reinvestment_and_titling_rows_cover_every_holdings_account(ws):
    import src.server.app_core as ac
    (ws.input_dir / "client_holdings.csv").write_text(
        "account,symbol,purchase_date,shares,purchase_price,lot_type\n"
        "Member_1_IRA,VTI,2020-01-01,10,100,long\n"
        "Family_Checking,CASH,2020-01-01,1000,1,\n",
        encoding="utf-8")
    with ac._edit_active_plan() as edit:
        for row in edit.store.all_rows():
            if row["section"] in ("Account Titling", "Account Policy") and row["label"] in (
                    "reinvest_dividends", "primary_beneficiary", "contingent_beneficiary", "titling", "trust_see_through"):
                edit.store.delete_row(row["row_id"])
    ac._ensure_user_ui_plan_data_rows()
    values = _values(ws)
    assert {k[1] for k in values if k[0] == "Account Policy" and k[2] == "reinvest_dividends"} >= {"Member_1_IRA"}
    assert "Family_Checking" not in {k[1] for k in values if k[0] == "Account Policy" and k[2] == "reinvest_dividends"}
    titled = {k[1] for k in values if k[0] == "Account Titling"}
    assert {"Member_1_IRA", "Family_Checking"} <= titled
    for acct in ("Member_1_IRA", "Family_Checking"):
        assert {k[2] for k in values if k[:2] == ("Account Titling", acct)} == {
            "primary_beneficiary", "contingent_beneficiary", "titling", "trust_see_through"}
