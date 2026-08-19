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


if __name__ == "__main__":
    unittest.main()
