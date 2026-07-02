from openpyxl import load_workbook


def _visible_wb(workbook_path):
    assert workbook_path.exists(), 'Generated workbook is missing'
    return load_workbook(workbook_path, read_only=False, data_only=False)


def test_system_section_uses_clean_sheet_sequence_without_feature_toggle(built_workbook_path):
    wb = _visible_wb(built_workbook_path)
    visible = [ws.title for ws in wb.worksheets if ws.sheet_state == 'visible']
    expected = [
        '1. Reports','1A. Executive Summary','1B. Net Worth','1C. Cash Flow','1D. Balance Sheet','1E. Charts','1F. Lifetime Taxes',
        '1G. Core Spending','1H. Spending Summary',
        '2. Optimizers','2A. Roth Conversion','2B. Asset Allocation','2C. State Residency','2D. Social Security','2E. S-Corp vs LLC','2F. Charitable Giving','2G. Estate & Legacy Planning','2H. Planning Levers',
        '3. Risk & Stress Tests','3A. Monte Carlo','3B. Survivor','3C. LTC + Life Insurance',
        '4. System','4A. Plan Data','4B. Assumptions','4C. Account Reconciliation','4D. Quality Control','4E. RMD Audit','4F. Methodology','4G. Glossary',
    ]
    assert visible[:len(expected)] == expected
    assert '4D. Feature Toggle' not in visible
    assert '4A. Plan Scope' not in visible


def test_visible_workbook_has_no_stale_feature_or_plan_scope_labels(built_workbook_path):
    wb = _visible_wb(built_workbook_path)
    banned = ['Feature Toggle', 'Feature Toggles', 'FEATURE TOGGLES', 'Feature / Toggle', 'Plan Scope', 'Charts Dashboard', 'System Configuration']
    hits = []
    for ws in wb.worksheets:
        if ws.sheet_state != 'visible':
            continue
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    for term in banned:
                        if term in cell.value:
                            hits.append((ws.title, cell.coordinate, term, cell.value))
    assert not hits


def test_column_width_caps_are_applied_without_header_driven_expansion(built_workbook_path):
    wb = _visible_wb(built_workbook_path)
    # The generated layout pass uses Excel character widths approximating the requested pixel caps.
    max_text_width = round((200 - 5) / 7, 1) + 0.1
    max_dollar_width = round((71 - 5) / 7, 1) + 0.1
    max_int_width = round((40 - 5) / 7, 1) + 0.1
    assert wb['4F. Methodology'].column_dimensions['A'].width <= max_text_width
    assert wb['4E. RMD Audit'].column_dimensions['G'].width <= max_dollar_width
    assert wb['4E. RMD Audit'].column_dimensions['C'].width <= max_int_width
