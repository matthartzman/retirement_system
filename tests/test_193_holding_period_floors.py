"""Tests for Phase 3 (5b): opt-in time-segmented real-loss-probability
floors in compute_optimal_allocation's optimizer/max-Sharpe recommendation
branch (c['holding_period_allocation_enabled']).

Off by default (byte-stable): c['_holding_period_buckets'] is only ever
populated by data_io._resolve_holding_period_floors_and_reapply, which is
itself gated on holding_period_allocation_enabled, so a plan that has not
opted in sees zero change to equity_pct/cash_pct/fi_base_split/total_targets.

Golden-master style: floor math is asserted against hand-computed expected
values using directly-injected synthetic buckets, so a future refactor that
silently changes the floor math will fail these tests visibly.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

import src.optimization as opt
import src.allocation_policy as ap
from src.data_io import load_csv, parse_client, _resolve_holding_period_floors_and_reapply

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


def sample_data():
    return load_csv(ROOT / "input" / "client_data.csv")


SYNTHETIC_BUCKETS = {
    '0-2 yr': {'dollars': 0.0, 'share': 0.40},
    '3-5 yr': {'dollars': 0.0, 'share': 0.10},
    '6-10 yr': {'dollars': 0.0, 'share': 0.10},
    '11-15 yr': {'dollars': 0.0, 'share': 0.10},
    '16+ yr': {'dollars': 0.0, 'share': 0.30},
}


# ---------------------------------------------------------------------------
# Byte-stability: off by default
# ---------------------------------------------------------------------------


def test_holding_period_allocation_disabled_by_default():
    c = sample_config()
    assert c.get('holding_period_allocation_enabled') is False


def test_buckets_present_but_flag_off_has_no_effect():
    # Even if _holding_period_buckets were somehow present, the consumption
    # side must gate strictly on holding_period_allocation_enabled, not on
    # bucket presence alone.
    c = sample_config()
    assert c.get('holding_period_allocation_enabled') is False
    out_without = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)

    c2 = sample_config()
    c2['_holding_period_buckets'] = SYNTHETIC_BUCKETS
    out_with_buckets_flag_off = opt.compute_optimal_allocation(c2, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)

    assert out_without['equity_pct'] == pytest.approx(out_with_buckets_flag_off['equity_pct'])
    assert out_without['total_targets'] == pytest.approx(out_with_buckets_flag_off['total_targets'])
    assert out_with_buckets_flag_off['diagnostics']['holding_period_floors_applied'] is None


# ---------------------------------------------------------------------------
# Floor mechanics — golden-master style with injected synthetic buckets
# ---------------------------------------------------------------------------


def _with_synthetic_buckets(strength=1.0):
    c = sample_config()
    c['holding_period_allocation_enabled'] = True
    c['holding_period_floor_strength'] = strength
    c['_holding_period_buckets'] = copy.deepcopy(SYNTHETIC_BUCKETS)
    return c


def test_long_term_share_floors_equity_pct():
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    baseline_equity_pct = out_off['equity_pct']

    c_on = _with_synthetic_buckets(strength=1.0)
    out_on = opt.compute_optimal_allocation(c_on, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)

    # Floor is max(baseline, long_term_share); synthetic long_term_share=0.30.
    expected_floor = max(baseline_equity_pct, 0.30)
    assert out_on['equity_pct'] == pytest.approx(expected_floor, abs=1e-6)
    assert out_on['equity_pct'] >= baseline_equity_pct - 1e-9


def test_near_term_share_floors_cash_target():
    # total_targets['Cash'] goes through the function's existing rollup-sum
    # normalization (it is normalized alongside aggregate 'Bonds/Fixed
    # Income'/'REITs/Real Estate' keys, not a bare cash_pct), so assert the
    # directional/magnitude effect rather than a hand-computed exact value:
    # near_term_share (0.40) is far above the household's configured
    # cash_target_pct (default 0.05), so the floor should meaningfully raise
    # Cash's total-target weight versus the floors-off baseline.
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    baseline_cash = out_off['total_targets'].get('Cash', 0.0)

    c_on = _with_synthetic_buckets(strength=1.0)
    out_on = opt.compute_optimal_allocation(c_on, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    floored_cash = out_on['total_targets'].get('Cash', 0.0)

    assert floored_cash > baseline_cash


def test_floor_strength_scales_the_floor():
    c_full = _with_synthetic_buckets(strength=1.0)
    out_full = opt.compute_optimal_allocation(c_full, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    c_half = _with_synthetic_buckets(strength=0.5)
    out_half = opt.compute_optimal_allocation(c_half, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    c_zero = _with_synthetic_buckets(strength=0.0)
    out_zero = opt.compute_optimal_allocation(c_zero, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)

    cash_full = out_full['total_targets'].get('Cash', 0.0)
    cash_half = out_half['total_targets'].get('Cash', 0.0)
    cash_zero = out_zero['total_targets'].get('Cash', 0.0)
    assert cash_full > cash_half > cash_zero


def test_floor_strength_zero_disables_floor_without_disabling_feature():
    c_zero = _with_synthetic_buckets(strength=0.0)
    out_zero = opt.compute_optimal_allocation(c_zero, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    assert out_zero['total_targets'].get('Cash', 0.0) == pytest.approx(out_off['total_targets'].get('Cash', 0.0), abs=1e-6)
    assert out_zero['equity_pct'] == pytest.approx(out_off['equity_pct'], abs=1e-6)
    # But the feature is still flagged on in diagnostics.
    assert out_zero['diagnostics']['holding_period_floors_applied']['enabled'] is True


def test_floor_never_lowers_a_higher_risk_tolerance_equity_pct():
    # A household whose risk-tolerance-driven equity_pct already exceeds the
    # long-term-share floor should be unaffected (floor, not override).
    c = sample_config()
    c['risk_tolerance'] = 10  # near-maximum equity_pct
    out_off = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    baseline_equity_pct = out_off['equity_pct']

    c2 = sample_config()
    c2['risk_tolerance'] = 10
    c2['holding_period_allocation_enabled'] = True
    c2['_holding_period_buckets'] = {'0-2 yr': {'share': 0.0}, '16+ yr': {'share': 0.30}}
    out_on = opt.compute_optimal_allocation(c2, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    if baseline_equity_pct >= 0.30:
        assert out_on['equity_pct'] == pytest.approx(baseline_equity_pct, abs=1e-6)


def test_lesson_3_shifts_fixed_income_ladder_toward_short_duration():
    # Isolate the fi_base_split shift: zero near/long-term shares so only the
    # lesson-3 ladder shift is exercised, holding fi_pct constant.
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    bonds_off = out_off['total_targets'].get('Bonds', 0.0)
    short_off = out_off['total_targets'].get('Short-Term Bonds', 0.0)

    c_on = sample_config()
    c_on['holding_period_allocation_enabled'] = True
    c_on['_holding_period_buckets'] = {'0-2 yr': {'share': 0.0}, '16+ yr': {'share': 0.0}}
    out_on = opt.compute_optimal_allocation(c_on, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    bonds_on = out_on['total_targets'].get('Bonds', 0.0)
    short_on = out_on['total_targets'].get('Short-Term Bonds', 0.0)

    if bonds_off > 0 or short_off > 0:
        # fi_pct should be essentially unchanged (zero equity/cash floor
        # nudge), but the split within it shifts toward Short-Term Bonds.
        assert (bonds_off + short_off) == pytest.approx(bonds_on + short_on, abs=1e-6)
        assert short_on > short_off - 1e-9
        assert bonds_on < bonds_off + 1e-9


def test_floors_do_not_affect_tangency_mode():
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_TANGENCY)

    c_on = _with_synthetic_buckets(strength=1.0)
    out_on = opt.compute_optimal_allocation(c_on, force_mode=ap.ALLOCATION_MODE_TANGENCY)

    assert out_off['liquid_targets'] == pytest.approx(out_on['liquid_targets'])


def test_floors_do_not_affect_user_target_mode():
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_USER)

    c_on = _with_synthetic_buckets(strength=1.0)
    out_on = opt.compute_optimal_allocation(c_on, force_mode=ap.ALLOCATION_MODE_USER)

    assert out_off['liquid_targets'] == pytest.approx(out_on['liquid_targets'])


def test_max_sharpe_mode_also_receives_floors():
    c_off = sample_config()
    out_off = opt.compute_optimal_allocation(c_off, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    baseline_cash = out_off['total_targets'].get('Cash', 0.0)

    c_on = _with_synthetic_buckets(strength=1.0)
    out_on = opt.compute_optimal_allocation(c_on, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    assert out_on['total_targets'].get('Cash', 0.0) > baseline_cash
    assert out_on['diagnostics']['allocation_policy_mode'] == 'max_sharpe_recommendation'


# ---------------------------------------------------------------------------
# Two-pass integration: _resolve_holding_period_floors_and_reapply
# ---------------------------------------------------------------------------


def test_resolve_holding_period_floors_is_noop_when_disabled():
    c = sample_config()
    ret_before = c['ret']
    sigma_before = c['mc_sigma']
    _resolve_holding_period_floors_and_reapply(c)
    assert '_holding_period_buckets' not in c
    assert c['ret'] == ret_before
    assert c['mc_sigma'] == sigma_before


def test_resolve_holding_period_floors_populates_buckets_when_enabled():
    c = sample_config()
    c['holding_period_allocation_enabled'] = True
    _resolve_holding_period_floors_and_reapply(c)
    assert '_holding_period_buckets' in c
    assert c.get('_holding_period_buckets_source') in (
        'withdrawal_schedule', 'no_projected_withdrawals', 'no_liquid_assets'
    )


def test_resolve_holding_period_floors_does_not_mutate_real_lots():
    c = sample_config()
    c['holding_period_allocation_enabled'] = True
    lots_ref_before = c.get('lots_by_account')
    _resolve_holding_period_floors_and_reapply(c)
    assert c.get('lots_by_account') is lots_ref_before


def test_parse_client_holding_period_floors_end_to_end():
    data = sample_data()
    data.setdefault('Asset Allocation Policy', {}).setdefault('Global', {})['holding_period_allocation_enabled'] = 'YES'
    c = parse_client(data, "")
    assert c['holding_period_allocation_enabled'] is True
    assert '_holding_period_buckets' in c


def test_parse_client_holding_period_floors_disabled_matches_baseline():
    data_baseline = sample_data()
    data_off = sample_data()
    data_off.setdefault('Asset Allocation Policy', {}).setdefault('Global', {})['holding_period_allocation_enabled'] = 'NO'
    c_baseline = parse_client(data_baseline, "")
    c_off = parse_client(data_off, "")
    assert c_baseline['ret'] == pytest.approx(c_off['ret'])
    assert c_baseline['mc_sigma'] == pytest.approx(c_off['mc_sigma'])
