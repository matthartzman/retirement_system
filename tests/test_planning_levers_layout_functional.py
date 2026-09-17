from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_function_source, dashboard_js_text


def test_planning_levers_ui_has_source_column_and_compact_inputs():
    js = (dashboard_js_text() + (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8-sig'))
    css = (ROOT / 'frontend/css/dashboard.css').read_text(encoding='utf-8')
    assert '<th>Source</th><th>Test amount</th>' in js
    assert 'source-jump' in js
    assert '"Spending Categories",\n    "spending_core",' in js
    assert '"Retirement Timing",\n    "household_people"' in js
    assert 'lever-test-input' in css
    assert 'width:76px' in css
    assert 'white-space:nowrap' in css


def test_planning_levers_no_longer_carries_its_own_quick_nav_hub():
    # #256's original fix (and its follow-up "make sure applied to all
    # optional modules") gated a "Stress tests - resilience" quick-nav card
    # here through leverNavButton()/stepGatedByOptionalModule(), so the
    # Long-term care button correctly disappeared when long_term_care_stress
    # was off. Ticket 323 removed that hub entirely: every one of its former
    # destinations, including Long-Term Care, now has a real, permanent nav
    # entry of its own (one of the three Strategy screens), so an in-page
    # launcher grid duplicating them was exactly the redundancy the redesign
    # removes. The module-gating contract for Long-Term Care did not
    # disappear with the hub -- it moved onto strategySection()'s `gate`
    # parameter in dashboard_decomp_strategy_workspace.js, asserted against
    # the same server-declared step_gate_map() in
    # test_strategy_workspace_module_gating.py.
    fn = dashboard_function_source('renderPlanningLevers')
    # Checks the function's actual code shape (the declaration and a real
    # call), not comment prose that legitimately names the removed helper
    # while explaining its removal.
    assert 'function leverNavButton(stepId' not in fn
    assert '= leverNavButton(' not in fn
    assert '"ltc_stress"' not in fn
    assert 'data-step-id="ltc_stress"' not in fn


def test_planning_levers_workbook_has_source_section_column():
    py = (ROOT / 'src/reporting/workbook_builder.py').read_text()
    assert "'Source Section'" in py
    assert "'Spending Categories', 10000" in py
    assert "'Retirement Timing', 1" in py
    assert "'=D{r}*$B$10*0.55'" in py
    assert "ws.merge_cells(start_row=j, start_column=1, end_row=j, end_column=10)" in py
