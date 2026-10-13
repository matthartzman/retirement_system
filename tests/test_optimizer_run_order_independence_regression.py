"""M5: a scenario run gives the same result however many runs came before it in the process.

The cause was ``LotEngine`` holding a live reference to the process-wide price cache
(``market_data.PRICE_CACHE``), which is cleared and refilled between runs: a config built
once and run twice priced its lots from whatever the cache held at the time."""
from __future__ import annotations

import copy

import src.planning_engines as pe
from src import market_data
from src.core import LotEngine
from tests import rental_fixtures as rf
from tests.golden_pricing import frozen_holdings_prices
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace


def test_lot_engine_does_not_alias_the_price_cache():
    cache = {"VTI": 100.0}
    eng = LotEngine({}, cache)
    cache.clear()
    cache["VTI"] = 5.0
    assert eng.prices == {"VTI": 100.0}


def test_first_and_second_run_agree_after_the_price_cache_is_cleared():
    c0 = rf.base_config()  # built outside the frozen pricing: fills the cache the way a first run sees it
    nw = []
    for _ in range(3):
        with empty_workspace(), frozen_holdings_prices():
            _, rows = pe.run_scenario(copy.deepcopy(c0))
        nw.append(rows[-1]["total_nw"])
    assert nw[0] == nw[1] == nw[2]
    assert market_data.PRICE_CACHE == {}
