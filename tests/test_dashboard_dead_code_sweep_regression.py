"""Pre-conversion dead-code sweep (docs/superpowers/plans/2026-08-06-dashboard-js-
ast-module-conversion.md) removed three top-level bindings from dashboard.js that
had zero references anywhere in the repo (confirmed via tools/js_codemod/
find_dead_functions.mjs plus a manual variable-usage cross-check): the string
constant APP_UNAVAILABLE_MESSAGE, the array BUDGET_SECTION_DEFS, and the state
object planFileHandles. Guards against them silently reappearing.

2026-08-11: this file used to assert ``dead_candidates == []`` and passed, but
that green was meaningless. find_dead_functions.mjs could not report ANY
candidate, for three independent reasons, each sufficient on its own:

  1. Its raw-text pass counted each function's own ``function foo()``
     declaration site as a reference to ``foo``.
  2. Every frontend file ends with an ``Object.assign(window, {...})`` bridge
     naming every function it declares, which the text pass also counted.
  3. Only dashboard.js was mined for declarations, so nothing in
     frontend/js/dashboard_decomp_*.js could ever become a candidate.

A fourth blind spot turned up during triage: the Python side calls JS functions
by name through pywebview's evaluate_js (src/desktop_api.py pushes build
progress that way), so updateBuildProgress was reported dead while desktop mode
called it on every build tick. The finder now scans the Python sources too.

With all four fixed the tool reported 71 genuinely dead functions. 83 were
deleted (those 56, plus 27 more that fell out as cascades once their only
callers went); the 15 that remain are kept on purpose, see below. Asserting an
empty list again would just restore the vacuum, so this is a RATCHET: the test
fails if anything NEW goes dead. The list may shrink freely; it may never grow.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "tools" / "js_codemod" / "dead_function_candidates.json"

# Deliberately retained, 2026-08-11. The other 83 names this list once held were
# deleted outright (56 directly dead, plus 27 that fell out as cascades once
# their only callers went). What remains is the Planning Cases rendering layer:
# its data layer is still live and wired to a Save Case button, and a
# replacement UI is planned, so these are kept as building blocks rather than
# deleted and rewritten later.
#
# This is NOT a "dead code we tolerate" list -- it is a "dead today, on purpose"
# list. Anything not covered by that intent should be deleted, not added here.
KNOWN_DEAD_BACKLOG = {
    "normalizePlanningCaseRunType", "normalizePlanningCaseSource", "planningCaseActiveId",
    "planningCaseBaseSnapshotId", "planningCaseCardsHtml", "planningCaseId",
    "planningCaseMatrixHtml", "planningCaseMetricSummary", "planningCaseNowIso",
    "planningCaseOverrideFromRow", "planningCaseOverrideTable",
    "planningCaseOverridesForSource", "planningCaseSaveAll", "planningCaseSourceButtons",
    # Takes planning cases as its argument and delegates into the live
    # RetirementPlanningWorkbench module -- same carve-out as the above.
    "planningWorkbenchStressSelectorHtml",
}


def _report() -> dict | None:
    if not REPORT_PATH.exists():
        return None  # tool not yet run in this checkout; not this test's job to run it
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_removed_dead_bindings_do_not_reappear_in_dashboard_js():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    for name in ("APP_UNAVAILABLE_MESSAGE", "BUDGET_SECTION_DEFS", "planFileHandles"):
        assert name not in js, f"{name} was removed as dead code -- do not reintroduce it"


def test_no_new_dead_functions_beyond_the_known_backlog():
    """The ratchet. New dead code fails; burning down the backlog does not."""
    report = _report()
    if report is None:
        return
    newly_dead = sorted(set(report["dead_candidates"]) - KNOWN_DEAD_BACKLOG)
    assert not newly_dead, (
        "these top-level functions have no remaining callers (declaration + window-bridge "
        f"entry only): {newly_dead}. Either wire them up or delete them along with their "
        "bridge entries -- do not add them to KNOWN_DEAD_BACKLOG."
    )


def test_backlog_list_has_no_stale_entries():
    """Keeps the pin honest: a name that is no longer dead must leave the list,
    otherwise the backlog stops reflecting real work and quietly grows a
    permission to re-kill those functions."""
    report = _report()
    if report is None:
        return
    revived = sorted(KNOWN_DEAD_BACKLOG - set(report["dead_candidates"]))
    assert not revived, (
        f"no longer reported dead, so drop them from KNOWN_DEAD_BACKLOG: {revived}"
    )


def test_finder_is_still_capable_of_reporting_something():
    """Guard against silently returning to the vacuous-green state: if the tool
    ever reports zero candidates while the backlog above is non-empty, the tool
    itself broke (or someone re-introduced a blanket reference source) rather
    than 72 functions getting fixed at once."""
    report = _report()
    if report is None:
        return
    assert report.get("schema") == "dead_function_candidates_v2", (
        "unexpected report schema -- find_dead_functions.mjs changed shape; re-check that "
        "it still masks bridge blocks, imports, and declaration sites before counting"
    )
    if KNOWN_DEAD_BACKLOG:
        assert report["dead_candidates"], (
            "the finder reported zero dead candidates while the known backlog is still "
            "populated. That is the exact failure mode this file was rewritten to catch: "
            "verify the masking in find_dead_functions.mjs still works before trusting it."
        )
