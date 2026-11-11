"""FIN-007: the deceased spouse's unused exclusion (DSUE) is fixed at the
first death (IRC 2010(c)(4)); only the survivor's own exclusion keeps indexing.

Hand calculation: combined base $30M (two persons, $15M each), plan start 2026,
brk_inf 2.5%, first death 2030, second death 2050.
  survivor's own  = 15M * 1.025**24 = 27.1M
  frozen DSUE     = 15M * 1.025**4  = 16.5M
  total           = 43.7M   (the old behaviour indexed the whole 30M: 54.3M)
"""
import pytest

from src.core import household_first_death_year, indexed_federal_estate_exemption
from src.after_tax import estimate_terminal_estate_tax

BASE = 30_000_000.0


def test_dsue_frozen_at_first_death_year():
    got = indexed_federal_estate_exemption(BASE, 2026, 2050, 0.025, first_death_year=2030, members=2)
    expected = 15_000_000.0 * 1.025 ** 24 + 15_000_000.0 * 1.025 ** 4
    assert got == pytest.approx(expected)
    assert got == pytest.approx(43_688_000, rel=1e-3)   # 27.13M + 16.56M
    assert got < BASE * 1.025 ** 24


def test_no_first_death_year_is_legacy_behaviour():
    assert indexed_federal_estate_exemption(BASE, 2026, 2050, 0.025) == pytest.approx(BASE * 1.025 ** 24)


def test_single_member_is_not_split():
    got = indexed_federal_estate_exemption(15_000_000.0, 2026, 2050, 0.025, first_death_year=2030, members=1)
    assert got == pytest.approx(15_000_000.0 * 1.025 ** 24)


def test_first_death_at_or_after_target_is_unchanged():
    got = indexed_federal_estate_exemption(BASE, 2026, 2040, 0.025, first_death_year=2040, members=2)
    assert got == pytest.approx(BASE * 1.025 ** 14)


def test_household_first_death_year_uses_earliest_member_death():
    c = {"members": [{"death_yr": 2050}, {"death_yr": 2044}]}
    assert household_first_death_year(c) == 2044
    assert household_first_death_year({"members": [{"death_yr": 2050}]}) is None


def test_terminal_estate_tax_uses_frozen_dsue():
    c = {
        "fed_exempt": BASE, "plan_start": 2026, "plan_end": 2050, "brk_inf": 0.025,
        "model_state_est": False,
        "members": [{"death_yr": 2030}, {"death_yr": 2050}],
    }
    estate = 60_000_000.0
    tax = estimate_terminal_estate_tax(c, {"total_nw": estate, "year": 2050})
    exempt = 15_000_000.0 * 1.025 ** 24 + 15_000_000.0 * 1.025 ** 4
    assert tax == pytest.approx((estate - exempt) * 0.40, rel=1e-6)
