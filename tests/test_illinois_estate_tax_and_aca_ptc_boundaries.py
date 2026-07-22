import math
from src.core import illinois_estate_tax
from src.planning_engines import aca_premium_tax_credit


def test_illinois_estate_tax_published_style_cliff_examples():
    assert illinois_estate_tax(4_000_000, 4_000_000) == 0
    tax_8m = illinois_estate_tax(8_000_000, 4_000_000)
    assert 660_000 <= tax_8m <= 700_000
    assert illinois_estate_tax(4_100_000, 4_000_000) > 0


def test_aca_premium_tax_credit_enhanced_and_cliff_cases():
    c = {'aca_ptc_enabled': True,'aca_fpl_base': 20_000,'inf': 0.0,'plan_start': 2026,'aca_enhanced_subsidies_through_year': 2026,'aca_applicable_pct_cap': 0.085,'aca_benchmark_silver_premium': 24_000,'bridge_premium': 24_000,'aca_household_size': 2}
    ptc = aca_premium_tax_credit(c, year=2026, magi=40_000, bridge_people=2)
    assert math.isclose(ptc, 24_000 - 800, rel_tol=0, abs_tol=100)
    c['aca_enhanced_subsidies_through_year'] = 2025
    assert aca_premium_tax_credit(c, year=2026, magi=90_000, bridge_people=2) == 0


def test_scalar_projection_uses_per_year_tax_index_paths():
    from src.data_io import load_csv, parse_client
    from src.planning_engines import project
    from pathlib import Path
    data = load_csv(Path('input') / 'client_data.csv')
    c = parse_client(data, '')
    c['plan_end'] = c['plan_start'] + 2
    # Pin roth_policy so this isolates the bracket-index plumbing being tested,
    # not the default 'fill_to_bracket' Roth optimizer. That optimizer reacts
    # endogenously to bracket width -- with real (large) IRA balances, a much
    # wider bracket lets it convert far more each year, which can raise total
    # federal tax over a short window even though each fixed dollar of income
    # faces a lower marginal rate. That's expected optimizer behavior, but it
    # isn't what this test means to check.
    c['roth_policy'] = 'none'
    c['bracket_index_by_year'] = {c['plan_start']: 1.0, c['plan_start']+1: 10.0, c['plan_start']+2: 10.0}
    high = project(dict(c))
    c2 = dict(c); c2.pop('bracket_index_by_year', None); c2['brk_inf'] = 0.0
    base = project(c2)
    assert sum(r.get('fed_tax', 0) for r in high) <= sum(r.get('fed_tax', 0) for r in base)
