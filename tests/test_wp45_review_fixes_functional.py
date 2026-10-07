"""WP4.5 review fixes: one pinning test per finding (seed, demo migrate, blank all-or-nothing,
protected dates, override validation, spending reader root/labels, staleness path, YTD plan reads)."""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import src.server.app_core as app_core
from src import active_plan, optimization as opt, platform_runtime, plan_overrides as po
from src.server import app
from src.stores import PlanStore
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
HEADER = "section,subsection,label,value,units,notes\n"
CLASS = next(iter(opt._BASE_ASSET_CLASSES))
OTHER = list(opt._BASE_ASSET_CLASSES)[1]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_BASE_DIR", raising=False)
    return plan


# 1. frozen workspace seed --------------------------------------------------------------------

def _frozen(monkeypatch, tmp_path):
    pkg = tmp_path / "bundle"
    (pkg / "input" / "demo").mkdir(parents=True)
    (pkg / "input" / "demo" / "client_data.csv").write_text(
        HEADER + "Household,,member_1_name,Demo,text,\n", encoding="utf-8")
    monkeypatch.setattr(platform_runtime, "package_root", lambda: pkg)
    monkeypatch.delenv(platform_runtime.WORKSPACE_ROOT_ENV, raising=False)
    monkeypatch.setattr(platform_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    return pkg, tmp_path / "appdata" / "RetirementPlanner"


def test_seed_fills_an_existing_but_empty_plan_file(monkeypatch, tmp_path):
    _pkg, ws_root = _frozen(monkeypatch, tmp_path)
    ws_root.mkdir(parents=True)
    PlanStore.open(ws_root / "plan.rpx").close()  # exists, zero rows
    assert platform_runtime.seed_frozen_workspace() is True
    with PlanStore.open(ws_root / "plan.rpx", create=False, readonly=True) as store:
        assert store.sectioned_data() == {"Household": {"": {"member_1_name": "Demo"}}}


def test_a_failed_or_empty_import_raises_and_the_next_launch_retries(monkeypatch, tmp_path):
    _pkg, ws_root = _frozen(monkeypatch, tmp_path)
    real = active_plan.build_plan_file_from_csv_folder
    monkeypatch.setattr(active_plan, "build_plan_file_from_csv_folder", lambda dest, folder: 0)
    with pytest.raises(RuntimeError, match="imported no rows"):
        platform_runtime.seed_frozen_workspace()
    assert not (ws_root / "input" / "client_data.csv").exists()  # not marked as seeded
    monkeypatch.setattr(active_plan, "build_plan_file_from_csv_folder",
                        lambda dest, folder: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(RuntimeError, match="disk full"):
        platform_runtime.seed_frozen_workspace()
    assert not (ws_root / "input" / "client_data.csv").exists()
    monkeypatch.setattr(active_plan, "build_plan_file_from_csv_folder", real)
    assert platform_runtime.seed_frozen_workspace() is True
    assert (ws_root / "input" / "client_data.csv").exists()
    with PlanStore.open(ws_root / "plan.rpx", create=False, readonly=True) as store:
        assert store.all_rows()


# 3. Start New Plan is all or nothing -----------------------------------------------------------

def _blank_service(tmp_path, blank_rows, files=None, write=None):
    from src.server_services.plan_data_file_service import PlanDataFileService, PlanDataFileServiceContext
    db = tmp_path / "legacy.db"
    db.write_bytes(b"x")
    plan = tmp_path / "plan.rpx"
    plan.write_bytes(b"x")
    disk = {"client_holdings.csv": "real holdings\n"}
    events = []

    def write_file(name, content):
        disk[name] = content
        return tmp_path / name

    service = PlanDataFileService(PlanDataFileServiceContext(
        plan_data_files=["client_holdings.csv"], sqlite_db=lambda: db, plan_db=lambda: plan,
        normalize_plan_data_file_name=lambda n: n, read_plan_data_file=lambda n: disk.get(n),
        write_plan_data_file=write or write_file,
        make_blank_plan_files=files or (lambda: {"client_holdings.csv": "blank\n"}),
        blank_plan_rows=blank_rows, protected_client_data_status=lambda: {},
        ensure_user_ui_plan_data_rows=lambda: None,
        audit=lambda e, d=None: events.append(e)))
    return service, disk, events


def test_a_failed_row_change_puts_the_flat_files_back_and_reports_an_error(tmp_path):
    def boom(**kw):
        raise sqlite3.OperationalError("database is locked")
    service, disk, events = _blank_service(tmp_path, boom)
    payload, status = service.start_blank_payload()
    assert status == 500 and payload["success"] is False and "unchanged" in payload["error"]
    assert disk["client_holdings.csv"] == "real holdings\n"
    assert "blank_plan_failed" in events and "blank_plan_started" not in events


def test_the_rows_are_cleared_only_after_the_files_are_written(tmp_path):
    order = []
    service, disk, _ = _blank_service(tmp_path, lambda **kw: order.append("rows") or 3,
                                      write=lambda n, c: order.append("write") or tmp_path / n)
    assert service.start_blank_payload()[1] == 200 and order == ["write", "rows"]


def test_a_failed_file_prepare_or_write_never_touches_the_rows(tmp_path):
    called = []
    def prepare_fails():
        raise ValueError("cannot read holdings")
    service, _disk, _ = _blank_service(tmp_path, lambda **kw: called.append(1) or 1, files=prepare_fails)
    assert service.start_blank_payload()[1] == 500 and called == []
    def write_fails(name, content):
        raise PermissionError("locked")
    service, _disk, _ = _blank_service(tmp_path, lambda **kw: called.append(1) or 1, write=write_fails)
    payload, status = service.start_blank_payload()
    assert status == 500 and payload["success"] is False and called == []


# 4. protected retirement dates ------------------------------------------------------------------

def test_protection_is_off_unless_the_grid_or_forms_ask_for_it(ws):
    key = ("Household", "", "member_2_retirement_date")
    with active_plan.edit_active_plan() as edit:  # strategy endpoints / backfill / import: no protection
        edit.store.set_value(*key, "2035-01-01")
    assert ws.store_data()["Household"][""][key[2]] == "2035-01-01"
    with app_core._edit_active_plan() as edit:
        edit.store.set_value(*key, "")
    assert ws.store_data()["Household"][""][key[2]] == ""  # a household without Member 2 can clear it


def test_the_forms_keep_a_blanked_date_but_a_blank_plan_clears_it(ws):
    before = ws.store_data()["Household"][""]["member_1_retirement_date"]
    assert before
    client = app.test_client()
    resp = client.post("/api/plan/forms", headers=HEADERS,
                       json={"sections": {"Household": {"": {"member_1_retirement_date": ""}}}})
    assert resp.status_code == 200
    assert ws.store_data()["Household"][""]["member_1_retirement_date"] == before
    app_core._blank_plan_rows()
    assert ws.store_data()["Household"][""]["member_1_retirement_date"] == ""


# 5. override tables -----------------------------------------------------------------------------

@pytest.mark.parametrize("kind, row, message", [
    (po.CMA, {"asset_class": CLASS, "horizon_years": "30%"}, "horizon_years must be a whole number"),
    (po.CMA, {"asset_class": CLASS, "horizon_years": "7.5"}, "horizon_years must be a whole number"),
    (po.REAL_LOSS, {"curve_name": "x", "holding_years": "5%", "real_loss_prob": "10%"}, "holding_years must be a whole number"),
    (po.CMA, {"asset_class": CLASS, "expected_return": "7.5"}, "not a fraction"),
    (po.CMA, {"asset_class": CLASS, "volatility": "-5%"}, "not negative"),
    (po.CMA, {"asset_class": CLASS, "stock_index_correlation": "150%"}, "between -1 and 1"),
])
def test_percent_is_only_valid_on_rate_columns_and_years_are_whole_numbers(kind, row, message):
    with pytest.raises(po.OverrideRowsError) as exc:
        po.validate_rows(kind, [row])
    assert message in "; ".join(exc.value.errors)


def test_accepted_forms_are_stored_consistently_and_read_by_the_engine_as_typed():
    rows = po.validate_rows(po.CMA, [{"horizon_years": " 30 ", "asset_class": CLASS, "expected_return": "+7.5 %",
                                      "volatility": "0.2", "stock_index_correlation": "-0.5"}])
    assert rows == [{"horizon_years": "30", "asset_class": CLASS, "expected_return": "7.5%",
                     "volatility": "0.2", "stock_index_correlation": "-0.5"}]
    assert opt._parse_number(rows[0]["expected_return"]) == opt._parse_number("7.5%") == 0.075


def test_empty_rows_are_skipped_without_using_a_row_number():
    store_rows = po.validate_rows(po.CMA, [{}, {"asset_class": CLASS, "expected_return": "5%"}, {"asset_class": ""}])
    assert store_rows == [{"asset_class": CLASS, "expected_return": "5%"}]
    with PlanStore.open() as store:
        assert po.replace_rows(store, po.CMA, [{}, {"asset_class": CLASS}, {"asset_class": " "}, {"asset_class": OTHER}]) == 2
        assert list(store.sectioned_data()["Custom Capital Market"]) == ["row_1", "row_2"]


def test_a_post_of_only_empty_rows_changes_nothing(ws):
    client = app.test_client()
    good = {"rows": [{"asset_class": CLASS, "expected_return": "9%"}]}
    assert client.post("/api/capital-market/assumptions", headers=HEADERS, json=good).status_code == 200
    resp = client.post("/api/capital-market/assumptions", headers=HEADERS, json={"rows": [{}, {"asset_class": ""}]})
    assert resp.status_code == 400 and "empty" in " ".join(resp.get_json()["errors"])
    assert ws.store_data()["Custom Capital Market"]["row_1"]["expected_return"] == "9%"
    with PlanStore.open(ws.plan_db) as store:  # the writer itself refuses too
        with pytest.raises(po.OverrideRowsError):
            po.replace_rows(store, po.CMA, [{}])
        assert "Custom Capital Market" in store.sectioned_data()


# 6. spending tracker plan reader --------------------------------------------------------------

def _set_insurance(plan, flag_label="existing_life_insurance", premium="1,200"):
    with PlanStore.open(plan.plan_db) as store:
        store.set_value("Optional Functions", "", flag_label, "TRUE")
        store.set_value("Insurance In Force", "Policy 1", "Policy_Type ", " AUTO")
        store.set_value("Insurance In Force", " Policy 1", "annual_premium", premium)


def test_spending_reads_the_plan_of_base_dir_and_matches_labels_loosely(tmp_path, monkeypatch):
    from src import spending_tracker as st
    other = make_plan(tmp_path / "other")
    with PlanStore.open(other.plan_db) as store:
        store.set_value("Optional Functions", "", "existing_life_insurance", "TRUE")
    fixture_autos = st._insurance_policy_premium_sum(other.root, "Auto")  # the fixture's own policies
    with PlanStore.open(other.plan_db) as store:  # labels and sections typed loosely
        store.set_value("Optional Functions", "", "existing_life_insurance", "FALSE")
    assert st._insurance_policy_premium_sum(other.root, "Auto") == 0.0
    _set_insurance(other, flag_label=" Existing_Life_Insurance ")
    mine = make_plan(tmp_path / "mine")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(mine.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_BASE_DIR", raising=False)
    assert st._insurance_policy_premium_sum(None, "Auto") == 0.0  # the active plan has no policy
    monkeypatch.setenv("RETIREMENT_SYSTEM_BASE_DIR", str(other.root))
    assert st._insurance_policy_premium_sum(None, "auto") == fixture_autos + 1200.0  # BASE_DIR honoured, labels loose
    assert st._insurance_policy_premium_sum(other.root, "Auto") == fixture_autos + 1200.0


# 7. staleness of the outputs ---------------------------------------------------------------------

def test_outputs_are_stale_against_the_plan_file_only(ws, monkeypatch):
    from src.server import workbook_routes
    legacy = Path(workbook_routes._sqlite_db())
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"x")
    os.utime(ws.plan_db, (1_000_000, 1_000_000))
    os.utime(legacy, (2_000_000, 2_000_000))  # an audit / KPI write is newer than the plan
    assert workbook_routes._plan_staleness_path() == ws.plan_db
    wal = ws.plan_db.with_name(ws.plan_db.name + "-wal")
    wal.write_bytes(b"x")
    os.utime(wal, (3_000_000, 3_000_000))  # a commit still in the write-ahead log is a plan edit
    assert workbook_routes._plan_staleness_path() == wal


# 8. YTD plan reads --------------------------------------------------------------------------------

def test_ytd_summary_reads_the_plan_file_once(ws, monkeypatch):
    from src import ytd_tracking
    calls = []
    real = active_plan.peek_plan_data_for_input_dir
    monkeypatch.setattr(active_plan, "peek_plan_data_for_input_dir", lambda d: calls.append(d) or real(d))
    summary = ytd_tracking.ytd_summary(ws.input_dir, today=date(2026, 6, 30))
    assert summary and len(calls) == 1
    calls.clear()
    ytd_tracking.status_payload(ws.input_dir)
    assert len(calls) == 1
    calls.clear()
    ytd_tracking.annual_spending_forecast(ws.input_dir)  # outside a request block: still reads fresh
    ytd_tracking.annual_spending_forecast(ws.input_dir)
    assert len(calls) == 2


def test_the_plan_memo_is_gone_after_the_request_so_a_write_is_never_served_stale(ws):
    from src import ytd_tracking
    before = ytd_tracking.planned_spending_components(ws.input_dir, 2026)["core_spending"]
    with active_plan.edit_active_plan() as edit:
        edit.store.set_value("Cashflow", "Spending", "annual_spending_base_year", "12345")
    assert ytd_tracking.planned_spending_components(ws.input_dir, 2026)["core_spending"] == 12345.0 != before
