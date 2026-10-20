"""WI-024 phase 1 / FIN-001: net realized brokerage gain is part of IRMAA MAGI.

Phase 1 is IRMAA MAGI only (two-year lookback). NIIT, ACA and Social Security
taxation are phase 2 and unchanged here.

Hand computation (MFJ, 2026 tables, tier-1 threshold 218,000, IRMAA applies when
MAGI is strictly above the threshold; bracket/IRMAA factor 1.0 in 2026):
  year 2026: AGI 200,000, brokerage gain 50,000 -> IRMAA MAGI 250,000.
  2028 tier-1 threshold = 218,000 x 1.025^3 = 234,762, rounded to 2,000 = 234,000 (tier 2: 274,000 x 1.076891 = 295,0xx -> 294,000).
  year 2028 assesses on the 2026 return: 250,000 > 234,000 and <= 294,000 -> tier 1.
  Without the gain: 200,000 -> tier 0 (no surcharge).
"""
import pytest

from src import tax_kernel as tk
from src.core import irmaa_lookback_magi_and_filing

C = {"inf": 0.025, "plan_start": 2026}


def test_tier_two_years_after_a_brokerage_gain_closed_form():
    with_gain = [{"year": 2026, "irmaa_magi_current": 200_000.0 + 50_000.0, "filing": "MFJ"},
                 {"year": 2027, "irmaa_magi_current": 150_000.0, "filing": "MFJ"}]
    without = [{"year": 2026, "irmaa_magi_current": 200_000.0, "filing": "MFJ"},
               {"year": 2027, "irmaa_magi_current": 150_000.0, "filing": "MFJ"}]
    magi, filing = irmaa_lookback_magi_and_filing(with_gain, 150_000.0, "MFJ", 2)
    assert (magi, filing) == (250_000.0, "MFJ")
    assert tk.irmaa_tier(magi, 2028, filing, C) == 1
    magi0, filing0 = irmaa_lookback_magi_and_filing(without, 150_000.0, "MFJ", 2)
    assert tk.irmaa_tier(magi0, 2028, filing0, C) == 0


def test_engine_row_irmaa_magi_adds_net_brokerage_gain_and_feeds_the_lookback():
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    from src.planning_engines import project
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(_frozen_config())
    hit = 0
    for i, r in enumerate(rows):
        net = float(r.get("brokerage_gain_in_irmaa_magi") or 0.0)
        if net > 0:
            hit += 1
            assert float(r["irmaa_magi_current"]) >= float(r["agi"]) + net - 1.0
            if i + 2 < len(rows):
                assert rows[i + 2]["irmaa_magi_used"] == pytest.approx(r["irmaa_magi_current"])
    assert hit >= 2
