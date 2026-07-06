"""Ensure the project root is importable as `src` regardless of how pytest is
invoked. Most test modules do `from src.xxx import yyy` with no sys.path setup
of their own, relying on `python -m pytest` adding the current working
directory to sys.path automatically. CI (and any bare `pytest` invocation)
does not get that for free, so this must run before test collection imports
any test module.
"""
import os
import sys
from pathlib import Path

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
