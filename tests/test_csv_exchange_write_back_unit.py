"""WP4.3: ``csv_exchange.write_back_rows`` writes row-store edits back into the plan CSV set.

The CSV set must read back exactly as the plan rows (or the next CSV-to-rows bridge run would
undo the edit); everything the edit did not touch keeps its layout and comments.
"""
from __future__ import annotations

import pytest

from src.active_plan import _engine_rows
from src.csv_exchange import PlanCsvError, parse_plan_csv, read_plan_csv_set, sync_plan_rows, write_back_rows
from src.stores import PlanStore
from tests import plan_fixture as pf

HEADER = "section,subsection,label,value,units,notes\n"


def _rows_of(texts):
    """What the bridge would store: the plan rows read from ``texts``."""
    rows = []
    for name, text in texts.items():
        rows += parse_plan_csv(text, name).rows
    with PlanStore.open() as store:
        sync_plan_rows(store, _engine_rows(rows))
        return store.all_rows()


def _key(r):
    return (r["section"], r["subsection"], r["label"])


def _view(rows):
    return {_key(r): (r["value"], r["units"], r["notes"]) for r in rows}


def _edit(rows, key, **fields):
    return [dict(r, **fields) if _key(r) == key else r for r in rows]


def test_a_value_edit_changes_only_that_cell_and_keeps_comments():
    text = HEADER + ("Household,,a,1,,first\n"
                     "# about b\n"
                     "Household,,b,2,,n\n"
                     "\n"
                     "Household,,c,3,usd,\n")
    texts = {"client_household.csv": text}
    rows = _rows_of(texts)
    assert _view(rows)[("Household", "", "b")] == ("2", "", "n; about b")
    after = _edit(rows, ("Household", "", "b"), value="22, with comma")
    out = write_back_rows(texts, after, {("Household", "", "b")})
    assert out == {"client_household.csv": text.replace("Household,,b,2,,n", 'Household,,b,"22, with comma",,n')}
    assert _view(_rows_of(out)) == _view(after)


def test_untouched_files_are_not_rewritten():
    texts = {"client_household.csv": HEADER + "Household,,a,1,,\n",
             "client_income.csv": HEADER + "Income Streams,P,amount,5,,\n"}
    rows = _rows_of(texts)
    out = write_back_rows(texts, _edit(rows, ("Household", "", "a"), value="9"), {("Household", "", "a")})
    assert set(out) == {"client_household.csv"}


def test_a_deleted_row_takes_its_attached_comment_and_the_next_row_keeps_its_notes():
    texts = {"client_household.csv": HEADER + ("# file header block\n"
                                               "Household,,a,1,,\n"
                                               "# about b\n"
                                               "Household,,b,2,,n\n"
                                               "# about c\n"
                                               "Household,,c,3,,\n")}
    rows = _rows_of(texts)
    for gone in (("Household", "", "b"), ("Household", "", "a")):  # a: the first data row
        after = [r for r in rows if _key(r) != gone]
        out = write_back_rows(texts, after, {gone})
        assert _view(_rows_of(out)) == _view(after)
        assert "# about c" in out["client_household.csv"] or gone == ("Household", "", "a")
    out = write_back_rows(texts, [r for r in rows if _key(r) != ("Household", "", "b")], {("Household", "", "b")})
    assert "about b" not in out["client_household.csv"] and "# about c" in out["client_household.csv"]


def test_a_new_key_goes_after_the_last_row_of_its_section_and_a_new_section_to_its_primary_file():
    texts = {"client_household.csv": HEADER + "Household,,a,1,,\nWellness,,w,1,,\n# about x\nPayroll Tax,,x,1,,\n",
             "client_spending.csv": HEADER + "Wellness,Out-of-Pocket,w2,2,,\n"}
    rows = _rows_of(texts)
    new = [{"section": "Wellness", "subsection": "Out-of-Pocket", "label": "w3", "value": "3", "units": "", "notes": ""},
           {"section": "Note Receivable", "subsection": "", "label": "n", "value": "4", "units": "u", "notes": "n"},
           {"section": "Household", "subsection": "", "label": "b", "value": "5", "units": "", "notes": "x,y"}]
    after = rows + new
    out = write_back_rows(texts, after, {_key(r) for r in new})
    assert out["client_spending.csv"].endswith("Wellness,Out-of-Pocket,w2,2,,\nWellness,Out-of-Pocket,w3,3,,\n")
    assert out["client_household.csv"].startswith(HEADER + "Household,,a,1,,\nHousehold,,b,5,,\"x,y\"\n")
    assert out["client_assets.csv"] == HEADER + "Note Receivable,,n,4,u,n\n"  # new file, with a header
    assert _view(_rows_of(out)) == _view(after)


def test_a_repeated_key_is_set_on_every_copy_and_deleted_with_every_copy():
    texts = {"client_data.csv": HEADER + "Scenarios,Base,s,old,,\n",
             "client_policy.csv": HEADER + "Scenarios,Base,s,new,,\nScenarios,Base,t,1,,\n"}
    rows = _rows_of(texts)
    key = ("Scenarios", "Base", "s")
    out = write_back_rows(texts, _edit(rows, key, value="v"), {key})
    assert "Scenarios,Base,s,v" in out["client_data.csv"] and "Scenarios,Base,s,v" in out["client_policy.csv"]
    out = write_back_rows(texts, [r for r in rows if _key(r) != key], {key})
    assert out["client_data.csv"] == HEADER and "Base,s," not in out["client_policy.csv"]


def test_a_year_stamped_label_is_found_by_its_canonical_key():
    texts = {"client_spending.csv": HEADER + "Cashflow,Spending,annual_spending_2026,100,,\n"}
    rows = _rows_of(texts)
    key = ("Cashflow", "Spending", "annual_spending_base_year")
    out = write_back_rows(texts, _edit(rows, key, value="200"), {key})
    assert out["client_spending.csv"] == HEADER + "Cashflow,Spending,annual_spending_2026,200,,\n"


def test_a_csv_set_that_does_not_match_the_rows_is_refused_not_overwritten():
    texts = {"client_household.csv": HEADER + "Household,,a,1,,\nHousehold,,b,2,,\n"}
    rows = _rows_of(texts)
    stale = _edit(rows, ("Household", "", "b"), value="changed elsewhere")  # untouched key differs
    with pytest.raises(PlanCsvError):
        write_back_rows(texts, _edit(stale, ("Household", "", "a"), value="9"), {("Household", "", "a")})


@pytest.mark.parametrize("fixture", ["sample_frozen", "demo"])
def test_fixture_sets_read_back_after_edits_deletes_and_inserts(fixture):
    parsed = read_plan_csv_set(pf.fixture_dir(fixture))
    rows = _rows_of(parsed.texts)
    after, touched = [], set()
    for i, r in enumerate(rows):
        if i % 7 == 3:
            touched.add(_key(r))
            continue
        if i % 5 == 0:
            r = dict(r, value=(r["value"] + " edited, x").strip())
            touched.add(_key(r))
        after.append(r)
    extra = {"section": "Household", "subsection": "", "label": "wp43_new", "value": "1", "units": "", "notes": ""}
    out = write_back_rows(parsed.texts, after + [extra], touched | {_key(extra)})
    assert _view(_rows_of({**parsed.texts, **out})) == _view(after + [extra])
