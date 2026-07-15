"""Tests for the Phase 1 holding-period / real-loss-probability additions:

    - src/real_loss_curves.py: load_real_loss_curves, real_loss_prob,
      curve_for_asset_class
    - src/holding_period.py: withdrawal_liability_schedule,
      holding_period_profile, withdrawal_weighted_horizon

These modules are purely additive/observational in Phase 1: they read an
already-computed projection and reference-data curves, and do not change
compute_optimal_allocation's behavior. Uses the repo's sample client_data.csv
fixture the same way tests/test_183_efficient_frontier_sharpe.py does, so the
withdrawal cascade reflects a realistic household.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.real_loss_curves as rlc
import src.holding_period as hp
from src.data_io import load_csv, parse_client
from src.planning_engines import project

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


# ---------------------------------------------------------------------------
# real_loss_curves
# ---------------------------------------------------------------------------


def test_load_real_loss_curves_returns_all_four_shipped_curves():
    curves = rlc.load_real_loss_curves()
    for name in (rlc.CASH_CURVE, rlc.BONDS_CURVE, rlc.BLEND_CURVE, rlc.EQUITY_CURVE):
        assert name in curves
        assert len(curves[name]) >= 2


def test_cash_curve_is_increasing_with_holding_period():
    curves = rlc.load_real_loss_curves()
    pts = curves[rlc.CASH_CURVE]
    probs = [p for _, p in pts]
    assert probs == sorted(probs)  # non-decreasing: cash gets riskier over time


def test_equity_curve_is_decreasing_with_holding_period():
    curves = rlc.load_real_loss_curves()
    pts = curves[rlc.EQUITY_CURVE]
    probs = [p for _, p in pts]
    assert probs == sorted(probs, reverse=True)  # non-increasing: equities get safer


def test_real_loss_prob_interpolates_between_nodes():
    # Cash: (3, 0.14) and (5, 0.20) bracket year 4 -> should land between them.
    val = rlc.real_loss_prob('Cash', 4)
    assert 0.14 < val < 0.20


def test_real_loss_prob_clamped_below_zero_years():
    val_neg = rlc.real_loss_prob('Cash', -5)
    val_zero = rlc.real_loss_prob('Cash', 0)
    assert val_neg == pytest.approx(val_zero)


def test_real_loss_prob_clamped_beyond_last_node():
    # Chart's last sampled year is 21; holding periods beyond that should not
    # extrapolate past the last known value.
    val_21 = rlc.real_loss_prob('Cash', 21)
    val_50 = rlc.real_loss_prob('Cash', 50)
    assert val_50 == pytest.approx(val_21)


def test_curve_for_asset_class_maps_equity_bond_and_cash_distinctly():
    assert rlc.curve_for_asset_class('US Large Cap') == rlc.EQUITY_CURVE
    assert rlc.curve_for_asset_class('Bonds') == rlc.BONDS_CURVE
    assert rlc.curve_for_asset_class('Short-Term Bonds') == rlc.BONDS_CURVE
    assert rlc.curve_for_asset_class('Cash') == rlc.CASH_CURVE
    assert rlc.curve_for_asset_class('REITs') == rlc.EQUITY_CURVE


def test_curve_for_asset_class_unknown_class_falls_back_to_blend():
    assert rlc.curve_for_asset_class('Not A Real Asset Class') == rlc.BLEND_CURVE


def test_real_loss_prob_at_zero_years_ranks_cash_safest_equities_riskiest():
    # This is the chart's headline point: at holding period 0, cash is safest
    # and equities are riskiest (the ranking flips as horizon lengthens).
    cash0 = rlc.real_loss_prob('Cash', 0)
    equity0 = rlc.real_loss_prob('US Large Cap', 0)
    assert cash0 < equity0


def test_real_loss_prob_at_long_horizon_ranks_equities_safest():
    cash_long = rlc.real_loss_prob('Cash', 21)
    equity_long = rlc.real_loss_prob('US Large Cap', 21)
    assert equity_long < cash_long


# ---------------------------------------------------------------------------
# holding_period — synthetic projections (isolate bucketing logic)
# ---------------------------------------------------------------------------


def _rows_with_withdrawals(plan_start, withdrawals_by_offset):
    rows = []
    for offset, amount in withdrawals_by_offset.items():
        rows.append({
            'year': plan_start + offset,
            '_account_withdrawals': {'acct_1': amount} if amount else {},
        })
    return rows


def test_holding_period_profile_no_liquid_assets_returns_empty():
    c = {'balances': {}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.025}
    rows = _rows_with_withdrawals(2026, {0: 50000})
    profile = hp.holding_period_profile(rows, c)
    assert profile['source'] == 'no_liquid_assets'
    assert profile['buckets'] == {}
    assert profile['weighted_horizon_years'] is None


def test_holding_period_profile_no_withdrawals_is_all_long_horizon():
    # Pure accumulation-phase plan: liquid balance exists but the modeled
    # window has no projected withdrawals yet.
    c = {'balances': {'acct_1': 500000.0}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.025}
    rows = [{'year': 2026, '_account_withdrawals': {}}, {'year': 2027, '_account_withdrawals': {}}]
    profile = hp.holding_period_profile(rows, c)
    assert profile['source'] == 'no_projected_withdrawals'
    assert profile['buckets']['16+ yr']['dollars'] == pytest.approx(500000.0)
    assert profile['buckets']['16+ yr']['share'] == pytest.approx(1.0)


def test_holding_period_profile_near_term_spender_buckets_short():
    # Small balance, big near-term withdrawals: nearly all of today's balance
    # should land in the shortest bucket.
    c = {'balances': {'acct_1': 100000.0}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.0}
    rows = _rows_with_withdrawals(2026, {0: 60000, 1: 60000})
    profile = hp.holding_period_profile(rows, c)
    assert profile['source'] == 'withdrawal_schedule'
    assert profile['buckets']['0-2 yr']['dollars'] == pytest.approx(100000.0, rel=1e-6)
    assert profile['weighted_horizon_years'] < 1.0


def test_holding_period_profile_fifo_spreads_across_buckets():
    # $10k/yr spend against a $100k balance with 0% inflation should exhaust
    # the balance at year 10, landing dollars progressively across buckets
    # 0-2, 3-5, 6-10 and none in the 11-15/16+ buckets.
    c = {'balances': {'acct_1': 100000.0}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.0}
    withdrawals = {offset: 10000.0 for offset in range(0, 12)}
    rows = _rows_with_withdrawals(2026, withdrawals)
    profile = hp.holding_period_profile(rows, c)
    buckets = profile['buckets']
    total = sum(b['dollars'] for b in buckets.values())
    assert total == pytest.approx(100000.0, rel=1e-6)
    assert buckets['0-2 yr']['dollars'] > 0
    assert buckets['3-5 yr']['dollars'] > 0
    assert buckets['6-10 yr']['dollars'] > 0
    assert buckets['11-15 yr']['dollars'] == pytest.approx(0.0, abs=1.0)
    assert buckets['16+ yr']['dollars'] == pytest.approx(0.0, abs=1.0)


def test_holding_period_profile_durable_remainder_uses_plan_horizon():
    # Withdrawals stop well before the plan ends (e.g. high funded ratio);
    # the unconsumed remainder should be treated as durable, long-horizon
    # money rather than disappearing or landing in an early bucket.
    c = {'balances': {'acct_1': 1000000.0}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.0}
    rows = _rows_with_withdrawals(2026, {0: 20000, 1: 20000})
    profile = hp.holding_period_profile(rows, c)
    assert profile['buckets']['16+ yr']['dollars'] == pytest.approx(960000.0, rel=1e-6)
    # weighted horizon should be pulled far out by the durable remainder
    assert profile['weighted_horizon_years'] > 20


def test_withdrawal_weighted_horizon_falls_back_when_no_schedule():
    c = {'balances': {}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.025}
    rows = []
    horizon = hp.withdrawal_weighted_horizon(rows, c)
    assert horizon == 30


def test_withdrawal_liability_schedule_deflates_nominal_to_real():
    c = {'balances': {'acct_1': 100000.0}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.10}
    rows = _rows_with_withdrawals(2026, {0: 10000.0, 10: 10000.0})
    schedule = hp.withdrawal_liability_schedule(rows, c)
    # Year-10 nominal $10k deflated at 10%/yr should be worth much less than
    # the year-0 $10k in today's dollars.
    assert schedule[10] < schedule[0]
    assert schedule[10] == pytest.approx(10000.0 / (1.10 ** 10), rel=1e-6)


def test_withdrawal_liability_schedule_ignores_negative_offsets():
    c = {'balances': {'acct_1': 100000.0}, 'plan_start': 2026, 'plan_end': 2056, 'inf': 0.0}
    rows = [{'year': 2020, '_account_withdrawals': {'acct_1': 5000.0}},
            {'year': 2026, '_account_withdrawals': {'acct_1': 8000.0}}]
    schedule = hp.withdrawal_liability_schedule(rows, c)
    assert -6 not in schedule
    assert schedule[0] == pytest.approx(8000.0)


# ---------------------------------------------------------------------------
# holding_period — realistic household projection (integration smoke test)
# ---------------------------------------------------------------------------


def test_holding_period_profile_on_real_projection_is_well_formed():
    c = sample_config()
    rows = project(c)
    profile = hp.holding_period_profile(rows, c)
    assert profile['source'] in ('withdrawal_schedule', 'no_projected_withdrawals', 'no_liquid_assets')
    if profile['source'] == 'withdrawal_schedule':
        total_bucketed = sum(b['dollars'] for b in profile['buckets'].values())
        assert total_bucketed == pytest.approx(profile['liquid_nw'], rel=1e-6)
        for b in profile['buckets'].values():
            assert 0.0 <= b['share'] <= 1.0 + 1e-9
        horizon = profile['weighted_horizon_years']
        assert horizon is None or horizon >= 0


def test_withdrawal_weighted_horizon_on_real_projection_is_nonnegative():
    c = sample_config()
    rows = project(c)
    horizon = hp.withdrawal_weighted_horizon(rows, c)
    assert horizon is not None
    assert horizon >= 0


# ---------------------------------------------------------------------------
# compute_optimal_allocation diagnostics wiring (Phase 1: additive only)
# ---------------------------------------------------------------------------


def test_compute_optimal_allocation_without_rows_marks_not_computed():
    import src.optimization as opt
    c = sample_config()
    out = opt.compute_optimal_allocation(c)
    assert out['diagnostics']['holding_period_source'] == 'not_computed'
    assert 'holding_period_profile' not in out['diagnostics']


def test_compute_optimal_allocation_with_rows_adds_holding_period_diagnostics():
    import src.optimization as opt
    c = sample_config()
    rows = project(c)
    out = opt.compute_optimal_allocation(c, projection_rows=rows)
    assert out['diagnostics']['holding_period_source'] in (
        'withdrawal_schedule', 'no_projected_withdrawals', 'no_liquid_assets'
    )
    if out['diagnostics']['holding_period_source'] == 'withdrawal_schedule':
        assert isinstance(out['diagnostics']['holding_period_profile'], dict)
        assert out['diagnostics']['withdrawal_weighted_horizon_years'] is not None


def test_compute_optimal_allocation_diagnostics_wiring_does_not_change_allocation():
    # Phase 1 must be purely observational: passing projection_rows should
    # never change the computed liquid_targets/total_targets/equity_pct.
    import src.optimization as opt
    c = sample_config()
    rows = project(c)
    without_rows = opt.compute_optimal_allocation(c)
    with_rows = opt.compute_optimal_allocation(c, projection_rows=rows)
    assert without_rows['liquid_targets'] == with_rows['liquid_targets']
    assert without_rows['total_targets'] == with_rows['total_targets']
    assert without_rows['equity_pct'] == with_rows['equity_pct']


def test_compute_optimal_allocation_handles_malformed_rows_gracefully():
    import src.optimization as opt
    c = sample_config()
    out = opt.compute_optimal_allocation(c, projection_rows=[{'not_a_valid_row': True}])
    # Should never raise; worst case is an 'error' source, not an exception.
    assert out['diagnostics']['holding_period_source'] in (
        'withdrawal_schedule', 'no_projected_withdrawals', 'no_liquid_assets', 'error'
    )


def test_allocation_portfolio_stats_forwards_projection_rows():
    import src.optimization as opt
    c = sample_config()
    rows = project(c)
    stats = opt.allocation_portfolio_stats(c, projection_rows=rows)
    assert 'holding_period_source' in stats['diagnostics']
