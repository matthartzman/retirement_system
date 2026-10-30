"""State income tax on realized capital gains in the projection engine.

The state tax base (stage 9) carries no capital gain, and the investment-tax cascade used to add only federal
LTCG and NIIT. So in a state that taxes gains (Illinois, 4.95% flat) every simulated taxable sale, every
home-sale gain and every realized-ledger gain was taxed federally only. The cascade now adds the state tax on
the year's net gain (losses netted first); a rental sale's long-term gain is already state-taxed by the rental
stage and is not taxed twice."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.planning_engines import project
from tests import synthetic_plans as sp
from tests.test_synthetic_golden_master import empty_workspace

YEAR = 2026
IL_RATE = 0.0495


def run(seed=None, *, state=None):
    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        assert c["state"] == "Illinois"
        if state:
            c["state"] = state
        c["realized_seed"] = seed
        return project(c)


def seed(lg=0.0, pool=0.0):
    return {"year": YEAR, "gain_ordinary": 0.0, "gain_ltcg": lg, "loss_pool": pool}


@pytest.fixture(scope="module")
def base():
    return run()


def _net_gain(r):
    gain = max(0.0, float(r.get("ltcg_gain") or 0.0))
    return max(0.0, gain - min(float(r.get("cap_loss_used") or 0.0), gain))


def test_ledger_gain_pays_illinois_tax_on_top_of_federal(base):
    rows = run(seed(lg=20_000.0))
    net = _net_gain(rows[0])
    assert net >= 20_000.0
    assert rows[0]["state_tax_on_capital_gains"] == pytest.approx(IL_RATE * net, abs=0.01)
    # 15% federal plus 4.95% state on the seeded gain, at the least.
    assert rows[0]["total_tax"] - base[0]["total_tax"] >= 3_000.0 + IL_RATE * 20_000.0 - 1.0


def test_every_simulated_taxable_sale_pays_state_tax(base):
    taxed = [r for r in base if _net_gain(r) > 1.0 and not r.get("rental_sale_capital_gain")]
    assert taxed, "the baseline plan should realize brokerage gains in some year"
    for r in taxed:
        assert r["state_tax_on_capital_gains"] == pytest.approx(IL_RATE * _net_gain(r), abs=0.01), r["year"]


def test_losses_net_against_the_gain_before_state_tax():
    rows = run(seed(lg=20_000.0, pool=8_000.0))
    assert rows[0]["state_tax_on_capital_gains"] == pytest.approx(IL_RATE * _net_gain(rows[0]), abs=0.01)
    assert _net_gain(rows[0]) < float(rows[0]["ltcg_gain"])


def test_no_state_tax_on_gains_in_a_no_income_tax_state():
    rows = run(seed(lg=20_000.0), state="Florida")
    assert all(not r.get("state_tax_on_capital_gains") for r in rows)


def test_cashflow_tax_itemization_still_sums_to_total_tax():
    rows = run(seed(lg=20_000.0))
    for r in rows:
        tax = r["cashflow_breakdown"]["tax"]
        assert sum(tax.values()) == pytest.approx(r["total_tax"], abs=0.01), r["year"]
    tax0 = rows[0]["cashflow_breakdown"]["tax"]
    assert tax0["state"] == pytest.approx(rows[0]["state_tax"] + rows[0]["state_tax_on_capital_gains"], abs=0.01)
