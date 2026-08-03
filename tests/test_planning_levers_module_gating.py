"""#256: the Planning Levers page's "Stress tests" quick-nav card showed a
"Divorce / QDRO" button unconditionally, even when the divorce_qdro optional
workbook module is turned off. The sibling renderWorkbenchStressHtml()
function (same file) already gated its own Divorce Planning block correctly
with optionalFunctionEnabled("divorce_qdro") -- renderPlanningLevers() just
never got the same treatment.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _planning_levers_fn():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    start = js.index('function renderPlanningLevers(')
    end = js.index('\nfunction chatMessageHtml', start)
    return js[start:end]


def test_divorce_lever_button_is_gated_by_the_optional_module():
    fn = _planning_levers_fn()
    assert 'optionalFunctionEnabled("divorce_qdro")' in fn
    assert 'divorceLeverButton' in fn
    # The button markup itself must live inside the conditional assignment,
    # not appear a second time unconditionally in the returned template.
    assert fn.count('data-step-id="divorce_options">Divorce / QDRO</button>') == 1
    assign_start = fn.index('const divorceLeverButton')
    assign_end = fn.index('\n', fn.index(';', assign_start))
    assert 'data-step-id="divorce_options">Divorce / QDRO</button>' in fn[assign_start:assign_end]


def test_other_quick_nav_buttons_are_unaffected():
    """Guard against an overly broad fix that also hides always-available
    levers (Monte Carlo, Scenarios, Survivor, Social Security, etc.)."""
    fn = _planning_levers_fn()
    for label, step in [
        ('Monte Carlo', 'monte_carlo_options'),
        ('Scenarios', 'scenarios'),
        ('Survivor', 'survivor_stress'),
        ('Social Security', 'income_retirement'),
    ]:
        assert f'data-step-id="{step}">{label}</button>' in fn
    # #255: State residency is deliberately removed from this card (the
    # merged State Residency "Tax and Expenses" table replaces its role).
    assert 'data-step-id="state_residency">State residency</button>' not in fn
