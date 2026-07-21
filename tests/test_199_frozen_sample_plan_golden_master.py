"""Mandatory dollar-exact gate against a FROZEN copy of the sample plan.

Wave 1.7 built a synthetic-scenario gate (test_synthetic_golden_master.py)
that reads no client data, plus demoted the real, live-edited sample plan's
dollar pins in test_2_recommendations.py to warn-only, since input/ churns
routinely and that churn was previously conflated with engine regressions.

Both the original panel sign-off (§8 item 6) and the second post-Wave-1
planner review (§10) wanted a THIRD leg in addition to those two: a frozen,
version-controlled copy of a realistic full plan (multiple accounts, lots,
liabilities, insurance, business interests -- everything the synthetic
scenarios don't have) that pins dollar-exact figures as a MANDATORY gate,
decoupled entirely from the live input/ directory. This file is that leg.

This was deliberately not built during Wave 1 -- the user chose
synthetic-only at the time, and building it later needed the 401(k) rollover
fix (which destroyed the pre-tax balance for an owner with no traditional
IRA) to land first, since freezing before that fix would have enshrined a
broken plan as the mandatory baseline. Both preconditions are now satisfied.

The frozen copy lives at tests/fixtures/sample_plan_frozen/ (every
client_*.csv from a clean checkout of the commit this file was authored
against). To update it after a deliberate plan-shape change: copy the new
client_*.csv files over the ones in that directory, regenerate the two pins
below via the __main__ block, and update this docstring's commit reference.
Last regenerated against commit fa6652b.

Landmine avoided, documented rather than fixed: src/data_io.py's parse_client
loads client_holdings.csv via
``candidate_input_files('client_holdings.csv', ..., root=Path(_project_root))``
with an EXPLICIT root kwarg, so RETIREMENT_SYSTEM_WORKSPACE_ROOT alone does
NOT redirect holdings resolution -- only the sectioned client_data.csv merge
honors it. Confirmed empirically before this file was written: pointing only
the workspace root at a temp copy while leaving client_holdings.csv out of it
produced IDENTICAL results, proving holdings were still being read from the
real repo input/. Fixing that root= hardcode belongs to a future item (it
would affect the Android/mobile workspace-redirection story generally, not
just this test) -- this file works around it locally by monkeypatching
candidate_input_files for the duration of the frozen build only, verified
empirically (see the two PASS checks in this file's development history) to
correctly redirect holdings to the frozen copy and to exactly reproduce a
direct run against the source commit's real input/.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"

# Regenerated 2026-07-20 against commit fa6652b, after fixing a hermeticity
# bug in this file (see test_frozen_plan_dollar_figures_are_exact's comment):
# parse_client() was being called OUTSIDE the frozen_holdings_prices block, so
# c['balances'] depended on ambient pricing-cache state rather than being
# truly pinned. The two values below are correct; they happen to equal
# test_2_recommendations.py's pre-401(k)-fix pins, which makes sense once
# verified: this frozen household holds both a 401(k) AND a traditional IRA,
# so it never exercises the destination==source path the rollover bug required
# -- the fix legitimately has zero effect on this specific plan's numbers.
#
# Re-pinned 2026-07-21 — Wave 4 item 4.2 (P4): the frozen fixture's
# client_assets.csv has DAF enabled ($20,000 contribution in 2026), and this
# item wires a DAF contribution into the itemized deduction stack (60%/30%
# AGI-limited, 5-year carryforward) for the first time -- previously
# daf_contrib_yr was pure cash outflow with no tax effect at all (despite
# GOLDEN_MASTER_CHANGELOG.md's 2026-07-08 "DAF activation baseline" entry
# describing a tax-reducing effect that, per this codebase, did not actually
# exist yet; that entry's terminal-NW/lifetime-tax movement at the time came
# from something else). Terminal NW rises (the $20k contribution's -0.005*agi
# phaseout on char plus the real DAF deduction beats the cash cost, and the
# tax savings compound); lifetime tax drops from the real deduction.
PINNED_TERMINAL_NW = 6555144.64
PINNED_LIFETIME_TAX = 1524551.07


def _frozen_config():
    import src.data_io as _data_io
    from src.data_io import load_csv, parse_client
    from src.plan_config import ensure_engine_config
    from src.workspace_context import candidate_input_files as _real_candidate_input_files

    workspace = Path(tempfile.mkdtemp(prefix="frozen_sample_plan_"))
    (workspace / "input").mkdir(parents=True)
    for f in FROZEN_DIR.glob("client_*.csv"):
        shutil.copy(f, workspace / "input" / f.name)

    def _redirected(filename, workspace_id=None, root=None):
        return _real_candidate_input_files(filename, workspace_id, root=workspace)

    _data_io.candidate_input_files = _redirected
    try:
        data = load_csv(workspace / "input" / "client_data.csv")
        c = parse_client(data, "")
    finally:
        _data_io.candidate_input_files = _real_candidate_input_files
        shutil.rmtree(workspace, ignore_errors=True)

    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return ensure_engine_config(c, source="test")


class FrozenSamplePlanGoldenMasterTests(unittest.TestCase):
    """Mandatory: a regression here means the ENGINE changed, since the input
    is a static, committed copy no one edits day to day. Contrast with
    test_2_recommendations.py's warn-only pins, which track the live plan."""

    def test_frozen_plan_dollar_figures_are_exact(self):
        from src.data_io import summarize_validation
        from src.planning_engines import project
        from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

        # _frozen_config() calls parse_client(), which itself calls
        # market_data.configure_holdings_pricing() and computes c['balances']
        # from priced holdings -- so it must be INSIDE the frozen-prices block,
        # matching test_2_recommendations.py's sample_config()+project() pattern.
        # Calling it outside (as an earlier version of this file did) makes
        # c['balances'] depend on whatever pricing-cache state happens to be
        # ambient (e.g. output/market_price_cache.json), which differs between
        # a warm main checkout and a fresh git worktree with no such file --
        # producing a large, environment-dependent, and entirely spurious
        # "regression" with no relation to any actual code change. Confirmed
        # empirically: reverting an unrelated Wave-2 change to bit-identical
        # parent-commit code in its own worktree still showed the same delta,
        # which only a pricing-cache difference between directories explains.
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = _frozen_config()
            rows = project(c)
        summary = summarize_validation(rows, c)

        self.assertEqual(summary["fail_count"], 0)
        self.assertEqual(summary["warn_count"], 0)

        terminal_nw = rows[-1]["total_nw"]
        lifetime_tax = sum(r["total_tax"] for r in rows)
        self.assertAlmostEqual(
            terminal_nw, PINNED_TERMINAL_NW, places=2,
            msg=(
                f"Frozen-plan terminal NW moved from {PINNED_TERMINAL_NW:,.2f} to "
                f"{terminal_nw:,.2f}. The frozen fixture did not change, so this is an "
                f"engine regression, not routine data drift. If the change is intentional "
                f"(a deliberate engine/tax-law update), regenerate the pin via this file's "
                f"__main__ block and update PINNED_TERMINAL_NW with a note why."
            ),
        )
        self.assertAlmostEqual(
            lifetime_tax, PINNED_LIFETIME_TAX, places=2,
            msg=(
                f"Frozen-plan lifetime tax moved from {PINNED_LIFETIME_TAX:,.2f} to "
                f"{lifetime_tax:,.2f}. Same as above: the fixture is static, so this is "
                f"an engine change."
            ),
        )

    def test_frozen_fixture_is_isolated_from_the_real_input_directory(self):
        """Guardrail for this file itself: prove the redirect is real, not a
        no-op that happens to agree with the live plan by coincidence. Runs a
        second frozen build with client_holdings.csv withheld from the
        redirected workspace; if parse_client fell back to the real
        input/client_holdings.csv, this would silently produce the SAME
        balances as the full frozen build instead of different ones."""
        import src.data_io as _data_io
        from src.data_io import load_csv, parse_client
        from src.workspace_context import candidate_input_files as _real_candidate_input_files

        full = _frozen_config()
        full_balance = sum(full["balances"].values())

        workspace = Path(tempfile.mkdtemp(prefix="frozen_sample_plan_noholdings_"))
        (workspace / "input").mkdir(parents=True)
        for f in FROZEN_DIR.glob("client_*.csv"):
            if f.name == "client_holdings.csv":
                continue
            shutil.copy(f, workspace / "input" / f.name)

        def _redirected(filename, workspace_id=None, root=None):
            return _real_candidate_input_files(filename, workspace_id, root=workspace)

        _data_io.candidate_input_files = _redirected
        try:
            data = load_csv(workspace / "input" / "client_data.csv")
            c = parse_client(data, "")
        finally:
            _data_io.candidate_input_files = _real_candidate_input_files
            shutil.rmtree(workspace, ignore_errors=True)

        no_holdings_balance = sum(c["balances"].values())
        self.assertNotEqual(
            full_balance, no_holdings_balance,
            "Removing client_holdings.csv from the redirected workspace had no effect on "
            "total balances. This means the frozen build silently fell back to the real "
            "repo input/client_holdings.csv instead of the frozen copy -- the mandatory "
            "gate above would be pinned against live, not frozen, data.",
        )


if __name__ == "__main__":
    # Regenerate the pins after a deliberate change to the frozen fixture.
    from src.data_io import summarize_validation
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        rows = project(c)
    print(f"PINNED_TERMINAL_NW = {round(rows[-1]['total_nw'], 2)!r}")
    print(f"PINNED_LIFETIME_TAX = {round(sum(r['total_tax'] for r in rows), 2)!r}")
