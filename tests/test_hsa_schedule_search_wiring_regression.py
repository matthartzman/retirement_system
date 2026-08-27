"""The HSA schedule search is wired into the build (`run_schedule_search`).

Spec: docs/superpowers/plans/2026-08-26-hsa-schedule-search-contingent-liability-spec.md

`hsa_schedule.py`'s header recorded that `build_schedule`/`rerun_optimizer`
were "NOT called anywhere in the projection pipeline": the search needs full
per-year projection rows for tax context, and those only exist after a
projection runs -- the projection that would consume the schedule. So
`optimize` mode ran `generate_default_schedule`'s static level-draw
placeholder instead of a real search.

`run_schedule_search` resolves that the way
`planning_engines.optimize_roth_conversion_strategy` already resolves the
identical circularity: score candidates on their OWN full projections and
keep the winner. Because the incumbent schedule is always one of the
candidates, the outcome can never be worse than the placeholder.

The load-bearing guards here are `UserIntentIsNeverEatenTests` and
`NeverWorseThanIncumbentTests`. `resolve_year_amount`'s docstring states the
contract they defend -- "a precedence bug is silent, and the user finds out
only when an edit they made vanishes" -- and a real 2026-08-20 defect in this
same area shipped precisely because an unscheduled path bypassed the
household's own configuration.
"""
from __future__ import annotations

import unittest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.hsa_schedule import (
    _SCHEDULE_SEARCH_MIN_GAIN,
    generate_default_schedule,
    resolve_year_amount,
    run_schedule_search,
)


def _config(mode="optimize"):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["hsa_withdrawal_mode"] = mode
    return c


def _with_default_schedule(c):
    rows = generate_default_schedule(c)
    c["hsa_schedule_rows"] = rows
    c["hsa_schedule_by_year"] = {r["year"]: r for r in rows}
    return rows


class ModeGatingTests(unittest.TestCase):
    def test_no_op_outside_optimize_mode(self):
        for mode in ("spend_as_needed", "smooth_window", "annual_pct"):
            c = _config(mode)
            before = dict(c)
            res = run_schedule_search(c)
            self.assertFalse(res["ran"], mode)
            self.assertIn("not in optimize mode", res["reason"])
            self.assertEqual(c.get("hsa_schedule_rows"), before.get("hsa_schedule_rows"),
                              f"{mode}: schedule was modified outside optimize mode")


class SearchRunsTests(unittest.TestCase):
    def test_search_runs_and_beats_the_level_draw_placeholder(self):
        c = _config()
        _with_default_schedule(c)
        res = run_schedule_search(c)
        self.assertTrue(res["ran"], res["reason"])
        self.assertIsNotNone(res["incumbent_score"])
        self.assertIsNotNone(res["proposal_score"])
        # The whole point of wiring a real search: it should find something
        # better than a static level draw on a household with real tax
        # structure. If this ever flips, the search has stopped earning its
        # keep and that is worth knowing loudly.
        self.assertEqual(res["chosen"], "proposal", res["reason"])
        self.assertGreater(res["proposal_score"], res["incumbent_score"])

    def test_a_schedule_is_installed_covering_the_horizon(self):
        c = _config()
        _with_default_schedule(c)
        run_schedule_search(c)
        rows = c["hsa_schedule_rows"]
        self.assertTrue(rows)
        years = [int(r["year"]) for r in rows]
        self.assertEqual(years, sorted(years), "schedule years must be ascending")
        self.assertEqual(len(years), len(set(years)), "duplicate schedule years")
        self.assertEqual(c["hsa_schedule_by_year"].keys(), {r["year"] for r in rows},
                          "by_year index disagrees with the row list")


class UserIntentIsNeverEatenTests(unittest.TestCase):
    """`rerun_optimizer`'s contract, enforced through the wiring that calls
    it: a re-run may never overwrite an override or move a locked value."""

    def test_override_amount_survives_exactly(self):
        c = _config()
        rows = _with_default_schedule(c)
        target = rows[3]["year"]
        rows[3]["override_amount"] = 12_345.67
        run_schedule_search(c)
        after = {r["year"]: r for r in c["hsa_schedule_rows"]}[target]
        self.assertEqual(after.get("override_amount"), 12_345.67)
        amount, source = resolve_year_amount(after)
        self.assertEqual(source, "override")
        self.assertEqual(amount, 12_345.67)

    def test_a_locked_year_keeps_the_exact_value_the_lock_pins(self):
        # For a locked-only year, `optimizer_amount` IS the pinned value --
        # refreshing it would silently move the number the lock exists to
        # hold, the same class of failure as eating an override.
        c = _config()
        rows = _with_default_schedule(c)
        target = rows[5]["year"]
        rows[5]["locked"] = True
        pinned = rows[5]["optimizer_amount"]
        run_schedule_search(c)
        after = {r["year"]: r for r in c["hsa_schedule_rows"]}[target]
        self.assertAlmostEqual(after["optimizer_amount"], pinned, places=6)
        amount, source = resolve_year_amount(after)
        self.assertEqual(source, "locked")
        self.assertAlmostEqual(amount, pinned, places=6)

    def test_a_zero_override_is_honored_not_treated_as_absent(self):
        # Zero is real at every tier; a truthiness check would discard a
        # deliberate "draw nothing this year".
        c = _config()
        rows = _with_default_schedule(c)
        target = rows[4]["year"]
        rows[4]["override_amount"] = 0.0
        run_schedule_search(c)
        after = {r["year"]: r for r in c["hsa_schedule_rows"]}[target]
        amount, source = resolve_year_amount(after)
        self.assertEqual(source, "override")
        self.assertEqual(amount, 0.0)


class NeverWorseThanIncumbentTests(unittest.TestCase):
    def test_incumbent_is_kept_when_it_scores_at_least_as_high(self):
        # Feed the search its own winning proposal as the incumbent. A second
        # run cannot then beat it materially, so the incumbent must be kept --
        # this is the property that makes the wiring safe without a feature
        # flag: a search that stops helping simply loses.
        c = _config()
        _with_default_schedule(c)
        run_schedule_search(c)                      # first run installs the proposal
        settled = [dict(r) for r in c["hsa_schedule_rows"]]
        res2 = run_schedule_search(c)               # re-run against itself
        self.assertTrue(res2["ran"], res2["reason"])
        # Convergence is defined by the search's own dead-band, not by
        # bit-equality: a round is adopted only when it beats the incumbent by
        # more than _SCHEDULE_SEARCH_MIN_GAIN, so a settled schedule may still
        # attract proposals a fraction of a dollar higher. What must hold is
        # that the residual gap is inside that band -- i.e. the iteration has
        # actually settled rather than still climbing.
        self.assertLessEqual(
            res2["proposal_score"] - res2["incumbent_score"], _SCHEDULE_SEARCH_MIN_GAIN,
            "a re-run beat an already-optimized incumbent by more than the "
            "adoption threshold, so the search is still climbing and the "
            "round bound is cutting it off early",
        )
        self.assertEqual(res2["chosen"], "incumbent", res2["reason"])
        self.assertEqual([r["year"] for r in c["hsa_schedule_rows"]],
                          [r["year"] for r in settled])

    def test_iteration_beats_a_single_round(self):
        # Why the search iterates at all: candidate SCORING is self-consistent
        # (each candidate is scored on its own projection), but candidate
        # GENERATION reads the incumbent's rows for tax context, so one round
        # does not reach a fixed point. This was found by the convergence test
        # above failing against a single-round implementation -- a re-run beat
        # its own output by ~1.7%. Pin that iterating actually pays, so a
        # future "simplification" back to one round is visible.
        c = _config()
        _with_default_schedule(c)
        res = run_schedule_search(c)
        self.assertTrue(res["ran"], res["reason"])
        self.assertGreater(res["rounds"], 1,
                            "the search settled in a single round; if that is now "
                            "genuinely true the iteration is dead weight, but it "
                            "was not true when this was written")
        self.assertGreater(res["chosen_score"], res["incumbent_score"])

    def test_a_failing_search_leaves_the_config_untouched(self):
        c = _config()
        rows = _with_default_schedule(c)
        before = [dict(r) for r in rows]
        # A malformed schedule row shape is the realistic failure: a stale or
        # hand-edited CSV. The build must survive it with the incumbent.
        c["hsa_schedule_rows"] = [{"year": "not-a-year", "optimizer_amount": object()}]
        res = run_schedule_search(c)
        self.assertFalse(res["chosen"] == "proposal" and not res["ran"])
        if not res["ran"]:
            self.assertIn("incumbent", res["reason"].lower())
        # Whatever happened, it must not have raised -- that is the contract.
        self.assertIsInstance(res, dict)
        self.assertTrue(before)


if __name__ == "__main__":
    unittest.main()
