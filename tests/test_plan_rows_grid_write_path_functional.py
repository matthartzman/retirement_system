"""WP4.3 / WP4.5: the grid and ``/api/plan/forms`` write ``plan_rows``, and only the rows.

The grid (``/api/config/rows``) addresses rows by ``row_index`` = ``plan_rows.row_id`` and
writes them in one transaction; ``/api/plan/forms`` reads and writes the same rows. Since WP4.5
no CSV working copy exists: an edit is the plan file's rows and nothing else, and no part file
in ``input/`` is written.
"""
from __future__ import annotations

import hashlib

import pytest

from src.config_backend import load_active_config
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
HOME = ("Other Assets", "Home", "value_as_of_plan_start")
APPRECIATION = ("Other Assets", "Home", "appreciation_rate")
RETIRE = ("Household", "", "member_2_retirement_date")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return plan


def _grid(client):
    resp = client.get("/api/config/rows", headers=HEADERS)
    assert resp.status_code == 200
    return resp.get_json()


def _row(payload, key):
    return next(r for r in payload["rows"] if (r["section"], r["subsection"], r["label"]) == key)


def _save(client, updates):
    resp = client.post("/api/config/rows", headers=HEADERS, json={"updates": updates})
    return resp.status_code, resp.get_json()


def _plan_value(key):
    return load_active_config()[0][key[0]][key[1]][key[2]]


def _csv_hashes(ws):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ws.input_dir.glob("*.*"))}


def test_row_index_is_the_plan_row_id_and_stays_put(ws):
    client = app.test_client()
    first = _grid(client)
    row = _row(first, HOME)
    with ws.store() as store:
        (plan_row,) = store.find_rows(*HOME)
        revision = store.revision()
    assert row["row_index"] == plan_row["row_id"] and row["value"] == plan_row["value"]
    assert first["revision"] == revision
    assert {"source_file", "source_row_index", "columns"}.isdisjoint(row)
    assert "warning" not in first
    assert len({r["row_index"] for r in first["rows"]}) == len(first["rows"])
    status, out = _save(client, [{"row_index": row["row_index"], "value": "$1,500,000"}])
    assert status == 200 and out["updated"] == 1 and out["revision"] != revision
    assert "sync" not in out
    again = _grid(client)
    assert [r["row_index"] for r in again["rows"]] == [r["row_index"] for r in first["rows"]]
    assert _row(again, HOME)["value"] == "$1,500,000" and again["revision"] == out["revision"]


def test_an_edit_writes_the_plan_rows_and_no_file(ws):
    """No CSV working copy: a grid save, a form patch and a strategy save leave ``input/`` as it was."""
    client = app.test_client()
    home = _row(_grid(client), HOME)
    before = _csv_hashes(ws)
    status, _ = _save(client, [{"row_index": home["row_index"], "value": "$1,777,777"}])
    assert status == 200 and _plan_value(HOME) == "$1,777,777"
    resp = client.patch("/api/plan/forms/Other Assets/Home", headers=HEADERS,
                        json={"values": {"value_as_of_plan_start": "$1,888,888"}})
    assert resp.status_code == 200 and _plan_value(HOME) == "$1,888,888"
    resp = client.post("/api/liquidity-buffers", headers=HEADERS, json={"buffers": [
        {"start_year": "2031", "end_year": "2036", "years_of_expenses": "3", "reserve_account": "Cash"}]})
    assert resp.status_code == 200
    assert load_active_config()[0]["Liquidity Buffer"]["buffer_1"]["reserve_account"] == "Cash"
    assert _plan_value(HOME) == "$1,888,888"  # the strategy save did not undo the form edit
    assert _csv_hashes(ws) == before


def test_a_validation_failure_rolls_back_every_update(ws):
    client = app.test_client()
    grid = _grid(client)
    home, rate = _row(grid, HOME), _row(grid, APPRECIATION)
    status, out = _save(client, [{"row_index": home["row_index"], "value": "$2,000,000"},
                                 {"row_index": rate["row_index"], "value": "not a percent"}])
    assert status == 422 and out["error"] == "Plan Data validation failed"
    assert any("appreciation_rate" in e for e in out["errors"])
    assert _plan_value(HOME) == home["value"] and _grid(client)["revision"] == grid["revision"]


def test_a_stale_row_index_is_skipped_and_reported(ws):
    client = app.test_client()
    status, out = _save(client, [{"row_index": 10**9, "value": "x"}, {"row_index": "nope", "value": "x"}])
    assert status == 200 and out["updated"] == 0
    assert [s["reason"] for s in out["skipped"]] == ["out of range or stale row index", "invalid row_index"]


def test_forms_and_grid_share_one_row_store(ws):
    client = app.test_client()
    home = _row(_grid(client), HOME)
    _save(client, [{"row_index": home["row_index"], "value": "$1,234,000"}])
    forms = client.get("/api/plan/forms", headers=HEADERS).get_json()
    assert forms["sections"]["Other Assets"]["Home"]["value_as_of_plan_start"] == "$1,234,000"
    assert "warning" not in forms

    resp = client.patch("/api/plan/forms/Other Assets/Home", headers=HEADERS,
                        json={"values": {"value_as_of_plan_start": " $1,345,000 "}})
    assert resp.status_code == 200 and resp.get_json()["values"]["value_as_of_plan_start"] == "$1,345,000"
    # the grid sees the form edit on the same row id
    assert _row(_grid(client), HOME) == dict(home, value="$1,345,000")


def test_forms_apply_the_label_rules(ws):
    client = app.test_client()
    resp = client.patch("/api/plan/forms/Scenarios/Sell Home", headers=HEADERS,
                        json={"values": {"home_value": "1", "home_sale_year": "2044"}})
    payload = resp.get_json()
    assert resp.status_code == 200 and payload["skipped"] == ["home_value"]  # retired label
    resp = client.patch("/api/plan/forms/Cashflow/Spending", headers=HEADERS,
                        json={"values": {"annual_spending_2031": "$99,000", "label": "x"}})
    payload = resp.get_json()
    assert payload["skipped"] == ["label"]
    data = load_active_config()[0]
    assert data["Cashflow"]["Spending"]["annual_spending_base_year"] == "$99,000"
    assert "annual_spending_2031" not in data["Cashflow"]["Spending"]
    assert "home_value" not in data["Scenarios"]["Sell Home"]
    assert data["Scenarios"]["Sell Home"]["home_sale_year"] == "2044"


def test_forms_post_replaces_by_key_and_keeps_row_ids(ws):
    client = app.test_client()
    home = _row(_grid(client), HOME)  # the grid GET's backfill runs first (it adds rows)
    sections = client.get("/api/plan/forms", headers=HEADERS).get_json()["sections"]
    sections["Other Assets"]["Home"]["value_as_of_plan_start"] = "$1,111,111"
    del sections["Liquidity Buffer"]["buffer_1"]["reserve_account"]
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": sections, "replace": True})
    assert resp.status_code == 200 and resp.get_json()["sections"] == sections
    assert _row(_grid(client), HOME)["row_index"] == home["row_index"]
    data = load_active_config()[0]
    assert data["Other Assets"]["Home"]["value_as_of_plan_start"] == "$1,111,111"
    assert "reserve_account" not in data["Liquidity Buffer"]["buffer_1"]


def test_forms_post_never_deletes_without_replace_and_only_inside_posted_sections(ws):
    """A partial payload must not delete."""
    client = app.test_client()
    _grid(client)
    before = client.get("/api/plan/forms", headers=HEADERS).get_json()["sections"]
    partial = {"Other Assets": {"Home": {"value_as_of_plan_start": "$2,222,222"}}}
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": partial})
    out = resp.get_json()
    assert resp.status_code == 200 and out["replace"] is False
    expected = {sec: {sub: dict(vals) for sub, vals in subs.items()} for sec, subs in before.items()}
    expected["Other Assets"]["Home"]["value_as_of_plan_start"] = "$2,222,222"
    assert out["sections"] == expected
    assert "reserve_account" in load_active_config()[0]["Liquidity Buffer"]["buffer_1"]
    # flagged complete, it replaces the sections it names (here: one subsection of Other Assets)
    # and leaves every other section alone
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": partial, "replace": True})
    out = resp.get_json()
    assert resp.status_code == 200 and out["replace"] is True
    assert out["sections"]["Other Assets"] == partial["Other Assets"]
    assert {k: v for k, v in out["sections"].items() if k != "Other Assets"} == \
        {k: v for k, v in expected.items() if k != "Other Assets"}


def test_roth_controls_are_stored_canonical_whichever_endpoint_wrote_them(ws):
    """The edit transaction makes the Roth controls canonical in the rows before it commits."""
    client = app.test_client()
    grid = _grid(client)
    bracket = ("Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate")
    row = _row(grid, bracket)
    status, _ = _save(client, [{"row_index": row["row_index"], "value": "22%"}])
    assert status == 200 and _plan_value(bracket) == "22.00%"
    resp = client.patch("/api/plan/forms/Withdrawal Policy/Roth Conversion", headers=HEADERS,
                        json={"values": {"roth_target_bracket_rate": "24%"}})
    assert resp.status_code == 200 and _plan_value(bracket) == "24.00%"


def test_a_blanked_retirement_date_is_kept_by_every_writer(ws):
    """A save that blanks a protected retirement date keeps the stored one (the rule every plan
    write follows): the grid refuses the blank outright (the field is required), the forms
    endpoint stores the other values and keeps the date."""
    client = app.test_client()
    grid = _grid(client)
    protected, home = _row(grid, RETIRE), _row(grid, HOME)
    assert protected["value"]
    status, out = _save(client, [{"row_index": protected["row_index"], "value": ""}])
    assert status == 422 and _plan_value(RETIRE) == protected["value"]
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": {
        "Household": {"": {"member_2_retirement_date": ""}}, "Other Assets": {"Home": {"value_as_of_plan_start": "$1,500,001"}}}})
    assert resp.status_code == 200
    assert _plan_value(RETIRE) == protected["value"] and _plan_value(HOME) == "$1,500,001"
    # another non-blank date replaces it, through the grid; the grid reports a value the plan
    # did not keep (here: an unchanged date) as updated only when it was kept
    status, out = _save(client, [{"row_index": protected["row_index"], "value": "3/1/2031"}])
    assert status == 200 and out["updated"] == 1 and _plan_value(RETIRE) == "2031-03-01"


def test_the_edit_context_reports_a_value_the_plan_rules_gave_back():
    """``final_values`` is what the plan holds once the edit is complete; the grid reports a
    value that differs from what it set as skipped."""
    from src import active_plan

    with active_plan.edit_active_plan() as edit:
        (row,) = edit.store.find_rows(*RETIRE) or [None]
        if row is None:
            pytest.skip("the session plan has no retirement date row")
        kept = row["value"]
        edit.store.set_row(row["row_id"], value="")
    assert edit.final_values[RETIRE] == kept


def test_a_store_error_while_looking_up_a_row_fails_the_save_not_skips_it(ws, monkeypatch):
    from src.stores import PlanStore, StoreError

    client = app.test_client()
    row = _row(_grid(client), HOME)

    def broken(self, row_id):
        raise StoreError("plan file is corrupt")

    monkeypatch.setattr(PlanStore, "get_row", broken)
    status, out = _save(client, [{"row_index": row["row_index"], "value": "$5"}])
    assert status == 500 and out["success"] is False and "corrupt" in out["error"]
    assert "skipped" not in out
