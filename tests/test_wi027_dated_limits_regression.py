"""WI-027 (FIN-005, FIN-006, FIN-009, FIN-011): statutory limits and reference
rows come from dated dataset rows, with hand-computed expected values.

Sources: IRS Rev. Proc. 2025-32 (AMT sec. 4.10, student-loan interest sec. 4.29,
estate exclusion sec. 2.14), IRS Notice 2025-67 (QLAC, QCD), NC DOR, Indiana DOR,
FTB 2025 schedules, NY Tax Law sec. 601. Reviewed 2026-10-20.
"""
from __future__ import annotations

import pytest

import src.data_io  # noqa: F401  (import order: avoids a parsing/data_io cycle)
from src import core
from src.parsing.estate_planning import parse_estate_planning
from src.tax_law import default_tax_law_dataset


# ── AMT (FIN-005) ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("year,amti,expected", [
    # 2025 MFJ: exemption 137,000 (phase-out starts 1,252,700 at 25%), break 239,100.
    (2025, 1_200_000, 0.26 * 239_100 + 0.28 * (1_200_000 - 137_000 - 239_100)),
    # Exemption fully phased out above 1,252,700 + 137,000 / 0.25.
    (2025, 2_000_000, 0.26 * 239_100 + 0.28 * (2_000_000 - 239_100)),
    # 2026 MFJ: exemption 140,200, phase-out starts 1,000,000 at 50%, break 244,500.
    (2026, 1_200_000, 0.26 * 244_500 + 0.28 * (1_200_000 - (140_200 - 0.5 * 200_000) - 244_500)),
    (2026, 2_000_000, 0.26 * 244_500 + 0.28 * (2_000_000 - 244_500)),
])
def test_amt_mfj_closed_form(year, amti, expected):
    assert core.tentative_minimum_tax(amti, 0.0, "MFJ", year, 0.0) == pytest.approx(expected, abs=0.01)


def test_amt_2026_phaseout_endpoints_match_rev_proc():
    """Fully phased out at 1,280,400 (MFJ), 680,200 (single), 640,200 (MFS)."""
    for filing, full, exemption, brk in (("MFJ", 1_280_400, 140_200, 244_500),
                                         ("Single", 680_200, 90_100, 244_500),
                                         ("MFS", 640_200, 70_100, 122_250)):
        at_full = core.tentative_minimum_tax(full, 0.0, filing, 2026, 0.0)
        no_exemption = 0.26 * brk + 0.28 * (full - brk)
        assert at_full == pytest.approx(no_exemption, abs=0.01), filing
        # Just below the end the exemption is positive: tax is lower.
        assert core.tentative_minimum_tax(full - 2_000, 0.0, filing, 2026, 0.0) < no_exemption - 0.28 * 1_000


def test_amt_2025_rate_break_is_the_2025_value():
    # 232,600 was the 2024 figure; the 2025 break is 239,100 (119,550 for MFS).
    ds = default_tax_law_dataset()
    assert ds.indexed_value("amt_rate_break", 2025, 0.0) == 239_100
    assert ds.indexed_value("amt_rate_break", 2026, 0.0) == 244_500


def test_amt_later_years_compound_the_latest_row():
    ds = default_tax_law_dataset()
    assert ds.indexed_value("amt_exemption", 2028, 0.03, filing_status="MFJ") == pytest.approx(140_200 * 1.03 ** 2)
    # Phase-out rate is not indexed.
    assert ds.lookup_or_earliest("amt_phaseout_rate", 2030, filing_status="MFJ").value == 0.50


# ── QLAC / QCD / student-loan interest (FIN-011) ───────────────────────────

def test_qlac_limit_unchanged_for_2026_and_indexed_after():
    assert core.qlac_premium_limit(2025, 0.03) == 210_000
    assert core.qlac_premium_limit(2026, 0.03) == 210_000   # Notice 2025-67: not mechanically inflated
    assert core.qlac_premium_limit(2027, 0.03) == pytest.approx(210_000 * 1.03)


def test_qcd_limit_2026():
    assert core.qcd_annual_limit(2025, 0.03) == 108_000
    assert core.qcd_annual_limit(2026, 0.03) == 111_000
    assert core.qcd_annual_limit(2027, 0.03) == pytest.approx(111_000 * 1.03)


def test_student_loan_phaseout_rows_2026():
    ds = default_tax_law_dataset()
    assert ds.indexed_value("student_loan_interest_phaseout_start", 2026, 0.0, filing_status="MFJ") == 175_000
    assert ds.indexed_value("student_loan_interest_phaseout_end", 2026, 0.0, filing_status="MFJ") == 205_000
    assert ds.indexed_value("student_loan_interest_phaseout_start", 2026, 0.0, filing_status="Single") == 85_000
    assert ds.indexed_value("student_loan_interest_phaseout_end", 2026, 0.0, filing_status="Single") == 100_000
    assert ds.indexed_value("student_loan_interest_phaseout_end", 2025, 0.0, filing_status="MFJ") == 195_000
    assert ds.latest_value("student_loan_interest_max_deduction").value == 2_500


# ── State rows (FIN-006) ───────────────────────────────────────────────────

def _state_tax(state, amount, year, filing="Single"):
    return core.state_income_tax(state, 0.0, 0.0, 0.0, amount, 0.0, 0.0, year,
                                 age_over_65=False, filing=filing, brk_inf=0.0)


def test_flat_state_rates_2026():
    assert _state_tax("North Carolina", 100_000, 2026) == pytest.approx(3_990.0)
    assert _state_tax("Indiana", 100_000, 2026) == pytest.approx(2_950.0)


def test_new_york_2026_schedule():
    # 8,500*3.9% + 3,200*4.4% + 2,200*5.15% + 66,750*5.4% + 19,350*5.9%
    expected = 331.5 + 140.8 + 113.3 + 3_604.5 + 1_141.65
    assert _state_tax("New York", 100_000, 2026) == pytest.approx(expected, abs=0.01)


def test_california_behavioral_health_surcharge_is_one_percent_over_one_million():
    year = core._STATE_INCOME_BRACKETS_VALUE_YEARS["California"]
    assert year == 2025   # provisional carry-forward of the FTB 2025 schedule
    brackets = core._STATE_INCOME_BRACKETS[("California", "MFJ")]
    for taxable in (900_000, 1_000_000, 1_500_000):
        expected = core._bracket_tax(taxable, brackets) + 0.01 * max(0.0, taxable - 1_000_000)
        got = _state_tax("California", taxable, year, filing="MFJ")
        assert got == pytest.approx(expected, abs=0.01)
    # The threshold is not doubled for MFJ.
    assert _state_tax("California", 1_000_001, year, filing="MFJ") - core._bracket_tax(1_000_001, brackets) == pytest.approx(0.01)


def test_state_tax_rows_carry_new_values():
    from src import taxes
    assert taxes.STATE_TAX_DEFAULTS["North Carolina"]["rate"] == 0.0399
    assert taxes.STATE_TAX_DEFAULTS["Indiana"]["rate"] == 0.0295
    assert taxes.STATE_TAX_DEFAULTS["New York"]["estate_exempt"] == 7_350_000


# ── Part D, wage base, estate (FIN-006, FIN-009) ───────────────────────────

def test_part_d_and_wage_base_rows():
    ds = default_tax_law_dataset()
    assert ds.lookup("part_d_base_premium_monthly", 2026).value == 38.99
    assert ds.lookup("part_d_base_premium_monthly", 2026).status == "verified"
    wb = ds.lookup("ss_wage_base", 2026)
    assert (wb.value, wb.status) == (184_500, "verified")


def test_federal_estate_default_derived_from_household():
    assert parse_estate_planning({}, household_size=1)["fed_exempt"] == 15_000_000
    assert parse_estate_planning({}, household_size=2)["fed_exempt"] == 30_000_000
    assert parse_estate_planning({})["fed_exempt"] == 30_000_000   # unknown size keeps the couple default
    explicit = {"Estate Planning": {"Federal": {"exemption_mfj": "30000000"}}}
    assert parse_estate_planning(explicit, household_size=1)["fed_exempt"] == 30_000_000
