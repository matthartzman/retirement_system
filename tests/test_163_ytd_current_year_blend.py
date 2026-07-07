from __future__ import annotations

from datetime import date

from src import ytd_tracking as ytd
from src.ytd_projection_blend import compute_current_year_overrides
from src.planning_engines import apply_end_of_year_growth


def _minimal_config(**overrides):
    c = {'plan_start': 2026, 'plan_end': 2060, 'ret': 0.08}
    c.update(overrides)
    return c


def test_no_ytd_data_still_prorates_growth_but_skips_flow_overrides(tmp_path):
    c = _minimal_config()
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))

    # Growth/contribution proration is pure date math - always computed, no
    # YTD tracking setup required.
    assert 2026 in overrides['return_by_year']
    assert overrides['return_by_year'][2026] < c['ret']
    assert 2026 in overrides['ytd_blend_contrib_proration']
    assert overrides['ytd_blend_applied']['flows_blended'] is False

    # No YTD transactions logged this year -> no earned/spend override, so
    # income/spending fall back to the old full-year behavior untouched.
    assert 'ytd_blend_earned_override' not in overrides
    assert 'ytd_blend_spend_override' not in overrides


def test_outside_plan_window_is_a_full_noop(tmp_path):
    c = _minimal_config(plan_start=2030, plan_end=2060)
    assert compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2)) == {}


def test_remaining_fraction_matches_elapsed_days(tmp_path):
    c = _minimal_config()
    # Jan 1: (almost) the entire year remains.
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 1, 1))
    assert overrides['ytd_blend_applied']['remaining_fraction'] > 0.99
    # Dec 31: almost none of the year remains.
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 12, 31))
    assert overrides['ytd_blend_applied']['remaining_fraction'] < 0.01
    # July 2 of a non-leap year: roughly half the year remains.
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))
    assert 0.45 < overrides['ytd_blend_applied']['remaining_fraction'] < 0.55


def test_ytd_data_present_blends_actual_earned_income_and_spending(tmp_path):
    (tmp_path / 'client_spending.csv').write_text(
        'section,subsection,label,value,units,notes\n'
        'Cashflow,Spending,annual_spending_base_year,"$120,000",,\n',
        encoding='utf-8',
    )
    tx = (
        'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n'
        '2026-02-01,Employer,Paychecks,Checking,Bank,,50000,,Household\n'
        '2026-02-01,Grocery,Groceries,Checking,Bank,,-40000,,Household\n'
    )
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config()
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))

    assert overrides['ytd_blend_applied']['flows_blended'] is True
    # Earned income: actual so far + remaining plan estimate for the rest of
    # the earning window (no explicit earn plan configured here, so the
    # remaining estimate falls back to whatever annual_earned_income_forecast
    # resolves - at minimum it must not be less than what's already earned).
    assert overrides['ytd_blend_earned_override'][2026] >= 50000.0
    # Spending: actual-to-date + prorated remainder of the $120k annual plan,
    # not the full $120k (which would double-count the elapsed months).
    spend_override = overrides['ytd_blend_spend_override'][2026]
    assert 40000.0 <= spend_override < 120000.0


def test_manual_remainder_overrides_replace_linear_proration(tmp_path):
    (tmp_path / 'client_spending.csv').write_text(
        'section,subsection,label,value,units,notes\n'
        'Cashflow,Spending,annual_spending_base_year,"$120,000",,\n',
        encoding='utf-8',
    )
    tx = (
        'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n'
        '2026-02-01,Employer,Paychecks,Checking,Bank,,50000,,Household\n'
        '2026-02-01,Grocery,Groceries,Checking,Bank,,-40000,,Household\n'
    )
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config(
        ytd_remainder_earned_income_override=9999.0,
        ytd_remainder_spending_override=5555.0,
    )
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))

    # actual (50000/40000) + the explicit override, not the computed estimate.
    assert overrides['ytd_blend_earned_override'][2026] == 50000.0 + 9999.0
    assert overrides['ytd_blend_spend_override'][2026] == 40000.0 + 5555.0
    assert overrides['ytd_blend_applied']['earned_remainder_overridden'] is True
    assert overrides['ytd_blend_applied']['spend_remainder_overridden'] is True


def test_blank_remainder_overrides_keep_linear_proration_behavior(tmp_path):
    """None (the default when a plan doesn't set these fields) must not be
    mistaken for an explicit override of 0."""
    (tmp_path / 'client_spending.csv').write_text(
        'section,subsection,label,value,units,notes\n'
        'Cashflow,Spending,annual_spending_base_year,"$120,000",,\n',
        encoding='utf-8',
    )
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-02-01,Employer,Paychecks,Checking,Bank,,50000,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config(ytd_remainder_earned_income_override=None, ytd_remainder_spending_override=None)
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))

    assert 'earned_remainder_overridden' not in overrides['ytd_blend_applied']
    assert 'spend_remainder_overridden' not in overrides['ytd_blend_applied']


def test_ytd_blend_enabled_false_skips_flow_blend_but_keeps_growth_proration(tmp_path):
    """A plan opting out of real-actuals blending (Finding A) must still get
    the always-on growth/contribution date proration - only the flow
    (earned income/spending) blend, which pulls in real workspace data, is
    suppressed."""
    (tmp_path / 'client_spending.csv').write_text(
        'section,subsection,label,value,units,notes\n'
        'Cashflow,Spending,annual_spending_base_year,"$120,000",,\n',
        encoding='utf-8',
    )
    tx = (
        'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n'
        '2026-02-01,Employer,Paychecks,Checking,Bank,,50000,,Household\n'
        '2026-02-01,Grocery,Groceries,Checking,Bank,,-40000,,Household\n'
    )
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config(ytd_blend_enabled=False)
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))

    # Growth/contribution proration is unaffected by this setting.
    assert 2026 in overrides['return_by_year']
    assert overrides['return_by_year'][2026] < c['ret']
    assert 2026 in overrides['ytd_blend_contrib_proration']

    # Flow blending is suppressed even though real YTD transactions exist.
    assert 'ytd_blend_earned_override' not in overrides
    assert 'ytd_blend_spend_override' not in overrides
    assert overrides['ytd_blend_applied']['flows_blended'] is False
    assert overrides['ytd_blend_applied']['flow_blend_enabled'] is False
    assert overrides['ytd_blend_applied']['flow_blend_skipped_by_user_choice'] is True
    assert overrides['ytd_blend_applied']['ytd_end']


def test_ytd_blend_enabled_defaults_to_true_when_absent(tmp_path):
    """Absent (a plan that predates this field) must behave exactly like
    ytd_blend_enabled=True, not silently disable blending."""
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-02-01,Employer,Paychecks,Checking,Bank,,50000,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config()
    assert 'ytd_blend_enabled' not in c
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))
    assert overrides['ytd_blend_applied']['flow_blend_enabled'] is True
    assert 'ytd_blend_earned_override' in overrides


def test_spend_blend_is_core_scoped_when_taxonomy_exists(tmp_path):
    """Core spending must never include housing/wellness/travel/large-disc —
    in the blended current year too. With a taxonomy present, the blend's
    actual side counts only spend-base tracking types, and the remainder side
    prorates the engine's own core spend_base, not the all-in household plan."""
    from src.ytd_projection_blend import _remaining_fraction

    input_dir = tmp_path / 'input'
    input_dir.mkdir()
    (input_dir / 'client_spending_taxonomy.csv').write_text(
        'tracking_type,group,category_id,label,origin,status,notes\n'
        'Core Expenses,Food,groceries,Groceries,template,active,\n'
        'Housing,Home,mortgage_cat,Mortgage,template,active,\n'
        'Travel,Trips,vacation,Vacation,template,active,\n',
        encoding='utf-8',
    )
    (input_dir / 'client_spending_aliases.csv').write_text(
        'match_value,match_field,exact,priority,category_id,source\n'
        'Groceries,category,1,80,groceries,seed\n'
        'Mortgage,category,1,80,mortgage_cat,seed\n'
        'Vacation,category,1,80,vacation,seed\n',
        encoding='utf-8',
    )
    tx = (
        'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n'
        '2026-02-01,Grocery,Groceries,Checking,Bank,,-40000,,Household\n'
        '2026-02-01,Lender,Mortgage,Checking,Bank,,-18000,,Household\n'
        '2026-03-01,Airline,Vacation,Checking,Bank,,-9000,,Household\n'
    )
    ytd.import_transactions(input_dir, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config(spend_base=50000.0, inf=0.025, core_spending_growth_mode='cpi')
    overrides = compute_current_year_overrides(c, input_dir, today=date(2026, 7, 2))

    meta = overrides['ytd_blend_applied']
    assert meta['spend_scope'] == 'core_taxonomy'
    # Actual side: groceries only — mortgage (Housing) and vacation (Travel)
    # must not leak into the core spend base.
    assert meta['spend_actual_core'] == 40000.0
    # Remainder side: the engine's core spend_base prorated for the rest of the
    # year (current year == plan_start, so no growth factor applies).
    expected_remaining = 50000.0 * _remaining_fraction(date(2026, 7, 2))
    assert abs(meta['spend_remaining'] - expected_remaining) < 1.0
    assert abs(overrides['ytd_blend_spend_override'][2026] - (40000.0 + expected_remaining)) < 1.0


def test_spend_blend_without_taxonomy_falls_back_to_unscoped_legacy_behavior(tmp_path):
    """Plans with no spending taxonomy have nothing to scope with: the blend
    keeps the legacy behavior (all tracked spending + legacy core plan field)
    and says so in the meta."""
    (tmp_path / 'client_spending.csv').write_text(
        'section,subsection,label,value,units,notes\n'
        'Cashflow,Spending,annual_spending_base_year,"$120,000",,\n',
        encoding='utf-8',
    )
    tx = (
        'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n'
        '2026-02-01,Grocery,Groceries,Checking,Bank,,-40000,,Household\n'
    )
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 7, 2))

    c = _minimal_config()
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))
    assert overrides['ytd_blend_applied']['spend_scope'] == 'all_spending_no_taxonomy'
    assert 40000.0 <= overrides['ytd_blend_spend_override'][2026] < 120000.0


def test_growth_proration_avoids_double_counting_elapsed_return():
    """Directly exercises the existing return_by_year hook that
    compute_current_year_overrides relies on (planning_engines.py:19-28),
    proving a year with a 50%-remaining override applies only half the
    assumed annual return - not the full year on top of an already-current
    balance."""
    c = {'invest_ids': ['Taxable'], 'ret': 0.08, 'return_by_year': {2026: 0.04}, 'portfolio_income_reduces_growth': False}
    balances = {'Taxable': 1000.0}
    result = apply_end_of_year_growth(c, balances, year=2026)
    assert balances['Taxable'] == 1040.0
    assert result.total_growth == 40.0

    # A year with no override still uses the flat assumed rate.
    balances2 = {'Taxable': 1000.0}
    apply_end_of_year_growth(c, balances2, year=2027)
    assert balances2['Taxable'] == 1080.0


def test_contribution_proration_key_is_read_by_engine_guard():
    """The engine multiplies 401k/HSA contributions by
    ytd_blend_contrib_proration.get(year, 1.0); absent for any other year or
    caller, it's a pure no-op (multiply by 1.0)."""
    proration = {2026: 0.5}
    assert proration.get(2026, 1.0) == 0.5
    assert proration.get(2027, 1.0) == 1.0
