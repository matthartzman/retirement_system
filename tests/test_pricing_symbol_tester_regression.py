from __future__ import annotations

from pathlib import Path

from src.market_data import MarketDataProvider

ROOT = Path(__file__).resolve().parents[1]


def test_verbose_symbol_tester_records_command_response_and_selected_price(monkeypatch, tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    provider.configure_holdings_pricing(mode="LIVE", cache_hours=24)
    provider.fmp_api_key = "test-fmp-key"
    provider.alpha_vantage_api_key = "test-alpha-key"

    def fake_probe_json(provider_name, symbol, url):
        attempt = {
            "transport": "mock",
            "command": {"method": "GET", "url": url.replace("test-fmp-key", "***").replace("test-alpha-key", "***")},
            "ok": True,
            "status_code": 200,
            "elapsed_ms": 3,
            "response_preview": "mock response",
        }
        if "Yahoo Finance chart-query1" in provider_name:
            return {"chart": {"result": [{"meta": {"regularMarketPrice": 123.45}}]}}, None, [attempt]
        return {}, None, [attempt]

    def fake_probe_text(provider_name, symbol, url, accept="text/csv,*/*"):
        return "Symbol,Date,Time,Open,High,Low,Close,Volume\nVTI,2026-06-14,22:00,1,1,1,88.00,100\n", None, [{"transport": "mock", "command": {"method": "GET", "url": url}, "ok": True, "status_code": 200, "elapsed_ms": 2, "response_preview": "csv"}]

    monkeypatch.setattr(provider, "_probe_http_json", fake_probe_json)
    monkeypatch.setattr(provider, "_probe_http_text", fake_probe_text)
    trace = provider.verbose_symbol_test("vti")
    assert trace["success"] is True
    assert trace["symbol"] == "VTI"
    assert trace["selected_provider"] == "yahoo"
    assert trace["selected_price"] == 123.45
    assert trace["steps"]
    assert any(step["attempts"][0]["command"]["method"] == "GET" for step in trace["steps"] if step.get("attempts"))
    assert any(step.get("provider") == "stooq" and step.get("parsed_price") == 88.0 for step in trace["steps"])


def test_verbose_symbol_tester_skips_keyed_providers_when_keys_missing(monkeypatch, tmp_path):
    provider = MarketDataProvider(cache_path=tmp_path / "cache.json", diagnostics_path=tmp_path / "diag.json")
    provider.fmp_api_key = None
    provider.alpha_vantage_api_key = None
    monkeypatch.setattr(provider, "refresh_api_keys", lambda: None)
    monkeypatch.setattr(provider, "_probe_http_json", lambda provider_name, symbol, url: ({}, "mock failure", []))
    monkeypatch.setattr(provider, "_probe_http_text", lambda provider_name, symbol, url, accept="text/csv,*/*": ("", "mock failure", []))
    trace = provider.verbose_symbol_test("VTI")
    skipped = [s for s in trace["steps"] if s.get("outcome") == "skipped"]
    assert any(s.get("provider") == "financial_modeling_prep" for s in skipped)
    assert any(s.get("provider") == "alpha_vantage" for s in skipped)


def test_server_exposes_single_symbol_pricing_tester_endpoint():
    source = (ROOT / "src" / "server" / "plan_routes.py").read_text(encoding="utf-8")
    assert "/api/prices/test-symbol" in source
    assert "verbose_symbol_test" in source
    assert "MarketDataProvider" in source
    assert "live_pricing_working" in source


def test_admin_pricing_controls_include_verbose_symbol_tester():
    source = (ROOT / "frontend" / "js" / "admin.js").read_text(encoding="utf-8")
    assert "Single-symbol live pricing tester" in source
    assert "runLivePriceSymbolTest" in source
    assert "/api/prices/test-symbol" in source
    assert "Provider command / response trace" in source
    assert "Command sent" in source
    assert "Response preview" in source


def test_user_holdings_page_includes_same_live_pricing_tester():
    source = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "renderUserPricingSymbolTester" in source
    assert "runUserLivePriceSymbolTest" in source
    assert "/api/prices/test-symbol" in source
    assert "Provider command / response trace" in source
    assert "Command sent" in source
    assert "Response preview" in source


def test_user_pricing_tester_uses_dashboard_message_helper_not_admin_msg():
    source = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    start = source.index("async function runUserLivePriceSymbolTest")
    end = source.index("function renderHoldings", start)
    block = source[start:end]
    assert "msg(" not in block
    assert "showMessage(" in block
    assert "Pricing tester could not reach the local API" in block
