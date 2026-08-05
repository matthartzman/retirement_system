import sqlite3

from src.market_data import MarketDataProvider
from src.portfolio_analytics import (
    PRICING_FREEZE_SCHEMA,
    freeze_latest_pricing_snapshot,
    pricing_freeze_status,
    snapshot_prices,
    unfreeze_pricing_snapshot,
)


def test_pricing_snapshot_freeze_contract_round_trip(tmp_path):
    db = tmp_path / "retirement_system_v10.db"
    empty = freeze_latest_pricing_snapshot(db_path=db)
    assert empty["success"] is False
    assert empty["schema"] == PRICING_FREEZE_SCHEMA

    snapshot_prices({"VTI": 250.12, "VXUS": 62.5, "BAD": 0}, {"VTI": "unit_live", "VXUS": "cache"}, db_path=db)

    frozen = freeze_latest_pricing_snapshot(db_path=db)
    assert frozen["success"] is True
    assert frozen["active"] is True
    assert frozen["schema"] == PRICING_FREEZE_SCHEMA
    assert frozen["symbol_count"] == 2
    assert frozen["symbols"]["VTI"]["price"] == 250.12

    # Later snapshots should not mutate the active frozen contract.
    snapshot_prices({"VTI": 999.99}, {"VTI": "later_live"}, db_path=db)
    status = pricing_freeze_status(db_path=db)
    assert status["active"] is True
    assert status["prices"]["VTI"] == 250.12
    assert status["latest_count"] == 2

    unfrozen = unfreeze_pricing_snapshot(db_path=db)
    assert unfrozen["success"] is True
    assert unfrozen["active"] is False
    assert pricing_freeze_status(db_path=db)["active"] is False


def test_market_data_provider_frozen_mode_uses_snapshot_without_live_calls():
    provider = MarketDataProvider()
    provider.configure_holdings_pricing("LIVE", cache_hours=1)
    provider.set_frozen_prices({"VTI": 250.12}, {"schema": PRICING_FREEZE_SCHEMA, "frozen_at": "2026-06-26T00:00:00Z"})

    assert provider.pricing_mode == "FROZEN"
    assert provider.quote("VTI") == 250.12
    assert provider.sources["VTI"] == "frozen_snapshot"
    assert provider.provider_attempts == {}

    diag = provider.diagnostics()
    assert diag["pricing_source_category"] == "FROZEN"
    assert diag["frozen_pricing_active"] is True
    assert "VTI" in diag["frozen_symbols"]


def test_pricing_freeze_routes_and_docs_are_registered():
    docs = open("documentation/API_CONTRACTS.md", encoding="utf-8").read()
    routes = open("src/server/plan_routes.py", encoding="utf-8").read()
    js = open("frontend/js/dashboard.js", encoding="utf-8").read()

    assert "pricing_snapshot_freeze_v1" in docs
    assert "@app.route(\"/api/prices/freeze\"" in routes
    assert "@app.route(\"/api/prices/unfreeze\"" in routes
    assert "Freeze latest prices" in js
    assert "freezePricingSnapshot" in js
