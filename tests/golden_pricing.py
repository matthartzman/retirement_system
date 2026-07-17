"""Shared frozen-holdings-price pin for deterministic golden-master tests.

OFFLINE pricing (forced session-wide by tests/conftest.py) is cache-first
against the untracked ``output/market_price_cache.json``, so terminal-net-worth
baselines drift by machine/time (mark-to-market on unsold holdings). Pinning the
exact per-symbol prices below removes that dependency, making the golden-master
projections reproducible and portable.

This module is the single source of truth for the frozen snapshot and the
context manager; test_2, test_167, and test_phase5 all import from here (they
previously kept private, hand-synced copies). Update the prices only when
regenerating the golden-master pins deliberately.
"""
from __future__ import annotations

import contextlib
import os

from src import market_data as _market_data

FROZEN_GOLDEN_MASTER_PRICES = {
    "VTI": 371.835, "VXUS": 84.145, "AVUV": 126.37, "VBR": 245.525,
    "ITOT": 165.265, "IXUS": 93.94, "PDBC": 17.05,
}


@contextlib.contextmanager
def frozen_holdings_prices(prices=FROZEN_GOLDEN_MASTER_PRICES):
    """Pin holdings pricing to an exact snapshot for the duration of the block.

    parse_client() calls market_data.configure_holdings_pricing() on every
    invocation, forced to RETIREMENT_SYSTEM_FORCE_PRICING_MODE (OFFLINE, per
    tests/conftest.py) — which wipes provider.frozen_prices unless the mode is
    itself FROZEN. So this overrides that env var to FROZEN as well as setting
    the frozen prices, then restores both afterward so nothing leaks into other
    tests (the provider is a process-wide singleton).
    """
    provider = _market_data._DEFAULT_PROVIDER
    saved = (provider.pricing_mode, provider.cache_first, provider.use_live,
             dict(provider.frozen_prices), dict(provider.frozen_metadata))
    env_var = "RETIREMENT_SYSTEM_FORCE_PRICING_MODE"
    saved_env = os.environ.get(env_var)
    os.environ[env_var] = "FROZEN"
    provider.set_frozen_prices(prices, metadata={"frozen_for": "golden_master_test"})
    try:
        yield
    finally:
        if saved_env is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = saved_env
        (provider.pricing_mode, provider.cache_first, provider.use_live,
         provider.frozen_prices, provider.frozen_metadata) = saved
        _market_data.reset_pricing_runtime_state()
