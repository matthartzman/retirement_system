"""Tests for Phase 2 (5a): opt-in auto-derived capital-market planning
horizon (capital_market_config['horizon_source'] == 'auto_from_withdrawals'),
implemented as src/data_io.py's _resolve_auto_horizon_and_reapply.

Default behavior (horizon_source == 'manual', the shipped default) must be
byte-stable: _resolve_auto_horizon_and_reapply must be a true no-op unless a
plan explicitly opts in. When opted in, it must not corrupt the real config's
lot/balance state (the discovery projection runs on a deepcopy).
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.data_io import load_csv, parse_client, _resolve_auto_horizon_and_reapply

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


def sample_data():
    return load_csv(ROOT / "input" / "client_data.csv")


# ---------------------------------------------------------------------------
# Default (manual) behavior — byte-stable
# ---------------------------------------------------------------------------


def test_horizon_source_defaults_to_manual():
    c = sample_config()
    assert c['capital_market_config'].get('horizon_source') == 'manual'


def test_resolve_auto_horizon_is_noop_when_manual():
    c = sample_config()
    cfg_before = copy.deepcopy(c['capital_market_config'])
    ret_before = c['ret']
    sigma_before = c['mc_sigma']
    _resolve_auto_horizon_and_reapply(c)
    assert c['capital_market_config'] == cfg_before
    assert c['ret'] == ret_before
    assert c['mc_sigma'] == sigma_before


def test_parse_client_manual_source_matches_absent_source():
    # Explicitly writing horizon_source=manual must produce an identical
    # result to leaving it unset (the shipped client_data.csv has no such
    # row), confirming the new field's default truly matches prior behavior.
    data_explicit = sample_data()
    data_explicit.setdefault('Asset Class Assumptions', {}).setdefault('Global', {})['capital_market_assumption_horizon_source'] = 'manual'
    c_explicit = parse_client(data_explicit, "")
    c_default = sample_config()
    assert c_explicit['capital_market_config'] == c_default['capital_market_config']
    assert c_explicit['ret'] == pytest.approx(c_default['ret'])
    assert c_explicit['mc_sigma'] == pytest.approx(c_default['mc_sigma'])


# ---------------------------------------------------------------------------
# Opt-in auto_from_withdrawals behavior
# ---------------------------------------------------------------------------


def test_resolve_auto_horizon_overrides_horizon_when_enabled():
    c = sample_config()
    manual_horizon = c['capital_market_config']['horizon_years']
    c['capital_market_config']['horizon_source'] = 'auto_from_withdrawals'
    _resolve_auto_horizon_and_reapply(c)
    cfg = c['capital_market_config']
    assert cfg['horizon_source_resolved'] == 'auto_from_withdrawals'
    assert cfg['manual_horizon_years'] == manual_horizon
    assert cfg['horizon_years'] == pytest.approx(cfg['auto_derived_horizon_years'])
    assert cfg['horizon_years'] > 0


def _lot_fingerprint(lots_by_account):
    # TaxLot has no __eq__ (identity-based), so compare a value fingerprint
    # instead of the objects themselves.
    total = 0.0
    for acct, by_sym in (lots_by_account or {}).items():
        for sym, lots in (by_sym or {}).items():
            for lot in lots or []:
                total += float(getattr(lot, 'quantity', 0.0) or 0.0) * float(getattr(lot, 'cost_basis', 0.0) or 0.0)
    return total


def test_resolve_auto_horizon_does_not_mutate_balances_or_lots():
    c = sample_config()
    c['capital_market_config']['horizon_source'] = 'auto_from_withdrawals'
    balances_before = copy.deepcopy(c.get('balances', {}))
    lots_ref_before = c.get('lots_by_account')
    fingerprint_before = _lot_fingerprint(lots_ref_before)
    _resolve_auto_horizon_and_reapply(c)
    assert c.get('balances', {}) == balances_before
    # The real config's lots_by_account object must never be reassigned or
    # mutated -- the discovery projection runs on a deepcopy, not on c itself.
    assert c.get('lots_by_account') is lots_ref_before
    assert _lot_fingerprint(c.get('lots_by_account')) == pytest.approx(fingerprint_before)


def test_resolve_auto_horizon_updates_ret_and_sigma_consistently():
    # After re-resolving the horizon, c['ret']/c['mc_sigma'] should reflect
    # the allocation blend recomputed under the NEW horizon, not the stale
    # pass-1 (manual/default-horizon) values.
    c = sample_config()
    c['capital_market_config']['horizon_source'] = 'auto_from_withdrawals'
    ret_pass1 = c['ret']
    sigma_pass1 = c['mc_sigma']
    _resolve_auto_horizon_and_reapply(c)
    # allocation_projection_applied should still be True (re-blend succeeded)
    assert c['allocation_projection_applied'] is True
    assert c['allocation_projection_expected_return'] == pytest.approx(c['ret'])
    assert c['allocation_projection_volatility'] == pytest.approx(c['mc_sigma'])


def test_resolve_auto_horizon_never_raises_on_bad_config():
    c = sample_config()
    c['capital_market_config']['horizon_source'] = 'auto_from_withdrawals'
    c['balances'] = {}  # degenerate: no liquid assets at all
    _resolve_auto_horizon_and_reapply(c)  # must not raise
    assert c['capital_market_config'].get('horizon_source_resolved') is not None


def test_parse_client_auto_horizon_end_to_end():
    data = sample_data()
    data.setdefault('Asset Class Assumptions', {}).setdefault('Global', {})['capital_market_assumption_horizon_source'] = 'auto_from_withdrawals'
    c = parse_client(data, "")
    cfg = c['capital_market_config']
    assert cfg.get('horizon_source') == 'auto_from_withdrawals'
    assert cfg.get('horizon_source_resolved') in (
        'auto_from_withdrawals', 'auto_from_withdrawals_no_signal', 'auto_from_withdrawals_failed'
    )


def test_parse_client_auto_horizon_does_not_change_other_household_fields():
    # Opting into auto-horizon should only touch capital_market_config/ret/
    # mc_sigma-derived fields, not household facts like balances or plan dates.
    data_manual = sample_data()
    data_auto = sample_data()
    data_auto.setdefault('Asset Class Assumptions', {}).setdefault('Global', {})['capital_market_assumption_horizon_source'] = 'auto_from_withdrawals'
    c_manual = parse_client(data_manual, "")
    c_auto = parse_client(data_auto, "")
    assert c_manual['balances'] == c_auto['balances']
    assert c_manual['plan_start'] == c_auto['plan_start']
    assert c_manual['plan_end'] == c_auto['plan_end']
