"""#240: a demo-session grid edit must not survive "Open Current Plan".

The plan rows live in the plan file (WP4.5), so Open Demo swaps the plan file and Open Current Plan
puts the pre-demo file back: an edit made through the grid while "in the demo" (a natural thing for
an advisor exploring the demo to do) is captured into the demo slot, never into the real plan.

This test drives the real ``DemoPlanService`` and the real grid save
(``ConfigService.update_config_rows_payload`` over ``active_plan.edit_active_plan``) against a
real plan file in ``tmp_path``, redirecting the workspace root so it can never touch the repo's
real input/ (see memory/testing notes: pytest must not mutate live input/ files).
"""
from pathlib import Path

from src import active_plan
from src.server_services.config_service import ConfigService, ConfigServiceContext
from src.server_services.demo_plan_service import DEMO_SLOT_DIR, SLOT_PLAN_FILE, DemoPlanService, DemoPlanServiceContext
from src.sqlite_util import connect as closing_connect
from src.stores import PlanStore

HEADER = "section,subsection,label,value,units,notes\n"
KEY = ("Household", "", "client_name")


def _make_config_service() -> ConfigService:
    return ConfigService(ConfigServiceContext(
        version="9",
        base_dir=Path("."),
        edit_plan=active_plan.edit_active_plan,
        read_plan=lambda: active_plan.active_plan_store(),
        csv_rows_payload=lambda: {"rows": [], "schema_count": 0},
        read_schema_map=lambda: {},
        load_active_config=lambda: ({}, {"backend": "SQLITE"}),
        runtime_config=lambda: type("Cfg", (), {"sqlite_db": "", "config_backend": "SQLITE"})(),
        normalize_date_for_csv=lambda v: v,
    ))


def _grid_edit(service: ConfigService, row_id: int, value: str) -> None:
    result, status = service.update_config_rows_payload(
        {"updates": [{"row_index": row_id, "value": value}]}, allow_csv_write=True)
    assert status == 200 and result["success"] and result["updated"] == 1, result


def _value() -> str:
    return active_plan.peek_plan_data()[KEY[0]][KEY[1]][KEY[2]]


def test_demo_grid_edit_does_not_survive_restore_of_real_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    plan_db = active_plan.active_plan_path()
    legacy_db = tmp_path / "local_state" / "retirement_system_v10.db"
    legacy_db.parent.mkdir(parents=True)
    with closing_connect(legacy_db) as con:  # closed on exit: an open handle blocks the swap on Windows
        con.execute("CREATE TABLE client_files(file_name TEXT PRIMARY KEY, content TEXT)")
    demo_dir = tmp_path / "input" / "demo"
    demo_dir.mkdir(parents=True)
    (demo_dir / "client_household.csv").write_text(HEADER + "Household,,client_name,Fictional Demo Name,text,\n", encoding="utf-8")

    with active_plan.active_plan_store() as store:
        store.set_value(*KEY, "Real Advisor Name")
        row_id = store.find_rows(*KEY)[0]["row_id"]
    config = _make_config_service()
    demo = DemoPlanService(DemoPlanServiceContext(
        sqlite_db=lambda: legacy_db,
        plan_db=active_plan.active_plan_path,
        demo_dir=lambda: demo_dir,
        plan_data_csv_files=[],
        read_plan_data_file=lambda name: None,
        write_plan_data_file=lambda name, content: tmp_path / name,
        ensure_user_ui_plan_data_rows=lambda: None,
        materialize=lambda: None,
    ))

    # The advisor's real edit, made through the grid-save path.
    _grid_edit(config, row_id, "Real Advisor Name 2")
    assert _value() == "Real Advisor Name 2"

    # Open Demo Plan: the plan file is the demo household now (a different file, new row ids).
    assert demo.open_demo_payload()["success"] is True
    assert _value() == "Fictional Demo Name"
    with PlanStore.open(plan_db, create=False, readonly=True) as store:
        demo_row_id = store.find_rows(*KEY)[0]["row_id"]

    # While "in the demo", the advisor edits the same field via the grid -- the repro step.
    _grid_edit(config, demo_row_id, "Accidental Demo Edit")
    assert _value() == "Accidental Demo Edit"

    # Open Current Plan: the real plan file is back, and the demo edit went to the slot only.
    assert demo.restore_current_payload() == {"success": True, "restored": True}
    assert _value() == "Real Advisor Name 2", (
        "Open Current Plan must restore the advisor's real pre-demo edit, not "
        "leave a demo-session grid edit behind (#240)")
    slot_plan = legacy_db.parent / DEMO_SLOT_DIR / SLOT_PLAN_FILE
    with PlanStore.open(slot_plan, create=False, readonly=True) as store:
        assert store.sectioned_data()["Household"][""]["client_name"] == "Accidental Demo Edit"
