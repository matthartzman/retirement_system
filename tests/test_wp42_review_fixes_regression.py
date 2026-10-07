"""WP4.2 review findings, pinned (one test group per finding).

1. the CSV-set -> plan sync never wipes the plan when the set is empty or missing
2. the protected-date status reads without creating the plan file, and not a false 'missing'
3. one resolver for the plan CSV folder
4. part files deleted/emptied on disk leave client_files
5. Save As and snapshot restore fail loudly when the sync fails
6. the startup warning names the plan rows
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import src.server.app_core as app_core
import src.server.plan_routes as plan_routes
from src import active_plan
from src.config_backend import configured_plan_csv_path, configured_plan_input_dir, load_active_config
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
DATE_KEY = ("Household", "", "member_1_retirement_date")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(app_core, "CSV_PATH", plan.input_dir / "client_data.csv")
    assert app_core._sync_config_backends()["success"] is True  # creates the legacy database
    return plan


def _client_files(ws):
    with sqlite3.connect(ws.root / "local_state" / "retirement_system_v10.db") as con:
        return {r[0] for r in con.execute("SELECT file_name FROM client_files")}


# --------------------------------------------------------------------------- 1
def test_sync_of_an_empty_or_missing_csv_set_keeps_the_plan_rows(ws, tmp_path):
    before = ws.store_data()
    assert before
    empty = tmp_path / "empty_folder"
    empty.mkdir()
    for folder in (empty, tmp_path / "no_such_folder"):
        with pytest.raises(active_plan.EmptyPlanCsvSet):
            active_plan.sync_active_plan_from_csv(folder)
    assert ws.store_data() == before


def test_header_only_csv_set_keeps_the_plan_rows(ws, tmp_path):
    folder = tmp_path / "headers_only"
    folder.mkdir()
    (folder / "client_data.csv").write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
    with pytest.raises(active_plan.EmptyPlanCsvSet):
        active_plan.sync_active_plan_from_csv(folder)
    assert ws.store_data() == ws.data()


def test_sync_config_backends_reports_failure_and_keeps_rows_when_the_csvs_are_gone(ws):
    before = ws.store_data()
    for f in ws.input_dir.glob("*.csv"):
        f.unlink()
    result = app_core._sync_config_backends()
    assert result["success"] is False and "no plan CSV rows" in result["error"]
    assert ws.store_data() == before
    assert load_active_config()[0]["Household"] == before["Household"]


def test_first_read_of_an_empty_folder_with_no_plan_yields_no_rows(ws, tmp_path):
    ws.plan_db.unlink()
    assert active_plan.active_plan_data(tmp_path / "nothing_here") == {}


# --------------------------------------------------------------------------- 2
def test_protected_status_creates_no_plan_file_and_is_not_falsely_missing(ws):
    ws.plan_db.unlink()
    status = app_core._protected_client_data_status()
    assert status["member_1_retirement_date_present"] is True  # read from the CSV set
    assert not ws.plan_db.exists(), "a status read must not create plan.rpx"


def test_protected_status_of_an_unfilled_plan_reads_the_csv_set(ws):
    with ws.store() as store:
        store.clear_rows()
    assert app_core._protected_client_data_status()["member_1_retirement_date_present"] is True


def test_protected_status_reads_the_plan_when_it_has_rows(ws):
    with ws.store() as store:
        store.set_value(*DATE_KEY, "")
    assert app_core._protected_client_data_status()["member_1_retirement_date_present"] is False


# --------------------------------------------------------------------------- 3
def test_one_resolver_for_the_plan_csv_folder(ws, tmp_path, monkeypatch):
    assert configured_plan_input_dir() == ws.input_dir == configured_plan_csv_path().parent
    other = tmp_path / "elsewhere"
    monkeypatch.setenv("RETIREMENT_SYSTEM_CONFIG_FILE", str(other / "client_data.csv"))
    assert configured_plan_input_dir() == other
    # the first-read bootstrap, the sync and the migration all follow it
    other.mkdir()
    for f in ws.input_dir.glob("*.csv"):
        (other / f.name).write_bytes(f.read_bytes())
    (other / "client_household.csv").write_text(
        (other / "client_household.csv").read_text(encoding="utf-8").replace(
            "member_1_retirement_date,2027-01-01", "member_1_retirement_date,2031-01-01"), encoding="utf-8")
    assert app_core._sync_config_backends()["success"] is True
    assert load_active_config()[0]["Household"][""]["member_1_retirement_date"] == "2031-01-01"


def test_csv_path_comes_from_the_resolver():
    import importlib
    src_text = Path(app_core.__file__).read_text(encoding="utf-8")
    assert "CSV_PATH = configured_plan_csv_path()" in src_text
    assert "CSV_PATH.parent)" not in src_text.split("def _sync_config_backends")[1].split("def _permission")[0]
    importlib.import_module("src.plan_data_migration")


def test_startup_migration_default_folder_is_the_resolved_one(ws, tmp_path, monkeypatch):
    import src.plan_data_migration as pdm
    seen = {}
    monkeypatch.setenv("RETIREMENT_SYSTEM_CONFIG_FILE", str(tmp_path / "x" / "client_data.csv"))
    monkeypatch.setattr(pdm, "migrate_plan_data_at_rest",
                        lambda input_dir, db_path=None, **kw: seen.setdefault("dir", Path(input_dir)) or {})
    pdm.run_startup_plan_data_migration()
    assert seen["dir"] == tmp_path / "x"


# --------------------------------------------------------------------------- 4
def test_part_files_deleted_or_emptied_leave_client_files(ws):
    assert {"client_household.csv", "client_income.csv", "client_business.csv"} <= _client_files(ws)
    (ws.input_dir / "client_business.csv").unlink()
    (ws.input_dir / "client_income.csv").write_text("", encoding="utf-8")
    assert app_core._sync_config_backends()["success"] is True
    files = _client_files(ws)
    assert "client_business.csv" not in files and "client_income.csv" not in files
    assert "client_household.csv" in files
    # a load's materialize step cannot bring them back
    from src.config_backend import materialize_workspace_files
    materialize_workspace_files(file_names=["client_business.csv", "client_income.csv"], overwrite_existing=True)
    assert not (ws.input_dir / "client_business.csv").exists()


# --------------------------------------------------------------------------- 5
def _break_sync(monkeypatch):
    monkeypatch.setattr(plan_routes, "_sync_config_backends",
                        lambda: {"success": False, "error": "boom", "trace": ""})


def test_save_as_does_not_save_a_stale_database_when_the_sync_fails(ws, tmp_path, monkeypatch):
    _break_sync(monkeypatch)
    target = tmp_path / "saved.rpx"
    resp = app.test_client().post("/api/plan/save-as", headers=HEADERS, json={"path": str(target)})
    payload = resp.get_json()
    assert resp.status_code == 500 and payload["success"] is False and "boom" in payload["error"]
    assert not target.exists()


def test_save_as_still_saves_when_the_sync_works(ws, tmp_path):
    target = tmp_path / "saved.rpx"
    resp = app.test_client().post("/api/plan/save-as", headers=HEADERS, json={"path": str(target)})
    assert resp.status_code == 200 and resp.get_json()["success"] is True and target.is_file()


def test_snapshot_restore_reports_failure_when_the_sync_fails(ws, monkeypatch):
    from src.server_services.plan_file_service import PlanFileService
    monkeypatch.setattr(PlanFileService, "snapshot_restore_payload",
                        lambda self, body=None: ({"success": True, "backup_database": "x"}, 200))
    _break_sync(monkeypatch)
    resp = app.test_client().post("/api/plan/snapshot/restore", headers=HEADERS, json={})
    payload = resp.get_json()
    assert resp.status_code == 500 and payload["success"] is False
    assert payload["db_replaced"] is True and "boom" in payload["error"]


def test_snapshot_restore_reports_failure_when_materialize_fails(ws, monkeypatch):
    from src.server_services.plan_file_service import PlanFileService
    monkeypatch.setattr(PlanFileService, "snapshot_restore_payload",
                        lambda self, body=None: ({"success": True}, 200))

    def _boom(**kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(plan_routes, "materialize_workspace_files", _boom)
    resp = app.test_client().post("/api/plan/snapshot/restore", headers=HEADERS, json={})
    assert resp.status_code == 500 and resp.get_json()["success"] is False
    assert "disk full" in resp.get_json()["error"]


# --------------------------------------------------------------------------- 6
def test_startup_warning_names_the_plan_rows_not_the_db_snapshot():
    text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "DB-snapshot" not in text and "DB snapshots" not in text
    assert "plan-rows migration failed" in text
    from src.plan_data_migration import migrate_plan_data_at_rest  # report key is plan_rows
    assert "snapshots" not in (migrate_plan_data_at_rest.__doc__ or "").split("Returns")[1].split("Only files")[0]
