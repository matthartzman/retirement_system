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
BUFFERS = [{"start_year": "2031", "end_year": "2036", "years_of_expenses": "2", "reserve_account": "Cash"}]


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


def _save_buffers(client, buffers, sync=True):
    resp = client.post("/api/liquidity-buffers", headers=HEADERS, json={"buffers": buffers, "sync": sync})
    assert resp.status_code == 200 and resp.get_json()["success"] is True


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
    _save_buffers(client, BUFFERS)
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
    _save_buffers(client, BUFFERS, sync=False)  # CSV written, bridge not run
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
    _save_buffers(client, BUFFERS)
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
    del sections["Liquidity Buffer"]
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": sections})
    assert resp.status_code == 200 and resp.get_json()["sections"] == sections
    assert _row(_grid(client), HOME)["row_index"] == home["row_index"]
    assert "Liquidity Buffer," not in (ws.input_dir / "client_assets.csv").read_text(encoding="utf-8")
    assert app_core._sync_config_backends()["success"] is True
    assert load_active_config()[0]["Other Assets"]["Home"]["value_as_of_plan_start"] == "$1,111,111"
