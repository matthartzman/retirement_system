"""WP4.3: the grid and ``/api/plan/forms`` write ``plan_rows``; no edit is lost to a CSV writer.

The grid (``/api/config/rows``) addresses rows by ``row_index`` = ``plan_rows.row_id`` and
writes them in one transaction; ``/api/plan/forms`` reads and writes the same rows. Both write
their touched keys back into the plan CSV set, so the writers that still edit CSV (strategy
endpoints, ``_replace_*``; WP4.4/4.5) and the CSV-to-rows bridge keep the edit.
"""
from __future__ import annotations

import pytest

import src.server.app_core as app_core
from src.config_backend import load_active_config
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
HOME = ("Other Assets", "Home", "value_as_of_plan_start")
APPRECIATION = ("Other Assets", "Home", "appreciation_rate")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(app_core, "CSV_PATH", plan.input_dir / "client_data.csv")
    return plan


def _grid(client):
    resp = client.get("/api/config/rows", headers=HEADERS)
    assert resp.status_code == 200
    return resp.get_json()


def _row(payload, key):
    return next(r for r in payload["rows"] if (r["section"], r["subsection"], r["label"]) == key)


def _save(client, updates, sync=True):
    resp = client.post("/api/config/rows", headers=HEADERS, json={"updates": updates, "sync": sync})
    return resp.status_code, resp.get_json()


def _save_buffers(ws, sync=True):
    """A CSV writer (as the Plan Data file editor): buffer_1 edited in the part file by hand,
    then (``sync``) the bridge. Liquidity buffers themselves are plan rows since WP4.4c."""
    path = ws.input_dir / "client_assets.csv"
    text = path.read_text(encoding="utf-8")
    for label, old, new in (("start_year", "2027", "2031"), ("end_year", "2029", "2036"),
                            ("reserve_account", "Taxable/Trust", "Cash")):
        text = text.replace(f"Liquidity Buffer,buffer_1,{label},{old},", f"Liquidity Buffer,buffer_1,{label},{new},")
    path.write_text(text, encoding="utf-8")
    if sync:
        assert app_core._sync_config_backends()["success"] is True


def _plan_value(key):
    return load_active_config()[0][key[0]][key[1]][key[2]]


def _buffer_1():
    return load_active_config()[0].get("Liquidity Buffer", {}).get("buffer_1", {})


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
    assert len({r["row_index"] for r in first["rows"]}) == len(first["rows"])
    status, out = _save(client, [{"row_index": row["row_index"], "value": "$1,500,000"}])
    assert status == 200 and out["updated"] == 1 and out["revision"] != revision
    again = _grid(client)
    assert [r["row_index"] for r in again["rows"]] == [r["row_index"] for r in first["rows"]]
    assert _row(again, HOME)["value"] == "$1,500,000" and again["revision"] == out["revision"]


def test_grid_edit_then_csv_strategy_edit_then_build_input_keeps_both(ws):
    client = app.test_client()
    home = _row(_grid(client), HOME)
    status, out = _save(client, [{"row_index": home["row_index"], "value": "$1,777,777"}], sync=False)
    assert status == 200 and out["success"] is True
    # the edit is in the CSV set the remaining writers read ...
    assert "$1,777,777" in (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8")
    # ... so a still-CSV writer of the same file (read-modify-write + bridge) keeps it
    _save_buffers(ws)
    assert _plan_value(HOME) == "$1,777,777"
    assert _buffer_1()["reserve_account"] == "Cash"
    after = _grid(client)
    assert _row(after, HOME)["row_index"] == home["row_index"]
    # and a later grid edit keeps the strategy edit
    status, _ = _save(client, [{"row_index": home["row_index"], "value": "$1,888,888"}])
    assert status == 200
    assert _plan_value(HOME) == "$1,888,888" and _buffer_1()["years_of_expenses"] == "2"


def test_a_csv_write_not_yet_synced_is_kept_by_the_next_grid_edit(ws):
    client = app.test_client()
    home = _row(_grid(client), HOME)
    _save_buffers(ws, sync=False)  # CSV written, bridge not run
    status, _ = _save(client, [{"row_index": home["row_index"], "value": "$1,666,666"}], sync=False)
    assert status == 200
    assert _plan_value(HOME) == "$1,666,666" and _buffer_1()["start_year"] == "2031"
    assert "buffer_1" in (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8")


def test_a_validation_failure_rolls_back_every_update(ws):
    client = app.test_client()
    grid = _grid(client)
    home, rate = _row(grid, HOME), _row(grid, APPRECIATION)
    before = (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8")
    status, out = _save(client, [{"row_index": home["row_index"], "value": "$2,000,000"},
                                 {"row_index": rate["row_index"], "value": "not a percent"}])
    assert status == 422 and out["error"] == "Plan Data validation failed"
    assert any("appreciation_rate" in e for e in out["errors"])
    assert _plan_value(HOME) == home["value"] and _grid(client)["revision"] == grid["revision"]
    assert (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8") == before


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

    resp = client.patch("/api/plan/forms/Other Assets/Home", headers=HEADERS,
                        json={"values": {"value_as_of_plan_start": " $1,345,000 "}})
    assert resp.status_code == 200 and resp.get_json()["values"]["value_as_of_plan_start"] == "$1,345,000"
    # the grid sees the form edit on the same row id
    assert _row(_grid(client), HOME) == dict(home, value="$1,345,000")
    # a still-CSV writer and the bridge keep it (the old split brain overwrote it)
    _save_buffers(ws)
    assert app_core._sync_config_backends()["success"] is True
    assert _plan_value(HOME) == "$1,345,000"


def test_forms_apply_the_csv_label_rules(ws):
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
    # and the bridge reads the same back from the CSV set
    assert app_core._sync_config_backends()["success"] is True
    assert load_active_config()[0] == data


def test_forms_post_replaces_by_key_and_keeps_row_ids(ws):
    client = app.test_client()
    home = _row(_grid(client), HOME)  # the grid GET's backfill runs first (it adds rows)
    sections = client.get("/api/plan/forms", headers=HEADERS).get_json()["sections"]
    sections["Other Assets"]["Home"]["value_as_of_plan_start"] = "$1,111,111"
    del sections["Liquidity Buffer"]["buffer_1"]["reserve_account"]
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": sections, "replace": True})
    assert resp.status_code == 200 and resp.get_json()["sections"] == sections
    assert _row(_grid(client), HOME)["row_index"] == home["row_index"]
    assert "reserve_account" not in (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8")
    assert app_core._sync_config_backends()["success"] is True
    assert load_active_config()[0]["Other Assets"]["Home"]["value_as_of_plan_start"] == "$1,111,111"
    assert "reserve_account" not in _buffer_1()


def test_forms_post_never_deletes_without_replace_and_only_inside_posted_sections(ws):
    """A partial payload must not delete: write-back would carry the deletion into the CSV set."""
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
    assert "reserve_account" in (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8")
    # flagged complete, it replaces the sections it names (here: one subsection of Other Assets)
    # and leaves every other section alone
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": partial, "replace": True})
    out = resp.get_json()
    assert resp.status_code == 200 and out["replace"] is True
    assert out["sections"]["Other Assets"] == partial["Other Assets"]
    assert {k: v for k, v in out["sections"].items() if k != "Other Assets"} == \
        {k: v for k, v in expected.items() if k != "Other Assets"}


def test_the_csv_writers_own_rules_reach_the_rows(ws):
    """The write-back goes through _write_plan_data_file, which canonicalizes every Roth
    value of the file it writes; the bridge run that ends the edit brings that into the rows
    too, so rows and CSV set agree after the save."""
    client = app.test_client()
    _grid(client)  # the first GET backfills the canonical rows (and the file writer canonicalizes the file)
    policy = ws.input_dir / "client_policy.csv"
    policy.write_text(policy.read_text(encoding="utf-8").replace(
        "roth_target_bracket_rate,22.00%,", "roth_target_bracket_rate,22%,"), encoding="utf-8")
    bracket = ("Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate")
    grid = _grid(client)
    assert _row(grid, bracket)["value"] == "22%"  # an out-of-band CSV edit, picked up by the GET
    years = _row(grid, ("Withdrawal Policy", "Roth Conversion", "max_conversion_years"))
    status, _ = _save(client, [{"row_index": years["row_index"], "value": "9"}])
    assert status == 200
    assert _plan_value(bracket) == "22.00%" and "roth_target_bracket_rate,22.00%," in policy.read_text(encoding="utf-8")
    assert _plan_value(("Withdrawal Policy", "Roth Conversion", "max_conversion_years")) == "9"


# ------------------------------------------------------------- WP4.3 review fixes
RETIRE = ("Household", "", "member_2_retirement_date")


def test_a_grid_edit_the_plan_rules_revert_is_skipped_not_updated(ws):
    """The file writer's rules (protected retirement dates, canonical Roth values) can give a
    value back in the final pull: that row is reported skipped, not updated."""
    from types import SimpleNamespace

    from src import active_plan
    from src.server_services.config_service import ConfigService

    client = app.test_client()
    grid = _grid(client)
    protected, home = _row(grid, RETIRE), _row(grid, HOME)
    household = ws.input_dir / "client_household.csv"

    def write_file(name, text):
        if name == "client_household.csv":  # the protected merge puts the old date back
            text = text.replace("member_2_retirement_date,3/1/2030,", f"member_2_retirement_date,{protected['value']},")
        (ws.input_dir / name).write_text(text, encoding="utf-8")
        return ws.input_dir / name

    ctx = SimpleNamespace(
        read_schema_map=lambda: {}, normalize_date_for_csv=lambda v: v, audit=None, sync_config_backends=lambda: None,
        edit_plan=lambda: active_plan.edit_active_plan(ws.input_dir, write_file))
    out, status = ConfigService(ctx).update_config_rows_payload(
        {"updates": [{"row_index": protected["row_index"], "value": "3/1/2030"},
                     {"row_index": home["row_index"], "value": "$1,500,001"}]}, allow_csv_write=True)
    assert status == 200 and out["updated"] == 1
    (skipped,) = out["skipped"]
    assert skipped["row_index"] == protected["row_index"] and skipped["label"] == RETIRE[2]
    assert "value not kept" in skipped["reason"] and protected["value"] in skipped["reason"]
    assert _plan_value(RETIRE) == protected["value"] and _plan_value(HOME) == "$1,500,001"
    assert "member_2_retirement_date,3/1/2030," not in household.read_text(encoding="utf-8")


def test_reads_with_an_unparsable_part_file_serve_the_stored_rows_with_a_warning(ws):
    client = app.test_client()
    grid = _grid(client)
    (ws.input_dir / "client_business.csv").write_text("not,a,plan\n1,2,3\n", encoding="utf-8")
    again = client.get("/api/config/rows", headers=HEADERS)
    assert again.status_code == 200
    payload = again.get_json()
    assert "client_business.csv" in payload["warning"] and payload["rows"] == grid["rows"]
    forms = client.get("/api/plan/forms", headers=HEADERS)
    assert forms.status_code == 200 and "client_business.csv" in forms.get_json()["warning"]
    assert app_core._csv_rows_payload()["rows"] == grid["rows"]  # the build preflight's read
    # a write needs the CSV set: refused, rows unchanged
    row = _row(grid, HOME)
    status, out = _save(client, [{"row_index": row["row_index"], "value": "$9"}])
    assert status == 409 and "could not be saved" in out["error"]
    assert _plan_value(HOME) == row["value"]


def test_a_failed_second_bridge_run_leaves_neither_rows_nor_csv_changed(ws, monkeypatch):
    from src import active_plan

    client = app.test_client()
    home = _row(_grid(client), HOME)
    before = {p.name: p.read_text(encoding="utf-8") for p in ws.input_dir.glob("*.csv")}
    real, calls = active_plan._pull, []

    def pull(store, input_dir):
        calls.append(1)
        if len(calls) == 2:
            raise active_plan.PlanCsvError("second bridge run failed")
        return real(store, input_dir)

    monkeypatch.setattr(active_plan, "_pull", pull)
    status, out = _save(client, [{"row_index": home["row_index"], "value": "$3,333,333"}])
    assert status == 409 and out["success"] is False
    monkeypatch.undo()
    assert {p.name: p.read_text(encoding="utf-8") for p in ws.input_dir.glob("*.csv")} == before
    assert _plan_value(HOME) == home["value"]


def test_unchanged_grid_and_forms_reads_do_not_run_the_bridge(ws, monkeypatch):
    from src import active_plan

    client = app.test_client()
    _grid(client)  # first read syncs (and the backfill may write once)
    _grid(client)
    runs = []
    real = active_plan.sync_active_plan_from_csv
    monkeypatch.setattr(active_plan, "sync_active_plan_from_csv", lambda d: (runs.append(1), real(d))[1])
    for _ in range(2):
        assert client.get("/api/config/rows", headers=HEADERS).status_code == 200
        assert client.get("/api/plan/forms", headers=HEADERS).status_code == 200
    assert runs == []
    _save_buffers(ws, sync=False)  # a CSV write changes the set: the next read syncs it
    assert client.get("/api/plan/forms", headers=HEADERS).status_code == 200 and len(runs) == 1
    assert _buffer_1()["start_year"] == "2031"


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
