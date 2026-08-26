"""Optimization-refactor Phase 2: after-tax transfer/legacy value
distribution -- P1-P99 percentiles of after_tax_terminal_nw and
post_tax_inheritance (after_tax_terminal_nw minus estimated estate tax)
across Monte Carlo paths, from both engines.

Reuses estimate_after_tax_terminal_net_worth (src/after_tax.py) -- the SAME
helper already used by the deterministic Roth-optimizer scoring path
(planning_engines.py, a few hundred lines above monte_carlo_exact_scalar) --
applied per path against that path's own terminal balances and resampled
death years, rather than inventing a new tax model. The scalar engine's
last_row already has real per-account balances (an exact full deterministic
rerun); the vectorized engine only tracks aggregate cash/taxable/pretax/
roth/hsa buckets, so it uses the SAME aggregate-taxable-balance fallback
branch estimate_terminal_taxable_deferred_cap_gain_tax already has for a
config whose account-level taxable_ids weren't populated.

Reporting-only: does not feed back into path_success/success_rate/unfunded/
liquid/total.
"""
from __future__ import annotations

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_vectorized_batch,
    monte_carlo,
    monte_carlo_exact_scalar,
    project,
)


def _base_config(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c.update(overrides)
    return c


def _assert_valid_pct_dict(pct):
    assert pct is not None
    for p in (1, 5, 10, 25, 50, 75, 90, 95, 99):
        assert p in pct
    assert "mean" in pct


def test_vectorized_batch_surfaces_after_tax_legacy_distributions():
    c = _base_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    _assert_valid_pct_dict(batch["after_tax_terminal_nw_pct"])
    _assert_valid_pct_dict(batch["post_tax_inheritance_pct"])


def test_post_tax_inheritance_never_exceeds_after_tax_terminal_nw():
    # post_tax_inheritance = after_tax_terminal_nw - estimated estate tax,
    # and estate tax is never negative, so at every percentile the ordering
    # must hold.
    c = _base_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 30, 9, 0.06, 0.12, 0.0, use_asset_classes=False)
    after_tax = batch["after_tax_terminal_nw_pct"]
    post_tax = batch["post_tax_inheritance_pct"]
    for p in (1, 5, 25, 50, 75, 95, 99):
        assert post_tax[p] <= after_tax[p] + 1e-6


def test_after_tax_terminal_nw_never_exceeds_gross_terminal_total_nw():
    # after_tax_terminal_nw = terminal_nw - deferred pretax/cap-gain/HSA tax,
    # each haircut non-negative, so this can never exceed the gross terminal
    # total net worth already reported as terminal_total_nw.
    c = _base_config()
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=25, seed=11, base_rows=base_rows)
    gross = mc["terminal_total_nw"]
    after_tax = mc["after_tax_terminal_nw_pct"]
    for p in (1, 5, 25, 50, 75, 95, 99):
        assert after_tax[p] <= gross[p] + 1e-6


def test_monte_carlo_output_carries_after_tax_legacy_distribution_vectorized():
    c = _base_config()
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    _assert_valid_pct_dict(mc["after_tax_terminal_nw_pct"])
    _assert_valid_pct_dict(mc["post_tax_inheritance_pct"])


def test_scalar_engine_reports_the_same_after_tax_legacy_distribution():
    c = _base_config()
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    _assert_valid_pct_dict(result["after_tax_terminal_nw_pct"])
    _assert_valid_pct_dict(result["post_tax_inheritance_pct"])
    after_tax = result["after_tax_terminal_nw_pct"]
    post_tax = result["post_tax_inheritance_pct"]
    gross = result["terminal_total_nw"]
    for p in (1, 5, 25, 50, 75, 95, 99):
        assert post_tax[p] <= after_tax[p] + 1e-6
        assert after_tax[p] <= gross[p] + 1e-6
