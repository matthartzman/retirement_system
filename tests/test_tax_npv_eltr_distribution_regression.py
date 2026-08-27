"""Optimization-refactor Phase 3: tax NPV / ELTR (effective lifetime tax
rate) distribution across the Monte Carlo batch, per
docs/superpowers/plans/2026-08-27-phase3-tax-npv-eltr-spec.md's Option A.

Generalizes the PV-discounting pattern `_roth_strategy_metrics` already
uses to score a single deterministic Roth-conversion candidate
(`_roth_discount_rate`) into a per-path figure reported across the whole MC
distribution -- the "state-contingent" half of the phase name. Uses each
path's own NOMINAL dollar trajectory (not CPI-deflated), matching
`_roth_strategy_metrics`'s own convention, since a PV is already expressed
in year-0-equivalent dollars.

Reporting-only: reads each engine's already-finalized per-path tax/cash-flow
figures and never feeds back into unfunded/liquid/total/path_success/
success_rate.
"""
from __future__ import annotations

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_vectorized_batch,
    _mc_vectorized_projection,
    _roth_discount_rate,
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


def _synthetic_setup(total_tax_by_year: list, gross_cash_flow_by_year: list, discount_rate: float = 0.10):
    """Two-year, zero-inflation synthetic fixture with hand-picked
    total_tax/gross_cash_flow_yr per year, so tax_npv/ELTR can be checked
    against a manually-computed expected value.
    """
    plan_start = 2030
    n_years = len(total_tax_by_year)
    years = list(range(plan_start, plan_start + n_years))
    c = {
        "plan_start": plan_start,
        "inf": 0.0,
        "roth_tax_discount_rate": discount_rate,
        "account_registry": [{"id": "acct1", "tax": "taxable", "balance": 0.0}],
        "balances": {"acct1": 0.0},
    }
    base_rows = [
        {
            "year": y,
            "_account_withdrawals": {"acct1": 0.0},
            "total_spend": 0.0,
            "total_tax": tax,
            "gross_income": 0.0,
            "gross_cash_flow_yr": gcf,
            "total_nw": 0.0, "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0,
        }
        for y, tax, gcf in zip(years, total_tax_by_year, gross_cash_flow_by_year)
    ]
    n_sims = 3
    returns = np.zeros((n_sims, n_years))
    inflation_paths = {
        "inflation_index_matrix": np.ones((n_sims, n_years)),
        "medical_index_matrix": np.ones((n_sims, n_years)),
        "wellness_shock_matrix": np.zeros((n_sims, n_years)),
        "inflation_by_year_matrix": np.zeros((n_sims, n_years)),
    }
    max_death_years = np.full(n_sims, years[-1] + 100, dtype=int)
    return c, base_rows, returns, inflation_paths, max_death_years


def test_tax_npv_matches_manual_discounted_sum():
    # A single year sidesteps _mc_row_bucket_flows's deterministic_
    # inflation_index ((1+inf)**(year-start)) entirely -- exponent 0 is
    # always 1.0 regardless of the configured inflation rate (including the
    # pre-existing falsy-zero quirk where c['inf']=0.0 silently becomes
    # 0.025 -- see test_mc_cut_statistics_regression.py's matching comment)
    # -- so no other scaling factor can perturb the dollar amount checked
    # here for exact equality.
    discount = 0.10
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_setup(
        [10000.0], [50000.0], discount_rate=discount)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.allclose(proj["tax_npv"], 10000.0, atol=0.5))
    assert bool(np.allclose(proj["gross_cash_flow_npv"], 50000.0, atol=0.5))
    assert bool(np.allclose(proj["effective_lifetime_tax_rate"], 10000.0 / 50000.0, atol=1e-6))


def test_tax_npv_discounts_a_later_year_relative_to_the_first():
    # Two years, same tax each year: if discounting works, the SECOND
    # year's contribution to tax_npv must be worth strictly less than the
    # first's, so tax_npv < 2x a single year's tax_npv.
    discount = 0.10
    c1, rows1, ret1, infl1, md1 = _synthetic_setup([10000.0], [50000.0], discount_rate=discount)
    proj1 = _mc_vectorized_projection(c1, rows1, ret1, infl1, md1)
    c2, rows2, ret2, infl2, md2 = _synthetic_setup([10000.0, 10000.0], [50000.0, 50000.0], discount_rate=discount)
    proj2 = _mc_vectorized_projection(c2, rows2, ret2, infl2, md2)
    assert bool(np.all(proj2["tax_npv"] > proj1["tax_npv"]))
    assert bool(np.all(proj2["tax_npv"] < 2.0 * proj1["tax_npv"]))


def test_higher_tax_never_produces_a_lower_tax_npv():
    c_lo, rows_lo, ret_lo, infl_lo, md_lo = _synthetic_setup([5000.0], [50000.0])
    c_hi, rows_hi, ret_hi, infl_hi, md_hi = _synthetic_setup([15000.0], [50000.0])
    proj_lo = _mc_vectorized_projection(c_lo, rows_lo, ret_lo, infl_lo, md_lo)
    proj_hi = _mc_vectorized_projection(c_hi, rows_hi, ret_hi, infl_hi, md_hi)
    assert bool(np.all(proj_hi["tax_npv"] >= proj_lo["tax_npv"]))
    assert bool(np.all(proj_hi["effective_lifetime_tax_rate"] >= proj_lo["effective_lifetime_tax_rate"]))


def test_zero_gross_cash_flow_produces_nan_eltr_not_a_crash():
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_setup([5000.0], [0.0])
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(np.isnan(proj["effective_lifetime_tax_rate"])))
    assert bool(np.all(proj["tax_npv"] == 5000.0))


def test_rows_without_tax_fields_produce_zero_npv_and_nan_eltr():
    # base_rows that never carry total_tax/gross_cash_flow_yr (e.g. a
    # synthetic caller that never populated them) must not crash --
    # _mc_row_bucket_flows unconditionally defaults both to 0.0 per row, so
    # the fields are always present (unlike the conditionally-populated
    # spend_by_tier), just zero-valued here: tax_npv is exactly 0, and ELTR
    # is NaN (0/0), matching the zero-gross-cash-flow guard above.
    plan_start = 2030
    c = {
        "plan_start": plan_start,
        "inf": 0.0,
        "account_registry": [{"id": "acct1", "tax": "taxable", "balance": 0.0}],
        "balances": {"acct1": 0.0},
    }
    base_rows = [{"year": plan_start, "_account_withdrawals": {"acct1": 0.0}, "total_spend": 0.0}]
    n_sims = 2
    returns = np.zeros((n_sims, 1))
    inflation_paths = {
        "inflation_index_matrix": np.ones((n_sims, 1)),
        "medical_index_matrix": np.ones((n_sims, 1)),
        "wellness_shock_matrix": np.zeros((n_sims, 1)),
        "inflation_by_year_matrix": np.zeros((n_sims, 1)),
    }
    max_death_years = np.full(n_sims, plan_start + 100, dtype=int)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["tax_npv"] == 0.0))
    assert bool(np.all(np.isnan(proj["effective_lifetime_tax_rate"])))


def test_vectorized_batch_surfaces_percentiles_on_real_fixture():
    c = _base_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["tax_npv_pct"] is not None
    assert batch["effective_lifetime_tax_rate_pct"] is not None
    for p in (5, 50, 95):
        assert p in batch["tax_npv_pct"]
        assert batch["tax_npv_pct"][p] >= 0.0
        assert p in batch["effective_lifetime_tax_rate_pct"]
        assert 0.0 <= batch["effective_lifetime_tax_rate_pct"][p] <= 1.0


def test_scalar_engine_surfaces_percentiles_and_agrees_in_ballpark_with_vectorized():
    c = _base_config()
    base_rows = project(c)
    scalar = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    vector = _mc_vectorized_batch(c, base_rows, 15, 2, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert scalar["tax_npv_pct"] is not None
    assert scalar["effective_lifetime_tax_rate_pct"] is not None
    for eng in (scalar["effective_lifetime_tax_rate_pct"], vector["effective_lifetime_tax_rate_pct"]):
        assert 0.0 <= eng[50] <= 1.0
    # Both engines discount the SAME deterministic-adjacent tax/cash-flow
    # trajectory with the SAME shared discount rate -- their medians should
    # land in the same ballpark, not just both be "some valid fraction."
    assert abs(scalar["effective_lifetime_tax_rate_pct"][50] - vector["effective_lifetime_tax_rate_pct"][50]) < 0.05


def test_shares_roth_discount_rate_with_the_roth_optimizer():
    c = _base_config()
    c["roth_tax_discount_rate"] = 0.11
    assert _roth_discount_rate(c) == 0.11
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 10, 4, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["tax_npv_pct"] is not None
