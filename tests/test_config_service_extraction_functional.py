import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_service_extraction_functional.py, alongside every other extracted service's
# equivalent pair. Only this file's genuine behavior + manifest tests remain.


def test_config_service_updates_plan_data_rows(tmp_path):
    from src.server_services.config_service import ConfigService, ConfigServiceContext

    plan_file = tmp_path / "client_data.csv"
    plan_file.write_text(
        "section,subsection,label,value,units,notes\n"
        "Client,Household,client_name,Old,,\n",
        encoding="utf-8",
    )
    written = {}

    def write_plan_data(name, content):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        written[str(path)] = content
        return path

    service = ConfigService(ConfigServiceContext(
        version="9",
        base_dir=tmp_path,
        csv_path=plan_file,
        plan_data_csv_files=["client_data.csv"],
        client_data_csv_file_set={"client_data.csv"},
        plan_data_path=lambda name, *args, **kwargs: tmp_path / name,
        client_csv_rows=lambda: [
            {"row_index": 0, "source_file": "client_data.csv", "source_row_index": 0, "columns": []},
            {"row_index": 1, "source_file": "client_data.csv", "source_row_index": 1, "columns": []},
        ],
        csv_rows_payload=lambda: {"rows": [], "schema_count": 0},
        read_schema_map=lambda: {},
        write_plan_data_file=write_plan_data,
        load_active_config=lambda: ({}, {"backend": "CSV"}),
        runtime_config=lambda: type("Cfg", (), {"sqlite_db": str(tmp_path / "retirement_system_v10.db"), "config_backend": "CSV"})(),
        normalize_date_for_csv=lambda value: value,
        sync_config_backends=lambda: {"success": True},
    ))

    payload, status = service.update_config_rows_payload({"updates": [{"row_index": 1, "value": "New"}], "sync": True}, allow_csv_write=True)
    assert status == 200
    assert payload["success"] is True
    assert payload["updated"] == 1
    assert payload["sync"] == {"success": True}
    assert written
    assert "New" in plan_file.read_text(encoding="utf-8")


def test_route_manifest_has_config_owner():
    text = Path("src/server/route_manifest.py").read_text(encoding="utf-8")
    assert '"plan_config"' in text
    assert '"/api/config/backends"' in text
    assert '"/api/allocation-preview"' in text
    # Allocation preview is now owned by the Plan Configuration service, not the strategy/assets service.
    strategy_block = text.split('"strategy_assets": [', 1)[1].split('],', 1)[0]
    assert '"/api/allocation-preview"' not in strategy_block


# ── #330 §3.4 (W5): the soft-dependency relation reaches the UI ──────────────

def test_module_taxonomy_serves_the_soft_dependency_relation_in_both_directions():
    """`_module_taxonomy` is the switch UI's only source for the off-impact
    warning, so it must carry the reverse map too. Inverting `degrades_without`
    in JavaScript would make the frontend a second place the relation is
    expressed — the hand-typed-twin problem #329 exists to end.
    """
    from src.server_services.config_service import ConfigService

    modules = ConfigService._module_taxonomy()["modules"]

    # Forward: the dependent declares what it loses.
    exec_summary = modules["executive_summary"]["degrades_without"]
    assert {"key": "market_luck_stress_test",
            "loses": "the success-probability headline"} in exec_summary

    # Reverse: the module being switched off knows what it takes with it, and
    # carries the display name so the sentence needs no second lookup.
    mc_off = modules["market_luck_stress_test"]["degraded_by"]
    assert [(d["key"], d["name"], d["loses"]) for d in mc_off] == [
        ("executive_summary", "Executive Summary", "the success-probability headline"),
        ("charts_dashboard", "Charts", "the fan chart"),
        ("planning_levers_echo", "Planning Levers",
         "the Monte Carlo success figure in the model anchor"),
    ]

    # A module nothing degrades without says so explicitly rather than being absent.
    assert modules["glossary"]["degraded_by"] == []
    assert modules["glossary"]["degrades_without"] == []


def test_module_taxonomy_carries_engine_participation():
    from src.server_services.config_service import ConfigService

    modules = ConfigService._module_taxonomy()["modules"]
    assert modules["equity_compensation"]["engine_participation"] is True
    assert modules["roth_conversion_plan"]["engine_participation"] is False
