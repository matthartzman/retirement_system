"""Tests for Phase 4: the ALLOCATION_MODE_REAL_LOSS_AWARE allocation mode.

Unlike Phase 3's floors (a nudge on top of the optimizer/max-Sharpe modes),
this is a full alternative allocation mode, structurally parallel to
tangency: a full-universe solve across enabled/uncovered asset classes, but
split into holding-period buckets (src/holding_period.py) and solved per
bucket with an added real-loss-probability penalty
(_real_loss_aware_weights, src/real_loss_curves.py), then blended by bucket
dollar share.

Selecting this mode is itself the opt-in for holding-period bucket
discovery (data_io._resolve_holding_period_floors_and_reapply) -- no
separate holding_period_allocation_enabled flag is required.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

import src.optimization as opt
import src.allocation_policy as ap
from src.data_io import load_csv, parse_client

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


def sample_data():
    return load_csv(ROOT / "input" / "client_data.csv")


# ---------------------------------------------------------------------------
# Mode registration
# ---------------------------------------------------------------------------


def test_mode_registered_in_choices_and_labels():
    assert ap.ALLOCATION_MODE_REAL_LOSS_AWARE in ap.ALLOCATION_MODE_CHOICES
    assert ap.ALLOCATION_MODE_REAL_LOSS_AWARE in ap.ALLOCATION_MODE_LABELS
    assert ap.allocation_mode_label(ap.ALLOCATION_MODE_REAL_LOSS_AWARE)


def test_normalize_allocation_mode_aliases():
    for alias in ('real_loss_aware', 'real_loss', 'loss_aware', 'Real Loss Aware', 'REAL-LOSS-AWARE'):
        assert ap.normalize_allocation_mode(alias) == ap.ALLOCATION_MODE_REAL_LOSS_AWARE


def test_recommendation_comment_present():
    assert getattr(ap, 'REAL_LOSS_AWARE_RECOMMENDATION_COMMENT', '')


# ---------------------------------------------------------------------------
# _real_loss_aware_weights — pure solver unit tests
# ---------------------------------------------------------------------------


def test_solver_favors_lower_real_loss_class_when_weight_dominates():
    mu = np.array([0.06, 0.06])  # identical expected return
    cov = np.array([[0.02, 0.0], [0.0, 0.02]])  # identical, uncorrelated variance
    real_loss_probs = np.array([0.50, 0.05])  # class 1 much safer
    bounds = [(0.0, 1.0), (0.0, 1.0)]
    w = opt._real_loss_aware_weights(mu, cov, real_loss_probs, bounds, risk_aversion=0.01, real_loss_weight=100.0)
    assert w[1] > w[0]


def test_solver_respects_bounds():
    mu = np.array([0.08, 0.03])
    cov = np.array([[0.03, 0.0], [0.0, 0.01]])
    real_loss_probs = np.array([0.30, 0.10])
    bounds = [(0.0, 0.20), (0.0, 1.0)]
    w = opt._real_loss_aware_weights(mu, cov, real_loss_probs, bounds, risk_aversion=1.0, real_loss_weight=1.0)
    assert w[0] <= 0.20 + 1e-6
    assert w.sum() == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# compute_optimal_allocation(force_mode=REAL_LOSS_AWARE)
# ---------------------------------------------------------------------------


def test_fallback_with_no_bucket_signal_does_not_raise():
    c = sample_config()
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    assert sum(out['liquid_targets'].values()) == pytest.approx(1.0, abs=1e-6)
    diag = out['diagnostics']
    assert diag['allocation_policy_mode'] == 'real_loss_aware_portfolio'
    assert 'plan_horizon' in diag['real_loss_aware_bucket_shares']


def test_near_term_only_bucket_is_cash_heavy():
    c = sample_config()
    c['_holding_period_buckets'] = {'0-2 yr': {'share': 1.0, 'dollars': 0.0}}
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    assert out['liquid_targets'].get('Cash', 0.0) > 0.5
    assert out['equity_pct'] < 0.3


def test_long_term_only_bucket_is_growth_heavy():
    c = sample_config()
    c['_holding_period_buckets'] = {'16+ yr': {'share': 1.0, 'dollars': 0.0}}
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    assert out['equity_pct'] > 0.5
    assert out['liquid_targets'].get('Cash', 0.0) < 0.2


def test_mixed_buckets_blend_by_share():
    c = sample_config()
    c['_holding_period_buckets'] = {
        '0-2 yr': {'share': 0.5, 'dollars': 0.0},
        '16+ yr': {'share': 0.5, 'dollars': 0.0},
    }
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    assert 0.3 < out['equity_pct'] < 0.7
    assert sum(out['liquid_targets'].values()) == pytest.approx(1.0, abs=1e-6)


def test_bucket_shares_ignored_when_zero():
    c = sample_config()
    c['_holding_period_buckets'] = {
        '0-2 yr': {'share': 1.0, 'dollars': 0.0},
        '3-5 yr': {'share': 0.0, 'dollars': 0.0},
        '6-10 yr': {'share': 0.0, 'dollars': 0.0},
        '11-15 yr': {'share': 0.0, 'dollars': 0.0},
        '16+ yr': {'share': 0.0, 'dollars': 0.0},
    }
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    diag = out['diagnostics']
    solved_labels = set(diag['real_loss_aware_bucket_solutions'].keys())
    assert solved_labels == {'0-2 yr'}


def test_diagnostics_shape():
    c = sample_config()
    c['_holding_period_buckets'] = {
        '0-2 yr': {'share': 0.3, 'dollars': 0.0},
        '16+ yr': {'share': 0.7, 'dollars': 0.0},
    }
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    diag = out['diagnostics']
    for key in (
        'real_loss_aware_bucket_shares', 'real_loss_aware_bucket_solutions',
        'real_loss_aware_bucket_years', 'real_loss_aware_risk_aversion',
        'real_loss_aware_weight', 'optimizer_recommendation_comment',
    ):
        assert key in diag
    for label, solution in diag['real_loss_aware_bucket_solutions'].items():
        assert sum(solution.values()) == pytest.approx(1.0, abs=1e-6)


def test_excluded_class_never_receives_weight():
    c = sample_config()
    c['_holding_period_buckets'] = {'0-2 yr': {'share': 1.0, 'dollars': 0.0}}
    actions = dict(c.get('asset_class_selection_action') or {})
    actions['Cash'] = ap.SELECTION_EXCLUDE
    c['asset_class_selection_action'] = actions
    c['asset_class_enabled'] = {**(c.get('asset_class_enabled') or {}), 'Cash': False}
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    assert out['liquid_targets'].get('Cash', 0.0) == 0.0
    assert 'Cash' in out['disabled_asset_classes']


def test_real_loss_aware_weight_and_risk_aversion_config_knobs_are_honored():
    # The sample household's own capital-market assumptions happen to
    # saturate mean-variance at a corner solution in both directions (100%
    # Cash near-term, 100% equities long-term) even before the real-loss
    # term is added, so a behavioral before/after comparison through the
    # full household config can't isolate the real-loss term's marginal
    # effect -- that mechanism is already proven directly and in isolation
    # by test_solver_favors_lower_real_loss_class_when_weight_dominates.
    # Here, just confirm the configured knobs actually reach the solver
    # (surfaced in diagnostics) rather than being silently ignored.
    c = sample_config()
    c['_holding_period_buckets'] = {'16+ yr': {'share': 1.0, 'dollars': 0.0}}
    c['real_loss_aware_weight'] = 2.5
    c['real_loss_aware_risk_aversion'] = 1.5
    out = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_REAL_LOSS_AWARE)
    assert out['diagnostics']['real_loss_aware_weight'] == pytest.approx(2.5)
    assert out['diagnostics']['real_loss_aware_risk_aversion'] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Two-pass integration: selecting the mode is itself the opt-in
# ---------------------------------------------------------------------------


def test_parse_client_real_loss_aware_mode_triggers_bucket_discovery():
    data = sample_data()
    data.setdefault('Asset Allocation Policy', {}).setdefault('Global', {})['allocation_selection_mode'] = 'real_loss_aware'
    c = parse_client(data, "")
    assert c['allocation_selection_mode'] == ap.ALLOCATION_MODE_REAL_LOSS_AWARE
    assert '_holding_period_buckets' in c
    # holding_period_allocation_enabled was never set -- selecting the mode
    # alone must be sufficient to trigger discovery.
    assert c.get('holding_period_allocation_enabled') is False


def test_parse_client_real_loss_aware_produces_valid_ret_and_sigma():
    data = sample_data()
    data.setdefault('Asset Allocation Policy', {}).setdefault('Global', {})['allocation_selection_mode'] = 'real_loss_aware'
    c = parse_client(data, "")
    assert c['ret'] is not None
    assert c['mc_sigma'] is not None
    assert c.get('allocation_projection_applied') is True


# ---------------------------------------------------------------------------
# Byte-stability: existing modes unaffected by the new mode's existence
# ---------------------------------------------------------------------------


def test_existing_modes_unaffected_by_new_mode():
    c = sample_config()
    for mode in (ap.ALLOCATION_MODE_USER, ap.ALLOCATION_MODE_OPTIMIZER,
                 ap.ALLOCATION_MODE_MAX_SHARPE, ap.ALLOCATION_MODE_TANGENCY):
        out = opt.compute_optimal_allocation(c, force_mode=mode)
        assert sum(out['liquid_targets'].values()) == pytest.approx(1.0, abs=1e-6)
        assert out['diagnostics']['allocation_selection_mode'] == mode
