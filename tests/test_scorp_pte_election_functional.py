"""PTE election (CPA-approved approach, W3-01 follow-up): entity tax reduces the distribution; the owner's Illinois base excludes the taxed income."""
from __future__ import annotations

import pytest

from src.projection_stages.income import _scorp_pte_tax


def test_pte_tax_applies_only_when_elected_in_illinois():
    c = {"state": "Illinois", "pte_election": True, "pte_rate": 0.0495}
    assert _scorp_pte_tax(c, 2026, 200_000.0) == pytest.approx(9_900.0)
    assert _scorp_pte_tax({**c, "pte_election": False}, 2026, 200_000.0) == 0.0
    assert _scorp_pte_tax({**c, "state": "Texas"}, 2026, 200_000.0) == 0.0
    assert _scorp_pte_tax(c, 2026, -5.0) == 0.0


def _frozen_rows(pte: bool):
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        c["pte_election"] = pte
        c["pte_rate"] = 0.0495
        return project(c)


def test_frozen_plan_2026_pte_election_hand_check():
    off, on = _frozen_rows(False)[0], _frozen_rows(True)[0]
    # base = 226,030 distribution - 3,375.45 replacement tax = 222,654.55; 4.95% of it = 11,021.40
    assert on["scorp_pte_base"] == pytest.approx(222_654.55, abs=0.01)
    assert on["scorp_pte_tax"] == pytest.approx(11_021.40, abs=0.01)
    assert off.get("scorp_pte_tax", 0.0) == 0.0
    assert on["state_earned_net"] == pytest.approx(off["state_earned_net"] - 222_654.55 - 11_021.40, abs=0.01)   # base excluded, and the entity tax already left the distribution
    assert on["state_tax"] < off["state_tax"]
