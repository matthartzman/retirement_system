from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_planning_levers_ui_has_source_column_and_compact_inputs():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8-sig')
    css = (ROOT / 'frontend/css/dashboard.css').read_text(encoding='utf-8')
    assert '<th>Source</th><th>Test amount</th>' in js
    assert 'source-jump' in js
    assert "'Spending Categories','spending_core'" in js
    assert "'Retirement Timing','household_people'" in js
    assert 'lever-test-input' in css
    assert 'width:76px' in css
    assert 'white-space:nowrap' in css


def test_planning_levers_workbook_has_source_section_column():
    py = (ROOT / 'src/reporting/workbook_builder.py').read_text()
    assert "'Source Section'" in py
    assert "'Spending Categories', 10000" in py
    assert "'Retirement Timing', 1" in py
    assert "'=D{r}*$B$10*0.55'" in py
    assert "ws.merge_cells(start_row=j, start_column=1, end_row=j, end_column=10)" in py
