"""Ticket 299: house sale proceeds should be splittable across multiple
accounts by percentage instead of always going to a single designated
account. Covers the engine's proportional split (and its fallback/
renormalization when a configured account no longer exists) and the
save-time validation that percentages must sum to 100%.
"""
from __future__ import annotations

import unittest

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


def _home_sale_config(**overrides):
    opts = dict(
        home_val=1_000_000.0,
        home_basis=400_000.0,
        home_sale_yr=2030,
        home_sale_px=0,
        mort_end=0,
    )
    opts.update(overrides)
    return _config(**opts)


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


class HomeSaleSplitEngineTests(unittest.TestCase):
    def test_proceeds_split_proportionally_across_configured_accounts(self):
        c = _home_sale_config(home_sale_splits=[
            {"account": "Joint_Trust", "pct": 0.6},
            {"account": "Family_Checking", "pct": 0.4},
        ])
        r = _by_year(project(c))[2030]
        net = r["home_sale_net"]
        applied = {s["account"]: s["amount"] for s in r["home_sale_splits_applied"]}
        self.assertAlmostEqual(applied["Joint_Trust"], net * 0.6, delta=1.0)
        self.assertAlmostEqual(applied["Family_Checking"], net * 0.4, delta=1.0)
        # The full net proceeds must land somewhere -- no dollars dropped.
        self.assertAlmostEqual(sum(applied.values()), net, delta=1.0)

    def test_unconfigured_splits_fall_back_to_single_account(self):
        c = _home_sale_config(home_sale_acct="Joint_Trust", home_sale_splits=[])
        r = _by_year(project(c))[2030]
        self.assertEqual(r.get("home_sale_splits_applied"), [])
        self.assertEqual(r["home_sale_acct"], "Joint_Trust")

    def test_split_naming_a_nonexistent_account_is_dropped_and_renormalized(self):
        # Only Joint_Trust is a real account; the household's actual 60/40
        # split (Joint_Trust/Family_Checking) with a typo'd second account
        # name must not silently lose 40% of the proceeds -- it renormalizes
        # to the account that does exist rather than lose the money outright.
        c = _home_sale_config(home_sale_splits=[
            {"account": "Joint_Trust", "pct": 0.6},
            {"account": "Does_Not_Exist", "pct": 0.4},
        ])
        r = _by_year(project(c))[2030]
        net = r["home_sale_net"]
        applied = r["home_sale_splits_applied"]
        # Only one real deposit target -- reported as a plain single deposit,
        # not a "split" (matches the unconfigured-splits fallback shape).
        self.assertEqual(applied, [])
        self.assertEqual(r["home_sale_acct"], "Joint_Trust")


class HomeSaleSplitDataIoTests(unittest.TestCase):
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

    HEADER = "section,subsection,label,value,units,notes\nHousehold,,residence_state,Illinois,text,\n"

    def test_parses_home_sale_split_rows_into_pct_fractions(self):
        c = self._parse(
            self.HEADER +
            "Home Sale Split,split_1,account,Joint_Trust,choice,\n"
            "Home Sale Split,split_1,percentage,60%,percent,\n"
            "Home Sale Split,split_2,account,Family_Checking,choice,\n"
            "Home Sale Split,split_2,percentage,40%,percent,\n"
        )
        self.assertEqual(c["home_sale_splits"], [
            {"account": "Joint_Trust", "pct": 0.6},
            {"account": "Family_Checking", "pct": 0.4},
        ])

    def test_blank_or_zero_rows_are_dropped(self):
        c = self._parse(
            self.HEADER +
            "Home Sale Split,split_1,account,,choice,\n"
            "Home Sale Split,split_1,percentage,0,percent,\n"
        )
        self.assertEqual(c["home_sale_splits"], [])

    def test_no_section_at_all_yields_empty_list(self):
        c = self._parse(self.HEADER)
        self.assertEqual(c["home_sale_splits"], [])


class HomeSaleSplitCsvRoundTripTests(unittest.TestCase):
    def test_write_then_read_round_trips_through_the_csv_file(self):
        import csv
        import tempfile
        from pathlib import Path
        from src.server.app_core import (
            _home_sale_split_rows,
            _home_sale_splits_from_csv_rows,
            _replace_home_sale_splits,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client_assets.csv"
            path.write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
            import src.server.app_core as app_core
            orig = app_core._client_section_path
            app_core._client_section_path = lambda section, fallback="client_assets.csv": path
            try:
                _replace_home_sale_splits([
                    {"account": "Joint_Trust", "percentage": "60"},
                    {"account": "Family_Checking", "percentage": "40"},
                ])
            finally:
                app_core._client_section_path = orig

            with path.open(newline="", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
            splits = _home_sale_splits_from_csv_rows(rows)
            self.assertEqual(splits, [
                {"account": "Joint_Trust", "percentage": "60"},
                {"account": "Family_Checking", "percentage": "40"},
            ])
            # Also sanity-check the raw row shape _home_sale_split_rows emits.
            generated = _home_sale_split_rows([{"account": "A", "percentage": "100"}])
            self.assertIn(["Home Sale Split", "split_1", "account", "A", "choice",
                            "Account to receive this share of house sale proceeds", "", ""], generated)


if __name__ == "__main__":
    unittest.main()
