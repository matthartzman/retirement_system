"""ARC-001: the housing helpers lifted out of the deterministic stage are pure and match the closed form."""
import pytest

from src.projection_stages.housing_next_steps import (
    mortgage_payment_and_balance,
    next_housing_for_year,
    next_housing_sale_inputs,
)


def test_mortgage_first_year_matches_closed_form():
    principal, rate, n = 300_000.0, 0.06, 360
    r = rate / 12
    pmt = principal * r / (1 - (1 + r) ** -n)
    expected_bal = principal * (1 + r) ** 12 - pmt * (((1 + r) ** 12 - 1) / r)
    annual, bal = mortgage_payment_and_balance(principal, rate, 0)
    assert annual == pytest.approx(pmt * 12)
    assert bal == pytest.approx(expected_bal, rel=1e-9)


def test_mortgage_paid_off_and_zero_principal():
    assert mortgage_payment_and_balance(100_000.0, 0.05, 30) == (0.0, 0.0)
    assert mortgage_payment_and_balance(0.0, 0.05, 3) == (0.0, 0.0)


def _infl(year, base):
    return 1.0


def test_purchase_step_down_payment_only_in_start_year():
    step = {"id": "h2", "type": "purchase", "start_year": 2030, "purchase_price": 500_000.0,
            "down_payment_pct": 0.2, "mortgage_rate_pct": 0.05}
    c = {"next_housing_steps": [step], "home_appr": 0.0}
    start = next_housing_for_year(c, _infl, 2030)
    later = next_housing_for_year(c, _infl, 2031)
    assert start["purchase_cash"] == pytest.approx(100_000.0)
    assert later["purchase_cash"] == 0.0
    assert start["active_labels"] == ["h2"] and next_housing_for_year(c, _infl, 2029)["active_labels"] == []
    assert start["home_value"] == pytest.approx(500_000.0)


def test_rent_step_and_sale_year_stop():
    rent = {"id": "r", "type": "rent", "start_year": 2030, "monthly_rent": 2_000.0}
    sold = {"id": "p", "type": "purchase", "start_year": 2030, "purchase_price": 400_000.0, "sale_year": 2035}
    c = {"next_housing_steps": [rent, sold], "home_appr": 0.0}
    assert next_housing_for_year(c, _infl, 2032)["rent"] == pytest.approx(24_000.0)
    assert "p" not in next_housing_for_year(c, _infl, 2035)["active_labels"]


def test_sale_inputs_use_prior_year_value_and_skip_rent():
    step = {"type": "purchase", "start_year": 2030, "purchase_price": 400_000.0, "down_payment_pct": 0.2,
            "mortgage_rate_pct": 0.05}
    c = {"home_appr": 0.03}
    value, bal = next_housing_sale_inputs(c, step, 2036)
    assert value == pytest.approx(400_000.0 * 1.03 ** 6)       # valuation year 2035
    assert 0 < bal < 320_000.0
    assert next_housing_sale_inputs(c, {"type": "rent", "start_year": 2030}, 2036) is None
