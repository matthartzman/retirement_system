from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text


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


def test_planning_levers_gates_ltc_quick_nav_button_on_optional_function():
    # #256 (and its follow-up "make sure applied to all optional modules"):
    # the "Stress tests - resilience" quick-nav card must not show the
    # "Long-term care" button when the long_term_care_stress optional module
    # is disabled. Originally a hand-picked ltcLeverButton conditional (like
    # divorce_qdro's own hand-picked conditional); both were superseded by
    # leverNavButton(), which gates every quick-nav button here through the
    # same server-declared stepGatedByOptionalModule() the rest of the app's
    # navigation already uses -- see test_planning_levers_module_gating.py
    # for the full cross-module coverage.
    js = (dashboard_js_text() + (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8-sig'))
    start = js.index('function renderPlanningLevers(')
    fn = js[start: js.index('\nfunction ', start + 1)]
    assert 'leverNavButton("ltc_stress", "Long-term care")' in fn
    assert 'stepGatedByOptionalModule(stepId)' in fn
    # The only reference to the ltc_stress button should be the single
    # leverNavButton(...) call, not a second hardcoded copy in the template.
    assert fn.count('data-step-id="ltc_stress"') == 0
    assert fn.count('"ltc_stress"') == 1


def test_planning_levers_workbook_has_source_section_column():
    py = (ROOT / 'src/reporting/workbook_builder.py').read_text()
    assert "'Source Section'" in py
    assert "'Spending Categories', 10000" in py
    assert "'Retirement Timing', 1" in py
    assert "'=D{r}*$B$10*0.55'" in py
    assert "ws.merge_cells(start_row=j, start_column=1, end_row=j, end_column=10)" in py
