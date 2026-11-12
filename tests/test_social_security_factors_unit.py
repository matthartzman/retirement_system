"""ARC-001: Social Security factor helpers lifted from the deterministic stage; SSA schedule hand values."""
import pytest

from src.projection_stages.index_paths import infl_ratio, ss_ratio
from src.projection_stages.social_security_factors import (
    fra_for_birth_year,
    ss_benefit_from_age70,
    ss_claim_factor,
    ss_first_claim_year_month_fraction,
    ss_spousal_excess_factor,
    ss_survivor_reduction_factor,
)


def test_fra_by_birth_year():
    assert fra_for_birth_year(1937) == 65.0
    assert fra_for_birth_year(1950) == 66.0
    assert fra_for_birth_year(1957) == pytest.approx(66.0 + 6 / 12)
    assert fra_for_birth_year(1960) == 67.0
    assert fra_for_birth_year(1960, 66.5) == 66.5


def test_claim_factor_reduction_and_delayed_credit():
    assert ss_claim_factor(62, 1960) == pytest.approx(0.70)    # 60 months early: 36*5/9 % + 24*5/12 %
    assert ss_claim_factor(67, 1960) == pytest.approx(1.0)
    assert ss_claim_factor(70, 1960) == pytest.approx(1.24)    # 36 months * 2/3 %
    assert ss_benefit_from_age70(2_480.0, 62, 1960) == pytest.approx(2_480.0 * 0.70 / 1.24)


def test_spousal_excess_factor_never_exceeds_one():
    assert ss_spousal_excess_factor(62, 1960) == pytest.approx(0.65)   # 36*25/36 % + 24*5/12 %
    assert ss_spousal_excess_factor(70, 1960) == 1.0


def test_survivor_reduction_linear_floor_and_cap():
    assert ss_survivor_reduction_factor(60, 1960) == pytest.approx(0.715)
    assert ss_survivor_reduction_factor(67, 1960) == 1.0
    assert ss_survivor_reduction_factor(63.5, 1960) == pytest.approx(1.0 - 0.285 * 3.5 / 7.0)


def test_first_claim_year_pays_in_arrears():
    assert ss_first_claim_year_month_fraction(2030, 2030, 8) == pytest.approx(4 / 12)   # Sep-Dec
    assert ss_first_claim_year_month_fraction(2030, 2030, 12) == 0.0
    assert ss_first_claim_year_month_fraction(2031, 2030, 8) == 1.0


def test_index_ratios_read_the_plan_paths():
    c = {"inf": 0.03, "ss_cola": 0.02, "inflation_index_by_year": {2030: 1.0, 2032: 1.1},
         "ss_cola_index_by_year": {2030: 1.0, 2032: 1.05}}
    assert infl_ratio(c, 2032, 2030) == pytest.approx(1.1)
    assert ss_ratio(c, 2032, 2030) == pytest.approx(1.05)
