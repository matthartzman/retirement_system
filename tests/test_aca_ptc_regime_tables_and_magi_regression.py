"""WI-307 / FIN-007: dated ACA applicable-percentage tables per regime, the
enhanced-through-year default from a dated dataset row, and ACA MAGI that
includes non-taxable Social Security.

The 2026 original-IRC-36B table is VERIFIED against IRS Rev. Proc. 2025-25. The
2025 enhanced-through-year default follows the statutory schedule (status
"legislated"; the "no later extension" caveat is kept in its source text). The
enhanced (ARPA/IRA) percentage table is a recalled, UNVERIFIED assumption (status
"assumption" in tax_law_v10.json); those tests pin the engine to the dataset.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src import tax_law
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    aca_applicable_percentage,
    aca_enhanced_through_year,
    aca_guardrail_max_fpl_multiple,
    aca_magi,
    aca_premium_tax_credit,
    project,
)

from conftest import TEST_INPUT_DIR

ROOT = Path(__file__).resolve().parents[1]
FPL = 20_000.0
BENCHMARK = 30_000.0


def _cfg(**over):
    c = {
        'aca_ptc_enabled': True, 'aca_fpl_base': FPL, 'inf': 0.0, 'plan_start': 2026,
        'aca_enhanced_subsidies_through_year': 2025, 'aca_applicable_pct_cap': 0.085,
        'aca_benchmark_silver_premium': BENCHMARK, 'aca_household_size': 2,
    }
    c.update(over)
    return c


def test_aca_row_verification_status_matches_what_was_checked():
    rows = [r for r in json.loads((ROOT / 'reference_data/tax_law_v10.json').read_text(encoding='utf-8'))['values']
            if r['name'].startswith('aca_')]
    assert rows
    # The 2026 original-36B table was checked against IRS Rev. Proc. 2025-25 (2026-09-29).
    orig = [r for r in rows if r['name'].startswith('aca_applicable_pct_original')]
    assert orig
    for r in orig:
        assert r['status'] == 'verified', r['name']
        assert 'Rev. Proc. 2025-25' in r['source'], r['name']
    # The enhanced-through-year default follows the statutory schedule (Inflation Reduction Act:
    # enhanced credit through 2025, expired 2026-01-01 unless extended; owner-confirmed 2026-09-29),
    # with the unverified "no later extension" caveat kept in its source text.
    default = [r for r in rows if r['name'] == 'aca_enhanced_subsidies_through_year']
    assert len(default) == 1 and default[0]['value'] == 2025
    assert default[0]['status'] == 'legislated'
    assert 'Inflation Reduction Act' in default[0]['source'] and 'NOT verified' in default[0]['source']
    # The enhanced ARPA/IRA percentage table is NOT covered by a supplied document and stays an
    # unverified assumption.
    others = [r for r in rows if r not in orig and r not in default]
    assert others
    for r in others:
        assert r['status'] == 'assumption', r['name']
        assert 'UNVERIFIED' in r['source'], r['name']


@pytest.mark.parametrize('fpl_mult, pct', [
    (1.00, 0.0210), (1.33, 0.0314), (1.50, 0.0419), (2.00, 0.0660),
    (2.25, (0.0660 + 0.0844) / 2), (2.50, 0.0844), (3.00, 0.0996), (3.50, 0.0996), (4.00, 0.0996),
])
def test_original_table_values_and_interpolation(fpl_mult, pct):
    assert math.isclose(aca_applicable_percentage(fpl_mult, enhanced=False, year=2027), pct, abs_tol=1e-9)


@pytest.mark.parametrize('fpl_mult, pct', [(250, 0.0844), (350, 0.0996)])
def test_ptc_2027_non_enhanced_matches_table(fpl_mult, pct):
    c = _cfg()
    magi = FPL * fpl_mult / 100.0
    ptc = aca_premium_tax_credit(c, year=2027, magi=magi, bridge_people=2)
    assert math.isclose(ptc, BENCHMARK - magi * pct, abs_tol=0.01)


def test_non_enhanced_above_400_pct_fpl_has_no_credit():
    assert aca_premium_tax_credit(_cfg(), year=2027, magi=FPL * 4.01, bridge_people=2) == 0.0


def test_enhanced_year_schedule_unchanged():
    c = _cfg(aca_enhanced_subsidies_through_year=2030)
    old = [(1.0, 0.0), (1.5, 0.0), (1.75, 0.01), (2.0, 0.02), (2.5, 0.04), (3.0, 0.06), (3.5, 0.0725), (4.0, 0.085), (6.0, 0.085)]
    for f, pct in old:
        assert math.isclose(aca_applicable_percentage(f, enhanced=True, cap=0.085, year=2027), pct, abs_tol=1e-9), f
        ptc = aca_premium_tax_credit(c, year=2027, magi=FPL * f, bridge_people=2)
        assert math.isclose(ptc, max(0.0, BENCHMARK - FPL * f * pct), abs_tol=0.01), f
    # The plan cap still governs the enhanced top rate.
    assert math.isclose(aca_applicable_percentage(5.0, enhanced=True, cap=0.09, year=2027), 0.09)


def test_guardrail_uses_same_regime_tables():
    c = _cfg(aca_ptc_guardrail_fpl_pct=5.0)
    assert aca_guardrail_max_fpl_multiple(c, 2027) == 4.0          # original: cliff at max_fpl
    c['aca_enhanced_subsidies_through_year'] = 2030
    assert aca_guardrail_max_fpl_multiple(c, 2027) == 5.0          # enhanced: credit continues


def _plan_data():
    return load_csv(TEST_INPUT_DIR / 'client_data.csv')


def _set_field(data, value):
    data.setdefault('Wellness', {}).setdefault('ACA Premium Tax Credit', {})['enhanced_subsidies_through_year'] = value


def test_blank_field_uses_dataset_default():
    assert tax_law.aca_enhanced_subsidies_through_year_default() == 2025
    data = _plan_data()
    _set_field(data, '')
    assert parse_client(data, '')['aca_enhanced_subsidies_through_year'] == 2025
    data['Wellness']['ACA Premium Tax Credit'].pop('enhanced_subsidies_through_year')
    assert parse_client(data, '')['aca_enhanced_subsidies_through_year'] == 2025
    assert aca_enhanced_through_year({}) == 2025


def test_explicit_field_wins():
    data = _plan_data()
    _set_field(data, '2026')
    assert parse_client(data, '')['aca_enhanced_subsidies_through_year'] == 2026
    _set_field(data, '2029')
    assert parse_client(data, '')['aca_enhanced_subsidies_through_year'] == 2029


def test_aca_magi_formula():
    assert aca_magi(50_000, 1_000, 30_000, 12_000) == 50_000 + 1_000 + 18_000


def test_projection_aca_magi_includes_non_taxable_ss_claimed_at_62(monkeypatch):
    from src.projection_stages import roth_conversion_and_agi_tax as agi_stage
    from src.projection_stages import spending_and_rmd as spend_stage

    c = parse_client(_plan_data(), '')
    y = int(c['plan_start'])
    c.update({
        'plan_end': y, 'roth_policy': 'none', 'h_dob_yr': y - 62, 'w_dob_yr': y - 62,
        'h_ss_claim_age': 62, 'w_ss_claim_age': 62, 'h_ss_claim_year': y, 'w_ss_claim_year': y,
        'h_ret_yr': y - 1, 'w_ret_yr': y - 1, 'aca_ptc_enabled': True,
    })
    seen = {'final_args': [], 'final_magi': [], 'pre_magi': []}
    real_magi, real_ptc = agi_stage.aca_magi, agi_stage.aca_premium_tax_credit

    def cap_magi(*a):
        seen['final_args'].append(a)
        return real_magi(*a)

    def cap_ptc(c_, *, year, magi, bridge_people):
        seen['final_magi'].append((magi, bridge_people))
        return real_ptc(c_, year=year, magi=magi, bridge_people=bridge_people)

    def cap_pre_ptc(c_, *, year, magi, bridge_people):
        seen['pre_magi'].append(magi)
        return real_ptc(c_, year=year, magi=magi, bridge_people=bridge_people)

    monkeypatch.setattr(agi_stage, 'aca_magi', cap_magi)
    monkeypatch.setattr(agi_stage, 'aca_premium_tax_credit', cap_ptc)
    monkeypatch.setattr(spend_stage, 'aca_premium_tax_credit', cap_pre_ptc)
    rows = project(c)
    assert rows and seen['final_args'] and seen['final_magi']
    agi, exempt, ss_gross, ss_taxable = seen['final_args'][0]
    magi, bridge_people = seen['final_magi'][0]
    assert bridge_people > 0
    assert ss_gross > 0 and ss_gross - ss_taxable > 0
    assert math.isclose(magi, agi + exempt + (ss_gross - ss_taxable), abs_tol=1e-6)
    assert magi > agi + exempt  # strictly above the IRMAA-style AGI + exempt figure
    # Pre-conversion estimate also carries the full (gross) SS.
    assert seen['pre_magi'] and seen['pre_magi'][0] >= ss_gross
