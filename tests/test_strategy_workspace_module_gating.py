"""Ticket 323: the module-gating contract #256 established for the Planning
Levers page's quick-nav buttons -- a module-gated destination must never be
offered while its module is off, checked uniformly through
stepGatedByOptionalModule() rather than one hand-picked conditional per
module -- migrates to the three Strategy screens (Optimize / Stress Test /
Scenarios) when the redesign removes the quick-nav hub they replace.

This file supersedes tests/test_planning_levers_module_gating.py, whose
LEVER_NAV_STEPS list and leverNavButton() helper both went away with the hub:
renderPlanningLevers() no longer needs quick-nav buttons of its own because
every one of its former destinations now has a real, permanent nav entry
(one of the three Strategy screens). The contract that test protected did not
disappear with the hub -- it moved onto strategySection()'s `gate` parameter,
asserted here against the same server-declared single source of truth
(module_catalog dashboard_step -> moduleGates.step_gates).
"""
from pathlib import Path

from src.module_catalog import step_gate_map

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_function_source, dashboard_js_text

WORKSPACE_JS = (ROOT / "frontend" / "js" / "dashboard_decomp_strategy_workspace.js").read_text(
    encoding="utf-8"
)

# Every strategySection() call across the three screens, and the legacy step
# id its `gate` argument names -- None where the section is never gated. Must
# match dashboard_decomp_strategy_workspace.js's renderStrategyOptimize/
# renderStrategyStress/renderStrategyScenarios.
SECTION_GATES = {
    "roth_conversion": "roth_conversion",
    "asset_allocation": None,
    "charitable_giving": "entity_charitable",
    "heloc": "heloc_strategy",
    "monte_carlo": "monte_carlo_options",
    "survivor": "survivor_stress",
    "ltc": "ltc_stress",
    "divorce": "divorce_options",
    "levers": None,
    "change_sets": "scenarios",
    "workbench": None,
}


def test_every_gated_section_names_the_key_step_gate_map_expects():
    """Cross-check against the real server-side gate map: every section whose
    gate is a legacy id that step_gate_map() says IS module-gated must
    resolve to the real optional module key -- catches a typo'd step id
    silently never gating."""
    gates = step_gate_map()
    for section_key, legacy_id in SECTION_GATES.items():
        if legacy_id is None:
            continue
        if legacy_id in gates:
            assert f'gate: "{legacy_id}"' in WORKSPACE_JS, (
                f"section {section_key!r} must gate on {legacy_id!r}"
            )
    # At minimum, the modules #256 was originally filed about, plus every
    # other gate this redesign carries forward.
    assert gates.get("roth_conversion") == "roth_conversion_plan"
    assert gates.get("entity_charitable") == "charitable_giving"
    assert gates.get("monte_carlo_options") == "market_luck_stress_test"
    assert gates.get("survivor_stress") == "survivor_stress_test"
    assert gates.get("ltc_stress") == "long_term_care_stress"
    assert gates.get("divorce_options") == "divorce_qdro"
    assert gates.get("scenarios") == "what_if_analysis"


def test_heloc_stays_the_declared_special_case_not_a_new_hand_picked_one():
    # HELOC isn't a client_optional_functions.csv toggle (module_catalog has
    # no entry for it) -- it's a plan-data feature flag
    # (HELOC/Setup/heloc_enabled), so stepGatedByOptionalModule() special-cases
    # it explicitly rather than through step_gate_map(). Confirm that's still
    # the ONLY special case, not a precedent for reintroducing hand-picked
    # per-module conditionals the way #256 originally had to remove.
    gates = step_gate_map()
    assert "heloc_strategy" not in gates
    row_model_js = (
        ROOT / "frontend" / "js" / "dashboard_decomp_row_model.js"
    ).read_text(encoding="utf-8")
    gate_fn = dashboard_function_source("stepGatedByOptionalModule", dashboard_js_text())
    assert 'stepId === "heloc_strategy"' in gate_fn
    # No leftover or reintroduced one-off conditionals for any other module.
    assert "divorceLeverButton" not in row_model_js
    assert "ltcLeverButton" not in row_model_js


def test_every_section_gates_through_the_single_generic_helper():
    """The contract #256 fixed: no section may gate through a hand-picked
    conditional (optionalFunctionEnabled("some_module") sprinkled ad hoc) --
    every gated section must route through stepGatedByOptionalModule(), the
    one place that decision is made."""
    assert "export function strategySection(" in WORKSPACE_JS
    section_fn_start = WORKSPACE_JS.index("export function strategySection(")
    section_fn = WORKSPACE_JS[section_fn_start : section_fn_start + 800]
    assert "stepGatedByOptionalModule(gateStepId)" in section_fn
    # Sections pass their gate id as data, not by calling optionalFunctionEnabled
    # themselves -- confirm no screen-builder function bypasses the helper.
    assert 'optionalFunctionEnabled("divorce_qdro")' not in WORKSPACE_JS
    assert 'optionalFunctionEnabled("long_term_care_stress")' not in WORKSPACE_JS
    assert 'optionalFunctionEnabled("charitable_giving")' not in WORKSPACE_JS


def test_the_old_lever_hub_and_its_helper_are_gone():
    fn = dashboard_function_source("renderPlanningLevers", dashboard_js_text())
    assert "function leverNavButton" not in fn
    assert "optimizer-hub" not in fn
    assert "Strategy · decide" not in fn
    assert "Stress tests · resilience" not in fn
