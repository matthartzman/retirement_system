"""Optimization-refactor "Not done" item, Option B ("Genuinely redirecting
withdrawal requests... by tier priority" --
docs/superpowers/plans/2026-08-27-mc-tier-priority-withdrawal-redirection-
spec.md): SPENDING_TIER_BUCKET_POLICY restricts WHICH bucket each spend tier
may draw from, not just how much money moves in total.

The pre-existing tier tests (test_essential_fully_funded_probability_
regression.py, test_mc_cut_statistics_regression.py) use a single taxable
account, so they exercise total-shortfall-from-balance-exhaustion but never
prove a tier is blocked from a bucket it could otherwise reach. This file
uses multiple account types with deliberately lopsided balances (plenty of
money in one bucket, none in the others a tier is allowed to use) to prove
the RESTRICTION itself: a tier's need goes genuinely unfunded even though
money exists, as long as it's parked in a bucket that tier's own policy
doesn't authorize.
"""
from __future__ import annotations

import numpy as np

from src.planning_engines import _mc_vectorized_projection
from src.spending_budget_resolver import SPENDING_TIER_BUCKET_POLICY


def _single_year_setup(tiers: dict, balances: dict):
    """One synthetic year, zero income/tax, with an explicit per-bucket
    account balance so the test can prove a tier's bucket RESTRICTION
    (not just balance exhaustion) forces a genuine shortfall.
    """
    plan_start = 2030
    total_need = sum(tiers.values())
    registry = [{"id": f"acct_{tax}", "tax": tax, "balance": 0.0} for tax in
                ("taxable", "pre_tax", "roth", "hsa", "cash")]
    bal_by_acct = {
        "acct_taxable": balances.get("taxable", 0.0),
        "acct_pre_tax": balances.get("pretax", 0.0),
        "acct_roth": balances.get("roth", 0.0),
        "acct_hsa": balances.get("hsa", 0.0),
        "acct_cash": balances.get("cash", 0.0),
    }
    c = {
        "plan_start": plan_start,
        "inf": 0.0,
        "account_registry": registry,
        "balances": bal_by_acct,
    }
    base_rows = [{
        "year": plan_start,
        "_account_withdrawals": {"acct_taxable": total_need},
        "total_spend": total_need,
        "total_tax": 0.0,
        "gross_income": 0.0,
        "spend_by_tier": dict(tiers),
        "total_nw": 0.0, "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0,
    }]
    n_sims = 3
    returns = np.zeros((n_sims, 1))
    inflation_paths = {
        "inflation_index_matrix": np.ones((n_sims, 1)),
        "medical_index_matrix": np.ones((n_sims, 1)),
        "wellness_shock_matrix": np.zeros((n_sims, 1)),
        "inflation_by_year_matrix": np.zeros((n_sims, 1)),
    }
    max_death_years = np.full(n_sims, plan_start + 100, dtype=int)
    return c, base_rows, returns, inflation_paths, max_death_years


def test_policy_definitions_match_the_spec_decision():
    # Pins the actual product decision (AskUserQuestion answers recorded in
    # OPTIMIZATION_REFACTOR_STATUS.md) so a future edit to the policy dict is
    # a deliberate, reviewed change rather than a silent drift.
    assert SPENDING_TIER_BUCKET_POLICY["essential"] == ("cash", "hsa", "pretax", "taxable", "roth")
    assert SPENDING_TIER_BUCKET_POLICY["contingent_liability"] == ("cash", "hsa", "pretax", "taxable", "roth")
    assert SPENDING_TIER_BUCKET_POLICY["important"] == ("cash", "hsa", "pretax", "taxable")
    assert SPENDING_TIER_BUCKET_POLICY["discretionary"] == ("cash", "taxable", "pretax")


def test_discretionary_cannot_reach_ample_hsa_or_roth():
    # Discretionary's own bucket policy excludes HSA and Roth entirely.
    # essential/important are funded first (MC_TIER_FUNDING_ORDER) and both
    # can draw HSA, so with an ample HSA balance and NOTHING in taxable/
    # pretax/cash, essential and important are fully funded while
    # discretionary -- unable to touch HSA or the (already-drawn) Roth --
    # goes genuinely, entirely unfunded, even though real money exists in
    # the household's accounts.
    tiers = {"essential": 5000.0, "important": 5000.0, "discretionary": 5000.0}
    balances = {"hsa": 1_000_000.0}
    c, base_rows, returns, inflation_paths, max_death_years = _single_year_setup(tiers, balances)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["spend_essential_real"] == 5000.0))
    assert bool(np.all(proj["spend_important_real"] == 5000.0))
    assert bool(np.all(proj["spend_discretionary_real"] == 0.0))
    assert bool(np.all(proj["unfunded"] == 5000.0))
    assert bool(np.all(proj["essential_fully_funded"]))


def test_important_cannot_reach_ample_roth():
    # important's own bucket policy excludes Roth. With everything EXCEPT
    # Roth at zero, important (funded before discretionary, but after
    # essential) has nothing it's allowed to draw, so it goes fully
    # unfunded even though the Roth balance could easily cover it --
    # essential, whose policy DOES include Roth, drains the Roth for its
    # own need and is fully funded.
    tiers = {"essential": 4000.0, "important": 4000.0}
    balances = {"roth": 1_000_000.0}
    c, base_rows, returns, inflation_paths, max_death_years = _single_year_setup(tiers, balances)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["spend_essential_real"] == 4000.0))
    assert bool(np.all(proj["spend_important_real"] == 0.0))
    assert bool(np.all(proj["unfunded"] == 4000.0))


def test_contingent_liability_shares_essentials_full_cascade_access():
    # contingent_liability keeps the SAME unrestricted policy as essential
    # (ffa142b / 0e65806's cut-cascade precedent extended to bucket access):
    # an ample Roth balance with nothing else must fully fund it, just like
    # essential.
    tiers = {"contingent_liability": 3000.0, "discretionary": 3000.0}
    balances = {"roth": 1_000_000.0}
    c, base_rows, returns, inflation_paths, max_death_years = _single_year_setup(tiers, balances)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["spend_contingent_liability_real"] == 3000.0))
    assert bool(np.all(proj["spend_discretionary_real"] == 0.0))
    assert bool(np.all(proj["unfunded"] == 3000.0))


def test_no_tiers_present_preserves_pre_option_b_behavior():
    # base_rows with no spend_by_tier at all must take the untouched
    # pre-existing code path (the tier_scaled-empty branch) -- no policy
    # restriction applies, matching every plan predating Phase 0.
    plan_start = 2030
    c = {
        "plan_start": plan_start,
        "inf": 0.0,
        "account_registry": [
            {"id": "acct_taxable", "tax": "taxable", "balance": 0.0},
            {"id": "acct_roth", "tax": "roth", "balance": 1_000_000.0},
        ],
        "balances": {"acct_taxable": 0.0, "acct_roth": 1_000_000.0},
    }
    base_rows = [{
        "year": plan_start,
        "_account_withdrawals": {"acct_taxable": 5000.0},
        "total_spend": 5000.0,
        "total_tax": 0.0,
        "gross_income": 0.0,
        "total_nw": 0.0, "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0,
    }]
    n_sims = 3
    returns = np.zeros((n_sims, 1))
    inflation_paths = {
        "inflation_index_matrix": np.ones((n_sims, 1)),
        "medical_index_matrix": np.ones((n_sims, 1)),
        "wellness_shock_matrix": np.zeros((n_sims, 1)),
        "inflation_by_year_matrix": np.zeros((n_sims, 1)),
    }
    max_death_years = np.full(n_sims, plan_start + 100, dtype=int)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    # Old fallback-across-any-bucket behavior: taxable is empty, so the
    # request falls through to Roth and is fully funded, unfunded == 0.
    assert bool(np.all(proj["unfunded"] == 0.0))
    assert "spend_essential_real" not in proj
