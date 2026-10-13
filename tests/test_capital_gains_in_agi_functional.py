"""H1: the taxable gain of a home or rental sale is in AGI, NIIT MAGI and IRMAA MAGI
(documentation/reference/CAPITAL_GAINS_IN_AGI.md)."""
from __future__ import annotations

import pytest

from tests import rental_fixtures as rf


@pytest.fixture(scope="module")
def runs():
    return {
        "sale": rf.by_year(rf.project(rf.base_config({"home_sale_yr": 2029}))),
        "none": rf.by_year(rf.project(rf.base_config({"home_sale_yr": 0}))),
        "rental": rf.by_year(rf.project(rf.rental_config("sale_with_recapture"))),
    }


def test_home_sale_gain_is_in_reported_agi_and_irmaa_magi(runs):
    r = runs["sale"][2029]
    gain = r["home_sale_taxable"]
    assert gain > 0 and r["sale_cap_gain_in_agi"] == pytest.approx(gain)
    assert r["agi"] == pytest.approx(r["agi_ordinary"] + gain)
    assert r["irmaa_magi_current"] >= r["agi_ordinary"] + gain - 1e-6


def test_irmaa_bites_two_years_after_the_sale_only(runs):
    s, n = runs["sale"], runs["none"]
    assert s[2030]["irmaa_magi_used"] == pytest.approx(n[2030]["irmaa_magi_used"], rel=0.05)
    assert s[2031]["irmaa_magi_used"] > s[2029]["agi_ordinary"] + 0.9 * s[2029]["home_sale_taxable"]
    assert s[2031]["irmaa_tier"] > n[2031]["irmaa_tier"]


def test_niit_uses_magi_with_the_gain(runs):
    r = runs["sale"][2029]
    # NII exceeds the excess of MAGI over the 250k MFJ threshold, so NIIT = 3.8% of that excess.
    assert r["niit"] == pytest.approx(0.038 * (r["agi"] - 250000), rel=0.01)


def test_no_sale_year_has_no_gain_field(runs):
    assert "sale_cap_gain_in_agi" not in runs["none"][2029]


def test_rental_sale_ltcg_is_in_agi(runs):
    r = runs["rental"][2035]
    assert r["sale_cap_gain_in_agi"] > 0
    assert r["agi"] == pytest.approx(r["agi_ordinary"] + r["sale_cap_gain_in_agi"])
