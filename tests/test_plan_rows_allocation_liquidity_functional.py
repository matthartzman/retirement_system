"""WP4.4c: liquidity buffers, home sale splits and the UI-row backfill work on ``plan_rows``.

``/api/liquidity-buffers`` and ``/api/home-sale-splits`` read the active plan's rows and edit
them through ``app_core._edit_active_plan`` (one rows transaction on the plan file); a block that
exists is edited in place. The canonical-row backfill (``_ensure_user_ui_plan_data_rows``, run by
the grid GET and the Plan Data file endpoints) inserts missing rows into the plan rows.
"""
from __future__ import annotations

import pytest

import src.server.app_core as app_core
from src.config_backend import load_active_config
from src.server import app, plan_routes
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
ACCOUNTS = ["Family_Checking", "Member_1_IRA", "Member_1_Roth", "Member_2_IRA"]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(plan_routes, "_all_account_ids_from_holdings", lambda: list(ACCOUNTS))
    return plan


@pytest.fixture
def client(ws):
    return app.test_client()


def _get(client, path):
    resp = client.get(path, headers=HEADERS)
    return resp.status_code, resp.get_json()


def _post(client, path, body=None):
    resp = client.post(path, headers=HEADERS, json=body or {})
    return resp.status_code, resp.get_json()


def _rows(ws, section):
    with ws.store(readonly=True) as store:
        return store.rows(section)


# ------------------------------------------------------------------ liquidity buffers
def test_liquidity_buffers_read_the_plan_and_replace_their_block(ws, client):
    assert _get(client, "/api/liquidity-buffers") == (200, {"success": True, "buffers": [
        {"start_year": "2027", "end_year": "2029", "years_of_expenses": "2", "reserve_account": "Taxable/Trust"}]})
    assert _post(client, "/api/liquidity-buffers", {"buffers": "x"}) == (
        400, {"success": False, "error": "buffers must be a list"})
    ids = {(r["subsection"], r["label"]): r["row_id"] for r in _rows(ws, "Liquidity Buffer")}
    buffers = [{"start_year": "2031", "end_year": "2036", "years_of_expenses": "3", "reserve_account": "Cash"},
               {"start_year": "2037", "end_year": "", "years_of_expenses": "", "preserve_account": "Roth"}, "junk"]
    assert _post(client, "/api/liquidity-buffers", {"buffers": buffers}) == (200, {"success": True, "count": 2})
    rows = _rows(ws, "Liquidity Buffer")
    assert [(r["subsection"], r["label"], r["value"]) for r in rows] == [
        ("buffer_1", "start_year", "2031"), ("buffer_1", "end_year", "2036"), ("buffer_1", "years_of_expenses", "3"),
        ("buffer_1", "reserve_account", "Cash"), ("buffer_2", "start_year", "2037"), ("buffer_2", "end_year", ""),
        ("buffer_2", "years_of_expenses", "0"), ("buffer_2", "reserve_account", "Roth")]
    # buffer_1 was edited in place (row ids stay), buffer_2 is new with the field units and notes
    assert {(r["subsection"], r["label"]): r["row_id"] for r in rows[:4]} == {k: ids[k] for k in ids}
    assert (rows[4]["units"], rows[7]["units"]) == ("year", "choice")
    assert rows[6]["notes"] == "Years of expenses to retain as a reserve; default is 0"
    assert _get(client, "/api/liquidity-buffers")[1]["buffers"][1] == {
        "start_year": "2037", "end_year": "", "years_of_expenses": "0", "reserve_account": "Roth"}
    assert load_active_config()[0]["Liquidity Buffer"]["buffer_2"]["reserve_account"] == "Roth"
    # fewer buffers drop the rest; none empties the block
    assert _post(client, "/api/liquidity-buffers", {"buffers": buffers[:1]})[1]["count"] == 1
    assert {r["subsection"] for r in _rows(ws, "Liquidity Buffer")} == {"buffer_1"}
    assert _post(client, "/api/liquidity-buffers", {"buffers": []})[1]["count"] == 0
    assert not _rows(ws, "Liquidity Buffer")
    assert _get(client, "/api/liquidity-buffers")[1]["buffers"] == []


def test_liquidity_buffers_read_the_legacy_label(ws, client):
    with app_core._edit_active_plan() as edit:
        for r in edit.store.rows("Liquidity Buffer"):
            if r["label"] == "years_of_expenses":
                edit.store.set_row(r["row_id"], label="years_of_expenses_in_trust")
    assert _get(client, "/api/liquidity-buffers")[1]["buffers"][0]["years_of_expenses"] == "2"


# ------------------------------------------------------------------- home sale splits
def test_home_sale_splits_read_validate_and_replace(ws, client):
    assert _get(client, "/api/home-sale-splits") == (200, {"success": True, "splits": [], "accounts": ACCOUNTS})
    assert _post(client, "/api/home-sale-splits", {"splits": "x"})[0] == 400
    status, out = _post(client, "/api/home-sale-splits", {"splits": [
        {"account": "Member_1_IRA", "percentage": "60"}, {"account": "Family_Checking", "percentage": "30"}]})
    assert status == 400 and "Percentages must sum to 100% (currently 90%)" in out["error"]
    assert not _rows(ws, "Home Sale Split")
    splits = [{"account": "Family_Checking", "percentage": "60%"}, {"account": "Member_1_Roth", "percentage": "40"},
              {"account": "", "percentage": "0"}, "junk"]
    assert _post(client, "/api/home-sale-splits", {"splits": splits}) == (200, {"success": True, "count": 2})
    assert _get(client, "/api/home-sale-splits")[1]["splits"] == [
        {"account": "Family_Checking", "percentage": "60.0"}, {"account": "Member_1_Roth", "percentage": "40.0"}]
    rows = _rows(ws, "Home Sale Split")
    assert [(r["subsection"], r["label"], r["units"]) for r in rows] == [
        ("split_1", "account", "choice"), ("split_1", "percentage", "percent"),
        ("split_2", "account", "choice"), ("split_2", "percentage", "percent")]
    assert load_active_config()[0]["Home Sale Split"]["split_2"] == {"account": "Member_1_Roth", "percentage": "40.0"}
    ids = {(r["subsection"], r["label"]): r["row_id"] for r in rows}
    _post(client, "/api/home-sale-splits", {"splits": [{"account": "Member_1_Roth", "percentage": "100"}]})
    rows = _rows(ws, "Home Sale Split")
    assert [(r["subsection"], r["label"], r["value"]) for r in rows] == [
        ("split_1", "account", "Member_1_Roth"), ("split_1", "percentage", "100.0")]
    assert rows[0]["row_id"] == ids[("split_1", "account")]


def test_liquidity_and_split_edits_through_several_endpoints_keep_everything(ws, client):
    assert _post(client, "/api/home-sale-splits", {"splits": [{"account": "Family_Checking", "percentage": "100"}]})[0] == 200
    assert _post(client, "/api/withdrawal-account-order", {"accounts": [{"account_id": "Member_1_IRA", "priority": "2"}]})[0] == 200
    assert _post(client, "/api/liquidity-buffers", {"buffers": [
        {"start_year": "2040", "end_year": "", "years_of_expenses": "1", "reserve_account": "IRA"}]})[0] == 200
    data = load_active_config()[0]
    assert data["Home Sale Split"]["split_1"]["account"] == "Family_Checking"
    assert data["Withdrawal Policy"]["Account Order"]["Member_1_IRA"] == "2"
    assert data["Liquidity Buffer"]["buffer_1"]["start_year"] == "2040"


def test_liquidity_and_split_audit_events_after_the_edit(ws, client, monkeypatch):
    events = []
    monkeypatch.setattr(plan_routes, "_audit", lambda event, details=None: events.append((event, details)))
    _post(client, "/api/home-sale-splits", {"splits": [{"account": "A", "percentage": "10"}]})  # 400: nothing audited
    _post(client, "/api/liquidity-buffers", {"buffers": []})
    _post(client, "/api/home-sale-splits", {"splits": []})
    assert events == [("liquidity_buffers_saved", {"count": 0}), ("home_sale_splits_saved", {"count": 0})]


# --------------------------------------------------------------------------- backfill
def test_the_ui_row_backfill_adds_missing_canonical_rows_into_the_plan(ws, client):
    keys = {(r[0], r[1], r[2]) for e in app_core.PLAN_DATA_BACKFILL_ENTRIES if not callable(e.rows) for r in e.rows}
    with app_core._edit_active_plan() as edit:
        for row in edit.store.all_rows():
            if (row["section"], row["subsection"], row["label"]) in keys:
                edit.store.delete_row(row["row_id"])
    with ws.store(readonly=True) as store:
        assert not keys & {(r["section"], r["subsection"], r["label"]) for r in store.all_rows()}
    status, out = _get(client, "/api/config/rows")  # the grid GET runs the backfill
    assert status == 200
    with ws.store(readonly=True) as store:
        present = {(r["section"], r["subsection"], r["label"]) for r in store.all_rows()}
    assert keys <= present


def test_the_grid_get_shows_backfilled_rows(ws, client):
    with app_core._edit_active_plan() as edit:
        for row in edit.store.all_rows():
            if row["label"] == "mc_engine_mode":
                edit.store.delete_row(row["row_id"])
    status, out = _get(client, "/api/config/rows")
    assert status == 200
    assert [r for r in out["rows"] if r["label"] == "mc_engine_mode" and r["value"] == "quick_vectorized"]


# --------------------------------------------------------------------- conversion (C3)
def test_step_c3_converts_the_liquidity_and_split_blocks_the_endpoints_read(tmp_path):
    """The legacy CSV blocks reach plan_rows through the one C3 step (no step of its own is
    needed for these sections); the service reads the converted rows as it read the CSV."""
    from src.legacy_conversion.steps import c3_plan_rows
    from tests.plan_fixture import fixture_dir
    from tests.strategy_service_rows import service_over_rows

    service, store, _events = service_over_rows(tmp_path, [])
    with store:
        c3_plan_rows.run(fixture_dir("sample_frozen"), store)
        payload, status = service.liquidity_buffers_payload()
        assert status == 200 and payload["buffers"] == [
            {"start_year": "2027", "end_year": "2029", "years_of_expenses": "2", "reserve_account": "Taxable/Trust"}]
        assert service.home_sale_splits_payload()[0]["splits"] == []
