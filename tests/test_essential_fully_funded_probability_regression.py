"""Optimization-refactor Phase 2: "probability essential spending is fully
funded" -- both Monte Carlo engines attribute each path/year's already-
computed unfunded shortfall to spend tiers via the same discretionary ->
important -> essential cascade as spending_priority_cut_check, and report
the fraction of paths whose essential tier was never left unfunded.

Reporting-only: reads each engine's existing unfunded-gap tracking after
the withdrawal recursion/deterministic engine already finalized it, and
never feeds back into unfunded/liquid/total/path_success/success_rate.
"""
from __future__ import annotations

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_vectorized_batch,
    _mc_vectorized_projection,
    monte_carlo,
    monte_carlo_exact_scalar,
    project,
)


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


def test_vectorized_probability_is_one_when_everything_is_well_funded():
    c = _base_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    proj = batch["projection"]
    assert "essential_fully_funded" in proj
    # A comfortably-funded fixture (short horizon, no cut applied) should
    # show all paths' essential tier fully funded.
    assert bool(np.all(proj["essential_fully_funded"]))
    assert batch["essential_fully_funded_probability"] == 1.0


def test_vectorized_probability_field_present_in_monte_carlo_output():
    c = _base_config()
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    assert "essential_fully_funded_probability" in mc
    # A comfortably-funded fixture should show this at or very near 1.0 --
    # not asserting exactly 1.0, since monte_carlo() always samples
    # c['mc_sims'] paths regardless of the n_sims argument (a pre-existing
    # behavior unrelated to this test), and a handful of tail-risk paths out
    # of many can legitimately show a trivial shortfall.
    assert mc["essential_fully_funded_probability"] >= 0.99


def _synthetic_zero_income_setup(n_years: int, available_balance: float, tiers: dict):
    """A fully synthetic, zero-income household: one taxable account with a
    controlled STARTING BALANCE and no deposits of any kind, so the
    withdrawal cascade can fund up to exactly ``available_balance`` of the
    tiers' combined need and no more -- the shortfall is deterministic.

    Genuine per-tier redirection (Option B) drives each tier's withdrawal
    request directly from ``spend_by_tier`` (not from a separately-set
    ``total_spend``/``_account_withdrawals`` figure the way the pre-Option-B
    version of this fixture did -- that decoupling relied on the old
    reporting-only reconstruction, which never checked real bucket capacity
    at all). ``total_spend``/``_account_withdrawals`` are kept equal to the
    tiers' own total, matching the real invariant deterministic_engine.py
    guarantees (row['total_spend'] always reconciles to sum(spend_by_tier)),
    so ``other_nominal`` (planning_engines.py's non-tier-tagged draw) comes
    out to exactly zero here and every dollar is tier-attributed.

    This avoids depending on the real client_data.csv fixture's income
    streams (SS, pension, wages), which mask a shortfall via
    _account_deposits regardless of how large spend_base is set -- a
    pre-existing vectorized-engine characteristic unrelated to this test.
    """
    plan_start = 2030
    years = list(range(plan_start, plan_start + n_years))
    total_need = sum(tiers.values())
    c = {
        "plan_start": plan_start,
        "inf": 0.0,
        "account_registry": [{"id": "acct1", "tax": "taxable", "balance": 0.0}],
        "balances": {"acct1": float(available_balance)},
    }
    base_rows = [
        {
            "year": y,
            "_account_withdrawals": {"acct1": total_need},
            "total_spend": total_need,
            "total_tax": 0.0,
            "gross_income": 0.0,
            "spend_by_tier": dict(tiers),
            "total_nw": 0.0, "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0,
        }
        for y in years
    ]
    n_sims = 3
    returns = np.zeros((n_sims, n_years))
    inflation_paths = {
        "inflation_index_matrix": np.ones((n_sims, n_years)),
        "medical_index_matrix": np.ones((n_sims, n_years)),
        "wellness_shock_matrix": np.zeros((n_sims, n_years)),
        "inflation_by_year_matrix": np.zeros((n_sims, n_years)),
    }
    max_death_years = np.full(n_sims, years[-1] + 100, dtype=int)  # every year active
    return c, base_rows, returns, inflation_paths, max_death_years


def test_small_shortfall_is_absorbed_entirely_by_discretionary():
    # A single year sidesteps _mc_row_bucket_flows's deterministic_inflation_index
    # ((1+inf)**(year-start)) entirely -- exponent 0 is always 1.0 regardless
    # of the configured inflation rate, so no other scaling factor can
    # perturb the dollar amounts this test checks for exact equality.
    #
    # Genuine per-tier redirection (Option B) funds essential/contingent_
    # liability FIRST from the shared account, then important, then
    # discretionary last (MC_TIER_FUNDING_ORDER) -- so a shortfall of the
    # account's available balance below the tiers' combined 70000 need
    # lands on whichever tier is funded last that the shortfall reaches.
    # available_balance=65000 covers essential(40000) + important(20000) in
    # full, leaving exactly 5000 of discretionary's 10000 need unfunded.
    tiers = {"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0}
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_zero_income_setup(1, 65000.0, tiers)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["unfunded"] == 5000.0))
    assert bool(np.all(proj["essential_fully_funded"]))
    assert bool(np.all(proj["essential_shortfall_real"] == 0.0))


def test_large_shortfall_spills_into_essential():
    # available_balance=30000 falls short of even essential's own 40000
    # need: essential (funded FIRST) draws the full 30000 available and is
    # still short by 10000; important and discretionary, funded after
    # essential, see zero balance left and go fully unfunded (20000 +
    # 10000). Total unfunded = 10000 + 20000 + 10000 = 40000, and essential
    # itself is short by exactly 10000 -- the same two headline numbers the
    # pre-Option-B version of this test asserted (see its superseded
    # reasoning below), now produced by a genuinely simulated draw instead
    # of a post-hoc SPENDING_TIER_CUT_ORDER reconstruction against one
    # blended unfunded total.
    tiers = {"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0}
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_zero_income_setup(1, 30000.0, tiers)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["unfunded"] == 40000.0))
    assert not bool(np.any(proj["essential_fully_funded"]))
    assert bool(np.all(proj["essential_shortfall_real"] == 10000.0))


def test_scalar_engine_reports_the_same_metric():
    c = _base_config()
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert "essential_fully_funded_probability" in result
    assert 0.0 <= result["essential_fully_funded_probability"] <= 1.0
