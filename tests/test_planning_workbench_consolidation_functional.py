from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_planning_workbench_contract_helper_validates_shape():
    from src.planning_workbench import contract_example, validate_planning_case_v1

    payload = contract_example()
    ok, errors = validate_planning_case_v1(payload)
    assert ok is True
    assert errors == []
    assert payload["schema"] == "planning_case_v1"
    assert payload["source"] == "scenario"
    assert payload["run_type"] == "quick_compare"

    bad = {**payload, "source": "forecast", "overrides": {}}
    ok, errors = validate_planning_case_v1(bad)
    assert ok is False
    assert "source must be one of strategy, scenario, stress, manual" in errors
    assert "overrides must be a list" in errors


def test_dashboard_adds_planning_workbench_step_and_case_store():
    js = dashboard_js_text()

    assert 'id: "planning_workbench"' in js
    assert 'title: "Planning Workbench"' in js
    assert "retirement.planning_case_v1" in js
    # renderPlanningWorkbench() was a wrapper around planning_workbench_ui.js's
    # renderWorkbench(), which Planning Workbench Strategy Integration Task 4
    # deleted; Task 5 removed the now-dead wrapper (it would throw if called)
    # along with its unreachable renderMain() call site -- see
    # tests/test_frontend_module_extraction_functional.py::
    # test_planning_workbench_case_store_moved_out_of_dashboard.
    assert "renderPlanningWorkbench" not in js
    assert "function planningCaseCreate(source)" in js
    assert "function stepIdForRow(row) {\n  return sourceStepForRow(row);\n}" in js
    assert 'planning_workbench: pageHelp(\n    "Planning Workbench"' in js
    assert "planning_case_v1 browser-local store" in js
    assert "Baseline → Change Set → Run Type → Impact → Decision" in js


def test_planning_workbench_route_is_available_before_plan_load():
    dashboard = dashboard_js_text()
    navigation = (ROOT / "frontend" / "js" / "navigation.js").read_text(encoding="utf-8")

    # #323: the Workbench is a section of the strategy_scenarios screen now.
    # Each of these gates runs on the id the user actually lands on, so the
    # screen -- not the retired step id -- is what has to be listed, or the
    # "Compare & Decide" button in every page header bounces to Plan Status
    # whenever no plan is open. Where it lands is asserted behaviorally in
    # tests/frontend/strategy_section_redirects.test.mjs.
    assert '"strategy_scenarios",\n        "reports_and_review",\n      ].includes(s.id)' in dashboard
    assert '"strategy_scenarios",\n        "reports_and_review",\n      ].includes(activeStep)' in dashboard
    assert "'detailed_results','strategy_scenarios','reports_and_review']" in navigation
    assert "!PLAN_INDEPENDENT_STEPS.includes(id)" in navigation
    assert "planning_workbench:{step:'strategy_scenarios',section:'workbench'}" in navigation


def test_legacy_pages_use_workbench_language_and_preserve_routes():
    js = dashboard_js_text()

    for step_id in ["planning_levers", "scenarios", "monte_carlo_options", "build_impact"]:
        assert f'id: "{step_id}"' in js

    assert "Strategy Levers" in js
    assert "Scenario Change Sets" in js
    assert "Stress Suite & Monte Carlo" in js
    assert "Impact & Build History" in js
    assert 'planningWorkbenchBuildImpactHtml() + latestBuildImpactHtml' in js
    assert "No strategy or scenario" not in js  # proposal wording moved into implemented guardrails/docs
    assert "Planning cases never mutate the saved plan automatically" in js


def test_docs_mark_consolidation_implemented():
    proposal = (ROOT / "documentation" / "archive" / "PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md").read_text(encoding="utf-8")
    contracts = (ROOT / "documentation" / "reference" / "API_CONTRACTS.md").read_text(encoding="utf-8")

    assert "## Implementation Status" in proposal
    assert "Implemented in the Planning Workbench consolidation pass" in proposal
    assert "## `planning_case_v1` Browser-Local Contract" in contracts
