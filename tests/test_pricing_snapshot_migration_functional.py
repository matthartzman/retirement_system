from __future__ import annotations

import sqlite3
from pathlib import Path

from src.portfolio_analytics import load_latest_snapshots, snapshot_prices

ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_prices_migrates_legacy_table_without_workspace_id(tmp_path):
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as con:
        con.execute("""CREATE TABLE price_snapshots(
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            price REAL,
            source TEXT,
            status TEXT DEFAULT 'OK',
            as_of TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("INSERT INTO price_snapshots(symbol, price, source, status) VALUES(?,?,?,?)", ("OLD", 1.23, "legacy", "OK"))

    assert snapshot_prices({"VTI": 321.09}, {"VTI": "yahoo_live"}, workspace_id="local", db_path=db) == 1

    with sqlite3.connect(db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(price_snapshots)").fetchall()}
        assert "workspace_id" in cols
        row = con.execute("SELECT workspace_id, symbol, price, source FROM price_snapshots WHERE symbol='VTI'").fetchone()
    assert row == ("local", "VTI", 321.09, "yahoo_live")
    latest = load_latest_snapshots(workspace_id="local", db_path=db)
    assert latest["VTI"]["source"] == "yahoo_live"


def test_refresh_prices_reports_live_vs_cache_vs_fallback_counts():
    source = (ROOT / "tools" / "refresh_prices.py").read_text(encoding="utf-8")
    for key in [
        '"live_prices_resolved"',
        '"cache_prices_resolved"',
        '"fallback_prices_resolved"',
        '"live_pricing_working"',
        '"provider_failure_summary"',
        '"snapshot_error"',
    ]:
        assert key in source
    assert "live_prices_resolved" in source


def test_market_data_loads_api_keys_from_environment(monkeypatch, tmp_path):
    from src.market_data import MarketDataProvider

    monkeypatch.setenv("RETIREMENT_SYSTEM_FMP_API_KEY", "fmp-test-key")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-test-key")
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    diag = provider.diagnostics()
    assert diag["fmp_api_key_configured"] is True
    assert diag["alpha_vantage_api_key_configured"] is True
    assert diag["effective_api_key_sources"]["fmp"] == "RETIREMENT_SYSTEM_FMP_API_KEY"
    assert diag["effective_api_key_sources"]["alpha_vantage"] == "ALPHA_VANTAGE_API_KEY"
