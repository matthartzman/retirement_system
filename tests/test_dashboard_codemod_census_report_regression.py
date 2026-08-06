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

v3: 2 of those 42 externally-referenced variables (ACRONYM_DEFINITIONS,
DEFAULT_TRAVEL_TYPES) are `const` -- a setter that reassigns a const binding
is a runtime TypeError if ever invoked, even though it parses fine. The census
now reports const_variables so the codemod can give const-declared names a
get-only accessor regardless of external reference.
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
    # 2026-08-06: band lowered from 700-900 to 500-650 -- domain-module-split
    # shared-core extraction (docs/superpowers/plans/
    # 2026-08-06-dashboard-js-domain-module-split-SCOPE.md) moved 172
    # fan-in>=3 hub functions out of dashboard.js into
    # dashboard_decomp_row_model.js; census.mjs only counts dashboard.js's own
    # remaining top-level functions.
    assert 500 <= len(report["functions"]) <= 650
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


def test_known_const_variables_needing_get_only_are_still_detected():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    const_and_referenced = set(report["const_variables"]) & set(report["externally_referenced_variables"])
    # ACRONYM_DEFINITIONS moved to dashboard_decomp_row_model.js (domain-
    # module-split shared-core extraction, 2026-08-06) -- census.mjs only
    # scans dashboard.js itself, so it's no longer a dashboard.js-internal
    # const/external-reference finding. DEFAULT_TRAVEL_TYPES stayed.
    assert const_and_referenced >= {"DEFAULT_TRAVEL_TYPES"}


def test_no_reassigned_function_is_ever_a_const_variable():
    """Sanity invariant, not an expected finding: a `function` declaration and
    a `const` variable are mutually exclusive top-level declaration kinds, so
    this should always hold; if it ever doesn't, something is misclassified."""
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert set(report["reassigned_functions"]).isdisjoint(report["const_variables"])


def test_census_report_committed_copy_matches_a_fresh_run():
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    _run_census()
    fresh = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert committed == fresh, (
        "dashboard.js's top-level declarations or cross-file references changed since "
        "the committed census_report.json was generated. Re-run tools/js_codemod/census.mjs "
        "and commit the new report."
    )
