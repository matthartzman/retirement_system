"""WI-304 / FIN-009: IRMAA is assessed on MAGI (AGI + tax-exempt interest) from
the return filed two years earlier, against the IRMAA table for the filing
status on THAT return -- not on AGI, and not on the current year's filing
status (which, for a survivor, flips to Single the year after a death).
"""
from __future__ import annotations

import pytest

from src.core import irmaa_lookback_magi, irmaa_lookback_magi_and_filing
from src.planning_engines import project
from tests import synthetic_plans as sp


def test_lookback_reads_magi_and_filing_from_the_lookback_row():
    rows = [
        {"year": 2030, "agi": 300_000.0, "irmaa_magi_current": 320_000.0, "filing": "MFJ"},
        {"year": 2031, "agi": 150_000.0, "irmaa_magi_current": 150_000.0, "filing": "Single"},
    ]
    assert irmaa_lookback_magi_and_filing(rows, 90_000.0, "Single", 2) == (320_000.0, "MFJ")
    # Back-compat wrapper returns the MAGI only.
    assert irmaa_lookback_magi(rows, 90_000.0, 2) == 320_000.0


def test_lookback_falls_back_to_agi_for_rows_without_magi_field():
    rows = [{"agi": 250_000.0, "filing": "MFJ"}, {"agi": 1.0, "filing": "MFJ"}]
    assert irmaa_lookback_magi_and_filing(rows, 5.0, "MFJ", 2) == (250_000.0, "MFJ")


def test_pre_plan_years_use_historical_or_current_magi_and_current_filing():
    assert irmaa_lookback_magi_and_filing([], 100.0, "MFJ", 2, {2: 400_000}) == (400_000.0, "MFJ")
    assert irmaa_lookback_magi_and_filing([{}], 100.0, "Single", 2, {}) == (100.0, "Single")
    assert irmaa_lookback_magi_and_filing([], 100.0, "MFJ", 0) == (100.0, "MFJ")


@pytest.fixture(scope="module")
def muni_rows():
    cfg = sp.Scenario("muni", "muni", optimize_roth=False).build()
    # $20k of tax-exempt interest in plan year 1 on the $900k taxable trust.
    cfg["account_taxable_income_assumptions"] = {"Joint_Trust": {"tax_exempt_yield": 20_000.0 / 900_000.0}}
    return project(cfg)


def test_year_three_irmaa_magi_includes_muni_interest_from_year_one(muni_rows):
    year1, year3 = muni_rows[0], muni_rows[2]
    assert year1["irmaa_magi_current"] == pytest.approx(year1["agi"] + 20_000.0)
    assert year3["irmaa_magi_used"] == pytest.approx(year1["agi"] + 20_000.0)


def test_every_lookback_row_reads_magi_and_filing_two_years_back(muni_rows):
    for i in range(2, len(muni_rows)):
        assert muni_rows[i]["irmaa_magi_used"] == muni_rows[i - 2]["irmaa_magi_current"]
        assert muni_rows[i]["irmaa_filing_used"] == muni_rows[i - 2]["filing"]


@pytest.fixture(scope="module")
def survivor_rows():
    def _death_2030(cfg):
        cfg["h_death_yr"] = 2030
        cfg["first_death_yr"] = 2030
        for member in cfg.get("members", []):
            if member.get("role") == "member_1":
                member["death_yr"] = 2030

    cfg = sp.Scenario("survivor", "survivor", override=_death_2030, optimize_roth=False).build()
    return {r["year"]: r for r in project(cfg)}


def test_survivor_years_after_death_are_assessed_on_the_mfj_table(survivor_rows):
    assert survivor_rows[2030]["filing"] == "MFJ"
    for yr in (2031, 2032):
        assert survivor_rows[yr]["filing"] == "Single"
        assert survivor_rows[yr]["irmaa_filing_used"] == "MFJ", yr
    assert survivor_rows[2033]["irmaa_filing_used"] == "Single"
