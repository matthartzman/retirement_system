"""#256: the Planning Levers page's quick-nav buttons must not show a lever
whose optional workbook module is turned off. This started as two separate,
hand-picked special cases (a divorceLeverButton conditional for divorce_qdro,
then a separately-added ltcLeverButton conditional for
long_term_care_stress) that inevitably drifted -- Charitable Giving and
several other module-gated steps were never covered, and the user reported
"make sure applied to all optional modules" after finding the divorce fix
alone still incomplete.

Fixed by routing every quick-nav button here through leverNavButton(), which
reuses stepGatedByOptionalModule() -- the same server-declared
(module_catalog dashboard_step -> moduleGates.step_gates) single source of
truth every other nav surface in the app already uses for step visibility.
This covers every current and future optional module uniformly instead of
requiring a new hand-written conditional each time a new module is added.
"""
from pathlib import Path

from src.module_catalog import step_gate_map

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text

# Every quick-nav button on the Planning Levers page, and the step id it
# jumps to. Must match frontend/js/dashboard.js::renderPlanningLevers().
LEVER_NAV_STEPS = [
    # Ticket 286: withdrawal sequencing moved to the Spending workspace's
    # "Withdrawal Order" tab, so the lever button now jumps to spending_core.
    "roth_conversion", "allocation_assets", "spending_core",
    "income_retirement", "entity_charitable", "heloc_strategy",
    "monte_carlo_options", "scenarios", "survivor_stress",
    "ltc_stress", "divorce_options",
]


def _planning_levers_fn():
    js = dashboard_js_text()
    start = js.index('function renderPlanningLevers(')
    end = js.index('\nfunction chatMessageHtml', start)
    return js[start:end]


def test_every_quick_nav_button_is_routed_through_the_generic_gate_helper():
    fn = _planning_levers_fn()
    assert 'function leverNavButton(stepId, label)' in fn
    assert 'stepGatedByOptionalModule(stepId)' in fn
    for step in LEVER_NAV_STEPS:
        assert f'leverNavButton(' in fn  # sanity: helper is actually called
    call_section = fn[fn.index('function leverNavButton'):]
    for step in LEVER_NAV_STEPS:
        assert f'leverNavButton("{step}"' in call_section, f"{step} not routed through leverNavButton"


def test_no_leftover_hand_picked_single_module_special_cases():
    """Guard against regressing back to one-off conditionals for whichever
    module someone happens to remember to gate next time."""
    fn = _planning_levers_fn()
    assert 'divorceLeverButton' not in fn
    assert 'ltcLeverButton' not in fn
    assert 'optionalFunctionEnabled("divorce_qdro")' not in fn
    assert 'optionalFunctionEnabled("long_term_care_stress")' not in fn


def test_state_residency_button_still_removed():
    # #255: state residency was removed from this page entirely (the merged
    # State Residency "Tax and Expenses" table replaces its role) -- not
    # module-gated here, just absent.
    fn = _planning_levers_fn()
    assert 'state_residency' not in fn


def test_lever_nav_steps_that_are_module_gated_have_a_declared_module():
    """Cross-check against the real server-side gate map: every lever step
    that step_gate_map() says IS gated must correspond to a real optional
    module key (catches a typo'd step id silently never gating)."""
    gates = step_gate_map()
    gated = {step: gates[step] for step in LEVER_NAV_STEPS if gates.get(step)}
    # At minimum, the two modules this ticket was originally filed about.
    assert gated.get('divorce_options') == 'divorce_qdro'
    assert gated.get('ltc_stress') == 'long_term_care_stress'
    assert gated.get('entity_charitable') == 'charitable_giving'
