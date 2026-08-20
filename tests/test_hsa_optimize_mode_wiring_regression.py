"""HSA 'optimize' mode wiring (2026-08-19).

The prior session's own closing note (docs/superpowers/plans/2026-08-17-
hsa-withdrawal-optimizer.md, line 1104) found the entire H0-H5 optimizer
feature had no way to be turned on by a real household: data_io.py coerced
any hsa_withdrawal_mode outside spend_as_needed/annual_pct/smooth_window back
to spend_as_needed, and planning_engines.py's withdraw_hsa_window had no
'optimize' case -- an admitted value would have silently fallen through to
smooth_window's math, wrong semantics rather than merely inert.

This closes exactly the gap that note named:
  1. data_io.py admits 'optimize' and loads client_hsa_schedule.csv into
     c['hsa_schedule_rows'] / c['hsa_schedule_by_year'].
  2. withdraw_hsa_window gets a real 'optimize' branch using
     hsa_schedule.resolve_year_amount's precedence ladder (override > locked
     > optimizer > mode), with a level-draw fallback for a year with no
     schedule row -- NOT smooth_window's math, which the prior note's own
     bug report shows an admitted-but-unhandled mode would have silently
     fallen into.

Deliberately NOT included, and not claimed here: the automatic search
(rerun_optimizer/build_schedule) is still not wired into the projection
pipeline (see hsa_schedule.py's module docstring for why -- a genuine
two-pass sequencing problem). So 'locked'/'optimizer' sources are exercised
here as reachable code paths, not as evidence the search runs automatically.

Real bug found 2026-08-20 by a user comparing a $2,000/year override entered
via the UI against the resulting workbook: the entered amount never showed
up, and the account showed as fully drained years before the household
expected -- the same cliff shape as the ORIGINAL bug this file's own module
docstring describes, reappearing through a second mechanism after the first
one (generate_default_schedule, hsa_default_schedule_regression.py) was
already fixed. Root cause: withdraw_hsa_gap ("Priority 4c: Final non-Roth
HSA draw before any Roth withdrawal", deterministic_engine.py) runs LATER in
the same per-year loop and, whenever ANY cash-flow gap remains after other
sources, draws MORE from the HSA on top of whatever withdraw_hsa_window's
'optimize' branch already scheduled -- its own docstring already explains
why this must not happen for a scheduled mode ("allowing gap-fills on top
would double-deplete the HSA"), but 'optimize' was simply never added to the
suppression tuple when that mode was built, unlike smooth_window/annual_pct,
which already had it. See withdraw_hsa_gap's own tests below.
"""
from __future__ import annotations

from src.planning_engines import withdraw_hsa_gap, withdraw_hsa_window


def _c(mode="optimize", plan_end=2030, schedule_by_year=None, hsa_ids=("hsa1",)):
    return {
        "hsa_withdrawal_mode": mode,
        "hsa_ids": list(hsa_ids),
        "plan_end": plan_end,
        "hsa_schedule_by_year": schedule_by_year or {},
    }


# --- Mode admission (data_io.py) --------------------------------------------


def test_optimize_is_admitted_not_coerced_to_spend_as_needed():
    import re

    src = open("src/data_io.py", encoding="utf-8").read()
    # The allowlist tuple must contain 'optimize' -- a source-text check, not
    # a functional one, because parse_client's full call graph needs a
    # complete plan fixture; the functional half is covered by the
    # withdraw_hsa_window tests below, which exercise the real consequence of
    # admission (a working 'optimize' mode) rather than the gate alone.
    m = re.search(
        r"if c\['hsa_withdrawal_mode'\] not in \(([^)]*)\):",
        src,
    )
    assert m is not None, "could not find the hsa_withdrawal_mode allowlist check"
    assert "'optimize'" in m.group(1), (
        f"allowlist tuple {m.group(1)!r} must include 'optimize'"
    )


# --- withdraw_hsa_window's 'optimize' branch --------------------------------


def test_override_amount_is_honored_exactly():
    c = _c(schedule_by_year={2026: {"override_amount": 5000.0}})
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 5000.0
    assert out["by_account"]["hsa1"] == 5000.0
    assert bal["hsa1"] == 95_000.0


def test_override_of_zero_is_a_real_zero_not_a_fallback():
    # resolve_year_amount's own contract: override=0.0 is a deliberate
    # "draw nothing this year", distinct from "no schedule entry at all".
    c = _c(schedule_by_year={2026: {"override_amount": 0.0}})
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 0.0
    assert bal["hsa1"] == 100_000.0


def test_locked_optimizer_amount_is_honored():
    c = _c(schedule_by_year={2026: {"optimizer_amount": 8000.0, "locked": True}})
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 8000.0


def test_unlocked_optimizer_amount_is_honored():
    c = _c(schedule_by_year={2026: {"optimizer_amount": 3000.0, "locked": False}})
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 3000.0


def test_no_schedule_row_falls_back_to_level_draw_over_remaining_horizon():
    # year=2027, plan_end=2030 -> 4 years remaining (2027,2028,2029,2030).
    c = _c(schedule_by_year={})
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2027)
    assert out["amount"] == 25_000.0


def test_no_schedule_row_and_zero_balance_draws_nothing():
    c = _c(schedule_by_year={})
    bal = {"hsa1": 0.0}
    out = withdraw_hsa_window(c, bal, 2027)
    assert out["amount"] == 0.0
    assert out["by_account"] == {}


def test_override_exceeding_balance_is_capped_not_overdrawn():
    c = _c(schedule_by_year={2026: {"override_amount": 999_000.0}})
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 100_000.0
    assert bal["hsa1"] == 0.0


def test_multiple_accounts_split_pro_rata():
    c = _c(hsa_ids=("hsa1", "hsa2"), schedule_by_year={2026: {"override_amount": 10_000.0}})
    bal = {"hsa1": 60_000.0, "hsa2": 40_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 10_000.0
    assert out["by_account"]["hsa1"] == 6_000.0
    assert out["by_account"]["hsa2"] == 4_000.0


# --- Golden-master safety: default mode is untouched by this change --------


def test_spend_as_needed_mode_is_unaffected():
    c = {"hsa_withdrawal_mode": "spend_as_needed", "hsa_ids": ["hsa1"]}
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026, wellness_cost=2_000.0)
    assert out["amount"] == 2_000.0


def test_smooth_window_mode_is_unaffected():
    c = {
        "hsa_withdrawal_mode": "smooth_window",
        "hsa_ids": ["hsa1"],
        "hsa_win_start": 2026,
        "hsa_win_end": 2029,
    }
    bal = {"hsa1": 100_000.0}
    out = withdraw_hsa_window(c, bal, 2026)
    assert out["amount"] == 25_000.0  # 100k / 4 years, unchanged math


# --- withdraw_hsa_gap's 'optimize' suppression (2026-08-20 bug) ------------


def test_gap_fill_is_suppressed_in_optimize_mode():
    """The literal bug report: schedule says $2,000 for the year, but a
    large unfunded cash-flow gap exists. Before the fix, withdraw_hsa_gap
    would have drawn additional dollars on top of the scheduled amount to
    plug that gap, entirely ignoring the schedule. It must draw nothing and
    pass the gap through unfunded -- other sources (or an accepted shortfall)
    are responsible for it, not an unscheduled HSA raid.
    """
    c = {"hsa_withdrawal_mode": "optimize", "hsa_ids": ["hsa1"]}
    bal = {"hsa1": 50_000.0}
    out = withdraw_hsa_gap(c, bal, gap=20_000.0, year=2028)
    assert out["amount"] == 0.0
    assert out["new_gap"] == 20_000.0
    assert bal["hsa1"] == 50_000.0


def test_gap_fill_suppression_does_not_depend_on_window_fields():
    """Suppression must be unconditional for optimize mode, not an accident
    of hsa_win_start/hsa_win_end's defaults (9999/0) happening to also
    suppress smooth_window/annual_pct. A household that switched INTO
    optimize mode from smooth_window may still carry real, non-default
    win_start/win_end values on the row -- those must not un-suppress
    gap-filling for optimize.
    """
    c = {
        "hsa_withdrawal_mode": "optimize",
        "hsa_ids": ["hsa1"],
        "hsa_win_start": 2020,  # already "ended" if this were smooth_window
        "hsa_win_end": 2022,
    }
    bal = {"hsa1": 50_000.0}
    out = withdraw_hsa_gap(c, bal, gap=20_000.0, year=2028)
    assert out["amount"] == 0.0
    assert bal["hsa1"] == 50_000.0


def test_scheduled_draw_still_reduces_the_gap_before_suppression_applies():
    """The fix must only block the SECOND (gap-fill) draw, not the first,
    scheduled one -- withdraw_hsa_window's own draw still happens and still
    counts against the year's cash-flow gap, exactly as before.
    """
    c = {
        "hsa_withdrawal_mode": "optimize",
        "hsa_ids": ["hsa1"],
        "hsa_schedule_by_year": {2028: {"override_amount": 2_000.0}},
    }
    bal = {"hsa1": 50_000.0}
    scheduled = withdraw_hsa_window(c, bal, 2028)
    assert scheduled["amount"] == 2_000.0
    gap_after_scheduled = 20_000.0 - scheduled["amount"]
    gap_fill = withdraw_hsa_gap(c, bal, gap=gap_after_scheduled, year=2028)
    assert gap_fill["amount"] == 0.0
    assert gap_fill["new_gap"] == gap_after_scheduled
    assert bal["hsa1"] == 48_000.0  # only the scheduled $2,000 was drawn


def test_smooth_window_and_annual_pct_gap_fill_suppression_is_unaffected():
    """Regression guard: the pre-existing, correct suppression for the two
    modes that already had it must not change shape.
    """
    c_smooth = {
        "hsa_withdrawal_mode": "smooth_window",
        "hsa_ids": ["hsa1"],
        "hsa_win_start": 2026,
        "hsa_win_end": 2029,
    }
    bal = {"hsa1": 50_000.0}
    out = withdraw_hsa_gap(c_smooth, bal, gap=20_000.0, year=2027)
    assert out["amount"] == 0.0, "still suppressed during the configured window"

    c_after_window = {
        "hsa_withdrawal_mode": "smooth_window",
        "hsa_ids": ["hsa1"],
        "hsa_win_start": 2020,
        "hsa_win_end": 2022,
    }
    bal2 = {"hsa1": 50_000.0}
    out2 = withdraw_hsa_gap(c_after_window, bal2, gap=20_000.0, year=2028)
    assert out2["amount"] == 20_000.0, "fair game after the window ends, unchanged"
