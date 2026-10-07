"""WP4.1: conversion step C3 (legacy plan CSV set -> plan_rows), not wired into startup."""
from __future__ import annotations

import hashlib

import pytest

from src.data_io import load_csv as legacy_load
from src.csv_exchange import PlanCsvError, parse_plan_csv
from src.legacy_conversion.steps import c3_plan_rows as c3
from src.plan_data_migration import _target_key, migrate_sectioned_data
from src.stores import PlanStore
from tests import plan_fixture as pf

HEADER = "section,subsection,label,value,units,notes\n"


def _digest(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


@pytest.mark.parametrize("fixture", sorted(pf.FIXTURES))
def test_c3_equals_what_the_old_engine_path_saw(tmp_path, fixture):
    ws = pf.make_plan(tmp_path, fixture)
    before = _digest(ws.input_dir)
    with PlanStore.open(tmp_path / "converted.rpx") as store:
        report = c3.run(ws.input_dir, store)
        view = store.sectioned_data()
        rows = store.all_rows()
        marker = store.get_meta(c3.MARKER_KEY)
    expected, _ = migrate_sectioned_data(legacy_load(ws.input_dir / "client_data.csv"))
    assert view == expected
    assert report.legacy_renamed == 7 and report.retired_dropped == 0 and not report.skipped
    assert report.rows_written == len(rows) == report.source.rows
    assert marker == f"rows={len(rows)} legacy_renamed=7 retired_dropped=0"
    # no legacy key survives; notes (and the attached group comments) do
    assert all(_target_key([r["section"], r["subsection"], r["label"]]) ==
               (r["section"], r["subsection"], r["label"]) for r in rows)
    assert any("Forced Roth Conversions" in r["notes"] for r in rows)
    # originals are only read
    assert _digest(ws.input_dir) == before


def test_c3_rerun_is_a_noop_and_a_used_plan_is_refused(tmp_path):
    ws = pf.make_plan(tmp_path)
    with PlanStore.open(":memory:") as store:
        first = c3.run(ws.input_dir, store)
        rev = store.revision()
        again = c3.run(ws.input_dir, store)
        assert again.skipped and again.rows_written == 0 and store.revision() == rev
        assert first.as_dict()["source"]["files_missing"] == []
    with PlanStore.open(":memory:") as store:
        store.insert_row("Household", label="member_1_name", value="Pat")
        with pytest.raises(PlanCsvError, match="already has rows"):
            c3.run(ws.input_dir, store)
        assert store.get_meta(c3.MARKER_KEY) is None and len(store.all_rows()) == 1
    with PlanStore.open(":memory:") as store, pytest.raises(c3.ConversionError, match="no plan CSV"):
        c3.run(tmp_path / "empty", store)


def test_convert_rows_renames_once_current_key_wins_and_drops_retired_labels():
    text = HEADER + (
        "Household,Members,husband_name,Old Name,,\n"
        "Household,Members,member_1_name,New Name,,\n"     # current key exists: legacy row dropped
        "Household,Members,wife_name,Sam,,\n"              # renamed
        "Social Security,Wife,claim_age,67,,\n"            # subsection renamed
        "Scenarios,Sell Home,home_value,900000,,\n"        # retired label dropped
        "Scenarios,Sell Home,home_sale_year,2045,,\n"
    )
    rows, renamed, retired = c3.convert_rows(parse_plan_csv(text, "client_household.csv").rows)
    assert [(r.section, r.subsection, r.label, r.value) for r in rows] == [
        ("Household", "Members", "member_1_name", "New Name"),
        ("Household", "Members", "member_2_name", "Sam"),
        ("Social Security", "Member 2", "claim_age", "67"),
        ("Scenarios", "Sell Home", "home_sale_year", "2045"),
    ]
    assert (renamed, retired) == (3, 1)
    assert rows[1].source_file == "client_household.csv" and rows[1].line == 4


def test_retired_label_set_has_one_source():
    # WP4.1 review: the runtime sync and step C3 both use src/plan_label_rules.
    import inspect
    from src import active_plan, plan_label_rules
    assert not hasattr(c3, "RETIRED_SCENARIO_HOME_LABELS")
    assert not hasattr(active_plan, "RETIRED_SCENARIO_HOME_LABELS")
    for module in (c3, active_plan):
        assert "is_retired_scenario_home_row" in inspect.getsource(module)
    assert plan_label_rules.is_retired_scenario_home_row("Scenarios", "Sell Home", "home_value")
    assert not plan_label_rules.is_retired_scenario_home_row("Scenarios", "Base", "home_value")
