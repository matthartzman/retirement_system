"""PTE election (CPA-approved approach, W3-01 follow-up): entity tax reduces the distribution; the owner's Illinois base excludes the taxed income."""
from __future__ import annotations

import pytest

from src.projection_stages.income import _scorp_pte_tax, pte_first_year


def test_pte_tax_applies_only_when_elected_in_illinois():
    c = {"state": "Illinois", "pte_election": True, "pte_rate": 0.0495, "pte_first_year": 2027, "plan_start": 2026}
    assert _scorp_pte_tax(c, 2027, 200_000.0) == pytest.approx(9_900.0)
    assert _scorp_pte_tax({**c, "pte_election": False}, 2027, 200_000.0) == 0.0
    assert _scorp_pte_tax({**c, "state": "Texas"}, 2027, 200_000.0) == 0.0
    assert _scorp_pte_tax(c, 2027, -5.0) == 0.0


def test_pte_first_year_gates_the_tax():
    c = {"state": "Illinois", "pte_election": True, "pte_rate": 0.0495, "pte_first_year": 2027, "plan_start": 2026}
    assert _scorp_pte_tax(c, 2026, 200_000.0) == 0.0           # no election was made for 2026
    assert _scorp_pte_tax(c, 2027, 200_000.0) == pytest.approx(9_900.0)
    assert _scorp_pte_tax(c, 2030, 200_000.0) == pytest.approx(9_900.0)
    assert _scorp_pte_tax({**c, "pte_first_year": 2029}, 2028, 200_000.0) == 0.0
    assert _scorp_pte_tax({**c, "pte_first_year": 2029}, 2029, 200_000.0) == pytest.approx(9_900.0)
    assert _scorp_pte_tax({**c, "pte_election": False}, 2030, 200_000.0) == 0.0   # toggle off: zero everywhere


def test_pte_first_year_default_and_floor():
    base = {"state": "Illinois", "pte_election": True, "pte_rate": 0.0495}
    assert pte_first_year({**base, "plan_start": 2026, "pte_first_year": None}) == 2027   # blank: plan start + 1
    assert pte_first_year({**base, "plan_start": 2028}) == 2029
    assert pte_first_year({**base, "plan_start": 2026, "pte_first_year": 2025}) == 2027   # never before 2027
    assert pte_first_year({**base, "plan_start": 2026, "pte_first_year": 2026}) == 2027
    assert _scorp_pte_tax({**base, "plan_start": 2026}, 2026, 200_000.0) == 0.0


def _frozen_rows(pte: bool, first_year=2027):
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        c["earn_end"] = 2028   # the frozen plan stops earning after 2026; keep the S-corp running so 2027 has a business
        c["pte_election"] = pte
        c["pte_rate"] = 0.0495
        c["pte_first_year"] = first_year
        return {r["year"]: r for r in project(c)}


def test_frozen_plan_2026_is_never_elected():
    for first in (2026, 2027, None):   # an earlier or blank first year still leaves 2026 without the election
        assert _frozen_rows(True, first)[2026].get("scorp_pte_tax", 0.0) == 0.0
    assert _frozen_rows(True, 2027)[2027]["scorp_pte_tax"] > 0.0
    assert _frozen_rows(True, None)[2027]["scorp_pte_tax"] > 0.0   # blank: plan start 2026 + 1


def test_frozen_plan_2027_pte_election_hand_check():
    off, on = _frozen_rows(False)[2027], _frozen_rows(True)[2027]
    # replacement tax 3,514.78 = 1.5% x (D - 1,000), so D = 235,318.60 and the PTE base is D less that tax = 231,803.82;
    # 4.95% of the base = 11,474.29.
    assert on["scorp_pte_base"] == pytest.approx(231_803.82, abs=0.01)
    assert on["scorp_pte_tax"] == pytest.approx(11_474.29, abs=0.01)
    assert off.get("scorp_pte_tax", 0.0) == 0.0
    assert on["state_earned_net"] == pytest.approx(off["state_earned_net"] - 231_803.82 - 11_474.29, abs=0.01)   # base excluded, and the entity tax already left the distribution
    assert on["state_tax"] < off["state_tax"]
