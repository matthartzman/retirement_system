"""Realized-sales ledger step 3b.1: the seed reaching the projection engine (plan section 7.3).

An absent or all-zero seed must leave every row byte-identical; a seed must change year 1 the way a realized
gain or a capital-loss pool does, and the loss pool must keep working in later years."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.planning_engines import project
from tests import synthetic_plans as sp
from tests.test_synthetic_golden_master import empty_workspace

YEAR = 2026


def run(seed=None, *, with_key=True, filing=None):
    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        assert int(c["plan_start"]) == YEAR and c["filing_status"] == "MFJ"
        if filing:
            c["filing_status"] = filing
        if with_key:
            c["realized_seed"] = seed
        return project(c)


def seed(og=0.0, lg=0.0, pool=0.0):
    return {"year": YEAR, "gain_ordinary": og, "gain_ltcg": lg, "loss_pool": pool}


@pytest.fixture(scope="module")
def base():
    return run(with_key=False)


def test_absent_none_and_all_zero_seeds_leave_every_row_identical(base):
    assert run(None) == base
    assert run(seed()) == base


def test_short_term_gain_is_ordinary_income_in_year_one(base):
    rows = run(seed(og=10_000.0))
    assert rows[0]["agi"] == pytest.approx(base[0]["agi"] + 10_000.0)
    delta = rows[0]["total_tax"] - base[0]["total_tax"]
    assert 2_000.0 < delta < 4_000.0  # 22% federal bracket plus state
    assert rows[0]["niit"] == 0.0  # MAGI stays under the NIIT threshold


def test_long_term_gain_reaches_agi_and_is_taxed_at_ltcg_rates(base):
    rows = run(seed(lg=20_000.0))
    assert rows[0]["agi"] == pytest.approx(base[0]["agi"] + 20_000.0)
    assert rows[0]["sale_cap_gain_in_agi"] == pytest.approx(20_000.0)
    assert rows[0]["ltcg_tax"] == pytest.approx(3_000.0, abs=1.0)  # all in the 15% bracket
    assert rows[0]["total_tax"] > base[0]["total_tax"]


def test_loss_pool_takes_the_ordinary_offset_now_and_rolls_the_rest(base):
    rows = run(seed(pool=8_000.0))
    assert rows[0]["cap_loss_used"] == pytest.approx(3_000.0)
    assert rows[0]["cap_loss_carryforward"] == pytest.approx(5_000.0)
    assert 600.0 < rows[0]["tlh_ordinary_credit"] < 750.0
    assert rows[0]["total_tax"] < base[0]["total_tax"]
    assert rows[1]["cap_loss_carryforward"] == pytest.approx(2_000.0)  # next year uses another 3,000
    assert rows[2]["cap_loss_carryforward"] == 0.0


def test_other_years_are_untouched_by_the_gain_seeds(base):
    # Only year 1 carries the seed; later years differ only through balances, never by a re-added gain.
    rows = run(seed(og=10_000.0, lg=20_000.0))
    assert rows[1].get("sale_cap_gain_in_agi") is None


def test_mfs_takes_half_the_ordinary_offset():
    # IRC 1211(b): $1,500 for married filing separately. The engine used a flat $3,000 for every status.
    rows = run(seed(pool=8_000.0), filing="MFS")
    assert rows[0]["filing"] == "MFS"
    assert rows[0]["cap_loss_used"] == pytest.approx(1_500.0)
    assert rows[0]["cap_loss_carryforward"] == pytest.approx(6_500.0)
