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

from src.module_catalog import flag_gate_map, step_gate_map

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_function_source, dashboard_js_text

WORKSPACE_JS = (ROOT / "frontend" / "js" / "dashboard_decomp_strategy_workspace.js").read_text(
    encoding="utf-8"
)

# Every strategySection() call across the three screens, and the legacy step
# id its `gate` argument names -- None where the section is never gated. Must
# match dashboard_decomp_strategy_workspace.js's renderStrategyOptimize/
# renderStrategyStress/renderStrategyScenarios.
# #330 P8 / Q6 (W13): "roth_conversion" and "charitable_giving" are gone from
# this table because they are gone from the screens -- both became real Taxes
# nav steps, the way "heloc" did in W9. The step_gate_map() assertions below
# deliberately keep naming them: the gate declaration itself is unchanged, it
# is now read by visibleSteps() rather than by a strategySection() call.
SECTION_GATES = {
    "asset_allocation": None,
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


def test_heloc_gates_through_a_declaration_not_a_hand_written_branch():
    # HELOC isn't a client_optional_functions.csv toggle -- it's a plan-data
    # feature flag (HELOC/Setup/heloc_enabled). #330 §5.3 (W6) unified the two
    # mechanisms at the point of USE: the catalog declares the flag's
    # (section, subsection, label) and flag_gate_map() serves it beside
    # step_gate_map(), so stepGatedByOptionalModule() no longer carries an
    # `if (stepId === "heloc_strategy")`. It is the SAME contract #256 fixed
    # for toggles, now covering flags too -- a second plan flag must need no
    # second branch.
    assert "heloc_strategy" not in step_gate_map()
    flag = flag_gate_map()["heloc_strategy"]
    assert flag["key"] == "heloc"
    assert flag["ref"] == ["HELOC", "Setup", "heloc_enabled"]
    assert flag["enable_label"] == "Enable HELOC Strategy"

    row_model_js = (
        ROOT / "frontend" / "js" / "dashboard_decomp_row_model.js"
    ).read_text(encoding="utf-8")
    gate_fn = dashboard_function_source("stepGatedByOptionalModule", dashboard_js_text())
    # The declaration is read; the two hand-written branches are gone.
    assert "flag_gates" in gate_fn
    assert "sectionFlagEnabled(" in gate_fn
    assert 'stepId === "heloc_strategy"' not in gate_fn
    assert 'stepId === "special_strategies"' not in gate_fn
    assert "helocModuleEnabled()" not in gate_fn
    # No leftover or reintroduced one-off conditionals for any other module.
    assert "divorceLeverButton" not in row_model_js
    assert "ltcLeverButton" not in row_model_js


def test_the_enable_note_resolves_its_click_path_from_the_catalog():
    """§5.2/§5.3 (W12): strategySectionGatedNote() generalized into
    featureGatedNote(), registry-driven from planModuleTaxonomy() (which
    carries gate_kind/gate_ref/gate_enable_label per module, W9) instead of
    branching on the gate mechanism at each call site. No mechanism-specific
    string may be hand-typed in the function itself -- a plan flag's
    click-path text comes from the module's own declaration, read generically
    for whichever module key is passed in, not from an `if` singling out
    HELOC or any other one module."""
    note_start = WORKSPACE_JS.index("export function featureGatedNote(")
    note_fn = WORKSPACE_JS[note_start : WORKSPACE_JS.index("\n}", note_start)]
    assert 'key === "heloc"' not in note_fn
    assert "Enable HELOC Strategy" not in note_fn
    assert "gate_ref" in note_fn
    assert "gate_enable_label" in note_fn
    assert "gate_kind" in note_fn
    # ...and the catalog is where that copy now lives, exactly once.
    assert flag_gate_map()["heloc_strategy"]["enable_label"] == "Enable HELOC Strategy"


def test_the_enable_note_offers_an_inline_switch():
    """§5.1: 'the gated note... should offer the switch inline, because the
    user who is reading that note has already decided' -- not only a link to
    go decide somewhere else."""
    note_start = WORKSPACE_JS.index("export function featureGatedNote(")
    note_fn = WORKSPACE_JS[note_start : WORKSPACE_JS.index("\n}", note_start)]
    assert "InlineSwitch(" in note_fn

    flag_start = WORKSPACE_JS.index("function planFlagInlineSwitch(")
    flag_fn = WORKSPACE_JS[flag_start : WORKSPACE_JS.index("\n}", flag_start)]
    assert "editValue(" in flag_fn

    toggle_start = WORKSPACE_JS.index("function moduleToggleInlineSwitch(")
    toggle_fn = WORKSPACE_JS[toggle_start : WORKSPACE_JS.index("\n}", toggle_start)]
    assert "editValue(" in toggle_fn


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
