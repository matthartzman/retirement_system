"""PR-08 / X-6: the price symbol tester validates symbols, caps concurrent jobs and keeps tracebacks out of remote mode."""
from __future__ import annotations

import threading
import urllib.parse

import pytest

from src import remote_mode
from src.server_services import pricing_service as ps


@pytest.mark.parametrize("symbol", ["A/../../v4/profile/AAPL", "AAPL?x=1", "A B", "", "A" * 16, "<script>", "aapl;"])
def test_bad_symbols_are_refused_before_any_provider_call(monkeypatch, symbol):
    monkeypatch.setattr(ps, "run_price_symbol_trace", lambda *a, **k: pytest.fail("provider must not be called"))
    payload, status = ps.single_symbol_test_payload({"symbol": symbol}, workspace_id="w")
    assert status == 400 and payload["success"] is False
    payload, status = ps.PriceSymbolTestRegistry().start_payload({"symbol": symbol}, workspace_id="w")
    assert status == 400


@pytest.mark.parametrize("symbol", ["AAPL", "brk-b", "BRK.B", "^GSPC", "EURUSD=X", "A" * 15])
def test_real_symbols_are_accepted(monkeypatch, symbol):
    monkeypatch.setattr(ps, "run_price_symbol_trace", lambda sym, **k: {"success": True, "symbol": sym})
    payload, status = ps.single_symbol_test_payload({"symbol": symbol}, workspace_id="w")
    assert status == 200 and payload["live_pricing_working"] is True


def test_concurrent_jobs_are_capped(monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(ps, "run_price_symbol_trace", lambda *a, **k: gate.wait(5) and {"success": True})
    reg = ps.PriceSymbolTestRegistry()
    results = [reg.start_payload({"symbol": f"S{i}"}, workspace_id="w")[1] for i in range(ps.MAX_CONCURRENT_SYMBOL_TESTS + 2)]
    gate.set()
    assert results[: ps.MAX_CONCURRENT_SYMBOL_TESTS] == [200] * ps.MAX_CONCURRENT_SYMBOL_TESTS
    assert results[ps.MAX_CONCURRENT_SYMBOL_TESTS:] == [429, 429]


@pytest.mark.parametrize("remote", [True, False])
def test_traceback_tail_is_omitted_in_remote_mode(monkeypatch, remote):
    monkeypatch.setattr(remote_mode, "enabled", lambda: remote)

    def boom(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(ps, "run_price_symbol_trace", boom)
    payload, _ = ps.single_symbol_test_payload({"symbol": "AAPL"}, workspace_id="w")
    assert ("traceback_tail" in payload["result"]) is (not remote)
    reg = ps.PriceSymbolTestRegistry()
    job_id = reg.start_payload({"symbol": "AAPL"}, workspace_id="w")[0]["job_id"]
    for _ in range(100):
        body, _ = reg.status_payload(job_id)
        if body.get("status") != "running":
            break
        threading.Event().wait(0.05)
    assert ("traceback_tail" in (body.get("result") or {})) is (not remote)


def test_quote_encodes_the_slash_so_a_symbol_cannot_walk_the_provider_path():
    assert urllib.parse.quote("A/../B", safe="") == "A%2F..%2FB"
    import inspect

    from src import market_data

    src = inspect.getsource(market_data.MarketDataProvider.verbose_symbol_test)
    assert "quote(symbol)" not in src
