"""Social Security claim_age was replaced by a claim_date (MM/YYYY) input.

Two things this closes:

1. claim_age (a bare integer, no month) forced the deterministic engine to
   assume Social Security started on the person's own birthday-month every
   time, and to always pay a full 12 months in the claim year -- see
   deterministic_engine._ss_first_claim_year_month_fraction, added in the
   same change as this test. claim_date lets the user state the real month
   benefits start, and displays the resulting claim age instead of asking
   for it directly.

2. Backward compatibility: plans that predate claim_date (no claim_date row,
   only the legacy claim_age) must keep behaving exactly as before -- age
   70, claimed in the person's own birth month.

src/data_io.py's _ss_claim_from_date_or_age() and _month_year_parts() are
the two pure functions this fix added; both are unit-tested directly here
rather than through the full parse_client() CSV pipeline, matching this
codebase's existing test_core_tax_math.py-style approach for isolating
domain math from the CSV-loading machinery around it.
"""
from __future__ import annotations

from src.data_io import _month_year_parts, _ss_claim_from_date_or_age


class TestMonthYearParts:
    def test_parses_m_slash_yyyy(self):
        assert _month_year_parts("6/2029") == (2029, 6)

    def test_parses_mm_slash_yyyy(self):
        assert _month_year_parts("06/2029") == (2029, 6)

    def test_parses_iso_yyyy_dash_mm(self):
        assert _month_year_parts("2029-06") == (2029, 6)

    def test_rejects_a_full_date_with_a_day_component(self):
        # This is claim_date's job, not _date_parts' -- a 3-part M/D/YYYY
        # string is out of scope here (though _date_parts handles it fine).
        assert _month_year_parts("6/1/2029") is None

    def test_rejects_out_of_range_month(self):
        assert _month_year_parts("13/2029") is None

    def test_blank_is_none(self):
        assert _month_year_parts("") is None
        assert _month_year_parts(None) is None


class TestSsClaimFromDateOrAge:
    def test_claim_date_present_derives_age_and_month(self):
        data = {"Social Security": {"Member 1": {"claim_date": "6/2029"}}}
        age, year, month, age_precise = _ss_claim_from_date_or_age(data, "Member 1", dob_yr=1962, dob_month=8, legacy_default_age="70")
        assert (age, year, month) == (67, 2029, 6)
        # Claimed 2 months before the birth month -> a fraction below 67, not
        # exactly 67 (system review 2026-09-07 N2).
        assert age_precise == 67 + (6 - 8) / 12.0

    def test_no_claim_date_falls_back_to_legacy_claim_age_and_birth_month(self):
        data = {"Social Security": {"Member 1": {"claim_age": "68"}}}
        age, year, month, age_precise = _ss_claim_from_date_or_age(data, "Member 1", dob_yr=1962, dob_month=8, legacy_default_age="70")
        assert (age, year, month) == (68, 2030, 8)
        assert age_precise == 68.0

    def test_nothing_set_defaults_to_age_70_in_birth_month(self):
        data = {}
        age, year, month, age_precise = _ss_claim_from_date_or_age(data, "Member 1", dob_yr=1962, dob_month=8, legacy_default_age="70")
        assert (age, year, month) == (70, 2032, 8)
        assert age_precise == 70.0

    def test_claim_date_takes_priority_over_a_stale_claim_age_row(self):
        # A plan migrated to claim_date but with an old claim_age row still
        # sitting in the CSV must use the date, not the stale age.
        data = {"Social Security": {"Member 1": {"claim_date": "1/2028", "claim_age": "70"}}}
        age, year, month, age_precise = _ss_claim_from_date_or_age(data, "Member 1", dob_yr=1962, dob_month=8, legacy_default_age="70")
        assert (age, year, month) == (66, 2028, 1)
        assert age_precise == 66 + (1 - 8) / 12.0

    def test_claim_age_is_off_by_up_to_11_months_but_claim_age_precise_is_not(self):
        """System review 2026-09-07 N2: claim_year - dob_yr alone can
        misattribute up to 11 months of SSA reduction/delayed-credit --
        claim_age_precise is what closes that gap (consumed by
        deterministic_engine._ss_claim_factor, which already interpolates
        by month)."""
        # Born November 1960, claims March 2027: 66 years 4 months at claim,
        # not the whole-year-subtraction answer of 67.
        data = {"Social Security": {"Member 1": {"claim_date": "3/2027"}}}
        age, year, month, age_precise = _ss_claim_from_date_or_age(data, "Member 1", dob_yr=1960, dob_month=11, legacy_default_age="70")
        assert age == 67  # whole-year age: still used for the SSA benefit-table lookup
        assert abs(age_precise - (66 + 4 / 12.0)) < 1e-9
