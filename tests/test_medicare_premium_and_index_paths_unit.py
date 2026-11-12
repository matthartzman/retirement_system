"""ARC-001: Medicare-proration and index-path helpers lifted from the deterministic stage."""
import pytest

from src.projection_stages.index_paths import path_factor, path_ratio
from src.projection_stages.medicare_premiums import (
    medicare_month_fraction,
    sehi_deduction_source_amount,
    wellness_premium_for_age,
)


def test_medicare_fraction_prorates_only_the_turn_65_year():
    assert medicare_month_fraction(1960, 1, 2024) == 0.0       # age 64
    assert medicare_month_fraction(1960, 1, 2025) == 1.0       # age 65, born January
    assert medicare_month_fraction(1960, 7, 2025) == pytest.approx(6 / 12)   # eligible from July
    assert medicare_month_fraction(1960, 12, 2025) == pytest.approx(1 / 12)
    assert medicare_month_fraction(1960, 7, 2030) == 1.0
    assert medicare_month_fraction("bad", 7, 2030) == 0.0


def test_path_factor_uses_path_then_compounds():
    c = {"plan_start": 2026, "inflation_index_by_year": {2030: 1.2}}
    assert path_factor(c, "inflation_index_by_year", 0.03, 2030) == 1.2
    assert path_factor(c, "inflation_index_by_year", 0.03, 2031) == pytest.approx(1.03 ** 5)


def test_path_ratio_divides_path_values_and_floors_past_years():
    c = {"inflation_index_by_year": {2030: 1.2, 2035: 1.5}}
    assert path_ratio(c, "inflation_index_by_year", 0.03, 2035, 2030) == pytest.approx(1.25)
    assert path_ratio(c, "inflation_index_by_year", 0.03, 2029, 2030) == pytest.approx(1.0)


def _c():
    return {"plan_start": 2026, "inf": 0.0, "med_inf": 0.0, "bridge_premium": 12_000.0,
            "partb": 200.0, "partd": 50.0, "partg": 150.0}


def test_wellness_premium_pre_and_post_65():
    c = _c()
    assert wellness_premium_for_age(c, 60, 2026) == pytest.approx(12_000.0)
    assert wellness_premium_for_age(c, 70, 2026) == pytest.approx((200 + 50 + 150) * 12)
    # turn-65 year, born July: 6/12 bridge + 6/12 Medicare
    assert wellness_premium_for_age(c, 65, 2026, 7) == pytest.approx(6_000.0 + 0.5 * 400 * 12)


def test_sehi_source_override_derived_and_manual():
    c = _c()
    c["sehi_user_override"] = 5_000.0
    assert sehi_deduction_source_amount(c, 2026, 60, 60) == 5_000.0
    c = _c()
    c.update(sehi_derived_from_wellness=True)
    assert sehi_deduction_source_amount(c, 2026, 60, 70, h_alive=True, w_alive=False) == pytest.approx(12_000.0)
    c.update(sehi_derived_from_wellness=False, sehi=900.0)
    assert sehi_deduction_source_amount(c, 2026, 60, 70) == 900.0
