"""WP12.3: the Rental Properties parse boundary (``src.data_io.parse_rental_properties``).

Source rows -> ``c['rental_properties']``: defaults (land share 20%, vacancy 0, month 7),
coercion of mixed source forms, unknown keys ignored, clear errors naming the property
and field, and the optional household ``mfs_lived_apart`` input the engine reads.
"""
from __future__ import annotations

import pytest

import src.module_catalog as mc
from src.data_io import RentalPropertyInputError, parse_rental_properties
from src.projection_stages import rental_property as rp
from tests import rental_fixtures as rf

_C = {"plan_start": 2026, "inf": 0.025, "home_appr": 0.03, "home_sell_cost_pct": 0.06,
      "home_val": 1_000_000.0, "home_basis": 600_000.0}


def _parse(rows, **kw):
    c = dict(_C)
    return c, parse_rental_properties(c, rows, **kw)


def test_defaults_coercion_and_unknown_keys():
    c, props = _parse([rf.LOSS_MAKING, rf.PROFITABLE, rf.CONVERTED_HOME])
    assert c["rental_properties"] is props
    loss, prof, conv = props
    assert loss["kind"] == "standalone" and loss["purchase_price"] == 500000.0
    assert loss["management_pct"] == pytest.approx(0.08) and loss["active_participation"] is True
    assert "notes" not in loss
    assert (loss["land_share"], loss["vacancy_rate"], loss["sale_month"]) == (0.20, 0.0, 7)
    assert prof["land_share"] == pytest.approx(0.20) and prof["purchase_month"] == 6
    assert prof["improvements"] == [{"year": 2028, "amount": 27500.0, "month": 7}]
    assert conv["kind"] == "converted_home" and conv["conversion_month"] == 7 and conv["land_share"] == 0.25
    assert "mfs_lived_apart" not in c


def test_every_fixture_case_parses_and_reaches_the_engine():
    for name, case in rf.CASES.items():
        c, props = _parse(case.rows, mfs_lived_apart=case.mfs_lived_apart)
        specs = [rp.parse_rental_spec(p, i, c) for i, p in enumerate(props)]
        assert all(s is not None for s in specs), name


def test_overrides_from_rows_or_mapping():
    row = dict(rf.PROFITABLE, overrides=[{"year": "2030", "gross_rent": "12,000"}])
    _c, (p,) = _parse([row])
    assert p["overrides"] == {2030: {"gross_rent": 12000.0}}
    _c, (p,) = _parse([dict(rf.PROFITABLE, overrides={2031: {"operating_expenses": 500}})])
    assert p["overrides"] == {2031: {"operating_expenses": 500.0}}


def test_empty_input_gives_no_properties():
    for rows in (None, "", []):
        c, props = _parse(rows)
        assert props == [] and c["rental_properties"] == []


@pytest.mark.parametrize("rows,message", [
    ("not rows", "must be a list"),
    (["text"], "Rental property 1: must be a row"),
    ([{"name": "A"}], "purchase_price is required"),
    ([dict(rf.PROFITABLE, land_share="120%")], "'Duplex'): land_share must be between 0 and 1"),
    ([dict(rf.PROFITABLE, purchase_month=13)], "purchase_month must be a whole number from 1 to 12"),
    ([dict(rf.PROFITABLE, monthly_rent="lots")], "monthly_rent must be a number, got 'lots'"),
    ([dict(rf.PROFITABLE, kind="Timeshare")], "kind must be 'Standalone' or 'Converted home'"),
    ([dict(rf.PROFITABLE, sale_year=2010)], "sale_year is before purchase_year"),
    ([dict(rf.PROFITABLE, active_participation="maybe")], "active_participation must be yes or no"),
    ([dict(rf.PROFITABLE, improvements=[{"year": 2030}])], "improvement 1: year and amount are required"),
    ([dict(rf.PROFITABLE, loan_rate=None, loan_monthly_payment=None)], "needs loan_rate or loan_monthly_payment"),
    ([rf.PROFITABLE, dict(rf.PROFITABLE, name="duplex")], "both named 'duplex'"),
    ([rf.CONVERTED_HOME, dict(rf.CONVERTED_HOME, name="Again")], "Only one property can be the converted home"),
    ([dict(rf.CONVERTED_HOME, conversion_year=None)], "conversion_year is required"),
    ([dict(rf.CONVERTED_HOME, loan_balance=1000, sale_year=2030)], "takes loan_balance, sale_year from the plan's home"),
    ([dict(rf.PROFITABLE, conversion_year=2030)], "conversion_year applies only to kind 'Converted home'"),
])
def test_clear_errors(rows, message):
    with pytest.raises(RentalPropertyInputError) as err:
        _parse(rows)
    assert message in str(err.value)


def test_converted_home_needs_a_home():
    with pytest.raises(RentalPropertyInputError, match="no home to convert"):
        parse_rental_properties(dict(_C, home_val=0.0), [rf.CONVERTED_HOME])


def test_mfs_lived_apart_household_input_reaches_the_engine():
    c, _ = _parse([rf.LOSS_MAKING], mfs_lived_apart="yes")
    assert c["mfs_lived_apart"] is True
    mc.set_feature(c, "rental_property_income", True)
    assert rp.rental_book_for(c).mfs_lived_apart_all_year is True
    c2, _ = _parse([rf.LOSS_MAKING])
    mc.set_feature(c2, "rental_property_income", True)
    assert rp.rental_book_for(c2).mfs_lived_apart_all_year is False  # owner decision: unknown = together
    with pytest.raises(RentalPropertyInputError, match="mfs_lived_apart must be yes or no"):
        _parse([], mfs_lived_apart="sometimes")
