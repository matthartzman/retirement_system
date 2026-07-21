from pathlib import Path


def test_strategy_asset_service_exists_and_is_runtime_independent():
    service = Path("src/server_services/strategy_asset_service.py").read_text(encoding="utf-8")
    assert "class StrategyAssetService" in service
    assert "StrategyAssetServiceContext" in service
    assert "def add_insurance_policy_payload" in service
    assert "def seed_healthcare_oop_payload" in service
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_126_service_extraction.py.


def test_plan_routes_delegate_strategy_assets_logic_to_service():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _strategy_asset_feature_service()" in routes
    assert "StrategyAssetServiceContext" in routes
    assert ".save_forced_roth_conversions_payload(" in routes
    assert ".save_liquidity_buffers_payload(" in routes
    assert ".add_insurance_policy_payload(" in routes
    assert ".seed_healthcare_oop_payload()" in routes
    # These row templates should live in the service, not in route adapters.
    assert "HOUSING_SEED = [" not in routes
    assert "HEALTHCARE_OOP_SEED = [" not in routes
    assert "common[3:3]" not in routes


def test_strategy_asset_service_validates_insurance_delete_before_mutation(tmp_path):
    from src.server_services.strategy_asset_service import StrategyAssetService, StrategyAssetServiceContext

    audit_events = []
    read_rows = [["section", "subsection", "label", "value", "type", "comment"]]

    def write_rows(path, rows):  # pragma: no cover - should not be called for invalid payload
        raise AssertionError("delete validation should fail before writing rows")

    ctx = StrategyAssetServiceContext(
        base_dir=tmp_path,
        plan_data_path=lambda name: tmp_path / name,
        client_section_path=lambda section, file_name: tmp_path / file_name,
        reference_file_path=lambda name: tmp_path / name,
        csv_read_rows=lambda path: list(read_rows),
        csv_write_rows=write_rows,
        ensure_header=lambda rows: rows or [["section", "subsection", "label", "value", "type", "comment"]],
        write_client_rows=write_rows,
        read_client_section_rows=lambda section, file_name: [],
        large_discretionary_expenses_from_plan_data=lambda: [],
        normalize_large_discretionary_type=lambda value: str(value),
        replace_large_discretionary_expenses=lambda events: None,
        pre_tax_account_options_from_holdings=lambda: [],
        forced_roth_conversions_from_csv_rows=lambda rows: [],
        replace_forced_roth_conversions=lambda conversions: None,
        liquidity_buffers_from_csv_rows=lambda rows: [],
        replace_liquidity_buffers=lambda buffers: None,
        ensure_user_ui_plan_data_rows=lambda: None,
        sync_config_backends=lambda: {"success": True},
        audit=lambda event, details=None: audit_events.append((event, details or {})),
    )
    service = StrategyAssetService(ctx)
    payload, status = service.delete_insurance_policy_payload({})
    assert status == 400
    assert payload["success"] is False
    assert not audit_events
