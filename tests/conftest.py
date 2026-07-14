"""Ensure the project root is importable as `src` regardless of how pytest is
invoked. Most test modules do `from src.xxx import yyy` with no sys.path setup
of their own, relying on `python -m pytest` adding the current working
directory to sys.path automatically. CI (and any bare `pytest` invocation)
does not get that for free, so this must run before test collection imports
any test module.
"""
import copy
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Pin holdings pricing to OFFLINE for the whole test run so projections are
# reproducible in CI. Without this, the active plan config requests LIVE
# pricing, so every golden-master run re-prices holdings against live market
# data (and rewrites output/market_price_cache.json), making dollar-total
# assertions drift by thousands between identical runs. OFFLINE routes every
# quote through the committed cache snapshot / holdings cost basis — no network,
# no cache mutation. Only the default provider that parse_client drives honors
# this; tests that build their own MarketDataProvider to exercise live/frozen
# behavior call the instance method directly and are unaffected. setdefault so
# a developer can still override (e.g. LIVE) for an intentional refresh.
os.environ.setdefault("RETIREMENT_SYSTEM_FORCE_PRICING_MODE", "OFFLINE")


# Prevent one test's live/cache-mode price fetch from leaking into another
# (nominally OFFLINE/FROZEN) test's financial-projection results via the
# process-wide MarketDataProvider singleton (src/market_data.py's
# _DEFAULT_PROVIDER). Its .cache dict is loaded once from disk at provider
# construction (module import) time and never reloaded afterward, and
# reset_runtime_state()/set_frozen_prices() never clear it - so a test that
# fetches a live/cached price mutates .cache for the rest of the whole pytest
# process, silently changing later tests' results depending on run order
# (observed: test_2_recommendations.py's golden-master terminal net worth
# shifted ~$800k depending on whether an earlier test in the same file had
# called forecast_from_plan_json first). Snapshot the pristine on-disk cache
# once, then restore it before/after every test - mirrors the same pattern
# tests/test_market_data_module.py already uses for its own file, generalized
# to the whole suite.
import src.market_data as _market_data  # noqa: E402

_PRISTINE_PROVIDER_CACHE = copy.deepcopy(_market_data._DEFAULT_PROVIDER.cache)


@pytest.fixture(autouse=True)
def _reset_market_data_price_cache():
    _market_data._DEFAULT_PROVIDER.cache = copy.deepcopy(_PRISTINE_PROVIDER_CACHE)
    yield
    _market_data._DEFAULT_PROVIDER.cache = copy.deepcopy(_PRISTINE_PROVIDER_CACHE)
