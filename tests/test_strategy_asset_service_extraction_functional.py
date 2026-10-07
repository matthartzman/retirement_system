from pathlib import Path


def test_strategy_asset_service_exists_and_is_runtime_independent():
    service = Path("src/server_services/strategy_asset_service.py").read_text(encoding="utf-8")
    assert "class StrategyAssetService" in service
    assert "StrategyAssetServiceContext" in service
    assert "def add_insurance_policy_payload" in service
    assert "def seed_healthcare_oop_payload" in service
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_service_extraction_functional.py.


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
        reference_file_path=lambda name: tmp_path / name,
        normalize_large_discretionary_type=lambda value: str(value),
        pre_tax_account_options_from_holdings=lambda: [],
        audit=lambda event, details=None: audit_events.append((event, details or {})),
    )
    service = StrategyAssetService(ctx)
    payload, status = service.delete_insurance_policy_payload({})
    assert status == 400
    assert payload["success"] is False
    assert not audit_events


def test_home_sale_splits_reject_percentages_that_do_not_sum_to_100(tmp_path):
    """#299: percentages must sum to 100% before writing the split to the plan --
    silently accepting an under/over-100% split would either strand proceeds
    or fabricate money the sale never produced."""
    from tests.strategy_service_rows import service_over_rows

    service, store, audit_events = service_over_rows(tmp_path, [])

    payload, status = service.save_home_sale_splits_payload({
        "splits": [
            {"account": "Joint_Trust", "percentage": "60"},
            {"account": "Family_Checking", "percentage": "30"},
        ]
    })
    assert status == 400
    assert payload["success"] is False
    assert not audit_events
    assert not store.rows("Home Sale Split")

    payload, status = service.save_home_sale_splits_payload({
        "splits": [
            {"account": "Joint_Trust", "percentage": "60"},
            {"account": "Family_Checking", "percentage": "40"},
        ]
    })
    assert status == 200
    assert payload["success"] is True
    assert payload["count"] == 2
    assert len(store.rows("Home Sale Split")) == 4
