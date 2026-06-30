from pathlib import Path

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
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")

    assert "id:'planning_workbench'" in js
    assert "title:'Planning Workbench'" in js
    assert "retirement.planning_case_v1" in js
    assert "function renderPlanningWorkbench()" in js
    assert "function planningCaseCreate(source)" in js
    assert "function stepIdForRow(row){return sourceStepForRow(row)}" in js
    assert "planning_workbench:pageHelp('Planning Workbench'" in js
    assert "planning_case_v1 browser-local store" in js
    assert "Baseline → Change Set → Run Type → Impact → Decision" in js


def test_planning_workbench_route_is_available_before_plan_load():
    dashboard = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    navigation = (ROOT / "frontend" / "js" / "navigation.js").read_text(encoding="utf-8")

    assert "['start','system_configuration','detailed_results','planning_workbench','reports_and_review'].includes(s.id)" in dashboard
    assert "['detailed_results','system_configuration','planning_workbench','reports_and_review'].includes(activeStep)" in dashboard
    assert "PLAN_INDEPENDENT_STEPS=['start','system_configuration','detailed_results','planning_workbench','reports_and_review']" in navigation
    assert "!PLAN_INDEPENDENT_STEPS.includes(id)" in navigation


def test_legacy_pages_use_workbench_language_and_preserve_routes():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")

    for step_id in ["planning_levers", "scenarios", "monte_carlo_options", "build_impact"]:
        assert f"id:'{step_id}'" in js

    assert "Strategy Levers" in js
    assert "Scenario Change Sets" in js
    assert "Stress Suite & Monte Carlo" in js
    assert "Impact & Build History" in js
    assert "planningWorkbenchBuildImpactHtml()+latestBuildImpactHtml" in js
    assert "No strategy or scenario" not in js  # proposal wording moved into implemented guardrails/docs
    assert "Planning cases never mutate the saved plan automatically" in js


def test_docs_mark_consolidation_implemented():
    proposal = (ROOT / "documentation" / "PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md").read_text(encoding="utf-8")
    spec = (ROOT / "documentation" / "CURRENT_SYSTEM_DESIGN_SPEC.md").read_text(encoding="utf-8")
    contracts = (ROOT / "documentation" / "API_CONTRACTS.md").read_text(encoding="utf-8")

    assert "## Implementation Status" in proposal
    assert "Implemented in the Planning Workbench consolidation pass" in proposal
    assert "Planning Workbench Coherence Implementation" in spec
    assert "planning_case_v1" in spec
    assert "## `planning_case_v1` Browser-Local Contract" in contracts
