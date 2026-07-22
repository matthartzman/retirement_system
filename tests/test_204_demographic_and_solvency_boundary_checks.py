"""T2c (system review 2026-07-21, Q5): near-zero coverage existed for
malformed/nonsensical input before this file -- a deterministic projection
built on impossible demographics or day-one insolvency failed silently
rather than loudly. Follows test_198_unsupported_state_preflight.py's
pattern: a readable ValueError naming the offending value and how to fix it,
raised from the one common gate (plan_config.ensure_engine_config) every
build path passes through.

Mutations are applied to the raw sectioned `data` dict (as loaded from CSV),
not to an already-parsed config -- parse_client() calls ensure_engine_config()
internally, and that function's A4 fast path skips re-validation for a dict
that already carries its immutable-boundary marker. Mutating the source data
and re-parsing exercises the real, first-time validation path a malformed
CSV/JSON input would actually hit, rather than a synthetic double-call.
"""
import copy
from pathlib import Path

import pytest

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config

ROOT = Path(__file__).resolve().parents[1]


def load_sample_data():
    return load_csv(ROOT / 'input' / 'client_data.csv')


def parse(data):
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return c


def test_live_sample_plan_passes_all_boundary_checks():
    # Locks in the happy path: real client data must never trip these gates.
    parse(load_sample_data())


def test_dob_after_retirement_raises_actionable_error():
    data = copy.deepcopy(load_sample_data())
    data['Household']['']['member_1_dob'] = '1/1/2010'
    data['Household']['']['member_1_retirement_date'] = '1/1/2005'
    with pytest.raises(ValueError) as exc_info:
        parse(data)
    message = str(exc_info.value)
    assert '2005' in message
    assert '2010' in message
    assert 'negative retirement age' in message


def test_zero_mortality_age_raises_actionable_error():
    data = copy.deepcopy(load_sample_data())
    data['Household']['']['member_1_mortality_age'] = '0'
    with pytest.raises(ValueError) as exc_info:
        parse(data)
    message = str(exc_info.value)
    assert 'mortality' in message.lower()
    assert 'positive' in message.lower()


def test_negative_mortality_age_raises_actionable_error():
    data = copy.deepcopy(load_sample_data())
    data['Household']['']['member_1_mortality_age'] = '-3'
    with pytest.raises(ValueError) as exc_info:
        parse(data)
    assert 'mortality' in str(exc_info.value).lower()


def test_spending_exceeding_all_assets_in_year_one_raises_actionable_error():
    # spend_base is computed by spending_budget_resolver from the fuller
    # budget-line structure, not read straight through from a single CSV
    # field, so it's mutated post-parse rather than at the source. force=True
    # re-triggers full validation -- ensure_engine_config's A4 fast path
    # would otherwise skip re-checking a dict parse_client already validated.
    c = parse(copy.deepcopy(load_sample_data()))
    total_balance = sum(float(v) for v in c['balances'].values())
    c['spend_base'] = total_balance + 1_000_000
    with pytest.raises(ValueError) as exc_info:
        ensure_engine_config(c, source='test', force=True)
    message = str(exc_info.value)
    assert 'insolvent' in message.lower()
    assert 'spending' in message.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
