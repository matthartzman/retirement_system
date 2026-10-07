import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_service_extraction_functional.py, alongside every other extracted service's
# equivalent pair. Only this file's genuine behavior + manifest tests remain.


def test_config_service_updates_plan_data_rows(tmp_path, monkeypatch):
    """WP4.3 / WP4.5: the grid save writes the active plan's row by row_id in one transaction."""
    from src import active_plan
    from src.server_services.config_service import ConfigService, ConfigServiceContext

    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    with active_plan.active_plan_store() as store:
        store.insert_row("Client", subsection="Household", label="client_name", value="Old")

    service = ConfigService(ConfigServiceContext(
        version="9",
        base_dir=tmp_path,
        edit_plan=active_plan.edit_active_plan,
        read_plan=active_plan.active_plan_store,
        csv_rows_payload=lambda: {"rows": [], "schema_count": 0},
        read_schema_map=lambda: {},
        load_active_config=lambda: ({}, {"backend": "SQLITE", "plan_db": str(active_plan.active_plan_path())}),
        runtime_config=lambda: type("Cfg", (), {"sqlite_db": str(tmp_path / "retirement_system_v10.db"), "config_backend": "SQLITE"})(),
        normalize_date_for_csv=lambda value: value,
    ))
    with active_plan.active_plan_store() as store:
        (row,) = store.find_rows("Client", "Household", "client_name")
        before = store.revision()

    payload, status = service.update_config_rows_payload(
        {"updates": [{"row_index": row["row_id"], "value": " New "}, {"row_index": 999, "value": "x"}]},
        allow_csv_write=True)
    assert status == 200
    assert payload["success"] is True
    assert payload["updated"] == 1
    assert payload["skipped"] == [{"row_index": 999, "reason": "out of range or stale row index"}]
    assert "sync" not in payload
    assert payload["revision"] != before
    with active_plan.active_plan_store() as store:
        assert store.get_row(row["row_id"])["value"] == "New"
        assert payload["revision"] == store.revision()
    assert not list(tmp_path.glob("**/*.csv"))  # no file is written
    backends, status = service.config_backends_payload()
    assert status == 200 and backends["plan_path"] == str(active_plan.active_plan_path())
    assert {"csv_path", "json_path", "yaml_path"}.isdisjoint(backends)


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
