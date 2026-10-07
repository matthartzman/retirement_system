"""Ticket 302: state residency should be configurable as a schedule (state,
start_year, end_year rows, last row open-ended) instead of one fixed state
for the whole plan, and every state-tax call site must actually use it.
"""
from __future__ import annotations

import unittest

from src.core import state_for_year
from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from tests.synthetic_plans import base_plan, _no_voluntary_roth


def _config(**overrides):
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    c.update(overrides)
    return c


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


class StateForYearResolverTests(unittest.TestCase):
    def test_no_schedule_falls_back_to_static_state(self):
        self.assertEqual(state_for_year({"state": "Illinois"}, 2030), "Illinois")

    def test_resolves_the_period_covering_the_year(self):
        c = {
            "state": "Illinois",
            "residency_schedule": [
                {"state": "Illinois", "start_year": 2026, "end_year": 2029},
                {"state": "Florida", "start_year": 2030, "end_year": 9999},
            ],
        }
        self.assertEqual(state_for_year(c, 2028), "Illinois")
        self.assertEqual(state_for_year(c, 2030), "Florida")
        self.assertEqual(state_for_year(c, 2045), "Florida")

    def test_year_before_first_period_falls_back_to_static_state(self):
        c = {
            "state": "Illinois",
            "residency_schedule": [
                {"state": "Florida", "start_year": 2030, "end_year": 9999},
            ],
        }
        self.assertEqual(state_for_year(c, 2020), "Illinois")


class ResidencyScheduleEngineTests(unittest.TestCase):
    def test_moving_to_a_no_income_tax_state_actually_lowers_state_tax(self):
        # Illinois exempts retirement income from state tax, so both members'
        # retirement (2027/2028 in base_plan) already zeroes out state_tax
        # regardless of residency -- the move has to land while both are
        # still working (earned income IS state-taxable in Illinois) for
        # this test to observe a real difference.
        move_year = 2027
        c = _config(state="Illinois", residency_schedule=[
            {"state": "Illinois", "start_year": 2026, "end_year": move_year - 1},
            {"state": "Florida", "start_year": move_year, "end_year": 9999},
        ])
        rows = _by_year(project(c))
        before = rows[move_year - 1]
        after = rows[move_year]
        # Same household, same income shape either side of the move -- the
        # only thing that changed is which state's tax rules applied.
        self.assertGreater(before.get("state_tax", 0.0), 0.0)
        self.assertAlmostEqual(after.get("state_tax", 0.0), 0.0, delta=1.0)

    def test_unconfigured_schedule_behaves_exactly_like_today(self):
        c_static = _config(state="Illinois")
        c_scheduled = _config(state="Illinois", residency_schedule=[])
        rows_static = _by_year(project(c_static))
        rows_scheduled = _by_year(project(c_scheduled))
        for year in (2026, 2035, 2045):
            self.assertAlmostEqual(
                rows_static[year]["state_tax"], rows_scheduled[year]["state_tax"], delta=0.01,
            )


class ResidencyScheduleDataIoTests(unittest.TestCase):
    def _parse(self, csv_text):
        import csv
        import io
        from src.data_io import parse_client

        rows = list(csv.reader(io.StringIO(csv_text)))
        header = rows[0]
        data = {}
        for row in rows[1:]:
            padded = row + [""] * max(0, len(header) - len(row))
            sec, sub, lbl, val = padded[0], padded[1], padded[2], padded[3]
            if not sec or sec.startswith("#") or not lbl:
                continue
            data.setdefault(sec, {}).setdefault(sub, {})[lbl] = val
        return parse_client(data, "")

    HEADER = "section,subsection,label,value,units,notes\nHousehold,,residence_state,Illinois,text,\nHousehold,,member_1_dob,1/1/1960,date,\nHousehold,,member_2_dob,1/1/1962,date,\n"

    def test_parses_schedule_rows_sorted_by_start_year(self):
        c = self._parse(
            self.HEADER +
            "State Residency Schedule,period_2,state,Florida,choice,\n"
            "State Residency Schedule,period_2,start_year,2032,year,\n"
            "State Residency Schedule,period_2,end_year,,year,\n"
            "State Residency Schedule,period_1,state,Illinois,choice,\n"
            "State Residency Schedule,period_1,start_year,2026,year,\n"
            "State Residency Schedule,period_1,end_year,2031,year,\n"
        )
        self.assertEqual(c["residency_schedule"], [
            {"state": "Illinois", "start_year": 2026, "end_year": 2031},
            {"state": "Florida", "start_year": 2032, "end_year": 9999},
        ])

    def test_blank_end_year_becomes_open_ended(self):
        c = self._parse(
            self.HEADER +
            "State Residency Schedule,period_1,state,Illinois,choice,\n"
            "State Residency Schedule,period_1,start_year,2026,year,\n"
        )
        self.assertEqual(c["residency_schedule"], [
            {"state": "Illinois", "start_year": 2026, "end_year": 9999},
        ])

    def test_row_with_no_state_is_dropped(self):
        c = self._parse(
            self.HEADER +
            "State Residency Schedule,period_1,start_year,2026,year,\n"
        )
        self.assertEqual(c["residency_schedule"], [])

    def test_no_section_at_all_yields_empty_list(self):
        c = self._parse(self.HEADER)
        self.assertEqual(c["residency_schedule"], [])


class ResidencyScheduleRoundTripTests(unittest.TestCase):
    def test_save_then_read_round_trips_through_the_plan_rows(self):
        import tempfile
        from pathlib import Path
        from tests.strategy_service_rows import service_over_rows

        schedule = [
            {"state": "Illinois", "start_year": "2026", "end_year": "2031"},
            {"state": "Florida", "start_year": "2032", "end_year": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            service, store, _events = service_over_rows(Path(tmp), [])
            with store:
                payload, status = service.save_residency_schedule_payload({"schedule": schedule})
                self.assertEqual(status, 200, payload)
                self.assertEqual(service.residency_schedule_payload()[0]["schedule"], schedule)
                first = [r for r in store.rows("State Residency Schedule") if r["subsection"] == "period_1"]
        # the rows carry the field units and notes the CSV block used to
        self.assertIn(("state", "Illinois", "choice", "Residence state during this period"),
                      [(r["label"], r["value"], r["units"], r["notes"]) for r in first])


class ResidencyScheduleServiceValidationTests(unittest.TestCase):
    """The save endpoint's validation and its rows (WP4.4b: the schedule lives in plan_rows)."""

    def _run(self, schedule, existing=()):
        import tempfile
        from pathlib import Path
        from tests.strategy_service_rows import service_over_rows

        with tempfile.TemporaryDirectory() as tmp:
            service, store, events = service_over_rows(Path(tmp), list(existing))
            with store:
                payload, status = service.save_residency_schedule_payload({"schedule": schedule})
                rows = [(r["subsection"], r["label"], r["value"]) for r in store.rows("State Residency Schedule")]
                read = service.residency_schedule_payload()
        return payload, status, rows, events, read

    def test_rejects_an_end_year_on_the_last_row(self):
        payload, status, rows, events, _ = self._run([
            {"state": "Illinois", "start_year": "2026", "end_year": "2031"},
            {"state": "Florida", "start_year": "2032", "end_year": "2040"},
        ])
        self.assertEqual(status, 400)
        self.assertFalse(payload["success"])
        self.assertFalse(rows)
        self.assertFalse(events)

    def test_rejects_a_missing_end_year_on_a_non_last_row(self):
        payload, status, rows, events, _ = self._run([
            {"state": "Illinois", "start_year": "2026", "end_year": ""},
            {"state": "Florida", "start_year": "2032", "end_year": ""},
        ])
        self.assertEqual(status, 400)
        self.assertFalse(payload["success"])
        self.assertFalse(rows)
        self.assertFalse(events)

    def test_accepts_a_valid_open_ended_schedule(self):
        payload, status, rows, events, read = self._run([
            {"state": "Illinois", "start_year": "2026", "end_year": "2031"},
            {"state": "Florida", "start_year": "2032", "end_year": ""},
        ])
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"success": True, "count": 2, "sync": None})
        self.assertEqual(rows, [
            ("period_1", "state", "Illinois"), ("period_1", "start_year", "2026"), ("period_1", "end_year", "2031"),
            ("period_2", "state", "Florida"), ("period_2", "start_year", "2032"), ("period_2", "end_year", ""),
        ])
        self.assertEqual(events, [("residency_schedule_saved", {"count": 2})])
        self.assertEqual(read, ({"success": True, "schedule": [
            {"state": "Illinois", "start_year": "2026", "end_year": "2031"},
            {"state": "Florida", "start_year": "2032", "end_year": ""},
        ]}, 200))

    def test_replacing_a_schedule_edits_in_place_and_drops_the_extra_period(self):
        existing = [("State Residency Schedule", f"period_{i}", label, value)
                    for i, vals in ((1, ("Illinois", "2026", "2031")), (2, ("Florida", "2032", "")))
                    for label, value in zip(("state", "start_year", "end_year"), vals)]
        payload, status, rows, events, _ = self._run([{"state": "Texas", "start_year": "2027", "end_year": ""}], existing)
        self.assertEqual(status, 200)
        self.assertEqual(rows, [("period_1", "state", "Texas"), ("period_1", "start_year", "2027"), ("period_1", "end_year", "")])


if __name__ == "__main__":
    unittest.main()
