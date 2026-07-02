"""Unit tests for src/market_data.py.

Scope (see documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 5):

- Pure/deterministic helpers: _clean_secret, _secret_fingerprint, _clean_symbol,
  _is_good_price, _to_price, _redact_url, _parse_money_text.
- Forecasting helpers: ewma_forecast, linear_trend_forecast, random_walk_forecast,
  ensemble_forecast.
- Module-level pricing entry points (configure_holdings_pricing,
  configure_api_keys, configure_transport, set_fallback_prices,
  set_frozen_prices, reset_pricing_runtime_state, fetch_price, price_source,
  pricing_diagnostics) exercised ONLY with
  RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 so no real network call is
  ever made. No test in this file performs a live HTTP request.

The module keeps a module-level singleton (`_DEFAULT_PROVIDER`) plus two
module-level caches (`PRICE_CACHE`, `PRICE_SOURCE_CACHE`). An autouse fixture
resets all of that mutable state before and after every test so tests are
order-independent and safe to run twice in the same session.
"""

from __future__ import annotations

import hashlib
import math

import pytest

import src.market_data as market_data
from src.market_data import (
    _clean_secret,
    _clean_symbol,
    _is_good_price,
    _parse_money_text,
    _redact_url,
    _secret_fingerprint,
    _to_price,
    ensemble_forecast,
    ewma_forecast,
    linear_trend_forecast,
    random_walk_forecast,
)


# ---------------------------------------------------------------------------
# Fixture: full isolation of module-level mutable pricing state
# ---------------------------------------------------------------------------
#
# `_DEFAULT_PROVIDER.cache` is loaded ONCE from output/market_price_cache.json
# at provider construction (module import) time and never reloaded from disk
# afterward. Resetting it to `{}` at teardown therefore permanently destroys
# that on-disk-loaded cache for the rest of the pytest session: any later
# test that calls fetch_price() for the same symbols (e.g. via parse_client()
# in an unrelated test file) loses its cache hit and falls through to a real
# network request, which hangs under this project's network policy. Snapshot
# the pristine cache once at import time and restore that snapshot instead of
# wiping it, so this file's tests stay isolated without corrupting shared
# process-wide state for tests that run afterward.
import copy as _copy  # noqa: E402

_PRISTINE_PROVIDER_CACHE = _copy.deepcopy(market_data._DEFAULT_PROVIDER.cache)


def _hard_reset_default_provider():
    market_data.reset_pricing_runtime_state()
    provider = market_data._DEFAULT_PROVIDER
    provider.cache = _copy.deepcopy(_PRISTINE_PROVIDER_CACHE)
    provider.fallback_prices = {}
    provider.frozen_prices = {}
    provider.frozen_metadata = {}
    provider.pricing_mode = "CACHE"
    provider.cache_first = True
    provider.use_live = True
    provider.timeout_seconds = 8
    provider.max_retries = 2
    provider.fmp_api_key = None
    provider.alpha_vantage_api_key = None


@pytest.fixture(autouse=True)
def _isolated_market_data_state(monkeypatch):
    # Never allow this test file to hit the network even if a test forgets to
    # set the env var itself.
    monkeypatch.setenv("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")
    _hard_reset_default_provider()
    yield
    _hard_reset_default_provider()


# ---------------------------------------------------------------------------
# _clean_secret
# ---------------------------------------------------------------------------

def test_clean_secret_none_returns_none():
    assert _clean_secret(None) is None


def test_clean_secret_empty_string_returns_none():
    assert _clean_secret("") is None


def test_clean_secret_whitespace_only_returns_none():
    assert _clean_secret("   ") is None


@pytest.mark.parametrize("placeholder", ["YOUR_KEY", "your_key", "YOUR_KEY_HERE", "REPLACE_ME", "NONE", "N/A", "NA"])
def test_clean_secret_placeholder_values_return_none(placeholder):
    assert _clean_secret(placeholder) is None


def test_clean_secret_strips_whitespace_around_real_value():
    assert _clean_secret("  sk-real-value-123  ") == "sk-real-value-123"


def test_clean_secret_real_value_passthrough():
    assert _clean_secret("sk-abc123") == "sk-abc123"


def test_clean_secret_zero_is_falsy_and_returns_none():
    # str(0 or "") -> str("") -> "" -> None. Matches security.redact_secret's
    # documented falsy-int quirk.
    assert _clean_secret(0) is None


def test_clean_secret_non_string_int_is_coerced():
    assert _clean_secret(123456) == "123456"


# ---------------------------------------------------------------------------
# _secret_fingerprint
# ---------------------------------------------------------------------------

def test_secret_fingerprint_none_returns_none():
    assert _secret_fingerprint(None) is None


def test_secret_fingerprint_empty_string_returns_none():
    assert _secret_fingerprint("") is None


def test_secret_fingerprint_is_deterministic():
    assert _secret_fingerprint("my-api-key") == _secret_fingerprint("my-api-key")


def test_secret_fingerprint_length_is_12():
    assert len(_secret_fingerprint("my-api-key")) == 12


def test_secret_fingerprint_matches_sha256_prefix():
    expected = hashlib.sha256("my-api-key".encode("utf-8")).hexdigest()[:12]
    assert _secret_fingerprint("my-api-key") == expected


def test_secret_fingerprint_different_inputs_differ():
    assert _secret_fingerprint("key-a") != _secret_fingerprint("key-b")


# ---------------------------------------------------------------------------
# _clean_symbol
# ---------------------------------------------------------------------------

def test_clean_symbol_strips_and_uppercases():
    assert _clean_symbol("  vti  ") == "VTI"


def test_clean_symbol_already_clean_passthrough():
    assert _clean_symbol("AAPL") == "AAPL"


def test_clean_symbol_none_returns_empty_string():
    assert _clean_symbol(None) == ""


def test_clean_symbol_empty_string_returns_empty_string():
    assert _clean_symbol("") == ""


def test_clean_symbol_preserves_internal_punctuation():
    # Class-share tickers like BRK.B are uppercased but not otherwise altered.
    assert _clean_symbol("brk.b") == "BRK.B"


def test_clean_symbol_mixed_whitespace_and_case():
    assert _clean_symbol("\tqqq\n") == "QQQ"


# ---------------------------------------------------------------------------
# _is_good_price / _to_price
# ---------------------------------------------------------------------------

def test_is_good_price_none_is_false():
    assert _is_good_price(None) is False


def test_to_price_none_is_none():
    assert _to_price(None) is None


def test_is_good_price_positive_float_is_true():
    assert _is_good_price(123.45) is True


def test_to_price_positive_float_roundtrips():
    assert _to_price(123.45) == 123.45


def test_is_good_price_zero_is_false():
    assert _is_good_price(0) is False
    assert _is_good_price("0") is False


def test_to_price_zero_is_none():
    assert _to_price(0) is None


def test_is_good_price_negative_is_false():
    assert _is_good_price(-5) is False
    assert _is_good_price("-5.50") is False


def test_to_price_negative_is_none():
    assert _to_price(-5) is None


def test_is_good_price_non_numeric_string_is_false():
    assert _is_good_price("abc") is False


def test_to_price_non_numeric_string_is_none():
    assert _to_price("abc") is None


def test_is_good_price_nan_is_false():
    assert _is_good_price(float("nan")) is False


def test_is_good_price_inf_is_false():
    assert _is_good_price(float("inf")) is False


def test_to_price_nan_is_none():
    assert _to_price(float("nan")) is None


@pytest.mark.parametrize("placeholder", ["N/D", "NA", "N/A", "NULL", "NONE", "-", "--"])
def test_is_good_price_placeholder_strings_are_false(placeholder):
    assert _is_good_price(placeholder) is False


def test_is_good_price_string_with_commas_is_true():
    assert _is_good_price("1,234.56") is True


def test_to_price_string_with_commas_parses_correctly():
    assert _to_price("1,234.56") == 1234.56


def test_is_good_price_numeric_string_with_whitespace():
    assert _is_good_price("  42.5  ") is True
    assert _to_price("  42.5  ") == 42.5


# ---------------------------------------------------------------------------
# _redact_url
# ---------------------------------------------------------------------------

def test_redact_url_masks_apikey_query_param():
    url = "https://financialmodelingprep.com/api/v3/quote-short/VTI?apikey=SECRET123"
    out = _redact_url(url)
    assert "SECRET123" not in out
    assert "apikey=%2A%2A%2A" in out or "apikey=***" in out


def test_redact_url_masks_api_key_underscore_variant():
    url = "https://example.com/quote?symbol=VTI&api_key=SECRET456"
    out = _redact_url(url)
    assert "SECRET456" not in out
    assert "symbol=VTI" in out


def test_redact_url_preserves_other_query_params():
    url = "https://example.com/quote?symbol=VTI&apikey=SECRET123&range=1d"
    out = _redact_url(url)
    assert "symbol=VTI" in out
    assert "range=1d" in out
    assert "SECRET123" not in out


def test_redact_url_without_api_key_is_unchanged():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/VTI?range=1d&interval=1d"
    assert _redact_url(url) == url


def test_redact_url_case_insensitive_detection_still_masks():
    url = "https://example.com/quote?APIKey=SECRET789"
    out = _redact_url(url)
    assert "SECRET789" not in out


# ---------------------------------------------------------------------------
# _parse_money_text
# ---------------------------------------------------------------------------

def test_parse_money_text_dollar_and_commas():
    assert _parse_money_text("$1,234.56") == 1234.56


def test_parse_money_text_plain_number_string():
    assert _parse_money_text("42.50") == 42.5


def test_parse_money_text_usd_suffix():
    assert _parse_money_text("1234.56 USD") == 1234.56


def test_parse_money_text_parenthesized_negative_is_none():
    # SURPRISE: _parse_money_text rewrites "(123.45)" to the string "-123.45"
    # (accounting-negative convention) but then delegates to _to_price, which
    # calls _is_good_price and requires f > 0. So the parenthesis-negative
    # branch always produces a negative number that _to_price immediately
    # rejects, and this function can never actually return a negative value.
    assert _parse_money_text("(123.45)") is None


def test_parse_money_text_none_returns_none():
    assert _parse_money_text(None) is None


def test_parse_money_text_empty_string_returns_none():
    assert _parse_money_text("") is None


def test_parse_money_text_invalid_text_returns_none():
    assert _parse_money_text("not-a-price") is None


def test_parse_money_text_zero_dollar_amount_is_none():
    # _to_price requires f > 0, so "$0.00" is treated as not-a-good-price.
    assert _parse_money_text("$0.00") is None


def test_parse_money_text_negative_without_parens():
    assert _parse_money_text("-42.50") is None  # _is_good_price requires f > 0


# ---------------------------------------------------------------------------
# ewma_forecast
# ---------------------------------------------------------------------------

def test_ewma_forecast_known_series_and_horizon():
    result = ewma_forecast([100, 110, 120], 3)
    assert len(result) == 3
    # level_0 = 100; level_1 = 0.35*110 + 0.65*100 = 103.5;
    # level_2 = 0.35*120 + 0.65*103.5 = 109.275
    assert result[0] == pytest.approx(109.275)
    # All horizon values are flat (ewma forecast repeats the last level).
    assert result == [result[0]] * 3


def test_ewma_forecast_empty_series_returns_zeros():
    assert ewma_forecast([], 4) == [0.0, 0.0, 0.0, 0.0]


def test_ewma_forecast_single_value_series_holds_flat():
    assert ewma_forecast([50.0], 2) == [50.0, 50.0]


def test_ewma_forecast_ignores_non_finite_values():
    result = ewma_forecast([100, float("nan"), 110, float("inf"), 120], 1)
    assert result == ewma_forecast([100, 110, 120], 1)


# ---------------------------------------------------------------------------
# linear_trend_forecast
# ---------------------------------------------------------------------------

def test_linear_trend_forecast_known_linear_series():
    # Perfectly linear series with slope 10 extrapolates exactly.
    result = linear_trend_forecast([100, 110, 120], 3)
    assert result == pytest.approx([130.0, 140.0, 150.0])


def test_linear_trend_forecast_empty_series_returns_zeros():
    assert linear_trend_forecast([], 3) == [0.0, 0.0, 0.0]


def test_linear_trend_forecast_single_value_holds_flat():
    assert linear_trend_forecast([42.0], 3) == [42.0, 42.0, 42.0]


def test_linear_trend_forecast_length_matches_horizon():
    assert len(linear_trend_forecast([1, 2, 3, 4, 5], 7)) == 7


# ---------------------------------------------------------------------------
# random_walk_forecast
# ---------------------------------------------------------------------------

def test_random_walk_forecast_length_matches_horizon():
    result = random_walk_forecast([100, 110, 120], 5)
    assert len(result) == 5
    assert all(math.isfinite(v) for v in result)


def test_random_walk_forecast_empty_series_returns_zeros():
    assert random_walk_forecast([], 3) == [0.0, 0.0, 0.0]


def test_random_walk_forecast_is_deterministic_for_fixed_seed():
    a = random_walk_forecast([100, 110, 120], 4, seed=42)
    b = random_walk_forecast([100, 110, 120], 4, seed=42)
    assert a == b


def test_random_walk_forecast_different_seeds_generally_differ():
    # A perfectly linear series like [100, 110, 120] has zero diff-variance
    # (vol == 0.0), so rng.gauss(0.0, 0.0) is 0.0 for every seed and the walk
    # is seed-independent. Use a series with real variance so the seed
    # actually influences the Gaussian noise term.
    series = [100, 105, 98, 120, 103]
    a = random_walk_forecast(series, 4, seed=1)
    b = random_walk_forecast(series, 4, seed=2)
    assert a != b


def test_random_walk_forecast_no_drift_no_vol_holds_flat():
    # A constant series has zero diffs, so drift and volatility are both 0;
    # the walk should stay exactly at the last observed value.
    result = random_walk_forecast([50.0, 50.0, 50.0], 3, seed=7)
    assert result == [50.0, 50.0, 50.0]


# ---------------------------------------------------------------------------
# ensemble_forecast
# ---------------------------------------------------------------------------

def test_ensemble_forecast_return_shape():
    result = ensemble_forecast([100, 110, 120], 3)
    assert set(result.keys()) == {"models", "ensemble", "horizon", "backtest_mae", "seed"}
    assert set(result["models"].keys()) == {"ewma", "linear_trend", "random_walk"}
    assert len(result["ensemble"]) == 3
    assert result["horizon"] == 3
    assert result["seed"] == 42


def test_ensemble_forecast_weighted_blend_matches_component_models():
    result = ensemble_forecast([100, 110, 120], 3)
    ew = result["models"]["ewma"]
    lt = result["models"]["linear_trend"]
    rw = result["models"]["random_walk"]
    expected = [0.45 * a + 0.35 * b + 0.20 * c for a, b, c in zip(ew, lt, rw)]
    assert result["ensemble"] == pytest.approx(expected)


def test_ensemble_forecast_short_history_skips_backtest():
    # len(hist) < 4 -> backtest is skipped and mae defaults to 0.0.
    result = ensemble_forecast([100, 110, 120], 2)
    assert result["backtest_mae"] == 0.0


def test_ensemble_forecast_longer_history_runs_backtest():
    result = ensemble_forecast([100, 105, 110, 115, 120, 125], 2)
    assert result["backtest_mae"] >= 0.0
    assert isinstance(result["backtest_mae"], float)


def test_ensemble_forecast_custom_seed_is_recorded():
    result = ensemble_forecast([100, 110, 120], 2, seed=99)
    assert result["seed"] == 99


# ---------------------------------------------------------------------------
# Module-level pricing configuration (network fully disabled)
# ---------------------------------------------------------------------------

def test_disable_live_env_flag_is_read_from_source():
    # Confirms the escape hatch this whole test file depends on actually
    # exists in the source at the documented location.
    import inspect
    source = inspect.getsource(market_data)
    assert "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS" in source
    assert "disable_live_env" in source


def test_configure_holdings_pricing_cache_mode_defaults():
    market_data.configure_holdings_pricing(mode="CACHE", cache_hours=24)
    diag = market_data.pricing_diagnostics()
    assert diag["pricing_mode"] == "CACHE"
    assert diag["cache_first_enabled"] is True
    assert diag["live_enabled"] is True
    assert diag["cache_ttl_hours"] == 24.0


def test_configure_holdings_pricing_live_mode():
    market_data.configure_holdings_pricing(mode="LIVE", cache_hours=12)
    diag = market_data.pricing_diagnostics()
    assert diag["pricing_mode"] == "LIVE"
    assert diag["cache_first_enabled"] is False
    assert diag["live_enabled"] is True
    assert diag["cache_ttl_hours"] == 12.0


def test_configure_holdings_pricing_offline_mode():
    market_data.configure_holdings_pricing(mode="OFFLINE", cache_hours=6)
    diag = market_data.pricing_diagnostics()
    assert diag["pricing_mode"] == "OFFLINE"
    # SURPRISE: cache_first is only True for CACHE/FROZEN modes, so OFFLINE
    # actually sets cache_first to False (it is not in ("CACHE", "FROZEN")).
    # OFFLINE still never calls live providers (use_live False); quote()
    # falls through to the "check cache regardless of cache_first" branch
    # after skipping the live-provider loop, which is how OFFLINE ends up
    # reading stale cache despite cache_first being False here.
    assert diag["cache_first_enabled"] is False
    assert diag["live_enabled"] is False


def test_configure_holdings_pricing_alias_realtime_maps_to_live():
    market_data.configure_holdings_pricing(mode="realtime", cache_hours=24)
    assert market_data.pricing_diagnostics()["pricing_mode"] == "LIVE"


def test_configure_holdings_pricing_alias_off_maps_to_offline():
    market_data.configure_holdings_pricing(mode="off", cache_hours=24)
    assert market_data.pricing_diagnostics()["pricing_mode"] == "OFFLINE"


def test_configure_holdings_pricing_unknown_mode_defaults_to_cache():
    market_data.configure_holdings_pricing(mode="not-a-real-mode", cache_hours=24)
    assert market_data.pricing_diagnostics()["pricing_mode"] == "CACHE"


def test_configure_holdings_pricing_invalid_cache_hours_defaults_to_24():
    market_data.configure_holdings_pricing(mode="CACHE", cache_hours="not-a-number")
    assert market_data.pricing_diagnostics()["cache_ttl_hours"] == 24.0


def test_configure_api_keys_sets_fingerprints_and_configured_flags():
    market_data.configure_api_keys(fmp_api_key="fmp-test-key-123", alpha_vantage_api_key="alpha-test-key-456")
    diag = market_data.pricing_diagnostics()
    assert diag["fmp_api_key_configured"] is True
    assert diag["alpha_vantage_api_key_configured"] is True
    assert diag["fmp_api_key_fingerprint"] == _secret_fingerprint("fmp-test-key-123")
    assert diag["alpha_vantage_api_key_fingerprint"] == _secret_fingerprint("alpha-test-key-456")


def test_configure_api_keys_placeholder_values_are_ignored():
    market_data.configure_api_keys(fmp_api_key="YOUR_KEY", alpha_vantage_api_key="REPLACE_ME")
    diag = market_data.pricing_diagnostics()
    assert diag["fmp_api_key_configured"] is False
    assert diag["alpha_vantage_api_key_configured"] is False


def test_configure_transport_updates_timeout_and_retries():
    market_data.configure_transport(timeout_seconds=15, max_retries=5)
    diag = market_data.pricing_diagnostics()
    assert diag["timeout_seconds"] == 15
    assert diag["max_retries"] == 5


def test_configure_transport_invalid_values_are_ignored():
    market_data.configure_transport(timeout_seconds=20, max_retries=4)
    market_data.configure_transport(timeout_seconds="not-a-number", max_retries="also-bad")
    diag = market_data.pricing_diagnostics()
    # Invalid values are swallowed; prior valid configuration is retained.
    assert diag["timeout_seconds"] == 20
    assert diag["max_retries"] == 4


def test_set_fallback_prices_only_keeps_good_prices():
    market_data.set_fallback_prices({"AAPL": 150.0, "BADSYM": -5, "ZERO": 0})
    diag = market_data.pricing_diagnostics()
    assert "AAPL" in diag["fallback_symbols"]
    assert "BADSYM" not in diag["fallback_symbols"]
    assert "ZERO" not in diag["fallback_symbols"]


def test_set_frozen_prices_activates_frozen_mode_and_metadata():
    market_data.set_frozen_prices({"VTI": 250.12}, metadata={"frozen_at": "2026-01-01T00:00:00Z"})
    diag = market_data.pricing_diagnostics()
    assert diag["frozen_pricing_active"] is True
    assert "VTI" in diag["frozen_symbols"]
    assert diag["pricing_mode"] == "FROZEN"
    assert diag["frozen_metadata"]["frozen_at"] == "2026-01-01T00:00:00Z"


def test_set_frozen_prices_clears_module_level_price_caches():
    market_data.fetch_price("CASH")
    assert "CASH" in market_data.PRICE_CACHE
    market_data.set_frozen_prices({"VTI": 250.12})
    assert market_data.PRICE_CACHE == {}
    assert market_data.PRICE_SOURCE_CACHE == {}


def test_reset_pricing_runtime_state_clears_module_price_caches():
    market_data.fetch_price("CASH")
    assert market_data.PRICE_CACHE
    market_data.reset_pricing_runtime_state()
    assert market_data.PRICE_CACHE == {}
    assert market_data.PRICE_SOURCE_CACHE == {}


def test_fetch_price_cash_is_hardcoded_and_never_calls_network():
    assert market_data.fetch_price("CASH") == 1.0
    assert market_data.price_source("CASH") == "cash"


def test_fetch_price_resolves_via_fallback_when_live_disabled_and_no_cache():
    market_data.configure_holdings_pricing(mode="CACHE", cache_hours=24)
    market_data.set_fallback_prices({"ZZFAKESYM": 42.75})
    price = market_data.fetch_price("ZZFAKESYM")
    assert price == 42.75
    assert market_data.price_source("ZZFAKESYM") == "holdings_cost_basis_fallback"


def test_fetch_price_missing_symbol_with_no_fallback_returns_zero():
    market_data.configure_holdings_pricing(mode="CACHE", cache_hours=24)
    price = market_data.fetch_price("ZZNOFALLBACKSYM")
    assert price == 0.0
    assert market_data.price_source("ZZNOFALLBACKSYM") == "missing"


def test_pricing_diagnostics_reports_live_providers_skipped_failure(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")
    market_data.configure_holdings_pricing(mode="LIVE", cache_hours=24)
    market_data.fetch_price("ZZANOTHERFAKESYM")
    diag = market_data.pricing_diagnostics()
    causes = [f.get("cause", "") for f in diag["failures"]]
    assert any("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS" in c for c in causes)


def test_price_source_unknown_symbol_never_requested_is_missing_after_fetch():
    market_data.configure_holdings_pricing(mode="CACHE", cache_hours=24)
    assert market_data.fetch_price("ZZANOTHERUNSEENSYM") == 0.0
    assert market_data.price_source("ZZANOTHERUNSEENSYM") == "missing"
