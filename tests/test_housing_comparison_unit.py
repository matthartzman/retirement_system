"""Unit tests for src/housing_comparison.py -- Slice 3 (H9a) of
docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-
convention-design.md.

Uses the frozen sample plan fixture (tests/fixtures/sample_plan_frozen/,
TEST_INPUT_DIR), which -- per test_cashflow_chart_home_purchase_down_payment.py's
own docstring -- has a real Housing Step 1 purchase configured (Texas,
$400,000 @ 27% down, 2036), so the "opposite type" swap has a real purchase
to flip to rent.
"""
from __future__ import annotations

from pathlib import Path

from src.data_io import load_csv, parse_client
from src.housing_comparison import compare_housing_candidates, opposite_type_step
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from conftest import TEST_INPUT_DIR
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]

# Small MC sample count -- these tests only need a real (non-skip_mc) call to
# succeed and return sane fields, not a converged estimate.
_FAST_MC_SIMS = 8


def _config_and_rows():
    c = ensure_engine_config(parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), ""), source="test")
    c['mc_sims'] = _FAST_MC_SIMS
    c['mc_sensitivity_sims'] = 1
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
    return c, rows


def test_configured_step1_is_a_real_purchase():
    c, _rows = _config_and_rows()
    steps = c.get('next_housing_steps') or []
    assert steps, "frozen fixture is expected to configure a Housing Step 1"
    assert steps[0]['type'] == 'purchase'


def test_opposite_type_step_flips_purchase_to_rent_same_year_and_location():
    c, _rows = _config_and_rows()
    step = c['next_housing_steps'][0]
    alt = opposite_type_step(c, step)
    assert alt['type'] == 'rent'
    assert alt['start_year'] == step['start_year']
    assert alt['end_year'] == step['end_year']
    assert alt['state'] == step['state']
    assert alt['city_type'] == step['city_type']
    assert alt['population_size'] == step['population_size']
    # A rent step carries no purchase-side dollar fields.
    assert alt['purchase_price'] == 0.0
    assert alt['maintenance_annual'] == 0.0
    assert alt['real_estate_tax_pct'] == 0.0
    assert alt['hoa_pct'] == 0.0
    assert alt['mortgage_rate_pct'] == 0.0
    assert alt['down_payment_pct'] == 0.0
    assert alt['monthly_rent'] > 0.0


def test_opposite_type_step_flips_rent_to_purchase():
    c, _rows = _config_and_rows()
    step = dict(c['next_housing_steps'][0])
    step['type'] = 'rent'
    alt = opposite_type_step(c, step)
    assert alt['type'] == 'purchase'
    assert alt['purchase_price'] > 0.0
    assert alt['monthly_rent'] == 0.0


def test_opposite_type_step_does_not_mutate_input():
    c, _rows = _config_and_rows()
    step = c['next_housing_steps'][0]
    original_type = step['type']
    original_price = step.get('purchase_price')
    opposite_type_step(c, step)
    assert step['type'] == original_type
    assert step.get('purchase_price') == original_price


def test_compare_housing_candidates_returns_both_scored_candidates():
    c, rows = _config_and_rows()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = compare_housing_candidates(c, rows)
    assert result is not None
    configured = result['configured']
    alternative = result['alternative']

    # The alternative is correctly the opposite type at the same year/location.
    assert configured['type'] == 'purchase'
    assert alternative['type'] == 'rent'
    assert alternative['start_year'] == configured['start_year']
    assert alternative['state'] == configured['state']
    assert alternative['city_type'] == configured['city_type']
    assert alternative['population_size'] == configured['population_size']

    # Both candidates got a real Monte Carlo score (H9a: no skip_mc).
    for cand in (configured, alternative):
        assert isinstance(cand['mc_success_rate'], float)
        assert 0.0 <= cand['mc_success_rate'] <= 1.0
        assert isinstance(cand['feasibility_probability'], float)
        assert 0.0 <= cand['feasibility_probability'] <= 1.0
        assert isinstance(cand['feasibility_gate_met'], bool)
        assert isinstance(cand['lcv'], float)
        assert isinstance(cand['net_worth'], float)


def test_compare_housing_candidates_none_when_no_step1_configured():
    c, rows = _config_and_rows()
    c = dict(c)
    c['next_housing_steps'] = []
    assert compare_housing_candidates(c, rows) is None


def test_compare_housing_candidates_does_not_mutate_base_config():
    c, rows = _config_and_rows()
    import copy
    before = copy.deepcopy(c['next_housing_steps'])
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        compare_housing_candidates(c, rows)
    assert c['next_housing_steps'] == before
