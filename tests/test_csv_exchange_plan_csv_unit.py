"""WP4.1: the minimal plan-CSV-set importer (src/csv_exchange/plan_csv.py)."""
from __future__ import annotations

import csv

import pytest

from src.csv_exchange import (
    PART_FILE_SECTIONS,
    PLAN_CSV_FILES,
    PlanCsvRow,
    canonical_label,
    import_plan_csv_set,
    parse_plan_csv,
    part_file_for_section,
    read_plan_csv_set,
    write_plan_rows,
)
from src.csv_exchange.plan_csv import PlanCsvError
from src.stores import PlanStore, ValidationError
from tests import plan_fixture as pf

HEADER = "section,subsection,label,value,units,notes,\n"


@pytest.fixture
def store():
    s = PlanStore.open(":memory:")
    yield s
    s.close()


def _rows(text, name="client_x.csv"):
    return parse_plan_csv(text, name)


def test_file_list_and_year_patterns_match_the_legacy_readers():
    from src import data_io
    from src.plan_data_registry import client_data_csv_files
    assert PLAN_CSV_FILES == tuple(client_data_csv_files())
    # one source for the year-label table: data_io and csv_exchange both use plan_label_rules
    from src import plan_label_rules
    assert canonical_label is plan_label_rules.canonical_label
    assert data_io._normalize_label is plan_label_rules.canonical_label
    assert not hasattr(data_io, "_YEAR_LABEL_PATTERNS")
    assert canonical_label("  annual_spending_2026 ") == "annual_spending_base_year"
    assert canonical_label("balance_4_1_2026") == "balance_as_of_plan_start"
    assert canonical_label("plain") == "plain"


def test_cells_are_stripped_and_read_by_header_name():
    out = _rows("\ufeff" + HEADER + ' Household , Members , member_1_name ," Pat ", text , A note \n')
    assert out.report.rows == 1 and out.report.files_read == ["client_x.csv"]
    r = out.rows[0]
    assert (r.section, r.subsection, r.label, r.value, r.units, r.notes) == \
        ("Household", "Members", "member_1_name", "Pat", "text", "A note")
    assert (r.source_file, r.line) == ("client_x.csv", 2)


def test_fifth_column_may_be_called_type_and_other_headers_are_refused():
    ok = _rows("section,subsection,label,value,type,notes\nA,,x,1,number,n\n")
    assert ok.rows[0].units == "number"
    with pytest.raises(PlanCsvError, match="not a plan CSV"):
        _rows("subsection,label,value\ns,x,1\n")


def test_unquoted_commas_in_notes_are_joined_back():
    out = _rows(HEADER + "A,s,x,1,choice,a | b; first part, second part,,\n")
    assert out.rows[0].notes == "a | b; first part, second part"


def test_record_kinds_and_skips_are_reported():
    text = HEADER + (
        ",,,,,,\n"
        "A,,,1,,\n"                      # section without a label
        ",s,x,1,,\n"                     # label without a section
        "section,subsection,label,value,,\n"  # repeated header
        "A,s,x,1,,\n"
    )
    out = _rows(text)
    assert [r.label for r in out.rows] == ["x"]
    assert [s.reason for s in out.report.skipped] == ["no label", "no section", "repeated header"]
    assert [s.line for s in out.report.skipped] == [3, 4, 5]


def test_comment_attached_to_the_row_below_becomes_its_notes():
    text = HEADER + (
        "# -- opening block: the file's header comment --,,,,,\n"
        "A,s,first,1,,n1\n"
        ",,,,,\n"
        "# -- Group heading --,,,,,\n"
        "# second line,,,,,\n"
        "# ==========,,,,,\n"            # decoration only: dropped, does not break the block
        "A,s,second,2,,n2\n"
        "# above nothing,,,,,\n"
        ",,,,,\n"
        "A,s,third,3,,\n"
        ',"# -- in the subsection column --",,,,\n'
        "A,s,fourth,4,,\n"
        "# trailing,,,,,\n"
    )
    out = _rows(text)
    notes = {r.label: r.notes for r in out.rows}
    assert notes == {
        "first": "n1",                                   # opening block dropped
        "second": "n2; Group heading second line",       # attached, '#', rule ends removed
        "third": "",                                     # blank line in between: dropped
        "fourth": "in the subsection column",            # attached (comment in any column)
    }
    assert out.report.comments_attached == 3
    assert out.report.comments_dropped == 4  # opening, decoration, above-nothing, trailing


def test_comment_rows_never_become_data():
    out = _rows(HEADER + "#Household,s,x,1,,\nA,s,x,1,,\n")
    assert [r.section for r in out.rows] == ["A"]


def test_read_set_reads_in_order_and_lists_missing_files(tmp_path):
    (tmp_path / "client_income.csv").write_text(HEADER + "Cashflow,Earned Income,x,1,,\n", encoding="utf-8")
    (tmp_path / "client_data.csv").write_text(HEADER + "Scenarios,Base,y,2,,\n", encoding="utf-8")
    parsed = read_plan_csv_set(tmp_path)
    assert [r.source_file for r in parsed.rows] == ["client_data.csv", "client_income.csv"]
    assert parsed.report.files_read == ["client_data.csv", "client_income.csv"]
    assert set(parsed.report.files_missing) == set(PLAN_CSV_FILES) - {"client_data.csv", "client_income.csv"}


def test_write_assigns_per_section_order_and_keeps_read_order(store, tmp_path):
    (tmp_path / "client_data.csv").write_text(HEADER + "B,,b0,1,,\nA,,a0,1,,\n", encoding="utf-8")
    (tmp_path / "client_household.csv").write_text(HEADER + "A,,a1,1,,\nB,,b1,1,,\nA,,a0,9,,\n",
                                                  encoding="utf-8")
    report = import_plan_csv_set(tmp_path, store)
    assert report.rows == 4 and report.duplicates_collapsed == 1
    assert [(r["label"], r["sort_order"], r["value"]) for r in store.rows("A")] == [("a0", 0, "9"), ("a1", 1, "1")]
    assert [(r["label"], r["sort_order"]) for r in store.rows("B")] == [("b0", 0), ("b1", 1)]
    # sections in first-seen order, the later duplicate wins but keeps the first position
    view = store.sectioned_data()
    assert list(view) == ["B", "A"]
    assert view["A"][""] == {"a0": "9", "a1": "1"}
    assert list(view["A"][""]) == ["a0", "a1"]


def test_write_is_one_transaction_and_needs_an_empty_plan(store, tmp_path):
    store.insert_row("Existing", label="x")
    (tmp_path / "client_data.csv").write_text(HEADER + "A,,a,1,,\n", encoding="utf-8")
    with pytest.raises(PlanCsvError, match="already has rows"):
        import_plan_csv_set(tmp_path, store)
    assert store.sections() == ["Existing"]

    fresh = PlanStore.open(":memory:")
    bad = parse_plan_csv(HEADER + "A,,a,1,,\n", "x.csv").rows
    bad.append(PlanCsvRow("", "", "b", "", "", "", "x.csv", 3))  # empty section: the store refuses it
    with pytest.raises(ValidationError):
        write_plan_rows(fresh, bad)
    assert fresh.sections() == []
    fresh.close()


def test_part_file_mapping_is_the_legacy_primary_file():
    """Every fixture section maps to the first part file that holds it, which is where the
    legacy writers (app_core._client_section_path) put that section's rows."""
    for fixture in pf.FIXTURES:
        first_file: dict[str, str] = {}
        for name in PLAN_CSV_FILES[1:]:
            with (pf.fixture_dir(fixture) / name).open(newline="", encoding="utf-8-sig") as f:
                for row in list(csv.reader(f))[1:]:
                    sec = (row[0] if row else "").strip()
                    if sec and not sec.startswith("#") and len(row) > 2 and row[2].strip():
                        first_file.setdefault(sec, name)
                        assert sec in PART_FILE_SECTIONS[name], (fixture, name, sec)
        for sec, name in first_file.items():
            assert part_file_for_section(sec) == name
    assert part_file_for_section("Brand New Section") == "client_data.csv"
