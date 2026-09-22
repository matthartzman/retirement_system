"""W7 (#330 F3): the engine asks ``module_enabled()``, like every other call site.

``deterministic_engine.py`` used to gate ``equity_compensation`` and
``disability_income_insurance`` on a raw ``c['opt']`` read. That read skipped
two things ``module_enabled()`` does:

* the ``RETIREMENT_SYSTEM_FORCE_*`` env overrides, and
* ``effective_enabled_modules()``' prerequisite auto-selection, plus the
  default-on treatment of a key absent from ``c['opt']`` entirely.

Either way the result was the same class of defect: a module the *sheets*
consider on while the *engine* models it as off, so the module's own sheet is
built from a projection that excludes its subject. Nothing pinned that, because
the two fixtures that would have caught it both happen to be immune -- the
frozen sample plan names both toggles explicitly ``FALSE``, and the synthetic
scenarios configure no disability event for a flipped gate to act on. This file
is the missing pin: it constructs the divergence on purpose.

The observable is the DI benefit stream. ``disability_income_insurance`` is the
better probe of the two because ``equity_compensation``'s gate is ANDed with a
non-empty ``c['equity_comp']``, so a plan without grants cannot show the
difference no matter which way the toggle reads.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

import pytest

import src.module_catalog as mc
from tests.golden_pricing import frozen_holdings_prices
from tests.synthetic_plans import SCENARIOS
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace

DI_KEY = "disability_income_insurance"


@contextmanager
def _env(**pairs):
    """Set/clear env vars for the duration of the block."""
    prev = {k: os.environ.get(k) for k in pairs}
    try:
        for k, v in pairs.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _plan_with_a_disability_event(opt):
    """A synthetic plan that actually configures a disability event.

    ``opt=None`` leaves ``c['opt']`` absent entirely, which is what every
    JSON-built plan looks like -- and is itself one of the divergent states,
    since an absent key reads as OFF raw but ON through ``module_enabled()``.
    """
    c = SCENARIOS["baseline_balanced_couple"].build()
    start = c["plan_start"]
    c["disability"] = {
        "simulate_year": start + 1,
        "policies": [{
            "monthly_benefit": 5000.0,
            "benefit_period_years": 3,
            "elimination_days": 0,
            "premium_pre_tax": True,
        }],
    }
    if opt is not None:
        c["opt"] = dict(opt)
    else:
        c.pop("opt", None)
    return c


def _di_benefit_years(c):
    """Years in which the projection paid a DI benefit."""
    from src.planning_engines import project

    with empty_workspace(), frozen_holdings_prices():
        rows = project(c)
    return [r["year"] for r in rows if r.get("disability_benefit")]


class EngineGateAgreesWithTheSheets(unittest.TestCase):
    def test_an_explicit_off_toggle_still_keeps_the_engine_off(self):
        """The ordinary case, unchanged by W7: off means off, in both layers."""
        c = _plan_with_a_disability_event({DI_KEY: False})
        self.assertFalse(mc.module_enabled(c, DI_KEY))
        self.assertEqual(_di_benefit_years(c), [])

    def test_an_explicit_on_toggle_models_the_benefit(self):
        """The control: the engine does react to this plan when the gate is on,
        so a later assertion of "no benefit" means the gate, not a dead fixture.
        """
        c = _plan_with_a_disability_event({DI_KEY: True})
        self.assertTrue(mc.module_enabled(c, DI_KEY))
        self.assertTrue(_di_benefit_years(c))

    def test_a_plan_with_no_opt_map_matches_what_the_sheets_would_build(self):
        """An absent toggle defaults to ON (``_base_enabled``'s documented
        contract, so always-on core sheets are never dropped). Before W7 the
        engine read that same absent key as OFF -- the sheets said on, the
        projection said off.
        """
        c = _plan_with_a_disability_event(None)
        self.assertTrue(mc.module_enabled(c, DI_KEY))
        self.assertTrue(
            _di_benefit_years(c),
            "a plan whose sheets treat DI as on must be projected with DI on",
        )

    def test_force_enable_reaches_the_engine_too(self):
        """``RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES`` is how tests and support
        sessions pin a module on. The raw read ignored it entirely.
        """
        c = _plan_with_a_disability_event({DI_KEY: False})
        with _env(RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES=DI_KEY):
            self.assertTrue(mc.module_enabled(c, DI_KEY))
            self.assertTrue(_di_benefit_years(c))

    def test_force_disable_still_wins_over_everything(self):
        """Precedence rule (1) in ``module_enabled``: an explicit force-off beats
        a force-on. Worth pinning here because the engine now inherits the whole
        precedence ladder, not just the parts W7 was aimed at.
        """
        c = _plan_with_a_disability_event({DI_KEY: True})
        with _env(RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES=DI_KEY,
                  RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES=DI_KEY):
            self.assertFalse(mc.module_enabled(c, DI_KEY))
            self.assertEqual(_di_benefit_years(c), [])

    def test_prerequisite_auto_selection_reaches_the_engine(self):
        """W7's stated rationale, exercised through the real resolver.

        No module declares either engine-participating module as a prerequisite
        today, so this edge is added for the length of the test rather than
        waited for. The mechanism is entirely generic -- the day some module
        does declare one, the engine follows without further work, and this
        pins that.
        """
        c = _plan_with_a_disability_event({DI_KEY: False, "life_insurance_need": True})
        self.assertFalse(mc.module_enabled(c, DI_KEY))  # baseline: nothing pulls it in

        borrower = mc.CATALOG["life_insurance_need"]
        original = borrower.requires_outputs
        object.__setattr__(borrower, "requires_outputs", tuple(original) + (DI_KEY,))
        try:
            self.assertIn(DI_KEY, mc.effective_enabled_modules(c))
            self.assertTrue(mc.module_enabled(c, DI_KEY))
            self.assertTrue(
                _di_benefit_years(c),
                "a module auto-enabled as a prerequisite must be modelled by "
                "the engine, not just given a sheet",
            )
        finally:
            object.__setattr__(borrower, "requires_outputs", original)


class TheGateAloneIsInert(unittest.TestCase):
    """Why W7 moves no golden master.

    The gate flipping on is not by itself a projection change: ``income.py``
    only pays a benefit when the plan configures both a simulated year and at
    least one policy. Every current fixture fails that inner guard, which is
    what makes W7's golden-master regeneration a zero delta rather than a
    reviewer's judgement call over thousands of moved numbers.
    """

    def test_no_synthetic_scenario_configures_a_disability_event(self):
        for name, scenario in SCENARIOS.items():
            di = scenario.build().get("disability", {}) or {}
            with self.subTest(scenario=name):
                self.assertFalse(
                    int(di.get("simulate_year", 0) or 0) and (di.get("policies") or []),
                    f"{name} now configures a disability event, so the DI gate "
                    f"is no longer inert for it -- re-measure the golden masters",
                )

    def test_the_gate_is_a_no_op_without_a_configured_event(self):
        """Same plan, both gate states, no configured event: identical rows."""
        from src.planning_engines import project

        def rows_for(opt):
            c = SCENARIOS["baseline_balanced_couple"].build()
            c.pop("disability", None)
            c["opt"] = dict(opt)
            with empty_workspace(), frozen_holdings_prices():
                return project(c)

        self.assertEqual(rows_for({DI_KEY: False}), rows_for({DI_KEY: True}))


if __name__ == "__main__":
    unittest.main()
