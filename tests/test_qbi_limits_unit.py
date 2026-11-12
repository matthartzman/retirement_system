"""W3-02 / FIN-001: closed-form cases for the Section 199A limits (MFJ 2026: threshold 403,500, phase-in 150,000)."""
from __future__ import annotations

import pytest

from src.qbi import qbi_deduction
from src.tax_law import default_tax_law_dataset

T, W = 403_500.0, 150_000.0


def ded(qbi, ti, wages=0.0, ubia=0.0, sstb=False, ncg=0.0, mind=400.0, mininc=1_000.0):
    return qbi_deduction(qbi, wages, ubia, sstb, ti, ncg, T, W, mind, mininc)


def test_below_threshold_is_flat_20_percent():
    assert ded(100_000, 300_000) == pytest.approx(20_000)


def test_sstb_inside_phase_in_is_scaled_by_applicable_percentage():
    # ti 478,500 -> 50% phased in; QBI 100k scales to 50k, tentative 10k, no wages so the
    # phase-in reduction removes half of it: 10,000 - 0.5 * 10,000 = 5,000.
    assert ded(100_000, 478_500, sstb=True) == pytest.approx(5_000)


def test_sstb_above_the_range_is_zero():
    assert ded(100_000, 560_000, sstb=True) == 0.0


def test_non_sstb_inside_phase_in_without_wages_reduces_by_phase_in_share():
    assert ded(100_000, 478_500) == pytest.approx(10_000)  # 20,000 - 0.5 * (20,000 - 0)


def test_wage_limit_binding_above_the_range():
    assert ded(300_000, 600_000, wages=100_000) == pytest.approx(50_000)   # 50% of wages < 60,000


def test_wages_plus_ubia_alternative_limit():
    # 25% of 40,000 + 2.5% of 2,000,000 = 60,000 > 50% of 40,000 = 20,000
    assert ded(400_000, 600_000, wages=40_000, ubia=2_000_000) == pytest.approx(60_000)


def test_taxable_income_cap_binding():
    assert ded(100_000, 50_000) == pytest.approx(10_000)               # 20% of taxable income


def test_overall_cap_nets_qualified_dividends_and_gains():
    assert ded(100_000, 50_000, ncg=20_000) == pytest.approx(6_000)    # 20% x (50,000 - 20,000)


def test_minimum_deduction_where_twenty_percent_is_below_400():
    assert ded(1_500, 100_000) == pytest.approx(400)
    assert ded(900, 100_000) == pytest.approx(180)                      # under the $1,000 floor test
    assert ded(1_500, 100_000, mind=0.0) == pytest.approx(300)          # before 2026


def test_dated_rows_match_rev_proc_2025_32():
    ds = default_tax_law_dataset()
    assert ds.indexed_value("qbi_threshold", 2026, 0.0, filing_status="MFJ") == 403_500
    assert ds.indexed_value("qbi_threshold", 2026, 0.0, filing_status="Single") == 201_750
    assert ds.indexed_value("qbi_phasein_width", 2026, 0.0, filing_status="MFJ") == 150_000
    assert ds.indexed_value("qbi_phasein_width", 2025, 0.0, filing_status="Single") == 50_000
    assert ds.indexed_value("qbi_min_deduction", 2026, 0.0, filing_status="Single") == 400
