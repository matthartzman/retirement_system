"""WI-308 / FIN-008 (system review 2026-09-25-2): a survivor's home sale
after the first spousal death must (a) use a basis stepped up on the
deceased's share (IRC §1014; half under common-law §2040(b) joint
ownership, full under community property) and (b) keep the $500k §121
exclusion when sold within two years of the death and the survivor has not
remarried (IRC §121(b)(4)), even though filing has reverted to Single.

Verification plan from the finding: h dies 2035, survivor sells 2036,
basis $300k, FMV $1.3M, common-law -> basis $800k, exclusion $500k,
taxable gain ~= 0 before selling costs.
"""
from src.planning_engines import project
from src.projection_stages.home_sale import (
    first_death_home_basis, surviving_spouse_sec121_window,
)

from tests.test_regressions_functional import sample_config


def _survivor_plan(sale_yr=2036, **overrides):
    c = sample_config()
    c.update({
        'plan_start': 2034,
        'plan_end': max(sale_yr, 2036),
        'h_death_yr': 2035,
        'w_death_yr': 2055,
        'first_death_yr': 2035,
        'qss_dependent': False,
        'survivor_filing': 'Single',
        'home_val': 1_300_000.0,
        'home_appr': 0.0,
        'home_sale_yr': sale_yr,
        'home_sale_px': 0.0,
        'home_basis': 300_000.0,
        'home_sell_cost_pct': 0.0,
        'mortgage_bal': 0.0,
        'mort_schedule': {},
        'mort_end': 2033,
        'sec121': 500_000.0,
        'basis_step_up_property_regime': 'COMMON_LAW',
    })
    c.update(overrides)
    return c


def _row(rows, year):
    return next(r for r in rows if r['year'] == year)


def test_finding_synthetic_plan_common_law():
    rows = project(_survivor_plan())
    death = _row(rows, 2035)
    assert death['home_basis_after_first_death'] == 800_000.0
    assert death['home_basis_first_death_step_up'] == 500_000.0
    sale = _row(rows, 2036)
    assert sale['filing'] == 'Single'  # no QSS dependent: filing has reverted
    assert sale['home_sale_gross'] == 1_300_000.0
    assert sale['home_sale_basis'] == 800_000.0
    assert sale['home_sale_gain'] == 500_000.0
    assert sale['home_sale_sec121_exclusion'] == 500_000.0
    assert sale['home_sale_sec121_survivor_window'] is True
    assert sale['home_sale_taxable'] == 0
    assert sale['home_sale_tax'] == 0


def test_community_property_steps_up_both_halves():
    rows = project(_survivor_plan(basis_step_up_property_regime='COMMUNITY_PROPERTY'))
    assert _row(rows, 2035)['home_basis_after_first_death'] == 1_300_000.0
    sale = _row(rows, 2036)
    assert sale['home_sale_gain'] == 0
    assert sale['home_sale_taxable'] == 0


def test_sale_after_two_year_window_gets_single_exclusion_but_keeps_step_up():
    rows = project(_survivor_plan(sale_yr=2038))
    sale = _row(rows, 2038)
    assert sale['home_sale_basis'] == 800_000.0
    assert sale['home_sale_sec121_exclusion'] == 250_000.0
    assert sale['home_sale_sec121_survivor_window'] is False
    assert sale['home_sale_taxable'] == 250_000.0


def test_remarriage_closes_the_survivor_window():
    rows = project(_survivor_plan(survivor_remarriage_yr=2036))
    sale = _row(rows, 2036)
    assert sale['home_sale_sec121_exclusion'] == 250_000.0
    assert sale['home_sale_taxable'] == 250_000.0


def test_sale_while_both_alive_is_unchanged():
    rows = project(_survivor_plan(sale_yr=2034))
    sale = _row(rows, 2034)
    assert sale['filing'] == 'MFJ'
    assert sale['home_sale_gain'] == 1_000_000.0
    assert sale['home_sale_taxable'] == 500_000.0
    assert 'home_sale_basis' not in sale
    assert all('home_basis_after_first_death' not in r for r in rows)


def test_next_housing_step_owned_at_first_death_is_stepped_up():
    c = _survivor_plan(sale_yr=2034, home_sale_px=1_300_000.0)
    c['next_housing_steps'] = [{
        'id': 'condo', 'type': 'purchase', 'start_year': 2034, 'end_year': 2035,
        'sale_year': 2036, 'purchase_price': 600_000.0, 'down_payment_pct': 1.0,
    }]
    c['home_appr'] = 0.10
    rows = project(c)
    sale = _row(rows, 2036)
    # FMV at end of 2035 = 600k * 1.1^2 = 726k (also the 2036 sale price);
    # common-law half step-up -> basis 663k, gain 63k, fully excluded.
    assert abs(sale['next_housing_sale_gross'] - 726_000.0) < 1e-6
    assert abs(sale['next_housing_sale_gain'] - 63_000.0) < 1e-6
    assert sale['next_housing_sale_sec121_exclusion'] == 500_000.0
    assert sale['next_housing_sale_taxable'] == 0


def test_helpers():
    assert first_death_home_basis(300_000, 1_300_000, 0.5) == 800_000
    assert first_death_home_basis(300_000, 1_300_000, 1.0) == 1_300_000
    assert first_death_home_basis(500_000, 400_000, 0.5) == 450_000  # §1014 steps down too
    assert surviving_spouse_sec121_window({}, year=2037, first_death_yr=2035)
    assert not surviving_spouse_sec121_window({}, year=2038, first_death_yr=2035)
    assert not surviving_spouse_sec121_window({}, year=2036, first_death_yr=None)
    assert not surviving_spouse_sec121_window(
        {'survivor_remarriage_yr': 2036}, year=2036, first_death_yr=2035)
