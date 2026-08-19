"""The consume-by deadline is the HSA optimizer's risk dial.

Resolving it too early is the expensive, unbounded failure (the tax-free bucket
is gone in the survivor years); resolving it too late is bounded at
residual x heir rate. Every fallback here therefore leans late, never early.
"""
import unittest
import warnings

import pytest

from src.hsa_schedule import resolve_consume_by_year

# A two-member household the mortality table can actually build a
# second-death distribution for, with a horizon wide enough that clamping
# does not hide the distribution's shape.
COUPLE = {
    "plan_start": 2026,
    "plan_end": 2100,
    "members": [
        {"role": "member_1", "dob_yr": 1960, "mortality_age": 92},
        {"role": "member_2", "dob_yr": 1961, "mortality_age": 95},
    ],
}


@pytest.mark.unit
class ConsumeByTests(unittest.TestCase):
    def test_explicit_year_is_honored(self):
        self.assertEqual(resolve_consume_by_year({"hsa_consume_by": "2044"}, []), 2044)

    def test_percentile_form_resolves_within_the_plan_horizon(self):
        c = {"hsa_consume_by": "second_death_p90", "plan_start": 2026, "plan_end": 2056}
        yr = resolve_consume_by_year(c, [])
        self.assertGreaterEqual(yr, 2026)
        self.assertLessEqual(yr, 2056)

    def test_a_higher_percentile_never_resolves_earlier(self):
        c = {"plan_start": 2026, "plan_end": 2056}
        p50 = resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p50"), [])
        p90 = resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p90"), [])
        self.assertGreaterEqual(p90, p50)

    def test_unparseable_value_falls_back_to_the_conservative_default(self):
        c = {"hsa_consume_by": "nonsense", "plan_start": 2026, "plan_end": 2056}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual(resolve_consume_by_year(c, []),
                             resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p90"), []))


@pytest.mark.unit
class ConsumeByMortalityTests(unittest.TestCase):
    """The percentile branch has to come off the engine's own mortality table.
    Without members every case collapses to plan_end, which would let a stub
    that ignores the percentile entirely pass the brief's cases."""

    def test_percentile_uses_the_mortality_table_not_the_horizon(self):
        yr = resolve_consume_by_year(dict(COUPLE, hsa_consume_by="second_death_p50"), [])
        self.assertGreater(yr, COUPLE["plan_start"])
        self.assertLess(yr, COUPLE["plan_end"])

    def test_higher_percentile_is_strictly_later_when_the_horizon_does_not_clamp(self):
        p50 = resolve_consume_by_year(dict(COUPLE, hsa_consume_by="second_death_p50"), [])
        p90 = resolve_consume_by_year(dict(COUPLE, hsa_consume_by="second_death_p90"), [])
        self.assertGreater(p90, p50)

    def test_percentile_is_monotone_across_the_whole_range(self):
        years = [resolve_consume_by_year(dict(COUPLE, hsa_consume_by=f"second_death_p{n}"), [])
                 for n in range(5, 100, 5)]
        self.assertEqual(years, sorted(years))
        # A constant sequence is trivially sorted, so pin that the dial moves.
        self.assertGreater(len(set(years)), 1)

    def test_a_resolved_year_past_the_horizon_is_clamped_to_plan_end(self):
        c = dict(COUPLE, plan_end=2040, hsa_consume_by="second_death_p90")
        self.assertEqual(resolve_consume_by_year(c, []), 2040)

    def test_no_distribution_available_falls_back_to_plan_end_not_earlier(self):
        c = {"hsa_consume_by": "second_death_p50", "plan_start": 2026, "plan_end": 2056}
        self.assertEqual(resolve_consume_by_year(c, []), 2056)


@pytest.mark.unit
class ConsumeByMalformedTests(unittest.TestCase):
    def test_malformed_value_is_loud(self):
        c = dict(COUPLE, hsa_consume_by="second_death_p90ish")
        with self.assertWarns(UserWarning):
            resolve_consume_by_year(c, [])

    def test_missing_key_defaults_to_p90_silently(self):
        c = dict(COUPLE)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(resolve_consume_by_year(c, []),
                             resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p90"), []))

    def test_an_out_of_range_percentile_is_malformed_not_extrapolated(self):
        c = dict(COUPLE, hsa_consume_by="second_death_p100")
        with self.assertWarns(UserWarning):
            yr = resolve_consume_by_year(c, [])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual(yr, resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p90"), []))


@pytest.mark.unit
class ConsumeByHorizonFromRowsTests(unittest.TestCase):
    def test_rows_supply_the_horizon_when_the_config_does_not(self):
        rows = [{"year": y} for y in range(2026, 2041)]
        c = {"hsa_consume_by": "2099"}
        self.assertEqual(resolve_consume_by_year(c, rows), 2040)

    def test_explicit_year_before_the_horizon_is_clamped_up_to_plan_start(self):
        c = {"hsa_consume_by": "2010", "plan_start": 2026, "plan_end": 2056}
        self.assertEqual(resolve_consume_by_year(c, []), 2026)


@pytest.mark.unit
class ScoringTests(unittest.TestCase):
    def test_a_higher_marginal_rate_year_scores_higher(self):
        from src.hsa_schedule import score_year
        lo = {"year": 2030, "effective_marginal_rate": 0.12, "irmaa_tier": 0}
        hi = {"year": 2030, "effective_marginal_rate": 0.32, "irmaa_tier": 0}
        self.assertGreater(score_year({}, hi, 10_000.0), score_year({}, lo, 10_000.0))

    def test_a_year_that_avoids_an_irmaa_crossing_scores_higher(self):
        from src.hsa_schedule import score_year
        flat = {"year": 2030, "effective_marginal_rate": 0.22, "irmaa_tier": 1,
                "irmaa_headroom": 50_000.0}
        cliff = {"year": 2030, "effective_marginal_rate": 0.22, "irmaa_tier": 1,
                 "irmaa_headroom": 500.0}
        self.assertGreater(score_year({}, cliff, 10_000.0), score_year({}, flat, 10_000.0))

    def test_survivor_years_score_higher_than_joint_years_at_equal_income(self):
        """Section 1.3 of the spec: the survivor files Single at compressed
        brackets, so the displaced dollar is dearer."""
        from src.hsa_schedule import score_year
        joint = {"year": 2040, "filing": "MFJ", "effective_marginal_rate": 0.22, "irmaa_tier": 0}
        single = {"year": 2040, "filing": "Single", "effective_marginal_rate": 0.32, "irmaa_tier": 0}
        self.assertGreater(score_year({}, single, 10_000.0), score_year({}, joint, 10_000.0))

    def test_an_hoh_survivor_also_gets_the_compressed_bracket_premium(self):
        """`survivor_filing_status` is `Single | HOH` (reference_data/schema.csv),
        and the engine writes that value straight into `row['filing']`. HOH
        brackets are compressed relative to MFJ for the same reason Single's
        are, so an HOH survivor must out-score an MFJ year at the same rate."""
        from src.hsa_schedule import score_year
        joint = {"year": 2040, "filing": "MFJ", "effective_marginal_rate": 0.22, "irmaa_tier": 0}
        hoh = {"year": 2040, "filing": "HOH", "effective_marginal_rate": 0.22, "irmaa_tier": 0}
        self.assertGreater(score_year({}, hoh, 10_000.0), score_year({}, joint, 10_000.0))

    def test_the_single_table_is_read_for_a_single_filer(self):
        """The IRMAA table's keys are mixed case ('Single'), so an upper-cased
        lookup misses and silently substitutes another filing status's rows."""
        from src.hsa_schedule import _irmaa_tiers_for
        from src.taxes import IRMAA_TIERS_BASE_YEAR
        for raw, key in (("Single", "Single"), ("single", "Single"), ("MFS", "MFS"),
                         ("HOH", "HOH"), ("MFJ", "MFJ")):
            self.assertIs(_irmaa_tiers_for(raw.upper()), IRMAA_TIERS_BASE_YEAR[key])

    def test_a_malformed_headroom_is_read_as_no_signal_not_as_zero_headroom(self):
        """An unparseable headroom must degrade exactly the way `None` does --
        contributing nothing -- rather than reading as 'zero room left, about
        to cross' and paying out the whole surcharge step."""
        from src.hsa_schedule import score_year
        base = {"year": 2030, "effective_marginal_rate": 0.22, "irmaa_tier": 1}
        absent = score_year({}, dict(base), 10_000.0)
        for bad in ("abc", "", -5_000.0, float("nan")):
            with self.subTest(headroom=bad):
                row = dict(base, irmaa_headroom=bad)
                self.assertEqual(score_year({}, row, 10_000.0), absent)


if __name__ == "__main__":
    unittest.main()
