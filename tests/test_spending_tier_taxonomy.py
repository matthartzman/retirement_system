"""Unit and reconciliation coverage for the Phase 0 spending-tier taxonomy.

Phase 0 of the optimization refactor (documentation/optimization refactor
plan) adds a classification layer above the existing spending taxonomy:
every category resolves to one of essential / important / discretionary /
contingent_liability. Per that plan's acceptance criteria, this is a
purely additive reporting layer -- it must never change spend_base or any
other existing dollar total, and the golden-master suite is the proof of
that (no pins move). This file covers the classification logic itself and
the row['spend_by_tier'] reconciliation identity.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src import spending_budget_resolver as sbr
from src import spending_tracker as st


class ResolveSpendingTierDefaultsTests(unittest.TestCase):
    """Category/group/tracking-type default resolution, no overrides."""

    def test_grocery_is_essential(self):
        self.assertEqual(
            sbr.resolve_spending_tier("groceries", "Core Expenses", "Food & Dining"),
            sbr.SPENDING_TIER_ESSENTIAL,
        )

    def test_restaurants_is_important(self):
        self.assertEqual(
            sbr.resolve_spending_tier("restaurants_bars", "Core Expenses", "Food & Dining"),
            sbr.SPENDING_TIER_IMPORTANT,
        )

    def test_auto_transport_group_is_essential(self):
        self.assertEqual(
            sbr.resolve_spending_tier("auto_fuel", "Core Expenses", "Auto & Transport"),
            sbr.SPENDING_TIER_ESSENTIAL,
        )

    def test_shopping_group_is_discretionary(self):
        self.assertEqual(
            sbr.resolve_spending_tier("clothing_jewelry", "Core Expenses", "Shopping"),
            sbr.SPENDING_TIER_DISCRETIONARY,
        )

    def test_travel_tracking_type_is_discretionary(self):
        self.assertEqual(
            sbr.resolve_spending_tier("travel_vacation", "Travel", "Travel"),
            sbr.SPENDING_TIER_DISCRETIONARY,
        )

    def test_large_discretionary_tracking_type_is_discretionary(self):
        self.assertEqual(
            sbr.resolve_spending_tier("significant_gifts", "Large Discretionary", "Large Gifts"),
            sbr.SPENDING_TIER_DISCRETIONARY,
        )

    def test_home_improvement_group_is_discretionary(self):
        self.assertEqual(
            sbr.resolve_spending_tier("home_improvement", "Housing", "Home Improvement"),
            sbr.SPENDING_TIER_DISCRETIONARY,
        )

    def test_mortgage_is_essential(self):
        self.assertEqual(
            sbr.resolve_spending_tier("mortgage", "Housing", "Mortgage"),
            sbr.SPENDING_TIER_ESSENTIAL,
        )

    def test_medicare_premium_is_essential(self):
        self.assertEqual(
            sbr.resolve_spending_tier("medicare_part_b", "Wellness", "Healthcare Premium"),
            sbr.SPENDING_TIER_ESSENTIAL,
        )

    def test_fitness_wellness_detail_is_important(self):
        self.assertEqual(
            sbr.resolve_spending_tier("fitness", "Wellness", "Wellness Budget Detail"),
            sbr.SPENDING_TIER_IMPORTANT,
        )

    def test_long_term_care_id_hint_is_contingent(self):
        self.assertEqual(
            sbr.resolve_spending_tier("long_term_care_facility", "Core Expenses", "Other"),
            sbr.SPENDING_TIER_CONTINGENT,
        )

    def test_income_is_unclassified(self):
        self.assertIsNone(sbr.resolve_spending_tier("paychecks", "Income", "Income"))

    def test_business_is_unclassified(self):
        self.assertIsNone(sbr.resolve_spending_tier("business_travel_meals", "Business", "Business"))

    def test_unmapped_category_falls_back_to_important(self):
        self.assertEqual(
            sbr.resolve_spending_tier("some_brand_new_category", "Core Expenses", "Some New Group"),
            sbr.SPENDING_TIER_IMPORTANT,
        )

    def test_every_tier_key_is_a_declared_constant(self):
        # Guards against a typo in SPENDING_TIERS silently creating a fifth
        # tier that nothing downstream recognizes.
        declared = {
            sbr.SPENDING_TIER_ESSENTIAL, sbr.SPENDING_TIER_IMPORTANT,
            sbr.SPENDING_TIER_DISCRETIONARY, sbr.SPENDING_TIER_CONTINGENT,
        }
        self.assertEqual(set(sbr.SPENDING_TIERS.keys()), declared)
        self.assertEqual(set(sbr.SPENDING_TIER_CUT_ORDER), declared)


class SpendingTierOverrideRoundTripTests(unittest.TestCase):
    """Household overrides beat every built-in default and persist via CSV."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "input").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_override_beats_default_and_can_be_cleared(self):
        # groceries defaults to essential (see above).
        self.assertEqual(sbr.load_spending_tier_overrides(self.root), {})
        sbr.save_spending_tier_override(self.root, "groceries", sbr.SPENDING_TIER_DISCRETIONARY, "test override")
        overrides = sbr.load_spending_tier_overrides(self.root)
        self.assertEqual(overrides.get("groceries"), sbr.SPENDING_TIER_DISCRETIONARY)
        resolved = sbr.resolve_spending_tier("groceries", "Core Expenses", "Food & Dining", overrides)
        self.assertEqual(resolved, sbr.SPENDING_TIER_DISCRETIONARY)

        # Clearing (falsy tier) removes the override; default resumes.
        sbr.save_spending_tier_override(self.root, "groceries", "")
        overrides = sbr.load_spending_tier_overrides(self.root)
        self.assertNotIn("groceries", overrides)

    def test_invalid_tier_value_in_csv_is_ignored(self):
        path = self.root / "input" / "client_spending_tier_overrides.csv"
        path.write_text("category_id,tier,notes\ngroceries,not_a_real_tier,bad row\n", encoding="utf-8")
        overrides = sbr.load_spending_tier_overrides(self.root)
        self.assertEqual(overrides, {})


class SpendBaseTierSharesTests(unittest.TestCase):
    """resolve_spending_inputs() emits tier shares that sum to ~1.0 and
    correctly exclude Housing/Wellness/Travel/Business from spend_base."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "input").mkdir(parents=True)
        st.save_taxonomy_category(self.root, "Core Expenses", "Food & Dining", "groceries", "Groceries")
        st.save_taxonomy_category(self.root, "Core Expenses", "Food & Dining", "restaurants_bars", "Restaurants & Bars")
        st.save_taxonomy_category(self.root, "Core Expenses", "Shopping", "clothing_jewelry", "Clothing & Jewelry")
        st.save_taxonomy_category(self.root, "Housing", "Mortgage", "mortgage", "Mortgage")
        # resolve_spending_inputs reads the unified budget (client_spending_budget.csv
        # via _budget_indexes/load_unified_budget), not the legacy group-level
        # spending_budget.csv that save_budget() writes.
        st.save_unified_budget(self.root, [
            {"kind": "category", "key": "groceries", "annual_budget": "12000"},
            {"kind": "category", "key": "restaurants_bars", "annual_budget": "6000"},
            {"kind": "category", "key": "clothing_jewelry", "annual_budget": "2000"},
            {"kind": "category", "key": "mortgage", "annual_budget": "24000"},
        ])

    def tearDown(self):
        self._tmp.cleanup()

    def test_shares_sum_to_one_and_exclude_housing(self):
        resolved = sbr.resolve_spending_inputs(root=self.root, year_range=[2026])
        # spend_base = groceries + restaurants + clothing = 20,000 (mortgage,
        # Housing, is excluded from spend_base entirely -- unchanged behavior).
        self.assertAlmostEqual(resolved["spend_base"], 20000.0, places=2)
        shares = resolved["spend_base_tier_shares"]
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=6)
        # essential=12000, important=6000, discretionary=2000 of a 20000 base.
        self.assertAlmostEqual(shares[sbr.SPENDING_TIER_ESSENTIAL], 12000 / 20000, places=6)
        self.assertAlmostEqual(shares[sbr.SPENDING_TIER_IMPORTANT], 6000 / 20000, places=6)
        self.assertAlmostEqual(shares[sbr.SPENDING_TIER_DISCRETIONARY], 2000 / 20000, places=6)
        self.assertNotIn(sbr.SPENDING_TIER_CONTINGENT, shares)

    def test_zero_spend_base_yields_empty_shares(self):
        empty_root = Path(tempfile.mkdtemp())
        (empty_root / "input").mkdir(parents=True, exist_ok=True)
        resolved = sbr.resolve_spending_inputs(root=empty_root, year_range=[2026])
        self.assertEqual(resolved["spend_base"], 0.0)
        self.assertEqual(resolved["spend_base_tier_shares"], {})


class DeterministicEngineSpendByTierReconciliationTests(unittest.TestCase):
    """row['spend_by_tier'] must sum to row['total_spend'] every year --
    the accounting-identity discipline the plan calls for starting in
    Phase 0, verified against the frozen full-household sample plan."""

    def test_spend_by_tier_sums_to_total_spend_every_year(self):
        from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
        from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
        from src.planning_engines import project

        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = _frozen_config()
            rows = project(c)

        self.assertTrue(rows, "frozen plan produced no projection rows")
        checked_any_nonzero = False
        for row in rows:
            tier_total = sum(row.get("spend_by_tier", {}).values())
            total_spend = row.get("total_spend", 0.0)
            self.assertAlmostEqual(tier_total, total_spend, places=1,
                                    msg=f"year {row.get('year')}: tier total {tier_total} != total_spend {total_spend}")
            if total_spend > 0:
                checked_any_nonzero = True
        self.assertTrue(checked_any_nonzero, "no year had nonzero total_spend to reconcile")

    def test_frozen_plan_golden_master_pins_unchanged_by_tier_reporting(self):
        # Belt-and-suspenders companion to the mandatory golden-master gate:
        # spend_by_tier is new, additive output -- it must not perturb any
        # existing dollar total or introduce new solvency failures/warnings.
        # This deliberately does not duplicate the mandatory gate's exact
        # dollar pins (PINNED_TERMINAL_NW / PINNED_LIFETIME_TAX in
        # test_frozen_sample_plan_golden_master_regression.py) so there is
        # only one place to update when those are intentionally regenerated.
        from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
        from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
        from src.data_io import summarize_validation
        from src.planning_engines import project

        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = _frozen_config()
            rows = project(c)
        summary = summarize_validation(rows, c)
        self.assertEqual(summary["fail_count"], 0)
        self.assertEqual(summary["warn_count"], 0)
        self.assertIsInstance(rows[-1]["total_nw"], (int, float))


if __name__ == "__main__":
    unittest.main()
