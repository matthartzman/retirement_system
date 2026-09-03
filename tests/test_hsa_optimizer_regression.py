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


# --- Task 10 schedule-search fixtures ---------------------------------------
#
# Both households carry an explicit `hsa_consume_by` year. The percentile path
# is already pinned by ConsumeByMortalityTests below; resolving it again here
# would only make these fixtures hostage to the mortality table's exact shape
# (Task 7 found the p90 deadline collapses to `plan_end` on most stock
# horizons, which would leave the search no interior years to discriminate
# between). The mortality table is still load-bearing in these fixtures -- it
# is what the residual-risk term reads -- just not for the deadline.

def _rows(years, filing_of, rate_of, hsa_nw):
    out = []
    for i, y in enumerate(years):
        row = {"year": y, "filing": filing_of(y),
               "effective_marginal_rate": rate_of(y), "irmaa_tier": 0}
        if i == 0:
            row["hsa_nw"] = hsa_nw
        out.append(row)
    return out


# A single-filing-status household: every year is an MFJ year at the same rate,
# so nothing but the deadline constraint itself is under test.
FEASIBLE_ROWS = _rows(range(2026, 2041), lambda y: "MFJ", lambda y: 0.22, 500_000.0)

FEASIBLE_C = {
    "plan_start": 2026,
    "plan_end": 2040,
    "hsa_consume_by": "2040",
    "ret": 0.05,
    "brk_inf": 0.0,
    "members": [
        {"role": "member_1", "dob_yr": 1958, "mortality_age": 92},
        {"role": "member_2", "dob_yr": 1960, "mortality_age": 95},
    ],
}

# The same household with a floor the optimizer may not draw through. That
# floor is the only mechanism at this signature that can make the consume-by
# constraint genuinely unsatisfiable, so it is how the infeasible state is
# reached without ever moving the deadline.
OVERSIZED_C = dict(FEASIBLE_C, hsa_min_ending_balance=250_000.0)

# The survivor household: MFJ through 2030, then Single (first death) through
# the 2040 deadline.
#
# Three things about this fixture are deliberate and load-bearing:
#
# 1. `hsa_beneficiary_type` is 'non_spouse'. With the schema default ('spouse')
#    `hsa_terminal_tax` returns exactly 0.0 for every balance, the
#    residual-mortality-risk term is structurally zero, and
#    `test_optimizer_does_not_back_load_into_the_final_years` becomes a guard
#    that cannot fail -- it would then be passing or failing on discounting
#    alone, with zero contribution from the term it exists to test.
# 2. `ret` (12%) is above the 6.5% default tax discount rate, so deferral is
#    genuinely attractive here: a dollar left in the HSA compounds tax-free
#    faster than the objective discounts it. That makes this a HARD case for
#    anti-back-loading rather than one the discount factor wins by itself.
#    Verified: with the terminal-tax term neutralized, the search puts 58% of
#    the balance in the final three years; with it live, 38%.
# 3. The members are old enough (90 and 88 at plan start) that the second death
#    has real probability mass inside the window -- the residual term is an
#    expectation over that mass, and a young couple would make it negligible
#    for reasons that have nothing to do with whether the term is correct.
SURVIVOR_ROWS = _rows(range(2026, 2041),
                      lambda y: "MFJ" if y <= 2030 else "Single",
                      lambda y: 0.22 if y <= 2030 else 0.32,
                      600_000.0)

SURVIVOR_C = {
    "plan_start": 2026,
    "plan_end": 2040,
    "hsa_consume_by": "2040",
    "ret": 0.12,
    "brk_inf": 0.0,
    "hsa_beneficiary_type": "non_spouse",
    "roth_heir_filing_status": "Single",
    "members": [
        {"role": "member_1", "dob_yr": 1936, "mortality_age": 92},
        {"role": "member_2", "dob_yr": 1938, "mortality_age": 95},
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


class SurplusWaterfallTests(unittest.TestCase):
    def test_spending_need_is_funded_before_anything_else(self):
        from src.hsa_schedule import allocate_surplus
        out = allocate_surplus({}, {"spending_need": 30_000.0, "conversion_tax_capacity": 20_000.0},
                               50_000.0)
        self.assertAlmostEqual(out["to_spending"], 30_000.0, places=6)
        self.assertAlmostEqual(out["to_conversion_tax"], 20_000.0, places=6)
        self.assertAlmostEqual(out["to_taxable"], 0.0, places=6)

    def test_leftover_after_conversion_tax_spills_to_taxable(self):
        from src.hsa_schedule import allocate_surplus
        out = allocate_surplus({}, {"spending_need": 10_000.0, "conversion_tax_capacity": 5_000.0},
                               50_000.0)
        self.assertAlmostEqual(out["to_taxable"], 35_000.0, places=6)

    def test_priorities_saturate_correctly_when_surplus_is_short(self):
        """A surplus too small to clear even the first priority must all go
        to spending, and nothing should go negative."""
        from src.hsa_schedule import allocate_surplus
        out = allocate_surplus({}, {"spending_need": 30_000.0, "conversion_tax_capacity": 20_000.0},
                               10_000.0)
        self.assertAlmostEqual(out["to_spending"], 10_000.0, places=6)
        self.assertAlmostEqual(out["to_conversion_tax"], 0.0, places=6)
        self.assertAlmostEqual(out["to_taxable"], 0.0, places=6)

    def test_surplus_never_increases_the_conversion_itself(self):
        """The guardrail. Surplus changes how conversion tax is FUNDED, never how
        much conversion is worth doing. Without this pin, 'free' tax money
        quietly inflates the recommendation.

        The plan's own brief names a placeholder function, `choose_conversion_amount`,
        that does not exist. `plan_roth_conversion` is the real conversion-sizing
        function (found via `grep -rn "def .*conversion" src/planning_engines.py`),
        and its signature takes ~30 keyword args pulled from live engine state.
        `tests/test_roth_ltcg_niit_guardrails.py` already exercises it directly
        with a minimal fixture -- following that idiom here rather than inventing
        a new calling convention.

        `hsa_surplus_available` is not referenced anywhere in `planning_engines.py`
        today (grepped), so this test is a forward-looking guard: it passes now
        because nothing reads the key, and it exists to catch the day some later
        change wires HSA surplus into conversion sizing without going through the
        waterfall above -- i.e. lets "free" surplus dollars silently inflate how
        much conversion the engine decides is worth doing.
        """
        from src.core import (
            inflate_brackets, standard_deduction, compute_fed_tax,
            FEDERAL_BRACKETS_BASE_YEAR, FEDERAL_BRACKETS_MFJ,
        )
        from src.planning_engines import plan_roth_conversion

        def _amount(hsa_surplus_available):
            c = {
                'plan_start': 2026,
                'roth_policy': 'fill_to_bracket',
                'roth_target_rate': 0.35,
                'roth_headroom_usage_pct': 1.0,
                'roth_max_annual_conversion_pct_of_traditional_ira': 1.0,
                'roth_irmaa_cap': False,
                'roth_ltcg_headroom_usage_pct': 1.0,
                'roth_niit_headroom_usage_pct': 1.0,
                'brk_inf': 0.0,
                'account_registry': [{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': 'IRA'}],
                'hsa_surplus_available': hsa_surplus_available,
            }
            bal = {'H_IRA': 2_000_000.0}
            plan = plan_roth_conversion(
                c=c, bal=bal, year=2026, filing='MFJ',
                earned_base=0.0, half_se_ded=0.0, sehi_ded=0.0,
                h_ss=0.0, w_ss=0.0, rmd_total=0.0, pension=0.0,
                wife_single_ann=0.0, wife_joint_ann=0.0, h_single_ann=0.0, h_joint_ann=0.0,
                note_int_yr=0.0, note_princ_yr=0.0, total_spend_need=0.0, spend=0.0,
                portfolio_ordinary=0.0, portfolio_qualified=0.0, portfolio_tax_exempt=0.0,
                aca_bridge_people=0, h_age=60.0, w_age=58.0,
                brackets_by_status=FEDERAL_BRACKETS_BASE_YEAR, brackets_mfj=FEDERAL_BRACKETS_MFJ,
                inflate_brackets_fn=inflate_brackets, standard_deduction_fn=standard_deduction,
                compute_fed_tax_fn=compute_fed_tax, state_tax_estimate_fn=lambda agi, yr: 0.0,
            )
            return plan.amount

        base = _amount(0.0)
        with_surplus = _amount(100_000.0)
        self.assertGreater(base, 0.0, "the fixture must produce a real conversion to be a meaningful pin")
        self.assertAlmostEqual(with_surplus, base, places=6)


class JointScoringTests(unittest.TestCase):
    def test_headroom_is_not_double_counted(self):
        """An HSA draw lowers AGI and frees headroom; a conversion consumes it.
        Scored separately, both claim the same dollars."""
        from src.hsa_schedule import joint_headroom_used
        used = joint_headroom_used({}, {"bracket_room": 40_000.0},
                                   hsa_draw=25_000.0, conversion=40_000.0)
        self.assertLessEqual(used, 40_000.0 + 25_000.0)
        self.assertGreater(used, 40_000.0)

    def test_zero_conversion_uses_none_of_the_freed_room(self):
        """With no conversion at all, nothing is claiming any bracket room --
        the draw's freed headroom is real but unused, not "used"."""
        from src.hsa_schedule import joint_headroom_used
        used = joint_headroom_used({}, {"bracket_room": 40_000.0},
                                   hsa_draw=25_000.0, conversion=0.0)
        self.assertAlmostEqual(used, 0.0, places=6)

    def test_zero_draw_reduces_to_the_conversions_own_claim(self):
        """With no HSA draw, there is nothing to double-count against --
        headroom used collapses to whatever the conversion alone claims."""
        from src.hsa_schedule import joint_headroom_used
        used = joint_headroom_used({}, {"bracket_room": 40_000.0},
                                   hsa_draw=0.0, conversion=25_000.0)
        self.assertAlmostEqual(used, 25_000.0, places=6)

    def test_a_small_conversion_relative_to_room_claims_little_of_the_freed_room(self):
        """Monotonicity check on the interaction term itself, not just the
        overall bounds: a conversion using a SMALL fraction of bracket_room
        should claim a correspondingly SMALL fraction of hsa_draw, not the
        same fraction a much larger conversion would."""
        from src.hsa_schedule import joint_headroom_used
        small = joint_headroom_used({}, {"bracket_room": 40_000.0}, hsa_draw=25_000.0, conversion=4_000.0)
        large = joint_headroom_used({}, {"bracket_room": 40_000.0}, hsa_draw=25_000.0, conversion=36_000.0)
        # Both must sit strictly inside (own claim, own claim + hsa_draw) --
        # and the larger conversion must have claimed a bigger absolute share
        # of the freed room, not just a bigger total.
        self.assertGreater(small, 4_000.0)
        self.assertLess(small, 4_000.0 + 25_000.0)
        self.assertGreater(large, 36_000.0)
        self.assertLessEqual(large, 36_000.0 + 25_000.0)
        self.assertLess(small - 4_000.0, large - 36_000.0)

    def test_a_zero_base_room_still_credits_the_conversions_claim_on_freed_room(self):
        """The bracket_room-is-zero edge case.

        With no base room at all, the ONLY pool available is what the draw
        freed. An implementation that computes `min(conversion, bracket_room)`
        as its floor before adding a fraction of hsa_draw wrongly zeroes out
        here, discarding a real conversion's real claim on the freed room --
        caught during implementation precisely because none of the other
        fixtures in this file exercise bracket_room == 0.
        """
        from src.hsa_schedule import joint_headroom_used
        used = joint_headroom_used({}, {"bracket_room": 0.0}, hsa_draw=25_000.0, conversion=10_000.0)
        self.assertAlmostEqual(used, 10_000.0, places=6)
        # A conversion bigger than the entire pool (base + freed) cannot use
        # more than the pool actually contains.
        capped = joint_headroom_used({}, {"bracket_room": 0.0}, hsa_draw=25_000.0, conversion=40_000.0)
        self.assertAlmostEqual(capped, 25_000.0, places=6)


@pytest.mark.unit
class ScheduleSearchTests(unittest.TestCase):
    def test_a_feasible_plan_consumes_the_balance_by_the_deadline(self):
        from src.hsa_schedule import build_schedule
        out = build_schedule(FEASIBLE_C, FEASIBLE_ROWS)
        self.assertEqual(out["feasibility"], "feasible")
        self.assertAlmostEqual(out["residual"], 0.0, places=2)

    def test_an_oversized_balance_reports_infeasible_and_never_moves_the_deadline(self):
        from src.hsa_schedule import build_schedule, resolve_consume_by_year
        out = build_schedule(OVERSIZED_C, FEASIBLE_ROWS)
        self.assertEqual(out["feasibility"], "infeasible")
        self.assertGreater(out["residual"], 0.0)
        self.assertLessEqual(max(out["by_year"]), resolve_consume_by_year(OVERSIZED_C, FEASIBLE_ROWS))

    def test_optimizer_beats_smooth_window_by_weighting_survivor_years(self):
        """(a) Names the wrong implementation it must reject: a level drawdown.
        Beating it on total score is not enough -- it must beat it BECAUSE more
        dollars land in survivor years."""
        from src.hsa_schedule import build_schedule, schedule_score, level_schedule
        opt = build_schedule(SURVIVOR_C, SURVIVOR_ROWS)
        lvl = level_schedule(SURVIVOR_C, SURVIVOR_ROWS)
        self.assertGreater(schedule_score(SURVIVOR_C, SURVIVOR_ROWS, opt["by_year"]),
                           schedule_score(SURVIVOR_C, SURVIVOR_ROWS, lvl))
        survivor_years = [r["year"] for r in SURVIVOR_ROWS if r["filing"] == "Single"]
        opt_share = sum(opt["by_year"].get(y, 0.0) for y in survivor_years) / sum(opt["by_year"].values())
        lvl_share = sum(lvl.get(y, 0.0) for y in survivor_years) / sum(lvl.values())
        self.assertGreater(opt_share, lvl_share)

    def test_optimizer_does_not_back_load_into_the_final_years(self):
        """(b) The failure mode that appears if the residual term is missing or
        mis-weighted. Such a schedule satisfies every constraint and feasibility
        check while maximizing exposure to an early death. Nothing else catches it."""
        from src.hsa_schedule import build_schedule, resolve_consume_by_year
        out = build_schedule(SURVIVOR_C, SURVIVOR_ROWS)
        deadline = resolve_consume_by_year(SURVIVOR_C, SURVIVOR_ROWS)
        years = sorted(out["by_year"])
        last_three = [y for y in years if y > deadline - 3]
        share = sum(out["by_year"][y] for y in last_three) / sum(out["by_year"].values())
        self.assertLess(share, 0.50,
                        "more than half the balance in the final three years means the "
                        "residual term is not pricing early-death risk")

    def test_the_surplus_state_is_reachable_not_dead_code(self):
        """`feasible_with_surplus` is the third feasibility state and no test in
        the brief exercises it. A state nothing can reach is a state that does
        not exist, so pin one household that does reach it: very old members and
        a large balance make the terminal-cliff risk of carrying money into the
        late years exceed the tax value of drawing it there, so the schedule
        empties the account strictly before the deadline and the deadline never
        binds."""
        from src.hsa_schedule import build_schedule
        rows = [{"year": y, "filing": "Single", "effective_marginal_rate": 0.24, "irmaa_tier": 0}
                for y in range(2026, 2051)]
        rows[0]["hsa_nw"] = 3_000_000.0
        c = {"plan_start": 2026, "plan_end": 2050, "hsa_consume_by": "2050", "ret": 0.02,
             "brk_inf": 0.0, "hsa_beneficiary_type": "non_spouse",
             "members": [{"role": "member_1", "dob_yr": 1930},
                         {"role": "member_2", "dob_yr": 1932}]}
        out = build_schedule(c, rows)
        self.assertEqual(out["feasibility"], "feasible_with_surplus")
        self.assertAlmostEqual(out["residual"], 0.0, places=2)
        self.assertLess(max(y for y, v in out["by_year"].items() if v > 0.0), 2050)


class HsaScheduleSheetSectionTests(unittest.TestCase):
    """The workbook section that carries the schedule, tested directly.

    The workbook-snapshot guard for this section
    (`test_hsa_schedule_discloses_its_modeling_limits` in
    tests/test_workbook_pdf_build_snapshot.py) resolves the sheet out of a real
    build against the FROZEN fixture -- whose `hsa_withdrawal_mode` is not
    `'optimize'`. The section is mode-gated, so on that build it correctly does
    not render and the guard skips. A guard that skips proves nothing about the
    content, so the disclosure text and the table are pinned HERE, against a
    config that does turn the mode on, with no workbook build in the loop.
    """

    def _render(self, c, rows):
        import openpyxl
        from src.reporting.sheets_strategy import build_hsa_schedule_section
        ws = openpyxl.Workbook().active
        end = build_hsa_schedule_section(ws, c, rows, 1)
        text = "\n".join(
            str(cell)
            for row in ws.iter_rows(values_only=True)
            for cell in row if cell is not None
        )
        return text, end

    def test_the_section_is_absent_for_every_non_optimize_mode(self):
        """Tasks 5/6's modes produce no schedule, so there is nothing to report
        on. Rendering an empty or placeholder section for them would be worse
        than omitting it: it would present the four modeling limits as if they
        qualified a recommendation the build never made."""
        for mode in (None, "spend_as_needed", "annual_pct", "smooth_window"):
            c = dict(FEASIBLE_C)
            if mode is not None:
                c["hsa_withdrawal_mode"] = mode
            text, end = self._render(c, FEASIBLE_ROWS)
            self.assertEqual(text, "", f"mode {mode!r} rendered a schedule section")
            self.assertEqual(end, 1, f"mode {mode!r} consumed rows on the sheet")

    def test_optimize_mode_renders_the_schedule_and_all_four_limits(self):
        c = dict(FEASIBLE_C, hsa_withdrawal_mode="optimize")
        text, end = self._render(c, FEASIBLE_ROWS)
        self.assertGreater(end, 1, "optimize mode rendered nothing")

        # 1. Deterministic-path-only, not re-optimized per MC path.
        self.assertIn("optimized on the deterministic path", text)
        # 2. Bucket-level in the vectorized MC -> balances only, no volatility channel.
        self.assertIn("bucket level", text)
        self.assertIn("only through balances", text)
        # 3. Deadline is a longevity percentile and a planning choice, with the
        #    residual exposure spelled out as a consequence, not just a number.
        self.assertIn("longevity percentile", text)
        self.assertIn("planning choice, not a prediction", text)
        self.assertIn("If you outlive", text)
        self.assertIn("ordinary income", text)
        # 4. Objective shared with Roth -> changing either retunes both. Wording
        #    updated when the schedule moved to its own sheet ('11C. HSA
        #    Drawdown'): it used to say "shown above" because the section was
        #    appended directly below the Roth Conversion sheet's own content;
        #    that spatial reference is gone now that they are on separate tabs.
        self.assertIn("shares its objective with the Roth Conversion sheet", text)
        self.assertIn("retunes both", text)

        # The table itself: every funded year and its dollars, plus the
        # feasibility state and residual reported ONCE rather than per row.
        from src.hsa_schedule import build_schedule
        out = build_schedule(c, FEASIBLE_ROWS)
        funded = [y for y, v in out["by_year"].items() if v > 0.0]
        self.assertTrue(funded, "fixture produced no funded years to render")
        for year in funded:
            self.assertIn(str(year), text)
        self.assertEqual(text.count(out["feasibility"].replace("_", " ")), 1,
                         "feasibility state must be shown once, not per row")

    def test_the_infeasible_residual_is_reported_not_swallowed(self):
        """The one state whose number the reader most needs is the one a
        prettier sheet would hide."""
        c = dict(OVERSIZED_C, hsa_withdrawal_mode="optimize")
        text, _ = self._render(c, FEASIBLE_ROWS)
        from src.hsa_schedule import build_schedule
        out = build_schedule(c, FEASIBLE_ROWS)
        self.assertEqual(out["feasibility"], "infeasible")
        self.assertGreater(out["residual"], 0.0)
        self.assertIn("infeasible", text)
        self.assertIn(f"${out['residual']:,.0f}", text)


if __name__ == "__main__":
    unittest.main()
