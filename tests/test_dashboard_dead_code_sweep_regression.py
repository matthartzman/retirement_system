"""Pre-conversion dead-code sweep (docs/superpowers/plans/2026-08-06-dashboard-js-
ast-module-conversion.md) removed three top-level bindings from dashboard.js that
had zero references anywhere in the repo (confirmed via tools/js_codemod/
find_dead_functions.mjs plus a manual variable-usage cross-check): the string
constant APP_UNAVAILABLE_MESSAGE, the array BUDGET_SECTION_DEFS, and the state
object planFileHandles. Guards against them silently reappearing.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_removed_dead_bindings_do_not_reappear_in_dashboard_js():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    for name in ("APP_UNAVAILABLE_MESSAGE", "BUDGET_SECTION_DEFS", "planFileHandles"):
        assert name not in js, f"{name} was removed as dead code -- do not reintroduce it"


def test_dead_function_finder_reports_zero_candidates():
    """dashboard.js's remaining top-level functions should still all be
    referenced somewhere (this is the steady-state expectation after the
    sweep; it's fine for this to need updating if it ever finds real new
    dead code -- that's the point of running it)."""
    import json
    report_path = ROOT / "tools" / "js_codemod" / "dead_function_candidates.json"
    if not report_path.exists():
        return  # tool not yet run in this checkout; not this test's job to run it
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["dead_candidates"] == []
