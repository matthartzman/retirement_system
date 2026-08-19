"""Contract tests for registering client_hsa_schedule.csv as a flat plan-data table.

client_hsa_schedule.csv is a per-row override table (same category as
client_holdings.csv / client_liabilities.csv): no section/subsection/label
structure, no YAML counterpart, not part of the sectioned client_data.csv
bundle. This test file proves the three registration sites that let the file
be read, written, sync'd, and blanked correctly by the existing plan-data
infrastructure:

  1. src/server/plan_data_files.py PLAN_DATA_CSV_FILES -- the load-bearing
     list that feeds PLAN_DATA_FILE_SET, the gate _normalize_plan_data_file_name
     checks in src/server/app_core.py before _read_plan_data_file /
     _write_plan_data_file will touch a file at all.
  2. src/local_plan_data_sync.py PLAN_DATA_CSV_FILES -- the separate,
     independently-hardcoded list used for folder sync / download.
  3. src/server/app_core.py _blank_hsa_schedule_csv -- the "Start New Plan"
     blank-template function, mirroring _blank_holdings_csv / _blank_liabilities_csv.
"""
from __future__ import annotations

import csv
import io
import unittest

from src.server import app_core, plan_data_files
from src import local_plan_data_sync
# The Task 10 schedule-search fixtures, imported rather than re-declared: a
# second copy could drift, and then the search tests and the round-trip
# contract tests would silently be describing two different households.
from tests.test_hsa_optimizer_regression import FEASIBLE_C, FEASIBLE_ROWS, OVERSIZED_C

HSA_SCHEDULE_HEADER = ["year", "optimizer_amount", "override_amount", "locked", "note"]


class HsaScheduleRegistrationTests(unittest.TestCase):
    def test_registered_in_server_plan_data_files(self):
        self.assertIn("client_hsa_schedule.csv", plan_data_files.PLAN_DATA_CSV_FILES)

    def test_registered_in_local_plan_data_sync(self):
        self.assertIn("client_hsa_schedule.csv", local_plan_data_sync.PLAN_DATA_CSV_FILES)

    def test_registered_in_plan_data_file_set_gate(self):
        # Cheap proxy for "the DB-canonical read/write gate accepts it":
        # _normalize_plan_data_file_name (used by both _read_plan_data_file and
        # _write_plan_data_file) checks membership in this exact set.
        self.assertIn("client_hsa_schedule.csv", app_core.PLAN_DATA_FILE_SET)


class BlankHsaScheduleCsvTests(unittest.TestCase):
    def test_blank_with_real_content_returns_header_only(self):
        content = (
            "year,optimizer_amount,override_amount,locked,note\n"
            "2026,5000,,FALSE,\n"
            "2027,5200,4800,TRUE,manual override\n"
        )
        result = app_core._blank_hsa_schedule_csv(content)
        rows = list(csv.reader(io.StringIO(result)))
        self.assertEqual(rows, [HSA_SCHEDULE_HEADER])

    def test_blank_with_empty_content_falls_back_to_hardcoded_header(self):
        result = app_core._blank_hsa_schedule_csv("")
        rows = list(csv.reader(io.StringIO(result)))
        self.assertEqual(rows, [HSA_SCHEDULE_HEADER])

    def test_blank_dispatch_registered_for_client_hsa_schedule_csv(self):
        # _make_blank_plan_files must route this file name through
        # _blank_hsa_schedule_csv rather than leaving stale template rows in
        # place (the way _blank_holdings_csv / _blank_liabilities_csv are
        # routed for their own flat tables).
        files = app_core._make_blank_plan_files()
        self.assertIn("client_hsa_schedule.csv", files)
        rows = list(csv.reader(io.StringIO(files["client_hsa_schedule.csv"])))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], HSA_SCHEDULE_HEADER)


class PrecedenceTests(unittest.TestCase):
    def test_override_wins_over_everything(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": 25_000.0,
                                        "locked": True})
        self.assertAlmostEqual(amt, 25_000.0, places=6)
        self.assertEqual(src, "override")

    def test_locked_without_override_pins_the_optimizer_value(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                        "locked": True})
        self.assertAlmostEqual(amt, 10_000.0, places=6)
        self.assertEqual(src, "locked")

    def test_optimizer_value_is_used_when_nothing_else_applies(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                        "locked": False})
        self.assertEqual(src, "optimizer")

    def test_zero_is_a_real_override_not_an_absent_one(self):
        """The classic falsy bug: 0.0 must not be treated as 'no override'."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": 0.0,
                                        "locked": False})
        self.assertAlmostEqual(amt, 0.0, places=6)
        self.assertEqual(src, "override")


class ModeTierTests(unittest.TestCase):
    """The fourth precedence tier: nothing at the schedule layer for this year.

    src == 'mode' means "this function has nothing to say -- fall back to the
    hsa_withdrawal_mode path". amt is a placeholder 0.0 and must never be
    consumed as a real withdrawal figure.
    """

    def test_missing_optimizer_amount_falls_through_to_mode(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"year": 2030})
        self.assertEqual(src, "mode")
        self.assertAlmostEqual(amt, 0.0, places=6)

    def test_none_optimizer_amount_falls_through_to_mode(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": None, "override_amount": None,
                                        "locked": False})
        self.assertEqual(src, "mode")
        self.assertAlmostEqual(amt, 0.0, places=6)

    def test_empty_string_optimizer_amount_falls_through_to_mode(self):
        """A blank CSV cell is an absent optimizer value, not a zero one."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": "", "override_amount": "",
                                        "locked": ""})
        self.assertEqual(src, "mode")
        self.assertAlmostEqual(amt, 0.0, places=6)

    def test_override_still_wins_when_the_optimizer_never_ran_for_the_year(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"override_amount": 25_000.0})
        self.assertAlmostEqual(amt, 25_000.0, places=6)
        self.assertEqual(src, "override")

    def test_zero_override_still_wins_when_the_optimizer_never_ran(self):
        """Falsy-zero must survive the missing-optimizer path too."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": None, "override_amount": 0.0,
                                        "locked": False})
        self.assertAlmostEqual(amt, 0.0, places=6)
        self.assertEqual(src, "override")

    def test_locked_with_no_optimizer_amount_degrades_to_mode(self):
        """`locked` pins an optimizer value; with none written there is nothing
        to pin, so the year has no schedule-layer answer at all."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": None, "override_amount": None,
                                        "locked": True})
        self.assertEqual(src, "mode")
        self.assertAlmostEqual(amt, 0.0, places=6)

    def test_zero_optimizer_amount_is_a_real_schedule_value_not_an_absent_one(self):
        """0.0 from the optimizer means draw nothing this year -- a real
        answer, not a fall-through to mode."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 0.0, "override_amount": None,
                                        "locked": False})
        self.assertAlmostEqual(amt, 0.0, places=6)
        self.assertEqual(src, "optimizer")

    def test_zero_optimizer_amount_can_still_be_locked(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 0.0, "override_amount": None,
                                        "locked": True})
        self.assertAlmostEqual(amt, 0.0, places=6)
        self.assertEqual(src, "locked")


class LockedFlagParsingTests(unittest.TestCase):
    """locked arrives from a CSV cell, so it is a string, not a bool."""

    def test_string_false_is_not_locked(self):
        """The dangerous case: `if row.get('locked'):` treats "False" as True."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                        "locked": "False"})
        self.assertAlmostEqual(amt, 10_000.0, places=6)
        self.assertEqual(src, "optimizer")

    def test_string_upper_false_is_not_locked(self):
        from src.hsa_schedule import resolve_year_amount
        _, src = resolve_year_amount({"optimizer_amount": 10_000.0, "locked": "FALSE"})
        self.assertEqual(src, "optimizer")

    def test_other_falsy_spellings_are_not_locked(self):
        from src.hsa_schedule import resolve_year_amount
        for raw in ("0", "no", "No", "n", "off", "  ", ""):
            _, src = resolve_year_amount({"optimizer_amount": 10_000.0, "locked": raw})
            self.assertEqual(src, "optimizer", msg="locked=%r" % (raw,))

    def test_absent_and_none_locked_are_not_locked(self):
        from src.hsa_schedule import resolve_year_amount
        for row in ({"optimizer_amount": 10_000.0},
                    {"optimizer_amount": 10_000.0, "locked": None},
                    {"optimizer_amount": 10_000.0, "locked": False}):
            _, src = resolve_year_amount(row)
            self.assertEqual(src, "optimizer", msg="row=%r" % (row,))

    def test_truthy_spellings_are_locked(self):
        from src.hsa_schedule import resolve_year_amount
        for raw in ("True", "TRUE", "true", " true ", "1", "yes", "YES", "Yes", True):
            amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "locked": raw})
            self.assertAlmostEqual(amt, 10_000.0, places=6, msg="locked=%r" % (raw,))
            self.assertEqual(src, "locked", msg="locked=%r" % (raw,))


class OverridePresenceParsingTests(unittest.TestCase):
    """override_amount also arrives as a CSV string."""

    def test_blank_string_override_is_absent(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": "",
                                        "locked": False})
        self.assertAlmostEqual(amt, 10_000.0, places=6)
        self.assertEqual(src, "optimizer")

    def test_string_zero_override_is_present(self):
        """A "0.0" cell is still a real, deliberate zero override."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": "0.0",
                                        "locked": "TRUE"})
        self.assertAlmostEqual(amt, 0.0, places=6)
        self.assertEqual(src, "override")

    def test_numeric_string_override_is_parsed(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0,
                                        "override_amount": "25000", "locked": "False"})
        self.assertAlmostEqual(amt, 25_000.0, places=6)
        self.assertEqual(src, "override")

    def test_unparseable_override_is_treated_as_absent(self):
        """Garbage in the cell must not silently become a withdrawal figure."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": "n/a",
                                        "locked": False})
        self.assertAlmostEqual(amt, 10_000.0, places=6)
        self.assertEqual(src, "optimizer")

    def test_the_resolver_is_pure_and_does_not_mutate_the_row(self):
        from src.hsa_schedule import resolve_year_amount
        row = {"optimizer_amount": 10_000.0, "override_amount": "0.0", "locked": "TRUE"}
        before = dict(row)
        resolve_year_amount(row)
        self.assertEqual(row, before)

    def test_the_amount_is_always_a_float(self):
        from src.hsa_schedule import resolve_year_amount
        for row in ({"optimizer_amount": "10000", "locked": "TRUE"},
                    {"override_amount": "250"},
                    {}):
            amt, _ = resolve_year_amount(row)
            self.assertIsInstance(amt, float, msg="row=%r" % (row,))


def _expected_shares(c, rows, years, drawable, fixed=None):
    """Reference `_allocation_shares`, written against TRUE calendar offsets.

    Deliberately not a copy of the implementation: it calls the module's own
    `score_year` for the per-year weight and re-derives only the two things
    under test -- the growth offset (`year - plan_start`, never the list index)
    and the `fixed` mask. It is only valid for a config whose terminal-tax rate
    is zero (the schema-default 'spouse' beneficiary), which makes
    `_allocation_shares`'s carried-risk term structurally zero. FEASIBLE_C is
    such a config.
    """
    from src.hsa_schedule import _CONCENTRATION, _row_for_year, score_year
    growth = float(c.get("ret", 0.0))
    plan_start = int(c["plan_start"])
    increment = drawable / float(len(years))
    weights = {}
    for year in years:
        if fixed and year in fixed:
            weights[year] = 0.0
            continue
        grown = increment * (1.0 + growth) ** ((year - plan_start) + 1)
        weights[year] = max(0.0, score_year(c, _row_for_year(rows, year), grown))
    powered = {y: w ** _CONCENTRATION for y, w in weights.items()}
    total = sum(powered.values())
    if total <= 0.0:
        return {y: 1.0 / float(len(years)) for y in years}
    return {y: v / total for y, v in powered.items()}


class AllocationSharesOffsetTests(unittest.TestCase):
    """`_allocation_shares` must compound at each year's TRUE distance from
    plan_start, not at its position in the years list it was handed.

    For `build_schedule`'s own call the two are numerically identical -- that
    years list is always the contiguous plan_start..deadline range -- which is
    why the bug was invisible. The round-trip contract calls it with a FILTERED
    list (the years not already pinned by a lock or an override), and there the
    list index is simply the wrong number.
    """

    def test_contiguous_years_are_unchanged_by_the_offset_fix(self):
        """Backward-compatibility guard: over the full range the true offset and
        the list index agree, so the shares must still be exactly the reference."""
        from src.hsa_schedule import _allocation_shares, _schedule_years
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        got = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0)
        want = _expected_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0)
        self.assertEqual(sorted(got), sorted(want))
        for year in years:
            self.assertAlmostEqual(got[year], want[year], places=12,
                                   msg="year=%r" % (year,))

    def test_a_filtered_years_list_compounds_at_the_true_calendar_offset(self):
        """The real bug. 2033 is 7 years past plan_start but only index 1 in
        this list; its growth factor must be (1+ret)**8, not (1+ret)**2."""
        from src.hsa_schedule import _allocation_shares
        years = [2026, 2033, 2040]
        got = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0)
        want = _expected_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0)
        for year in years:
            self.assertAlmostEqual(got[year], want[year], places=12,
                                   msg="year=%r" % (year,))

    def test_the_filtered_case_is_discriminating_not_a_coincidence(self):
        """Names the wrong implementation explicitly. If list-index offsets and
        true-calendar offsets happened to produce the same shares for this
        fixture, the test above would be a guard that cannot fail."""
        from src.hsa_schedule import _CONCENTRATION, _row_for_year, score_year
        years = [2026, 2033, 2040]
        growth = FEASIBLE_C["ret"]
        increment = 400_000.0 / 3.0
        by_index, by_calendar = {}, {}
        for idx, year in enumerate(years):
            row = _row_for_year(FEASIBLE_ROWS, year)
            by_index[year] = score_year(
                FEASIBLE_C, row,
                increment * (1.0 + growth) ** (idx + 1)) ** _CONCENTRATION
            by_calendar[year] = score_year(
                FEASIBLE_C, row,
                increment * (1.0 + growth) ** (year - 2026 + 1)) ** _CONCENTRATION
        idx_total, cal_total = sum(by_index.values()), sum(by_calendar.values())
        self.assertNotAlmostEqual(by_index[2040] / idx_total,
                                  by_calendar[2040] / cal_total, places=6)

    def test_shares_still_sum_to_one_on_a_filtered_list(self):
        from src.hsa_schedule import _allocation_shares
        got = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, [2026, 2033, 2040], 400_000.0)
        self.assertAlmostEqual(sum(got.values()), 1.0, places=9)

    def test_fixed_is_optional_and_none_leaves_behavior_unchanged(self):
        from src.hsa_schedule import _allocation_shares, _schedule_years
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        without = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0)
        explicit_none = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0,
                                           fixed=None)
        empty = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0, fixed={})
        for year in years:
            self.assertAlmostEqual(without[year], explicit_none[year], places=12,
                                   msg="year=%r" % (year,))
            self.assertAlmostEqual(without[year], empty[year], places=12,
                                   msg="year=%r" % (year,))

    def test_a_fixed_year_gets_zero_weight_and_never_competes_for_the_pool(self):
        from src.hsa_schedule import _allocation_shares, _schedule_years
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        fixed = {2030: 50_000.0, 2031: 50_000.0}
        got = _allocation_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0, fixed=fixed)
        self.assertAlmostEqual(got[2030], 0.0, places=12)
        self.assertAlmostEqual(got[2031], 0.0, places=12)
        self.assertAlmostEqual(sum(got.values()), 1.0, places=9)
        want = _expected_shares(FEASIBLE_C, FEASIBLE_ROWS, years, 400_000.0, fixed=fixed)
        for year in years:
            self.assertAlmostEqual(got[year], want[year], places=12,
                                   msg="year=%r" % (year,))


class RoundTripTests(unittest.TestCase):
    def test_rerunning_the_optimizer_never_touches_override_values(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": 25_000.0,
                 "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertAlmostEqual(out[0]["override_amount"], 25_000.0, places=6)

    def test_rerunning_does_refresh_the_optimizer_column(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 1.0, "override_amount": None, "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertNotAlmostEqual(out[0]["optimizer_amount"], 1.0, places=6)

    def test_locked_years_are_planned_around_not_through(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": 40_000.0,
                 "locked": True}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertAlmostEqual(out[0]["override_amount"], 40_000.0, places=6)

    def test_clearing_an_override_returns_the_year_to_optimizer_control(self):
        from src.hsa_schedule import resolve_year_amount
        _, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                      "locked": False})
        self.assertEqual(src, "optimizer")

    def test_overrides_that_break_the_deadline_report_infeasible(self):
        """Honor the user's numbers, surface the consequence. Never silently
        redistribute into locked or overridden years."""
        from src.hsa_schedule import rerun_optimizer, schedule_feasibility
        rows = [{"year": y, "optimizer_amount": 0.0, "override_amount": 0.0, "locked": True}
                for y in range(2030, 2045)]
        out = rerun_optimizer(OVERSIZED_C, FEASIBLE_ROWS, rows)
        self.assertEqual(schedule_feasibility(OVERSIZED_C, out), "infeasible")


class RerunShapeTests(unittest.TestCase):
    """What `rerun_optimizer` returns, beyond the two headline guarantees."""

    def test_the_output_covers_exactly_the_true_horizon(self):
        from src.hsa_schedule import rerun_optimizer, _schedule_years
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": None,
                 "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertEqual(sorted(r["year"] for r in out),
                         _schedule_years(FEASIBLE_C, FEASIBLE_ROWS))

    def test_the_first_run_emits_the_horizon_in_ascending_order(self):
        from src.hsa_schedule import rerun_optimizer, _schedule_years
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        self.assertEqual([r["year"] for r in out],
                         _schedule_years(FEASIBLE_C, FEASIBLE_ROWS))

    def test_the_caller_s_own_rows_come_back_in_the_order_they_were_given(self):
        """A re-run refreshes the user's table; it does not reshuffle it. Rows
        the file did not cover are appended after, ascending."""
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": y, "optimizer_amount": 1.0, "override_amount": None, "locked": False}
                for y in (2035, 2030)]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        years = [r["year"] for r in out]
        self.assertEqual(years[:2], [2035, 2030])
        self.assertEqual(years[2:], sorted(years[2:]))

    def test_schedule_rows_outside_the_horizon_are_ignored_not_emitted(self):
        """The CSV can be stale relative to a changed `hsa_consume_by`. A year
        past the deadline must not survive into the new schedule: the deadline
        is never moved to accommodate a stale row."""
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2044, "optimizer_amount": 5_000.0, "override_amount": 99_000.0,
                 "locked": True}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertNotIn(2044, [r["year"] for r in out])
        self.assertLessEqual(max(r["year"] for r in out), 2040)

    def test_an_empty_schedule_reproduces_the_unconstrained_search(self):
        """With nothing pinned the round trip must agree with `build_schedule`
        exactly. A second, quietly-disagreeing allocation model would be its
        own bug."""
        from src.hsa_schedule import rerun_optimizer, build_schedule
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        want = build_schedule(FEASIBLE_C, FEASIBLE_ROWS)["by_year"]
        for row in out:
            self.assertAlmostEqual(row["optimizer_amount"], want[row["year"]], places=6,
                                   msg="year=%r" % (row["year"],))

    def test_the_starting_balance_is_stamped_onto_the_first_row(self):
        """`schedule_feasibility(c, rows)` cannot see the projection rows, so
        the round trip has to be self-describing about the balance it consumed."""
        from src.hsa_schedule import rerun_optimizer, _starting_balance
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        self.assertAlmostEqual(out[0]["hsa_nw"], _starting_balance(FEASIBLE_ROWS), places=6)

    def test_every_row_carries_the_full_csv_shape(self):
        from src.hsa_schedule import rerun_optimizer
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        for row in out:
            for key in ("year", "optimizer_amount", "override_amount", "locked", "note"):
                self.assertIn(key, row, msg="year=%r key=%r" % (row["year"], key))

    def test_the_note_column_survives_a_rerun(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 1.0, "override_amount": None,
                 "locked": False, "note": "why this year"}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertEqual([r["note"] for r in out if r["year"] == 2030], ["why this year"])

    def test_the_input_schedule_rows_are_not_mutated(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 1.0, "override_amount": 25_000.0,
                 "locked": True, "note": "keep"}]
        before = [dict(r) for r in rows]
        rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertEqual(rows, before)

    def test_a_horizon_year_with_no_schedule_row_is_simply_unpinned(self):
        from src.hsa_schedule import rerun_optimizer
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        for row in out:
            self.assertIsNone(row["override_amount"], msg="year=%r" % (row["year"],))
            self.assertGreater(row["optimizer_amount"], 0.0, msg="year=%r" % (row["year"],))


class RerunPlansAroundPinnedYearsTests(unittest.TestCase):
    """A pinned year is planned AROUND: it keeps its dollars, and the balance
    the remaining years share is what is genuinely left after it draws."""

    def test_a_large_override_shrinks_what_the_other_years_are_given(self):
        from src.hsa_schedule import rerun_optimizer
        base = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        rows = [{"year": 2030, "optimizer_amount": None, "override_amount": 200_000.0,
                 "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        base_rest = sum(r["optimizer_amount"] for r in base if r["year"] != 2030)
        out_rest = sum(r["optimizer_amount"] for r in out if r["year"] != 2030)
        self.assertLess(out_rest, base_rest)

    def test_the_pinned_year_is_not_re_planned_through(self):
        """The other years must absorb the whole REMAINING pool -- not the whole
        balance (which would double-spend the pinned dollars) and not a flat
        balance-minus-override (which would ignore that the pinned draw lands
        part-way through the growth sequence)."""
        from src.hsa_schedule import (rerun_optimizer, schedule_feasibility,
                                      _schedule_years, _simulate_residual)
        rows = [{"year": 2030, "optimizer_amount": None, "override_amount": 200_000.0,
                 "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        by_year = {r["year"]: (200_000.0 if r["year"] == 2030 else r["optimizer_amount"])
                   for r in out}
        self.assertAlmostEqual(
            _simulate_residual(FEASIBLE_C, FEASIBLE_ROWS, years, by_year), 0.0, places=2)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, out), "feasible")

    def test_a_locked_year_keeps_its_pinned_optimizer_amount(self):
        """`locked` means "pin the value the optimizer wrote". With no override
        behind it, `resolve_year_amount` reads that pin OUT of optimizer_amount
        -- so refreshing that column for a locked year would silently move the
        very number the lock exists to hold."""
        from src.hsa_schedule import rerun_optimizer, resolve_year_amount
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": None,
                 "locked": True}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        pinned = [r for r in out if r["year"] == 2030][0]
        self.assertAlmostEqual(pinned["optimizer_amount"], 10_000.0, places=6)
        amt, src = resolve_year_amount(pinned)
        self.assertEqual(src, "locked")
        self.assertAlmostEqual(amt, 10_000.0, places=6)

    def test_an_override_backed_year_still_refreshes_its_optimizer_column(self):
        """With an override present the optimizer column is inert -- the
        override wins unconditionally -- so it is refreshed to what the search
        would propose if the year were free, which is exactly what the user
        falls back to if they later clear the override."""
        from src.hsa_schedule import rerun_optimizer, build_schedule
        rows = [{"year": 2030, "optimizer_amount": 1.0, "override_amount": 25_000.0,
                 "locked": True}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        pinned = [r for r in out if r["year"] == 2030][0]
        self.assertAlmostEqual(pinned["override_amount"], 25_000.0, places=6)
        self.assertNotAlmostEqual(pinned["optimizer_amount"], 1.0, places=6)
        self.assertAlmostEqual(pinned["optimizer_amount"],
                               build_schedule(FEASIBLE_C, FEASIBLE_ROWS)["by_year"][2030],
                               places=6)

    def test_a_rerun_is_idempotent_on_its_own_output(self):
        """The round trip proper: re-running over the schedule a re-run just
        produced must not drift. This is the property a user experiences."""
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": 25_000.0,
                 "locked": True}]
        once = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        twice = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, once)
        self.assertEqual(len(once), len(twice))
        for a, b in zip(once, twice):
            self.assertEqual(a["year"], b["year"])
            self.assertAlmostEqual(a["optimizer_amount"], b["optimizer_amount"], places=6,
                                   msg="year=%r" % (a["year"],))
            self.assertEqual(a["override_amount"], b["override_amount"])
            self.assertEqual(a["locked"], b["locked"])


class ScheduleFeasibilityTests(unittest.TestCase):
    def test_a_clean_rerun_is_feasible(self):
        from src.hsa_schedule import rerun_optimizer, schedule_feasibility
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        self.assertEqual(schedule_feasibility(FEASIBLE_C, out), "feasible")

    def test_a_positive_floor_is_infeasible_by_construction(self):
        """Mirrors `build_schedule`: a floor the optimizer may not draw through
        is a residual that cannot reach zero, so it reports infeasible however
        well the remaining years are otherwise scheduled."""
        from src.hsa_schedule import rerun_optimizer, schedule_feasibility
        out = rerun_optimizer(OVERSIZED_C, FEASIBLE_ROWS, [])
        self.assertEqual(schedule_feasibility(OVERSIZED_C, out), "infeasible")

    def test_overrides_that_underdraw_leave_a_residual_and_report_infeasible(self):
        """No floor at all: the infeasibility comes purely from the user's own
        numbers, which are honored rather than quietly topped up."""
        from src.hsa_schedule import schedule_feasibility, _schedule_years, _starting_balance
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        rows = [{"year": y, "optimizer_amount": 0.0, "override_amount": 1.0, "locked": True}
                for y in years]
        rows[0]["hsa_nw"] = _starting_balance(FEASIBLE_ROWS)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "infeasible")

    def test_emptying_the_account_early_reports_surplus(self):
        """The third state has to be reachable through this signature too, or
        it is dead code here."""
        from src.hsa_schedule import schedule_feasibility, _schedule_years, _starting_balance
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        balance = _starting_balance(FEASIBLE_ROWS)
        rows = [{"year": y, "optimizer_amount": 0.0, "override_amount": 0.0, "locked": False}
                for y in years]
        # One early year draws more than the account can possibly hold, so the
        # balance is gone long before the deadline.
        rows[0]["override_amount"] = balance * 10.0
        rows[0]["hsa_nw"] = balance
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "feasible_with_surplus")

    def test_the_verdict_does_not_depend_on_which_row_is_first(self):
        """`rerun_optimizer` stamps the balance on the row it emits first, but a
        caller is entitled to sort the table by year before handing it back. A
        feasibility answer that quietly depended on row position would only
        break in production."""
        from src.hsa_schedule import rerun_optimizer, schedule_feasibility
        rows = [{"year": y, "optimizer_amount": 1.0, "override_amount": None, "locked": False}
                for y in (2035, 2030)]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, out), "feasible")
        self.assertEqual(
            schedule_feasibility(FEASIBLE_C, sorted(out, key=lambda r: r["year"])),
            "feasible")
        self.assertEqual(
            schedule_feasibility(FEASIBLE_C, list(reversed(out))), "feasible")

    def _underdrawn_rows(self, balance_at):
        """A schedule that draws $1/year against a real $500k balance, with the
        `hsa_nw`-carrying row at position `balance_at`.

        Every year underdraws by four orders of magnitude, so the residual is
        the starting balance almost untouched. That is what makes the fixture
        discriminating: the verdict is `'infeasible'` if and only if the real,
        nonzero balance was actually FOUND. An implementation that read the
        wrong row would see no `hsa_nw` at all, fall back to 0.0, and a
        zero-balance account is trivially consumed by any draw -- so it would
        report `'feasible'` and the guard would go red.

        The `'feasible'` fixture the order-independence test above uses cannot
        do this job: a schedule that already nets to zero nets to zero whatever
        `hsa_nw` resolves to, so it passes against a position-0-only read too.
        """
        from src.hsa_schedule import _schedule_years, _starting_balance
        years = _schedule_years(FEASIBLE_C, FEASIBLE_ROWS)
        rows = [{"year": y, "optimizer_amount": 0.0, "override_amount": 1.0,
                 "locked": True} for y in years]
        rows[balance_at]["hsa_nw"] = _starting_balance(FEASIBLE_ROWS)
        return rows

    def test_an_underdrawn_schedule_is_infeasible_with_the_balance_row_first(self):
        """Baseline placement: `rerun_optimizer`'s own stamping position."""
        from src.hsa_schedule import schedule_feasibility
        rows = self._underdrawn_rows(0)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "infeasible")

    def test_an_underdrawn_schedule_is_infeasible_with_the_balance_row_in_the_middle(self):
        """Same row set, balance moved off position 0. A position-0-only lookup
        reads no balance here and wrongly reports 'feasible'."""
        from src.hsa_schedule import schedule_feasibility
        rows = self._underdrawn_rows(7)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "infeasible")

    def test_an_underdrawn_schedule_is_infeasible_with_the_balance_row_last(self):
        """The far end of the same table, and the same requirement."""
        from src.hsa_schedule import schedule_feasibility
        rows = self._underdrawn_rows(-1)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "infeasible")

    def test_an_underdrawn_schedule_is_infeasible_when_the_table_is_reversed(self):
        """Reversing the caller's table moves the balance row from first to
        last without changing a single number in it. The verdict must not."""
        from src.hsa_schedule import schedule_feasibility
        rows = self._underdrawn_rows(0)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "infeasible")
        self.assertEqual(
            schedule_feasibility(FEASIBLE_C, list(reversed(rows))), "infeasible")

    def test_no_horizon_is_infeasible_rather_than_a_crash(self):
        from src.hsa_schedule import schedule_feasibility
        self.assertEqual(schedule_feasibility({}, []), "infeasible")

    def test_rows_outside_the_horizon_are_ignored(self):
        from src.hsa_schedule import schedule_feasibility, rerun_optimizer
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        stale = list(out) + [{"year": 2044, "optimizer_amount": 0.0,
                              "override_amount": 500_000.0, "locked": True}]
        self.assertEqual(schedule_feasibility(FEASIBLE_C, stale), "feasible")

    def _stale_balance_row(self):
        """A row past the deadline carrying a `hsa_nw` ten times the real one.

        2044 is outside the 2026..2040 horizon, so this row is stale by the
        function's own documented rule -- "a stale CSV must not move the
        deadline". The amount loop already skips it. The point of the wrong
        balance is that it is loud: if the balance scan honors it, the clean
        schedule underdraws by 4.5M and the verdict flips to 'infeasible'.
        """
        return {"year": 2044, "optimizer_amount": 0.0, "override_amount": 0.0,
                "locked": True, "hsa_nw": 5_000_000.0}

    def test_a_stale_out_of_horizon_row_cannot_supply_the_balance_when_appended(self):
        from src.hsa_schedule import schedule_feasibility, rerun_optimizer
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        rows = list(out) + [self._stale_balance_row()]
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "feasible")

    def test_a_stale_out_of_horizon_row_cannot_supply_the_balance_when_prepended(self):
        """The discriminating placement. Appending hid the bug because the real
        balance row still came first; prepending puts the stale row in front of
        it, and a scan without the horizon filter takes the stale number."""
        from src.hsa_schedule import schedule_feasibility, rerun_optimizer
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        rows = [self._stale_balance_row()] + list(out)
        self.assertEqual(schedule_feasibility(FEASIBLE_C, rows), "feasible")

    def test_the_stale_row_s_placement_cannot_change_the_verdict(self):
        """Same data, two positions, one answer -- stated as the contract rather
        than as two independent facts that happen to agree."""
        from src.hsa_schedule import schedule_feasibility, rerun_optimizer
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, [])
        appended = schedule_feasibility(FEASIBLE_C, list(out) + [self._stale_balance_row()])
        prepended = schedule_feasibility(FEASIBLE_C, [self._stale_balance_row()] + list(out))
        self.assertEqual(appended, prepended)


if __name__ == "__main__":
    unittest.main()
