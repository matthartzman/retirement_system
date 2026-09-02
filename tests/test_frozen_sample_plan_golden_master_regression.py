"""Mandatory dollar-exact gate against a FROZEN copy of the sample plan.

Wave 1.7 built a synthetic-scenario gate (test_synthetic_golden_master.py)
that reads no client data, plus demoted the real, live-edited sample plan's
dollar pins in test_recommendations_functional.py to warn-only, since input/ churns
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

When this file's mandatory test fails (PINNED_TERMINAL_NW / PINNED_LIFETIME_TAX
no longer match), do NOT hand-edit the two constants below -- see
documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md for the full recovery process
(decision tree, the two method traps that previously produced a confidently
wrong bisect result, and tools/regen_golden_master.py). A hand-edited pin with
no matching provenance update is caught by
tests/test_golden_master_pin_provenance.py, which fails the suite.

Landmine, now fixed: src/data_io.py's parse_client used to load
client_holdings.csv via
``candidate_input_files('client_holdings.csv', ..., root=Path(_project_root))``
with an EXPLICIT root kwarg, so RETIREMENT_SYSTEM_WORKSPACE_ROOT alone did
NOT redirect holdings resolution -- only the sectioned client_data.csv merge
honored it. Confirmed empirically before the fix: pointing only the
workspace root at a temp copy while leaving client_holdings.csv out of it
produced IDENTICAL results, proving holdings were still being read from the
real repo input/. The hardcoded root= kwarg has since been removed from
data_io's plan-data lookups (see ``_frozen_config()``'s docstring below), so
RETIREMENT_SYSTEM_WORKSPACE_ROOT alone now correctly redirects holdings too
-- verified by test_frozen_fixture_is_isolated_from_the_real_input_directory
below, which fails loudly if this ever regresses.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"

# Pinned wall-clock date. plan_start derives from the current year and the YTD
# blend prorates the current year by day-of-year, so the pins below are only
# reproducible with the date held still. Changing this value re-pins the test.
FROZEN_TODAY = "2026-08-04"

# Regenerated 2026-07-20 against commit fa6652b, after fixing a hermeticity
# bug in this file (see test_frozen_plan_dollar_figures_are_exact's comment):
# parse_client() was being called OUTSIDE the frozen_holdings_prices block, so
# c['balances'] depended on ambient pricing-cache state rather than being
# truly pinned. The two values below are correct; they happen to equal
# test_recommendations_functional.py's pre-401(k)-fix pins, which makes sense once
# verified: this frozen household holds both a 401(k) AND a traditional IRA,
# so it never exercises the destination==source path the rollover bug required
# -- the fix legitimately has zero effect on this specific plan's numbers.
#
# Re-pinned 2026-07-29 — business-expense/SEHI AGI+cash-flow fix: Schedule C
# business expenses and home-office deduction (biz_exp/home_off) previously
# only reduced the SE-tax and QBI bases -- never AGI/state-tax income, and
# never appeared as a cash outflow anywhere, so gross earned income was both
# over-taxed relative to real Schedule C treatment (only a partial 20% QBI
# credit instead of the full deduction) AND fully available to spend/save
# even though a real household pays those expenses out of pocket. Introduced
# net_earned_taxable (net of biz_exp/home_off; S-Corp uses salary+distribution)
# as the figure that actually drives AGI/state-tax/cash-flow, itemized a new
# "Business Expenses" cash-flow line (Option A), and gated the S-Corp SEHI
# deduction on sehi_added_to_w2 (also wired the previously-dead
# health_insurance_premiums_annual field as an optional override of the
# Wellness-derived SEHI estimate). Lifetime tax drops slightly (business
# expenses are now a full deduction, not a 20%-QBI-only partial credit);
# terminal NW drops more (the plan now correctly funds real business cash
# costs from spendable income each year instead of treating that money as
# available to compound, so less of it accumulates for retirement).
#
# Also discovered while re-pinning: this "frozen" fixture is not actually
# hermetic against wall-clock date -- regenerating on 2026-07-28 vs 2026-07-29
# (both against the identical frozen CSVs, no code change between them)
# produced different pins (6521581.18 -> 6487999.96), evidently from
# something in the projection keying off the real current date rather than a
# value fixed by the frozen inputs (likely the YTD-blend/remaining-year
# proration path). That is a pre-existing hermeticity gap in this test, not
# introduced by this change and not fixed here -- flagged for separate
# follow-up. Values below were regenerated on 2026-07-29 and confirmed
# stable across repeated runs on that date.
#
# Re-pinned 2026-08-04 -- fixture made self-contained (system review
# 2026-08-04). The hermeticity gap noted immediately above is now CLOSED on
# both axes: the date is pinned via FROZEN_TODAY, and every input is staged
# from FROZEN_DIR rather than only client_*.csv. See _frozen_config's
# docstring for the three specific leaks that were removed.
#
# Terminal NW moved 6,487,999.96 -> 4,057,824.89 and lifetime tax
# 1,517,126.54 -> 1,328,438.80. This is NOT an engine change: it is the
# fixture finally measuring the household it actually describes. Previously
# client_holdings.csv resolved to the REAL input/ (data_io hardcoded root=,
# fixed in e24da48), so the plan ran on ~$3.69M of unreconciled stated assets
# instead of its own ~$2.81M of priced holdings. The older, larger pins
# described a household that never existed in the fixture.
#
# At its true asset level the plan depletes in its final five years, so
# fail_count is now pinned rather than asserted to be zero. See the assertion
# for why that is a stricter gate, not a weaker one.
#
# Corrected 2026-08-10 -- the two values below were STALE, not drifted. They
# were never reproducible: running this file's own __main__ regen block at
# 77b7676 (the commit that first introduced 5,824,239.30, and the same commit
# that added the home-purchase scenario described below) already prints
# 6,044,750.40. So do the commits after it -- 56c457a, 52ffe60, 3b1cedf,
# 531c883, 355564d, and main -- and so does CI on BOTH windows-latest/3.11 and
# windows-latest/3.14, to the same 6044750.402866955. The frozen fixture is
# byte-unchanged since 56c457a.
#
# In other words: the 2026-08-05 regen note immediately below was written but
# the two numbers above it were never updated to match, so this gate has been
# red since it was authored and has never once passed. It was not noticed
# because CI is red on main for several unrelated reasons (a hardcoded
# C:\RetirementPlanning path in a frontend test, missing input/ CSVs on the
# runner, Playwright e2e timeouts), so one more red test did not stand out.
#
# This is therefore NOT an engine regression and regenerating does not mask
# one: the computed value has been constant across every commit and both
# interpreters since the pin was written. Verified by bisect + direct
# per-commit measurement, 2026-08-10.
#
# ---------------------------------------------------------------------------
# Re-pinned 2026-08-12 -- 6,044,750.40 was a BUG ARTIFACT, and the 08-10
# analysis above was measuring the bug rather than the fixture.
#
# data_io.parse_client passed spending_budget_resolver an explicit
# ``root=`` computed from ``__file__``, so the unified spending budget,
# spending taxonomy, and optional-module gating were resolved against the
# REPO's input/ directory and RETIREMENT_SYSTEM_WORKSPACE_ROOT was ignored for
# those three files. The frozen fixture ships its own copies of all three; they
# were never read.
#
# That made this gate answer differently depending on the machine it ran on:
#
#   fresh checkout / worktree / CI  input/*.csv is gitignored and absent, so
#                                   the resolver found nothing and fell through
#                                   to legacy fallbacks   -> 6,044,750.40
#   a warm working copy             the resolver read the developer's LIVE
#                                   plan                  -> 5,824,239.30
#
# Both readings ignore the fixture. The 08-10 measurements (bisect, per-commit,
# CI) were all taken in the first environment, which is why they agreed with
# each other, agreed across interpreters, and still disagreed with a working
# copy -- and why CI stayed green while the same commit failed locally.
#
# With the hardcoded root removed (src/data_io.py, same commit as this note),
# the frozen build reads the frozen spending data and produces 5,824,239.30 in
# BOTH environments -- verified in this working copy and in a clean worktree at
# a2693ea. The value below is that number: the first pin this gate has carried
# that describes the fixture rather than the ambient machine.
#
# Guarded by test_frozen_build_reads_its_own_spending_budget_not_the_live_one,
# which fails if any spending input is ever again resolved from outside the
# redirected workspace.
#
# --- Machine-checked provenance (tests/test_golden_master_pin_provenance.py) ---
# The line below is a test-enforced gate, not decoration: the provenance test
# parses it and fails if its date/values do not match this file's current
# PINNED_* constants AND documentation/GOLDEN_MASTER_CHANGELOG.md's newest
# entry. Do not hand-edit the constants below without updating this line and
# the changelog -- use `py -3.14 tools/regen_golden_master.py regen --reason
# <file>`, which updates all three together. See
# documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md.
# 2026-08-26: PINNED_TERMINAL_NW=5763251.84 PINNED_LIFETIME_TAX=1316887.09
PINNED_TERMINAL_NW = 5763251.84
PINNED_LIFETIME_TAX = 1316887.09
PINNED_FAILURES = []
# Regenerated 2026-08-05 (fixture data change, not an engine change): added a
# fictional home-purchase scenario to Housing next_step_1 (Texas, $400,000 @
# 27% down = $108,000 down payment in 2036) so
# test_cashflow_chart_home_purchase_down_payment.py has a scenario to
# exercise -- see that file's docstring. Buying a $400K house is a real,
# deliberate change to the household's cash flow, so this pin move is
# expected data drift, not a regression to investigate.
#
# Prior pins (post Wave 3.0-3.7, no purchase scenario): 6,995,542.24 /
# 1,362,412.33. Documented alongside the Wave 3 engine-correctness batch in
# GOLDEN_MASTER_CHANGELOG.md -- estate exemption indexing, the medical
# expense deduction, the Roth objective discount, sleeve-level account
# returns, and the SSA/SOA mortality table.


def _frozen_config(withhold: tuple[str, ...] = ()):
    """Build the frozen plan's engine config from a fully self-contained copy.

    ``withhold`` names files to leave OUT of the staged workspace. It exists for
    the isolation guardrails below, which prove the redirect is real by checking
    that removing a frozen input actually changes the result -- if it does not,
    the build silently read the live repo ``input/`` instead.

    Every file in FROZEN_DIR is staged -- not just client_*.csv. The earlier
    version copied only client_*.csv and monkeypatched
    ``src.data_io.candidate_input_files``, which left three holes that made this
    "frozen" fixture depend on live workspace state:

    * ``src/optimization.py`` and ``src/real_loss_curves.py`` import
      ``candidate_input_files`` directly, so patching the name bound inside
      data_io never reached them.
    * The fixture's own client_spending.csv sets ``ytd_blend_enabled=TRUE`` but
      no ytd_transactions.csv was staged, so the YTD blend read whatever the
      real workspace happened to contain.
    * Non-client inputs (target_allocation.csv, spending_budget.csv,
      spending_category_map.csv, asset_class_optimizer_controls.csv) were never
      staged at all.

    Redirection is now done with RETIREMENT_SYSTEM_WORKSPACE_ROOT, which
    reaches every module rather than one module's symbol. That env var only
    became load-bearing once the hardcoded ``root=`` arguments were removed
    from data_io's plan-data lookups -- before that it silently did nothing for
    holdings and liabilities.

    The date is pinned too: plan_start derives from the current year and the
    YTD blend prorates by day-of-year, so identical inputs otherwise produce
    different dollars on different days.
    """
    import src.data_io as _data_io
    from src.data_io import load_csv, parse_client
    from src.plan_config import ensure_engine_config

    workspace = Path(tempfile.mkdtemp(prefix="frozen_sample_plan_"))
    (workspace / "input").mkdir(parents=True)
    for f in sorted(FROZEN_DIR.iterdir()):
        if f.is_file() and f.name not in withhold:
            shutil.copy(f, workspace / "input" / f.name)

    _prev_root = os.environ.get("RETIREMENT_SYSTEM_WORKSPACE_ROOT")
    _prev_today = os.environ.get("RETIREMENT_SYSTEM_FROZEN_TODAY")
    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(workspace)
    os.environ["RETIREMENT_SYSTEM_FROZEN_TODAY"] = FROZEN_TODAY
    try:
        data = load_csv(workspace / "input" / "client_data.csv")
        c = parse_client(data, "")
    finally:
        for _k, _v in (("RETIREMENT_SYSTEM_WORKSPACE_ROOT", _prev_root),
                       ("RETIREMENT_SYSTEM_FROZEN_TODAY", _prev_today)):
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v
        shutil.rmtree(workspace, ignore_errors=True)

    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return ensure_engine_config(c, source="test")


@pytest.mark.golden_master
class FrozenSamplePlanGoldenMasterTests(unittest.TestCase):
    """Mandatory: a regression here means the ENGINE changed, since the input
    is a static, committed copy no one edits day to day. Contrast with
    test_recommendations_functional.py's warn-only pins, which track the live plan."""

    def test_frozen_plan_dollar_figures_are_exact(self):
        from src.data_io import summarize_validation
        from src.planning_engines import project
        from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

        # _frozen_config() calls parse_client(), which itself calls
        # market_data.configure_holdings_pricing() and computes c['balances']
        # from priced holdings -- so it must be INSIDE the frozen-prices block,
        # matching test_recommendations_functional.py's sample_config()+project() pattern.
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

        # Pinned, not asserted-zero -- deliberately: a solvency change in
        # EITHER direction (newly failing, or newly recovering) should fail
        # this gate, not just a change away from zero. As of the 2026-08-05
        # Wave 3.0 regen the frozen household is fully solvent (PINNED_FAILURES
        # is empty); it previously showed UNFUNDED_GAP in 2052-56 under an
        # older engine state that predated several already-merged fixes
        # (score-normalization #51, roth-conversion-factors #50, and others)
        # -- see the PINNED_* block above for how that was verified as a
        # legitimate engine-state difference rather than a data leak.
        self.assertEqual(summary["warn_count"], 0)
        self.assertEqual(
            [(year, code) for year, level, code, _detail in summary["failures"]],
            PINNED_FAILURES,
            msg=(
                "Frozen-plan solvency profile changed. The fixture is static and "
                "self-contained, so this is an engine change, not data drift. If "
                "intentional, regenerate via this file's __main__ block and note why."
            ),
        )

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

    def test_frozen_build_reads_its_own_spending_budget_not_the_live_one(self):
        """Second guardrail, same class as the one above but a different door.

        The holdings guardrail above only ever proved the redirect for the files
        parse_client resolves through candidate_input_files. The unified
        spending budget does NOT come through that path: data_io.parse_client
        handed spending_budget_resolver an explicit ``root=`` computed from
        ``__file__``, so the resolver read the repo's own input/ directory and
        ignored RETIREMENT_SYSTEM_WORKSPACE_ROOT entirely -- the exact landmine
        this file's module docstring describes as fixed, surviving in a second
        module nobody re-checked.

        The consequence was worse than a stale number: on a machine with a warm
        input/ the gate silently pinned against the LIVE plan's spending, and in
        a fresh checkout or on CI (where input/*.csv is gitignored and absent)
        the resolver found nothing and fell through to legacy fallback values.
        Same commit, same fixture, two different answers -- $220,511.10 apart --
        so the gate passed in CI while failing locally and proved nothing in
        either place.

        Withholding the frozen budget must change the answer. If it does not,
        the build is reading spending data from somewhere other than the frozen
        workspace.
        """
        full = _frozen_config()
        without_budget = _frozen_config(withhold=("client_spending_budget.csv",))

        self.assertNotEqual(
            round(float(full["spend_base"]), 2),
            round(float(without_budget["spend_base"]), 2),
            "Withholding client_spending_budget.csv from the redirected workspace had no "
            "effect on spend_base, so the frozen build resolved its spending budget from "
            "outside the frozen workspace (historically: the repo's live input/ directory, "
            "via a hardcoded root= in data_io.parse_client). The mandatory gate above is "
            "then pinned against ambient machine state, not the fixture.",
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
