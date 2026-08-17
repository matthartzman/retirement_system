"""Follow-up to #256: renderWorkbenchStressHtml() (the "stress suite" panel
in the Planning Case workbench) rendered its Monte Carlo and Survivor / Early
Death blocks unconditionally, while its Long-Term Care and Divorce Planning
blocks were correctly gated behind optionalFunctionEnabled(). Both Monte
Carlo (market_luck_stress_test) and Survivor (survivor_stress_test) are
optional=True modules in src.module_catalog, exactly like long_term_care_stress
and divorce_qdro sitting right next to them in the same function -- so an
unconditional render was an inconsistency, not a deliberate exception.

Fixed by gating both blocks through stepGatedByOptionalModule(), the same
server-declared (module_catalog dashboard_step -> moduleGates.step_gates)
single source of truth renderPlanningLevers() already uses, so this panel
can't drift from the nav gating again.
"""
from pathlib import Path

from src.module_catalog import step_gate_map
from tests._decomp_dashboard import dashboard_function_source, dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def _stress_suite_fn():
    """The body of renderWorkbenchStressHtml, wherever it currently lives.

    This used to read dashboard.js and slice up to renderWorkbenchLeverEditorHtml,
    the function that happened to follow it. F3.1 moved the stress panel into
    dashboard_decomp_mc_stress_options.js and left the lever editor behind, so
    the two landmarks are now in different files and the end marker no longer
    appears after the start one at all. Bounding the slice by the next
    top-level `function` in the SAME text keeps the intent -- assert about this
    function's body, not the whole file -- without assuming which neighbour it
    is or which file either ends up in.

    Bounding on a literal '\\nfunction ' was not enough: extracted modules
    declare `export function`, so that scan misses every declaration in the
    module and the slice runs on into the next file. dashboard_function_source
    matches both shapes.
    """
    return dashboard_function_source('renderWorkbenchStressHtml')


def test_monte_carlo_and_survivor_blocks_are_gated_through_the_generic_helper():
    fn = _stress_suite_fn()
    assert 'stepGatedByOptionalModule("monte_carlo_options")' in fn
    assert 'stepGatedByOptionalModule("survivor_stress")' in fn


def test_ltc_and_divorce_blocks_remain_gated():
    fn = _stress_suite_fn()
    assert 'optionalFunctionEnabled("long_term_care_stress")' in fn
    assert 'optionalFunctionEnabled("divorce_qdro")' in fn


def test_stress_suite_steps_that_are_module_gated_have_a_declared_module():
    """Cross-check against the real server-side gate map: both steps this
    fix gates must actually correspond to real optional module keys."""
    gates = step_gate_map()
    assert gates.get('monte_carlo_options') == 'market_luck_stress_test'
    assert gates.get('survivor_stress') == 'survivor_stress_test'
