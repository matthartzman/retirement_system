import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_config_service_exists_and_is_runtime_independent():
    service = Path("src/server_services/config_service.py").read_text(encoding="utf-8")
    assert "class ConfigService" in service
    assert "ConfigServiceContext" in service
    assert "def config_rows_payload" in service
    assert "def update_config_rows_payload" in service
    assert "def allocation_preview_payload" in service
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_126_service_extraction.py.


def test_plan_routes_delegate_config_logic_to_service():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _config_feature_service()" in routes
    assert "ConfigServiceContext" in routes
    assert ".config_backends_payload()" in routes
    assert ".config_rows_payload()" in routes
    assert ".allocation_preview_payload(" in routes
    assert ".update_config_rows_payload(" in routes
    assert "compute_optimal_allocation" not in routes
    assert "row_map = {int(e[\"row_index\"])" not in routes
    assert "Plan Data validation failed" not in routes


def test_config_service_updates_plan_data_rows(tmp_path):
    from src.server_services.config_service import ConfigService, ConfigServiceContext

    plan_file = tmp_path / "client_data.csv"
    plan_file.write_text(
        "section,subsection,label,value,units,notes\n"
        "Client,Household,client_name,Old,,\n",
        encoding="utf-8",
    )
    written = {}

    def write_rows(path, rows):
        written[str(path)] = rows
        with Path(path).open("w", encoding="utf-8", newline="") as f:
            import csv
            csv.writer(f).writerows(rows)

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
        write_client_rows=write_rows,
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
