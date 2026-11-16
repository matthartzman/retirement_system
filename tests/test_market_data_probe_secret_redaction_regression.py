"""The price tester reports exception text to the user; it must never carry the provider key from the request URL."""
from __future__ import annotations

from src import market_data


def test_probe_exception_text_has_the_api_key_masked(monkeypatch):
    assert hasattr(market_data, "_redact_exception")
    text = market_data._redact_exception(RuntimeError(
        "Max retries exceeded with url: /api/v3/quote-short/AAPL?apikey=SHAREDKEY_ABC123 (Caused by X)"))
    assert "SHAREDKEY_ABC123" not in text and "apikey=" in text
