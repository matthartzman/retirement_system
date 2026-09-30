"""Tax assumptions resolver: Auto model value vs. plan override.

Covers resolution order, validation, the build-time effective payload, and the
state-rate override reaching the engine. With no overrides the engine config
must equal what the pre-resolver code produced (2.00% inflator, 85% SS).
"""
from __future__ import annotations

import copy
from pathlib import Path
import unittest

from src.core import STATE_TAX_RULES, state_income_tax
from src.data_io import _n, build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.tax_assumptions import TaxAssumptionError, resolve_tax_assumptions
from tests.synthetic_plans import base_plan


def _resolve(raw, state="Illinois"):
    return resolve_tax_assumptions(raw, _n, state=state, state_rules=STATE_TAX_RULES)


class ResolutionOrderTests(unittest.TestCase):
    def test_blank_fields_use_model_values(self):
        r = _resolve({})
        self.assertEqual(r["fed_tax_bracket_inflator"].value, 0.02)
        self.assertEqual(r["fed_tax_bracket_inflator"].source, "model")
        self.assertEqual(r["social_security_taxable_fraction"].value, 0.85)
        self.assertEqual(r["state_income_tax_rate"].source, "model")
        self.assertAlmostEqual(r["state_income_tax_rate"].value, STATE_TAX_RULES["Illinois"]["rate"])

    def test_override_beats_model(self):
        r = _resolve({"fed_tax_bracket_inflator": "3.00%"})
        self.assertEqual(r["fed_tax_bracket_inflator"].source, "override")
        self.assertAlmostEqual(r["fed_tax_bracket_inflator"].value, 0.03)
        self.assertEqual(r["fed_tax_bracket_inflator"].model_value, 0.02)

    def test_explicit_value_equal_to_model_is_still_an_override(self):
        r = _resolve({"fed_tax_bracket_inflator": "2.00%"})
        lv = r["fed_tax_bracket_inflator"]
        self.assertEqual(lv.source, "override")
        self.assertTrue(lv.matches_model)

    def test_invalid_override_falls_back_with_warning(self):
        for bad in ("abc", "9.00%"):
            lv = _resolve({"fed_tax_bracket_inflator": bad})["fed_tax_bracket_inflator"]
            self.assertEqual(lv.source, "model")
            self.assertEqual(lv.value, 0.02)
            self.assertTrue(lv.warning)

    def test_unusual_override_warns_but_applies(self):
        lv = _resolve({"state_income_tax_rate": "12%"})["state_income_tax_rate"]
        self.assertEqual(lv.source, "override")
        self.assertAlmostEqual(lv.value, 0.12)
        self.assertTrue(lv.warning)

    def test_unknown_state_has_no_model_value_and_fails(self):
        with self.assertRaises(TaxAssumptionError):
            _resolve({}, state="Atlantis")


class BuildIntegrationTests(unittest.TestCase):
    def _build(self, **assumption_overrides):
        plan = copy.deepcopy(base_plan())
        plan["assumptions"].update(assumption_overrides)
        return build_plan_from_json(plan, "")

    def test_no_overrides_matches_legacy_values(self):
        c = self._build()
        self.assertEqual(c["brk_inf"], 0.02)
        self.assertEqual(c["ss_taxable"], 0.85)
        self.assertIsNone(c["state_rate_override"])
        eff = c["tax_assumptions_effective"]
        self.assertEqual(set(eff), {"fed_tax_bracket_inflator",
                                    "social_security_taxable_fraction",
                                    "state_income_tax_rate", "tax_law_scenario"})

    def test_missing_json_inflator_uses_single_model_default(self):
        plan = copy.deepcopy(base_plan())
        plan["assumptions"].pop("bracket_inflation")
        c = build_plan_from_json(plan, "")
        self.assertEqual(c["brk_inf"], 0.02)  # was a silent 2.8% on this path

    def test_inflator_override_reaches_engine_config(self):
        c = self._build(bracket_inflation=0.03)
        self.assertAlmostEqual(c["brk_inf"], 0.03)
        self.assertEqual(c["tax_assumptions_effective"]["fed_tax_bracket_inflator"]["source"], "override")


class StateRateOverrideTests(unittest.TestCase):
    def test_flat_override_replaces_state_rules(self):
        base = state_income_tax("Illinois", 100_000, 0, 0, 0, 0, 0, 2027)
        over = state_income_tax("Illinois", 100_000, 0, 0, 0, 0, 0, 2027, rate_override=0.10)
        self.assertAlmostEqual(over, 10_000.0)
        self.assertNotAlmostEqual(base, over)

    def test_override_applies_to_no_tax_state(self):
        self.assertEqual(state_income_tax("Florida", 100_000, 0, 0, 0, 0, 0, 2027), 0.0)
        self.assertAlmostEqual(
            state_income_tax("Florida", 100_000, 0, 0, 0, 0, 0, 2027, rate_override=0.05), 5_000.0)

    def test_none_override_is_identical_to_today(self):
        for st in ("Illinois", "California", "New York", "Texas"):
            a = state_income_tax(st, 150_000, 40_000, 10_000, 5_000, 0, 0, 2030)
            b = state_income_tax(st, 150_000, 40_000, 10_000, 5_000, 0, 0, 2030, rate_override=None)
            self.assertEqual(a, b)

    def test_override_changes_projected_state_tax(self):
        def lifetime_state_tax(**kw):
            plan = copy.deepcopy(base_plan())
            plan["assumptions"].update(kw)
            c = ensure_engine_config(build_plan_from_json(plan, ""), source="test_tax_assumptions")
            rows = project(c)
            if isinstance(rows, tuple):
                rows = rows[0]
            return sum(float(r.get("state_tax", 0.0) or 0.0) for r in rows)

        auto = lifetime_state_tax()
        high = lifetime_state_tax(state_income_tax_rate=0.12)
        self.assertGreater(high, auto)


if __name__ == "__main__":
    unittest.main()


class PayloadAndReportTests(unittest.TestCase):
    def _service(self, econ_rows, state="Illinois"):
        from types import SimpleNamespace
        from src.server_services.strategy_asset_service import StrategyAssetService

        header = ["section", "subsection", "label", "value"]

        def read_rows(section, _file="client_household.csv"):
            if section == "Economic Assumptions":
                return [header] + [["Economic Assumptions", "", k, v] for k, v in econ_rows.items()]
            if section == "Household":
                return [header, ["Household", "", "residence_state", state]]
            return []

        svc = StrategyAssetService.__new__(StrategyAssetService)
        svc.context = SimpleNamespace(read_client_section_rows=read_rows)
        return svc

    def test_payload_reports_auto_and_override(self):
        body, status = self._service({"fed_tax_bracket_inflator": "3.00%",
                                      "state_income_tax_rate": ""}).tax_assumptions_payload()
        self.assertEqual(status, 200)
        by_key = {lv["key"]: lv for lv in body["levers"]}
        self.assertEqual(by_key["fed_tax_bracket_inflator"]["source"], "override")
        self.assertEqual(by_key["state_income_tax_rate"]["source"], "model")
        self.assertEqual(body["state"], "Illinois")

    def test_payload_fails_for_unknown_state(self):
        body, status = self._service({}, state="Atlantis").tax_assumptions_payload()
        self.assertEqual(status, 400)
        self.assertFalse(body["success"])

    def test_summary_note_marks_override(self):
        from src.reporting.sheets_summary_builder import _tax_assumption_note
        c = {"tax_assumptions_effective": {
            "fed_tax_bracket_inflator": {"source": "override", "model_value": 0.02, "basis": "b"}}}
        self.assertTrue(_tax_assumption_note(c, "fed_tax_bracket_inflator", "x").startswith("OVERRIDE"))
        self.assertEqual(_tax_assumption_note({}, "fed_tax_bracket_inflator", "x"), "x")


class LawTableTests(unittest.TestCase):
    def test_law_table_is_read_only_dataset_view(self):
        from src.tax_assumptions import law_reference_table
        t = law_reference_table(2026)
        self.assertEqual(t["year"], 2026)
        self.assertIn("MFJ", t["standard_deduction"])
        self.assertTrue(t["ordinary_brackets"]["MFJ"])
        self.assertIsNone(t["ordinary_brackets"]["MFJ"][-1]["upper"])


class DriftAndSaveTests(unittest.TestCase):
    def test_baseline_round_trip_and_unknown_keys_dropped(self):
        from src.tax_assumptions import format_baseline, parse_baseline
        text = format_baseline({"fed_tax_bracket_inflator": 0.02, "state_income_tax_rate": 0.0495})
        self.assertEqual(parse_baseline(text), {"fed_tax_bracket_inflator": 0.02,
                                                "state_income_tax_rate": 0.0495})
        self.assertEqual(parse_baseline("bogus=1;fed_tax_bracket_inflator=x"), {})

    def test_validate_override_text(self):
        from src.tax_assumptions import validate_override_text as v
        self.assertEqual(v("fed_tax_bracket_inflator", ""), "")
        self.assertEqual(v("fed_tax_bracket_inflator", "3%"), "")
        self.assertTrue(v("fed_tax_bracket_inflator", "9%"))
        self.assertTrue(v("fed_tax_bracket_inflator", "abc"))
        self.assertTrue(v("nope", "1%"))

    def test_with_drift_flags_only_changed_overrides(self):
        from src.tax_assumptions import with_drift
        levers = [
            {"key": "fed_tax_bracket_inflator", "source": "override", "model_value": 0.025},
            {"key": "state_income_tax_rate", "source": "model", "model_value": 0.05},
        ]
        out = with_drift(levers, {"fed_tax_bracket_inflator": 0.02, "state_income_tax_rate": 0.05})
        self.assertTrue(out[0]["drifted"])
        self.assertFalse(out[1]["drifted"])

    def test_save_upserts_rows_and_records_baseline(self):
        from types import SimpleNamespace
        from src.server_services.strategy_asset_service import StrategyAssetService
        rows = [["section", "subsection", "label", "value", "units", "note"],
                ["Household", "", "residence_state", "Illinois", "text", ""],
                ["Economic Assumptions", "", "fed_tax_bracket_inflator", "2.00%", "pct", ""]]
        written = {}
        ctx = SimpleNamespace(
            client_section_path=lambda *a: Path("x.csv"),
            ensure_header=lambda r: r,
            csv_read_rows=lambda p: rows,
            read_client_section_rows=lambda sec, f="": [rows[0]] + [r for r in rows[1:] if r[0] == sec],
            write_client_rows=lambda p, r: written.setdefault("rows", r),
            sync_config_backends=lambda: {},
            audit=None,
        )
        svc = StrategyAssetService.__new__(StrategyAssetService)
        svc.context = ctx
        svc._audit = lambda *a, **k: None
        body, status = svc.save_tax_assumptions_payload(
            {"overrides": {"fed_tax_bracket_inflator": "3.00%", "state_income_tax_rate": "6%"}})
        self.assertEqual(status, 200, body)
        by_label = {r[2]: r for r in written["rows"] if r[0] == "Economic Assumptions"}
        self.assertEqual(by_label["fed_tax_bracket_inflator"][3], "3.00%")
        self.assertEqual(by_label["state_income_tax_rate"][3], "6%")
        self.assertIn("fed_tax_bracket_inflator=0.02", by_label["tax_model_baseline"][3])
        bad, st = svc.save_tax_assumptions_payload({"overrides": {"state_income_tax_rate": "40%"}})
        self.assertEqual(st, 400)


class LawScenarioTests(unittest.TestCase):
    def _rows(self, **assumptions):
        plan = copy.deepcopy(base_plan())
        plan["assumptions"].update(assumptions)
        c = ensure_engine_config(build_plan_from_json(plan, ""), source="test_law_scenario")
        rows = project(c)
        return c, (rows[0] if isinstance(rows, tuple) else rows)

    def test_resolver_defaults_and_fallbacks(self):
        from src.tax_assumptions import resolve_law_scenario as r
        self.assertFalse(r("", "", 2026, _n)["active"])
        self.assertFalse(r("current_law", "", 2026, _n)["active"])
        hi = r("higher_rates", "", 2026, _n)
        self.assertTrue(hi["active"])
        self.assertEqual(hi["start_year"], 2026)
        self.assertEqual(r("higher_rates", "2030", 2026, _n)["start_year"], 2030)
        bad = r("bogus", "abc", 2026, _n)
        self.assertFalse(bad["active"])
        self.assertTrue(bad["warning"])

    def test_stressed_brackets_gate_on_year_and_shape(self):
        from src.tax_assumptions import PRE_2018_ORDINARY_RATES, stressed_ordinary_brackets as s
        br = [(i * 10_000.0, (i + 1) * 10_000.0, r) for i, r in
              enumerate((0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37))]
        scen = {"active": True, "start_year": 2030}
        self.assertEqual(s(br, 2029, scen), br)
        self.assertEqual([r for _l, _h, r in s(br, 2030, scen)], list(PRE_2018_ORDINARY_RATES))
        self.assertEqual(s(br[:3], 2031, scen), br[:3])
        self.assertEqual(s(br, 2031, {"active": False, "start_year": 0}), br)

    def test_current_law_is_unchanged_and_stress_raises_federal_tax(self):
        def fed_total(**kw):
            _c, rows = self._rows(**kw)
            return sum(float(r.get("fed_tax", 0.0) or 0.0) for r in rows)
        base = fed_total()
        self.assertEqual(base, fed_total(tax_law_scenario="current_law"))
        self.assertGreater(fed_total(tax_law_scenario="higher_rates"), base)

    def test_effective_payload_reports_scenario(self):
        c, _rows = self._rows(tax_law_scenario="higher_rates", higher_rates_start_year="2031")
        eff = c["tax_assumptions_effective"]["tax_law_scenario"]
        self.assertTrue(eff["active"])
        self.assertEqual(eff["start_year"], 2031)
