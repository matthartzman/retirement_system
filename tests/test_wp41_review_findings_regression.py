"""WP4.1 review findings, pinned.

1. duplicate keys collapse at import (last value, first position): no stale copy
2. conversion step C3 is last-wins for two legacy rows of one key, like the old path
3. columns are found by header NAME, as the old DictReader readers did
4. the year-label table and the retired Sell Home label set have one source module
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import data_io
from src.csv_exchange import (
    PlanCsvError,
    collapse_duplicate_keys,
    import_plan_csv_set,
    parse_plan_csv,
    read_plan_csv_set,
    sync_plan_rows,
    write_plan_rows,
)
from src.legacy_conversion.steps import c3_plan_rows as c3
from src.plan_data_migration import migrate_sectioned_data
from src.stores import PlanStore
from tests import plan_fixture as pf

HEADER = "section,subsection,label,value,units,notes\n"
SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def store():
    s = PlanStore.open(":memory:")
    yield s
    s.close()


def _folder(tmp_path, **files):
    for name, text in files.items():
        (tmp_path / f"{name}.csv").write_text(text, encoding="utf-8")
    return tmp_path


def _old_view(folder):
    """What the old path saw: load_csv over the set, then migrate_sectioned_data."""
    data = data_io.load_csv(Path(folder) / "client_data.csv")
    migrate_sectioned_data(data)
    return data


# --------------------------------------------------------------------------- 1
def test_duplicate_keys_collapse_to_the_last_value_at_the_first_position(store, tmp_path):
    folder = _folder(
        tmp_path,
        client_data=HEADER + "Scenarios,Base,growth,1,pct,anchor copy\nScenarios,Base,other,5,,\n",
        client_policy=HEADER + "Scenarios,Base,growth,2,pct,policy copy\n",
    )
    report = import_plan_csv_set(folder, store)
    assert report.rows == 2 and report.duplicates_collapsed == 1
    rows = store.rows("Scenarios")
    assert [(r["label"], r["value"], r["notes"]) for r in rows] == [("growth", "2", "policy copy"), ("other", "5", "")]
    assert store.sectioned_data() == data_io.load_csv(folder / "client_data.csv")


def test_deleting_or_editing_the_effective_row_cannot_resurface_a_stale_copy(store, tmp_path):
    folder = _folder(
        tmp_path,
        client_data=HEADER + "Scenarios,Base,growth,OLD,,\n",
        client_policy=HEADER + "Scenarios,Base,growth,NEW,,\n",
    )
    import_plan_csv_set(folder, store)
    (row,) = store.rows("Scenarios")
    store.set_row(row["row_id"], value="EDITED")
    assert store.sectioned_data()["Scenarios"]["Base"]["growth"] == "EDITED"
    store.delete_row(row["row_id"])
    assert "Scenarios" not in store.sectioned_data()
    assert store.all_rows() == []


def test_the_anchor_duplicates_of_the_fixtures_are_one_row_each(tmp_path):
    ws = pf.make_plan(tmp_path, "sample_frozen")
    with ws.store(readonly=True) as plan:
        keys = [(r["section"], r["subsection"], r["label"]) for r in plan.all_rows()]
    assert len(keys) == len(set(keys))
    assert ws.store_data() == ws.data()


def test_writers_collapse_too(store):
    rows = parse_plan_csv(HEADER + "A,,k,1,,\nA,,x,2,,\nA,,k,3,,\n", "client_x.csv").rows
    assert len(rows) == 3
    collapsed, n = collapse_duplicate_keys(rows)
    assert n == 1 and [(r.label, r.value) for r in collapsed] == [("k", "3"), ("x", "2")]
    assert write_plan_rows(store, rows) == 2
    assert [(r["label"], r["value"]) for r in store.rows("A")] == [("k", "3"), ("x", "2")]
    sync_plan_rows(store, rows)
    assert len(store.rows("A")) == 2


# --------------------------------------------------------------------------- 2
def test_c3_is_last_wins_for_two_legacy_rows_of_one_key(store, tmp_path):
    folder = _folder(tmp_path, client_data=HEADER + "Household,,husband_name,First,,\n"
                                                    "Household,,wife_name,W,,\n"
                                                    "Household,,husband_name,Last,,\n")
    report = c3.run(folder, store)
    view = store.sectioned_data()
    assert view["Household"][""]["member_1_name"] == "Last"
    assert view == _old_view(folder)
    assert [r["label"] for r in store.rows("Household")] == ["member_1_name", "member_2_name"]
    assert report.rows_written == 2


def test_c3_current_key_still_wins_over_legacy_rows(store, tmp_path):
    folder = _folder(tmp_path, client_data=HEADER + "Household,,husband_name,Old,,\n"
                                                    "Household,,member_1_name,Current,,\n"
                                                    "Household,,husband_name,Older,,\n")
    c3.run(folder, store)
    assert store.sectioned_data()["Household"][""] == {"member_1_name": "Current"}
    assert store.sectioned_data() == _old_view(folder)


def test_convert_rows_collapses_before_renaming():
    rows = parse_plan_csv(HEADER + "Household,,husband_name,1,,\nHousehold,,husband_name,2,,\n", "client_household.csv").rows
    out, _, _ = c3.convert_rows(rows)
    assert [(r.label, r.value) for r in out] == [("member_1_name", "2")]


# --------------------------------------------------------------------------- 3
@pytest.mark.parametrize("header", [
    "label,section,subsection,value,units,notes",            # reordered columns
    "section,subsection,label,value,units,notes,extra,more",  # extra columns
    "section,subsection,label,value,unit,note",               # 'unit' / 'note' variants
    "section,subsection,label,value,type,notes",              # the optimizer-controls file
    "section,subsection,label,value",                         # no units / notes at all
    "notes,value,label,subsection,section,units",             # fully reversed
])
def test_every_header_the_old_reader_accepted_reads_the_same_values(store, tmp_path, header):
    names = [h.strip().lower() for h in header.split(",")]
    record = {"section": "Household", "subsection": "", "label": "member_1_name", "value": "Pat",
              "units": "text", "unit": "text", "type": "text", "notes": "n", "note": "n",
              "extra": "x", "more": "y"}
    second = dict(record, subsection="Sub", label="annual_spending_2026", value="40000")
    lines = [header] + [",".join(rec[n] for n in names) for rec in (record, second)]
    folder = _folder(tmp_path, client_data="\n".join(lines) + "\n")
    import_plan_csv_set(folder, store)
    view = store.sectioned_data()
    assert view == data_io.load_csv(folder / "client_data.csv")
    assert view["Household"]["Sub"]["annual_spending_base_year"] == "40000"
    assert view["Household"][""]["member_1_name"] == "Pat"


def test_header_names_are_compared_stripped_and_case_insensitively():
    # the old readers accepted such a file (and read nothing from it); the importer reads it
    parsed = parse_plan_csv("Section, Subsection ,LABEL,Value,Units,Notes\nA,s,x,1,u,n\n", "client_x.csv")
    assert [(r.section, r.subsection, r.label, r.value) for r in parsed.rows] == [("A", "s", "x", "1")]


def test_a_missing_value_or_subsection_column_reads_as_empty(store, tmp_path):
    folder = _folder(tmp_path, client_data="section,label\nA,x\n")
    import_plan_csv_set(folder, store)
    assert store.sectioned_data() == data_io.load_csv(folder / "client_data.csv") == {"A": {"": {"x": ""}}}


def test_the_row_fields_follow_the_named_columns(tmp_path):
    parsed = parse_plan_csv("notes,units,value,label,subsection,section\nthe note,usd,5,k,s,A\n", "client_x.csv")
    (row,) = parsed.rows
    assert (row.section, row.subsection, row.label, row.value, row.units, row.notes) == \
        ("A", "s", "k", "5", "usd", "the note")


def test_a_file_without_a_section_or_label_column_is_still_refused():
    for header in ("subsection,label,value", "section,subsection,value", "a,b,c"):
        with pytest.raises(PlanCsvError, match="not a plan CSV"):
            parse_plan_csv(header + "\nx,y,z\n", "client_x.csv")


def test_the_shipped_files_still_parse_to_the_same_view(tmp_path):
    for fixture in sorted(pf.FIXTURES):
        ws = pf.make_plan(tmp_path / fixture, fixture)
        assert ws.store_data() == ws.data()


# --------------------------------------------------------------------------- 4
def test_one_source_for_the_year_label_and_retired_label_rules():
    from src import active_plan, plan_label_rules
    from src.csv_exchange import plan_csv
    assert plan_csv.canonical_label is plan_label_rules.canonical_label
    assert data_io._normalize_label is plan_label_rules.canonical_label
    for name in ("data_io.py", "config_backend.py", "csv_exchange/plan_csv.py", "active_plan.py",
                 "legacy_conversion/steps/c3_plan_rows.py"):
        text = (SRC / name).read_text(encoding="utf-8")
        assert "annual_spending_\\d" not in text, f"{name} carries its own year-label table"
        assert "current_home_value" not in text, f"{name} carries its own retired-label set"
    assert not hasattr(active_plan, "RETIRED_SCENARIO_HOME_LABELS")
    assert not hasattr(c3, "RETIRED_SCENARIO_HOME_LABELS")


def test_canonical_label_behaviour_is_unchanged():
    from src.plan_label_rules import canonical_label
    assert canonical_label("  annual_spending_2026 ") == "annual_spending_base_year"
    assert canonical_label("balance_4_1_2026") == "balance_as_of_plan_start"
    assert canonical_label("part_b_premium_2026") == "part_b_base_premium_monthly"
    assert canonical_label("annual_spending_26") == "annual_spending_26"
    assert canonical_label(None) == ""
