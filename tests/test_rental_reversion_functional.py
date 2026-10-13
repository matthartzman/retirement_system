"""H3: a converted home the household moves back into (RENTAL_TAX_RULES.md section 10)."""
from __future__ import annotations

from datetime import date

import pytest

from src.rental_tax import section_121_converted_home
from tests import rental_fixtures as rf

HOME = dict(rf.CONVERTED_HOME, purchase_year=2015, purchase_month=1, rental_end_year=2029)


def _runs(sale_year=2031, price=None, **extra):
    plan = {"home_sale_yr": sale_year, **({"home_sale_px": price} if price else {})}
    out = {}
    for name, row in (("back", dict(HOME, moves_back_in=True, reversion_month=7, **extra)),
                      ("rented", dict(HOME, **extra))):
        out[name] = rf.by_year(rf.project(rf.rental_config(rf.RentalCase([row], plan=plan))))
    return out


@pytest.mark.parametrize("gain, ratio, exp_1250, exp_ltcg, exp_excluded", [
    (400_000, 731 / 6025, 29_090, 45_001.69, 325_908.31),   # T1
    (900_000, 731 / 6025, 29_090, 370_910.00, 500_000.00),  # T2
    (400_000, 731 / 5448, 29_090, 49_767.84, 321_142.16),   # T3
])
def test_nonqualified_use_splits_the_gain_after_the_1250_part(gain, ratio, exp_1250, exp_ltcg, exp_excluded):
    r = section_121_converted_home(gain, 29_090, qualifies=True, exclusion=500_000, nonqualified_ratio=ratio)
    assert r.unrecaptured_1250_gain == pytest.approx(exp_1250)
    assert r.capital_gain == pytest.approx(exp_ltcg, abs=0.01)
    assert r.excluded == pytest.approx(exp_excluded, abs=0.01)


def test_no_ratio_is_todays_split_and_a_failed_test_excludes_nothing():
    assert section_121_converted_home(400_000, 29_090, qualifies=True, exclusion=500_000).excluded == pytest.approx(370_910)
    r = section_121_converted_home(400_000, 29_090, qualifies=False, exclusion=500_000, nonqualified_ratio=0.12)
    assert r.excluded == 0 and r.capital_gain == pytest.approx(370_910)


def test_move_back_stops_rent_and_depreciation_in_the_end_year():
    runs = _runs()
    back, rented = runs["back"], runs["rented"]
    assert back[2029]["converted_home_share"] == pytest.approx(6 / 12)  # rented Jan-Jun, back 1 Jul
    assert rented[2029]["converted_home_share"] == pytest.approx(1.0)
    assert back[2029]["rental_depreciation"] == pytest.approx(rented[2029]["rental_depreciation"] * 6.5 / 12, rel=0.02)
    assert back[2030].get("rental_gross_rent", 0) == 0
    assert back[2028]["rental_gross_rent"] == pytest.approx(rented[2028]["rental_gross_rent"])


def test_move_back_passes_the_two_of_five_test_that_a_plain_rental_fails():
    runs = _runs()
    back, rented = runs["back"][2031], runs["rented"][2031]
    assert rented["home_sale_unrecaptured_1250_gain"] > 0 and rented["home_sale_sec121_excluded"] == 0
    assert back["home_sale_sec121_excluded"] > 0
    assert back["home_sale_unrecaptured_1250_gain"] < rented["home_sale_unrecaptured_1250_gain"]  # depreciation stops at the move-back
    assert back["home_sale_sec121_two_of_five"] and not rented["home_sale_sec121_two_of_five"]


def test_rental_months_are_nonqualified_use_when_the_exclusion_does_not_cap():
    back = _runs(price=1_300_000)["back"][2031]
    rest = back["home_sale_gain"] - back["home_sale_accumulated_depreciation"]
    ratio = 731 / (date(2031, 7, 1) - date(2015, 1, 1)).days
    assert back["home_sale_taxable"] == pytest.approx(rest * ratio, rel=1e-6)
    assert back["home_sale_sec121_excluded"] == pytest.approx(rest * (1 - ratio), rel=1e-6)


def test_off_by_default_and_validation():
    from src.parsing.rental_properties import RentalPropertyInputError, parse_rental_properties
    runs = _runs()
    assert runs["rented"][2031]["home_sale_sec121_excluded"] == 0
    c = rf.base_config()
    with pytest.raises(RentalPropertyInputError, match="needs rental_end_year"):
        parse_rental_properties(c, [dict(rf.CONVERTED_HOME, moves_back_in=True)])
    with pytest.raises(RentalPropertyInputError, match="after the conversion"):
        parse_rental_properties(c, [dict(rf.CONVERTED_HOME, moves_back_in=True, rental_end_year=2027, reversion_month=7)])
    with pytest.raises(RentalPropertyInputError, match="only to kind"):
        parse_rental_properties(c, [dict(rf.PROFITABLE, moves_back_in=True)])
    assert date(2031, 7, 1) > date(2029, 7, 1)
