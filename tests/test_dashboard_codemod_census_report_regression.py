"""The dashboard.js module-conversion census (tools/js_codemod/census.mjs) must
stay runnable and its invariants must hold, since the conversion codemod
(tools/js_codemod/convert_dashboard.mjs, see
docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md)
depends on this report being accurate.

v2: an early run of the census found dashboard_source_truth_banners.js and
dashboard_batch_assumption_edit.js reassign (not just call) renderMain and
showStepHelp as a monkey-patch decorator chain, and 42 top-level variables are
read or written by other already-converted leaf modules. The codemod handles
both (reassigned functions become reassignable let-bindings with a get+set
accessor; externally-referenced variables get a get+set accessor) -- this test
just guards that the census keeps finding them, so a future codemod change
can't silently regress to the unsafe value-copy/get-only design.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS_SCRIPT = ROOT / "tools" / "js_codemod" / "census.mjs"
REPORT_PATH = ROOT / "tools" / "js_codemod" / "census_report.json"


def _run_census():
    return subprocess.run(
        ["node", str(CENSUS_SCRIPT)], cwd=ROOT, text=True, capture_output=True, timeout=60
    )


def test_census_script_runs_successfully():
    result = _run_census()
    assert result.returncode == 0, result.stdout + result.stderr


def test_census_function_and_variable_counts_are_in_expected_bands():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert 700 <= len(report["functions"]) <= 900
    assert len(report["variables"]) >= 10
    assert set(report["functions"]).isdisjoint(report["variables"])


def test_known_reassigned_functions_are_still_detected():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert set(report["reassigned_functions"]) >= {"renderMain", "showStepHelp"}


def test_known_externally_referenced_variables_are_still_detected():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    # A representative sample from the original finding -- not the full 42,
    # so this doesn't need updating every time an unrelated one drops out.
    expected_subset = {"activeStep", "buildOverlayTimer", "csrfToken", "liquidityBuffers"}
    assert expected_subset <= set(report["externally_referenced_variables"])


def test_census_report_committed_copy_matches_a_fresh_run():
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    _run_census()
    fresh = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert committed == fresh, (
        "dashboard.js's top-level declarations or cross-file references changed since "
        "the committed census_report.json was generated. Re-run tools/js_codemod/census.mjs "
        "and commit the new report."
    )
