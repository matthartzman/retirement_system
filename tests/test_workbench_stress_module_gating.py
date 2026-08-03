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

ROOT = Path(__file__).resolve().parents[1]


def _stress_suite_fn():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    start = js.index('function renderWorkbenchStressHtml(')
    end = js.index('\nfunction renderWorkbenchLeverEditorHtml', start)
    return js[start:end]


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
