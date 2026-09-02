"""Wave 3 item 3.7 (system review 2026-08-31, finding F11, Option 2): a
cumulative claiming breakeven presentation on Sheet 10, computed directly
from each person's own SSA-quoted monthly benefit table
(h_ss_benefit_table/w_ss_benefit_table) -- no projection engine run
required, unlike the sweep the rest of the sheet is built from.
"""
import pytest

from src.reporting.sheets_strategy import ss_breakeven_age, ss_breakeven_row


def test_matches_the_classic_62_vs_70_reference_figure():
    # A well-known industry rule of thumb: delaying from 62 to 70 typically
    # breaks even around age 80, for a benefit roughly 1.77x higher (the
    # actual SSA reduction/delayed-credit factor over 8 years). Real dollar
    # amounts from a live household fixture, not invented numbers.
    breakeven = ss_breakeven_age(2835.0, 62, 5022.0, 70)
    assert breakeven == pytest.approx(80.37, abs=0.05)


def test_head_start_dollars_equal_delta_dollars_at_the_computed_age():
    # Definitional check: at the breakeven age, cumulative dollars from
    # claiming early must equal cumulative dollars from claiming late, to
    # within a rounding tolerance -- not just "a plausible-looking number".
    m_early, age_early = 2000.0, 63
    m_late, age_late = 2600.0, 68
    breakeven = ss_breakeven_age(m_early, age_early, m_late, age_late)
    years_early_has_a_head_start = age_late - age_early
    early_total = m_early * 12 * (years_early_has_a_head_start + (breakeven - age_late))
    late_total = m_late * 12 * (breakeven - age_late)
    assert early_total == pytest.approx(late_total, rel=1e-9)


def test_no_breakeven_when_later_age_is_not_actually_higher():
    # A degenerate/misconfigured benefit table (e.g. two ages entered with
    # the same or a lower amount at the later age) must not report a false
    # crossing point.
    assert ss_breakeven_age(3000.0, 65, 3000.0, 70) is None
    assert ss_breakeven_age(3000.0, 65, 2900.0, 70) is None


def test_breakeven_row_formats_a_complete_comparison():
    row = ss_breakeven_row('Alex: claim at 62 vs. delay to 70', {62: 2835.0, 70: 5022.0}, 62, 70)
    label, age_early, m_early, age_late, m_late, breakeven_str = row
    assert label == 'Alex: claim at 62 vs. delay to 70'
    assert (age_early, m_early, age_late, m_late) == (62, 2835.0, 70, 5022.0)
    assert breakeven_str == '80.4'


def test_breakeven_row_reports_never_when_no_crossing_point_exists():
    row = ss_breakeven_row('Alex: degenerate', {65: 3000.0, 70: 2900.0}, 65, 70)
    assert row[-1] == 'Never (later age is not higher)'


def test_breakeven_row_returns_none_when_an_age_is_missing_from_the_table():
    # A benefit table only entered for some ages (real households often
    # skip filling in every age 62-70) must not crash or fabricate a value.
    assert ss_breakeven_row('Alex', {62: 2835.0}, 62, 70) is None
    assert ss_breakeven_row('Alex', {}, 62, 70) is None
