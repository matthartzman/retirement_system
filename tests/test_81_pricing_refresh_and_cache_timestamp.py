from __future__ import annotations

import json
from pathlib import Path

from src.market_data import MarketDataProvider, _format_local_cache_timestamp

ROOT = Path(__file__).resolve().parents[1]


def test_cache_timestamp_range_collapses_when_formatted_endpoints_match():
    # Two raw cache writes can differ by seconds but display to the same minute.
    rendered = _format_local_cache_timestamp(
        "2026-06-14T16:06:01+00:00 to 2026-06-14T16:06:43+00:00"
    )
    assert " to " not in rendered
    assert rendered.endswith("AM") or rendered.endswith("PM")


def test_cache_summary_does_not_show_same_local_minute_as_range(tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    provider.configure_holdings_pricing(mode="CACHE", cache_hours=24)
    provider.cache["AAA"] = {
        "symbol": "AAA",
        "price": 10.0,
        "source": "yahoo",
        "timestamp_iso": "2026-06-14T16:06:01+00:00",
        "timestamp_epoch": 1781453161,
    }
    provider.cache["BBB"] = {
        "symbol": "BBB",
        "price": 20.0,
        "source": "stooq",
        "timestamp_iso": "2026-06-14T16:06:43+00:00",
        "timestamp_epoch": 1781453203,
    }
    provider.sources["AAA"] = "fresh_cache_24h_from_yahoo"
    provider.sources["BBB"] = "fresh_cache_24h_from_stooq"
    summary = provider.pricing_source_summary()
    assert summary["category"] == "CACHE"
    assert " to " not in summary["cache_as_of_local"]
    assert " to " not in summary["note"]


def test_runtime_state_reset_clears_stale_provider_failures_and_memoized_quotes(tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    provider.prices["VTI"] = 0.0
    provider.sources["VTI"] = "missing"
    provider.provider_attempts["VTI"] = ["yahoo"]
    provider.failures.append({"symbol": "VTI", "provider": "yahoo", "cause": "transient"})
    provider._global_provider_failures["yahoo"] = "transient timeout"
    provider.reset_runtime_state()
    assert provider.prices == {}
    assert provider.sources == {}
    assert provider.provider_attempts == {}
    assert provider.failures == []
    assert provider._global_provider_failures == {}


def test_live_mode_retries_live_provider_even_when_cache_exists_after_reset(tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    provider.cache["VTI"] = {
        "symbol": "VTI",
        "price": 99.0,
        "source": "old_cache",
        "timestamp_iso": "2020-01-01T00:00:00+00:00",
        "timestamp_epoch": 1577836800,
    }
    provider.configure_holdings_pricing(mode="LIVE", cache_hours=24)
    provider._fetch_fmp = lambda symbol: None  # type: ignore[method-assign]
    provider._fetch_yahoo = lambda symbol: 123.45  # type: ignore[method-assign]
    provider._fetch_alpha_vantage = lambda symbol: None  # type: ignore[method-assign]
    provider._fetch_stooq = lambda symbol: None  # type: ignore[method-assign]
    px = provider.quote("VTI")
    assert px == 123.45
    assert provider.sources["VTI"] == "yahoo_live"
    assert provider.cache["VTI"]["price"] == 123.45


def test_refresh_prices_defaults_to_live_instead_of_reusing_cache_first():
    source = (ROOT / "tools" / "refresh_prices.py").read_text(encoding="utf-8")
    assert 'RETIREMENT_SYSTEM_PRICE_REFRESH_MODE", "LIVE"' in source
    assert '"configured_pricing_mode"' in source
    assert '"refresh_pricing_mode"' in source
    assert "reset_pricing_runtime_state" in source


def test_pricing_env_keys_are_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("RETIREMENT_SYSTEM_FMP_API_KEY", "fmp-test-key")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-test-key")
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    diag = provider.diagnostics()
    assert diag["fmp_api_key_configured"] is True
    assert diag["alpha_vantage_api_key_configured"] is True
    assert diag["effective_api_key_sources"]["fmp"] == "RETIREMENT_SYSTEM_FMP_API_KEY"
    assert diag["effective_api_key_sources"]["alpha_vantage"] == "ALPHA_VANTAGE_API_KEY"


def test_refresh_prices_reports_live_quote_counts_and_no_live_exit_code_contract():
    source = (ROOT / "tools" / "refresh_prices.py").read_text(encoding="utf-8")
    assert '"live_prices_resolved"' in source
    assert '"live_pricing_working"' in source
    assert 'return 2' in source
    assert '"provider_failure_summary"' in source


def test_server_price_refresh_removes_stale_result_before_subprocess():
    source = (ROOT / "src" / "server_services" / "pricing_service.py").read_text(encoding="utf-8")
    assert "out_path.unlink()" in source
    assert "Price refresh did not produce price_refresh_result.json" in source
    assert "result.returncode == 0" in source


def test_provider_order_includes_browser_no_key_nasdaq_fallback(tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / 'cache.json', diagnostics_path=tmp_path / 'diag.json')
    provider.configure_holdings_pricing(mode='LIVE', cache_hours=24)
    assert provider.live_provider_order == ['financial_modeling_prep', 'yahoo', 'nasdaq', 'alpha_vantage', 'stooq']
    diag = provider.diagnostics()
    assert diag['nasdaq_configured'] is True
    assert 'nasdaq' in diag['no_key_providers']


def test_nasdaq_parser_accepts_last_sale_price(monkeypatch, tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / 'cache.json', diagnostics_path=tmp_path / 'diag.json')
    provider.configure_holdings_pricing(mode='LIVE', cache_hours=24)
    def fake_get_json(provider_name, symbol, url):
        return ({'data': {'primaryData': {'lastSalePrice': '$337.42'}}}, None)
    monkeypatch.setattr(provider, '_get_json', fake_get_json)
    assert provider._fetch_nasdaq('VTI') == 337.42


def test_live_quote_requests_use_browser_compatible_headers():
    source = (ROOT / 'src' / 'market_data.py').read_text(encoding='utf-8')
    assert 'QUOTE_BROWSER_USER_AGENT' in source
    assert 'Mozilla/5.0' in source
    assert '_quote_headers(' in source
    assert 'chart-query2' in source
    assert 'NASDAQ_INFO_URL' in source
