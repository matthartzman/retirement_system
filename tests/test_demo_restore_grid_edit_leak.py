"""#240: a demo-session grid edit must not survive "Exit demo".

WP8.4: the demo is its own plan file (``demo.rpx``) beside the real plan, one active at a time
through the plan registry. An edit made through the grid while "in the demo" (a natural thing for
an advisor exploring the demo to do) lands in ``demo.rpx``, never in the real plan.

This test drives the real ``DemoPlanService`` and the real grid save
(``ConfigService.update_config_rows_payload`` over ``active_plan.edit_active_plan``) against a
real plan file in ``tmp_path``, redirecting the workspace root so it can never touch the repo's
real input/ (see memory/testing notes: pytest must not mutate live input/ files).
"""
from pathlib import Path

from src import active_plan, plan_registry
from src.server_services.config_service import ConfigService, ConfigServiceContext
from src.server_services.demo_plan_service import DemoPlanService, DemoPlanServiceContext
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
    monkeypatch.delenv("RETIREMENT_SYSTEM_APP_DB", raising=False)
    plan_registry.invalidate()
    plan_db = active_plan.active_plan_path()
    demo_dir = tmp_path / "input" / "demo"
    demo_dir.mkdir(parents=True)
    (demo_dir / "client_household.csv").write_text(HEADER + "Household,,client_name,Fictional Demo Name,text,\n", encoding="utf-8")

    with active_plan.active_plan_store() as store:
        store.set_value(*KEY, "Real Advisor Name")
        row_id = store.find_rows(*KEY)[0]["row_id"]
    config = _make_config_service()
    demo = DemoPlanService(DemoPlanServiceContext(demo_dir=lambda: demo_dir))

    # The advisor's real edit, made through the grid-save path.
    _grid_edit(config, row_id, "Real Advisor Name 2")
    assert _value() == "Real Advisor Name 2"

    # Open demo: the active plan is the demo file now (a different file, new row ids).
    assert demo.open_demo_payload()["success"] is True
    assert _value() == "Fictional Demo Name" and active_plan.active_plan_path() != plan_db
    with PlanStore.open(active_plan.active_plan_path(), create=False, readonly=True) as store:
        demo_row_id = store.find_rows(*KEY)[0]["row_id"]

    # While "in the demo", the advisor edits the same field via the grid -- the repro step.
    _grid_edit(config, demo_row_id, "Accidental Demo Edit")
    assert _value() == "Accidental Demo Edit"

    # Exit demo: the real plan is active again, and the demo edit is in demo.rpx only.
    out = demo.exit_demo_payload()
    assert out["success"] is True and out["restored"] is True
    assert active_plan.active_plan_path() == plan_db
    assert _value() == "Real Advisor Name 2", (
        "Exit demo must bring back the advisor's real plan, not "
        "leave a demo-session grid edit behind (#240)")
    with PlanStore.open(tmp_path / "demo.rpx", create=False, readonly=True) as store:
        assert store.sectioned_data()["Household"][""]["client_name"] == "Accidental Demo Edit"
