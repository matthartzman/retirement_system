"""#252: a -50% earned_income_annual_increase must be accepted and must
actually halve the following year's earned income.

Root cause: reference_data/schema.csv hardcoded min=-20 (percent) for this
field, even though its own description already said "can be negative for a
planned pay cut, sabbatical year, or reduced hours" -- so ConfigService's
grid save (schema_registry.validate_rows) rejected any cut steeper than
-20% with a 422 before it ever reached the engine. The engine's compounding
formula (earned_base = earned * (1 + earn_inc) ** years_elapsed) was
already correct for negative rates; it just never got the chance to run.
"""
from src.schema_registry import validate_rows


def test_minus_50_percent_passes_schema_validation():
    rows = [{
        'section': 'Cashflow', 'subsection': 'Earned Income',
        'label': 'earned_income_annual_increase', 'value': '-50%',
    }]
    assert validate_rows(rows) == []


def test_minus_100_percent_still_passes_as_the_mathematical_floor():
    rows = [{
        'section': 'Cashflow', 'subsection': 'Earned Income',
        'label': 'earned_income_annual_increase', 'value': '-100%',
    }]
    assert validate_rows(rows) == []


def test_below_minus_100_percent_is_still_rejected_as_impossible():
    rows = [{
        'section': 'Cashflow', 'subsection': 'Earned Income',
        'label': 'earned_income_annual_increase', 'value': '-150%',
    }]
    errors = validate_rows(rows)
    assert errors and 'min' in errors[0]


def test_engine_halves_earned_income_the_following_year(tmp_path):
    """End-to-end: a -50% growth rate applied through the real projection
    engine must make year 2 exactly half of year 1 (matches the user's
    literal ask -- "earning half as much next year")."""
    from src.data_io import load_csv, parse_client
    from src.plan_config import ensure_engine_config
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

    c = ensure_engine_config(parse_client(load_csv('input/client_data.csv'), ''), source='test')
    c['earn_inc'] = -0.5
    # This household's real earn_end may equal earn_start (retiring this
    # year) -- extend it so there's a real "next year" of earned income to
    # observe the growth rate against.
    c['earn_end'] = c['earn_start'] + 1
    c['base_earn_end'] = c['earn_end']
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
    by_year = {r['year']: r.get('earned') for r in rows}
    y0 = c['earn_start']
    assert by_year[y0] > 0, 'sanity: year 1 earned income must be nonzero'
    assert abs(by_year[y0 + 1] - by_year[y0] * 0.5) < 1e-6, (
        f"year {y0 + 1} earned {by_year[y0 + 1]!r} is not half of year {y0} earned {by_year[y0]!r}"
    )
