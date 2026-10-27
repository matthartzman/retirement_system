"""quote_details(): live price + previous close for the Financial Trends Live Snapshot view.

Unlike quote(), it never memoizes (the reporter server is long-running and polls every
60 s), and it returns the previous close so the view can show Day $ / Day %.
No test here touches the network: _get_json / _try_provider are patched.
"""
from __future__ import annotations

import pytest

import src.market_data as market_data
from src.market_data import MarketDataProvider


def _chart(price=101.5, previous_close=100.0, chart_previous_close=99.0, market_time=1793114284):
    meta = {"regularMarketPrice": price, "chartPreviousClose": chart_previous_close, "regularMarketTime": market_time}
    if previous_close is not None:
        meta["previousClose"] = previous_close
    return {"chart": {"result": [{"meta": meta}], "error": None}}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.delenv("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", raising=False)
    p = MarketDataProvider()
    p.cache = {}
    monkeypatch.setattr(p, "_save_cache", lambda: None)
    return p


def test_yahoo_chart_gives_price_previous_close_and_time(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: (_chart(), None))
    d = provider.quote_detail("itot")
    assert d["symbol"] == "ITOT"
    assert d["price"] == 101.5
    assert d["previous_close"] == 100.0
    assert d["as_of"] == "2026-10-27T15:18:04Z"
    assert d["source"] == "yahoo_live"
    assert d["stale"] is False


def test_chart_previous_close_used_when_previous_close_missing(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: (_chart(previous_close=None), None))
    assert provider.quote_detail("ITOT")["previous_close"] == 99.0


def test_index_symbol_keeps_caret(provider, monkeypatch):
    urls = []
    monkeypatch.setattr(provider, "_get_json", lambda name, sym, url: (urls.append(url), (_chart(), None))[1])
    assert provider.quote_detail("^GSPC")["symbol"] == "^GSPC"
    assert "%5EGSPC" in urls[0]


def test_live_price_updates_shared_cache(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: (_chart(), None))
    provider.quote_detail("ITOT")
    assert provider.cache["ITOT"]["price"] == 101.5


def test_not_memoized_between_calls(provider, monkeypatch):
    prices = iter([101.0, 102.0])
    monkeypatch.setattr(provider, "_get_json", lambda *a: (_chart(price=next(prices)), None))
    assert provider.quote_detail("ITOT")["price"] == 101.0
    assert provider.quote_detail("ITOT")["price"] == 102.0


def test_other_provider_when_yahoo_fails(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: (None, "Yahoo Finance rate limit exceeded."))
    tried = []

    def fake_try(name, symbol):
        tried.append(name)
        return 55.0 if name == "nasdaq" else None

    monkeypatch.setattr(provider, "_try_provider", fake_try)
    d = provider.quote_detail("ITOT")
    assert "yahoo" not in tried
    assert d["price"] == 55.0
    assert d["previous_close"] is None
    assert d["source"] == "nasdaq_live"
    assert d["stale"] is False


def test_stale_cache_when_every_provider_fails(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: (None, "network timeout"))
    monkeypatch.setattr(provider, "_try_provider", lambda name, symbol: None)
    provider.cache["ITOT"] = {"price": 90.0, "source": "yahoo", "timestamp": 1.0}
    d = provider.quote_detail("ITOT")
    assert d["price"] == 90.0
    assert d["stale"] is True
    assert d["source"] == "stale_cache_from_yahoo"


def test_missing_when_nothing_available(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: (None, "network timeout"))
    monkeypatch.setattr(provider, "_try_provider", lambda name, symbol: None)
    d = provider.quote_detail("ZZZZ")
    assert d["price"] is None and d["stale"] is True and d["source"] == "missing"


def test_cash_is_one(provider, monkeypatch):
    monkeypatch.setattr(provider, "_get_json", lambda *a: pytest.fail("no network for CASH"))
    d = provider.quote_detail("CASH")
    assert (d["price"], d["previous_close"], d["stale"]) == (1.0, 1.0, False)


def test_disable_env_skips_network(provider, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")
    monkeypatch.setattr(provider, "_get_json", lambda *a: pytest.fail("network called"))
    monkeypatch.setattr(provider, "_try_provider", lambda *a: pytest.fail("network called"))
    provider.cache["ITOT"] = {"price": 90.0, "source": "yahoo", "timestamp": 1.0}
    assert provider.quote_detail("ITOT")["price"] == 90.0


def test_quote_details_batch_dedups_and_cleans(provider, monkeypatch):
    calls = []
    monkeypatch.setattr(provider, "_get_json", lambda name, sym, url: (calls.append(sym), (_chart(), None))[1])
    out = provider.quote_details(["itot", "ITOT ", "IXUS"])
    assert sorted(out) == ["ITOT", "IXUS"]
    assert sorted(calls) == ["ITOT", "IXUS"]


def test_module_level_wrapper_uses_default_provider(monkeypatch):
    monkeypatch.setattr(market_data._DEFAULT_PROVIDER, "quote_details", lambda symbols: {"X": {"price": 1.0}})
    assert market_data.quote_details(["X"]) == {"X": {"price": 1.0}}


def _history(timestamps, closes):
    return {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York", "gmtoffset": -18000}, "timestamp": timestamps,
                                   "indicators": {"quote": [{"close": closes}]}}], "error": None}}


def test_daily_closes_by_exchange_date(provider, monkeypatch):
    from datetime import date
    urls = []
    # 2025-12-30 and 2025-12-31 14:30Z bar starts (09:30 ET); a None close is skipped.
    payload = _history([1767105000, 1767191400, 1767364200], [60.0, 61.0, None])
    monkeypatch.setattr(provider, "_get_json", lambda name, sym, url: (urls.append(url), (payload, None))[1])
    out = provider.daily_closes("ixus", date(2025, 12, 21), date(2026, 1, 1))
    assert out == {"2025-12-30": 60.0, "2025-12-31": 61.0}
    assert "interval=1d" in urls[0] and "period1=" in urls[0] and "/IXUS?" in urls[0]


def test_daily_closes_empty_on_failure_or_disabled(provider, monkeypatch):
    from datetime import date
    monkeypatch.setattr(provider, "_get_json", lambda *a: (None, "network timeout"))
    assert provider.daily_closes("IXUS", date(2025, 12, 21), date(2026, 1, 1)) == {}
    monkeypatch.setenv("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")
    monkeypatch.setattr(provider, "_get_json", lambda *a: pytest.fail("network called"))
    assert provider.daily_closes("IXUS", date(2025, 12, 21), date(2026, 1, 1)) == {}
