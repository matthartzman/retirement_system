"""WP4.2 review findings, pinned (state after WP4.5 deleted the CSV bridge).

1. the protected-date status reads the plan rows without creating the plan file
2. the startup migration works on the workspace's input folder and the active plan file
3. Save As copies the plan file; a broken copy is refused, never half-written
4. the startup warning names the plan rows
"""
from __future__ import annotations

from pathlib import Path

import pytest

import src.server.app_core as app_core
from src import active_plan
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
DATE_KEY = ("Household", "", "member_1_retirement_date")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return plan


# --------------------------------------------------------------------------- 1
def test_protected_status_creates_no_plan_file_and_is_not_falsely_missing(ws):
    assert app_core._protected_client_data_status()["member_1_retirement_date_present"] is True
    ws.plan_db.unlink()
    status = app_core._protected_client_data_status()
    assert status == {"member_1_retirement_date_present": False, "member_2_retirement_date_present": False}
    assert not ws.plan_db.exists(), "a status read must not create plan.rpx"


def test_protected_status_reads_the_plan_rows(ws):
    with ws.store() as store:
        store.set_value(*DATE_KEY, "")
    assert app_core._protected_client_data_status()["member_1_retirement_date_present"] is False
    with ws.store() as store:
        store.set_value(*DATE_KEY, "2031-01-01")
    assert app_core._protected_client_data_status()["member_1_retirement_date_present"] is True


# --------------------------------------------------------------------------- 2
def test_startup_migration_default_folder_is_the_workspace_input_and_the_active_plan(ws, monkeypatch):
    import src.plan_data_migration as pdm
    seen = {}
    monkeypatch.setattr(pdm, "migrate_plan_data_at_rest",
                        lambda input_dir, db_path=None, **kw: seen.setdefault("dir", Path(input_dir)) or {})
    pdm.run_startup_plan_data_migration()
    assert seen["dir"] == ws.input_dir


def test_the_migration_leaves_the_legacy_sectioned_csv_files_alone(ws):
    """The part files are the converter's source now: the at-rest migration never rewrites them."""
    import src.plan_data_migration as pdm

    household = ws.input_dir / "client_household.csv"
    household.write_text(household.read_text(encoding="utf-8").replace("member_1_name", "husband_name"), encoding="utf-8")
    before = household.read_bytes()
    with ws.store() as store:  # an old plan: a legacy key in the rows
        store.set_value("Household", "", "husband_name", "Old Key")
    report = pdm.migrate_plan_data_at_rest(ws.input_dir, db_path=ws.root / "local_state" / "m.db")
    assert household.read_bytes() == before
    # the legacy key is dropped (the current key wins), in the plan rows
    assert report["plan_rows"] >= 1 and "husband_name" not in ws.store_data()["Household"][""]


# --------------------------------------------------------------------------- 3
def test_save_as_copies_the_plan_file(ws, tmp_path):
    target = tmp_path / "saved.rpx"
    resp = app.test_client().post("/api/plan/save-as", headers=HEADERS, json={"path": str(target)})
    assert resp.status_code == 200 and resp.get_json()["success"] is True and target.is_file()
    from src.stores import PlanStore
    with PlanStore.open(target, create=False, readonly=True) as saved:
        assert saved.sectioned_data() == ws.store_data()


def test_save_as_without_a_path_or_a_plan_file_is_refused(ws, tmp_path):
    client = app.test_client()
    assert client.post("/api/plan/save-as", headers=HEADERS, json={}).get_json() == {"success": False, "error": "No path provided"}
    ws.plan_db.unlink()
    out = client.post("/api/plan/save-as", headers=HEADERS, json={"path": str(tmp_path / "x.rpx")}).get_json()
    assert out["success"] is False and not (tmp_path / "x.rpx").exists()


# --------------------------------------------------------------------------- 4
def test_startup_warning_names_the_plan_rows_not_the_db_snapshot():
    text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "DB-snapshot" not in text and "DB snapshots" not in text
    assert "plan-rows migration failed" in text
    from src.plan_data_migration import migrate_plan_data_at_rest  # report key is plan_rows
    assert "snapshots" not in (migrate_plan_data_at_rest.__doc__ or "").split("Returns")[1].split("The plan file is canonical")[0]
