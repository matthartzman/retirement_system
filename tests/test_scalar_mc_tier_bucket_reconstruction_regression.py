"""Optimization-refactor "Not done" item, Option B ("Genuinely redirecting
withdrawal requests... by tier priority" --
docs/superpowers/plans/2026-08-27-mc-tier-priority-withdrawal-redirection-
spec.md), scalar-engine parity.

``monte_carlo_exact_scalar`` has no independent withdrawal mechanism to
redirect -- each path is a full rerun of ``project()``, which just replays
the deterministic engine's own already-decided bucket split. Genuine
per-tier redirection there is a PARALLEL reconstruction
(``_mc_scalar_tier_bucket_reconstruction``) that starts from the same
account balances and re-derives a tier-restricted withdrawal against ITS OWN
tracked balances, using each real row's own account-level ending balance to
infer that year's real per-bucket growth rate. This file tests that
reconstruction directly with synthetic rows (mirroring
test_mc_tier_bucket_policy_restriction_regression.py's vectorized-engine
coverage), plus one integration check against the real fixture through
``monte_carlo_exact_scalar`` itself.
"""
from __future__ import annotations

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_bucket_starting_balances,
    _mc_scalar_tier_bucket_reconstruction,
    monte_carlo_exact_scalar,
    project,
)


def _config_with_balances(balances: dict):
    registry = [{"id": f"acct_{tax}", "tax": tax, "balance": 0.0} for tax in
                ("taxable", "pre_tax", "roth", "hsa", "cash")]
    bal_by_acct = {
        "acct_taxable": balances.get("taxable", 0.0),
        "acct_pre_tax": balances.get("pretax", 0.0),
        "acct_roth": balances.get("roth", 0.0),
        "acct_hsa": balances.get("hsa", 0.0),
        "acct_cash": balances.get("cash", 0.0),
    }
    return {"account_registry": registry, "balances": bal_by_acct}


def _no_growth_row(year: int, tiers: dict, real_withdrawal_account: str, real_withdrawal_amount: float,
                    starts: dict, income_funding: float = 0.0):
    """A row whose real per-bucket ending balance exactly equals
    starting-minus-real-withdrawal (growth_factor == 1.0 for every bucket),
    so the reconstruction's own tier-restricted draw is the only thing that
    can move the numbers this test checks.
    """
    nw_field = {"acct_pretax": "pretax_nw", "acct_pre_tax": "pretax_nw", "acct_roth": "roth_nw",
                "acct_taxable": "trust_nw", "acct_hsa": "hsa_nw", "acct_cash": "cash_nw"}
    bucket_of = {"acct_taxable": "taxable", "acct_pre_tax": "pretax", "acct_roth": "roth",
                 "acct_hsa": "hsa", "acct_cash": "cash"}
    row = {
        "year": year,
        "_account_withdrawals": {real_withdrawal_account: real_withdrawal_amount},
        "_account_deposits": {},
        "_account_conversions_out": {},
        "_account_conversions_in": {},
        "spend_by_tier": dict(tiers),
        "total_tax": 0.0,
        "income_funding": income_funding,
        "pretax_nw": starts["pretax"], "roth_nw": starts["roth"],
        "trust_nw": starts["taxable"], "hsa_nw": starts["hsa"], "cash_nw": starts["cash"],
    }
    withdrawn_bucket = bucket_of[real_withdrawal_account]
    row[nw_field[real_withdrawal_account]] = starts[withdrawn_bucket] - real_withdrawal_amount
    return row


def test_no_spend_by_tier_returns_none():
    c = _config_with_balances({})
    rows = [{"year": 2030, "_account_withdrawals": {}, "total_tax": 0.0}]
    assert _mc_scalar_tier_bucket_reconstruction(c, rows) is None


def test_discretionary_cannot_reach_ample_hsa():
    c = _config_with_balances({"hsa": 1_000_000.0})
    starts = _mc_bucket_starting_balances(c)
    tiers = {"essential": 5000.0, "important": 5000.0, "discretionary": 5000.0}
    rows = [_no_growth_row(2030, tiers, "acct_hsa", 5000.0, starts)]
    result = _mc_scalar_tier_bucket_reconstruction(c, rows)
    assert result is not None
    yr = result[2030]
    assert yr["tier_actual_spend"]["essential"] == 5000.0
    assert yr["tier_actual_spend"]["important"] == 5000.0
    assert yr["tier_actual_spend"]["discretionary"] == 0.0
    assert yr["tier_shortfall"]["discretionary"] == 5000.0
    assert yr["unfunded"] == 5000.0


def test_important_cannot_reach_ample_roth():
    c = _config_with_balances({"roth": 1_000_000.0})
    starts = _mc_bucket_starting_balances(c)
    tiers = {"essential": 4000.0, "important": 4000.0}
    rows = [_no_growth_row(2030, tiers, "acct_roth", 4000.0, starts)]
    result = _mc_scalar_tier_bucket_reconstruction(c, rows)
    assert result is not None
    yr = result[2030]
    assert yr["tier_actual_spend"]["essential"] == 4000.0
    assert yr["tier_actual_spend"]["important"] == 0.0
    assert yr["unfunded"] == 4000.0


def test_income_funding_covers_need_before_any_bucket_draw():
    # Ample income, zero balances everywhere: every tier should be fully
    # funded by income alone, with no genuine shortfall.
    c = _config_with_balances({})
    starts = _mc_bucket_starting_balances(c)
    tiers = {"essential": 3000.0, "discretionary": 2000.0}
    rows = [_no_growth_row(2030, tiers, "acct_taxable", 0.0, starts, income_funding=10_000.0)]
    result = _mc_scalar_tier_bucket_reconstruction(c, rows)
    assert result is not None
    yr = result[2030]
    assert yr["tier_actual_spend"]["essential"] == 3000.0
    assert yr["tier_actual_spend"]["discretionary"] == 2000.0
    assert yr["unfunded"] == 0.0


def test_second_year_balance_carries_forward_from_reconstructed_state():
    # Two years, taxable-only account: year 1 draws down the reconstructed
    # balance (not the real one), so year 2's available capacity reflects
    # what THIS mechanism left behind.
    c = _config_with_balances({"taxable": 8000.0})
    starts = _mc_bucket_starting_balances(c)
    tiers_y1 = {"essential": 5000.0}
    tiers_y2 = {"essential": 5000.0}
    row1 = _no_growth_row(2030, tiers_y1, "acct_taxable", 5000.0, starts)
    # Year 2's real balances follow from year 1's REAL ending state (8000-5000=3000).
    row2 = {
        "year": 2031,
        "_account_withdrawals": {"acct_taxable": 3000.0},
        "_account_deposits": {},
        "_account_conversions_out": {},
        "_account_conversions_in": {},
        "spend_by_tier": dict(tiers_y2),
        "total_tax": 0.0,
        "income_funding": 0.0,
        "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0, "cash_nw": 0.0,
    }
    result = _mc_scalar_tier_bucket_reconstruction(c, [row1, row2])
    assert result[2030]["unfunded"] == 0.0
    # Reconstructed taxable balance after year 1 is 8000-5000=3000, same as
    # the real trajectory here, so year 2's essential need (5000) is short
    # by exactly 2000.
    assert result[2031]["unfunded"] == 2000.0
    assert result[2031]["tier_actual_spend"]["essential"] == 3000.0


def test_scalar_engine_essential_fully_funded_probability_still_sane_on_real_fixture():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert "essential_fully_funded_probability" in result
    assert 0.0 <= result["essential_fully_funded_probability"] <= 1.0
    assert "probability_any_cut" in result
    assert 0.0 <= result["probability_any_cut"] <= 1.0
