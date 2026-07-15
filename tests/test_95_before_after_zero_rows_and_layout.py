from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from src.reporting.workbook_common import TEMPLATE_LAYOUT

ROOT = Path(__file__).resolve().parents[1]


def _zero_money(value) -> bool:
    try:
        return abs(float(value or 0)) < 0.50
    except Exception:
        return False


def test_before_after_rebalancing_omits_zero_before_and_after_rows(built_workbook_path):
    wb = load_workbook(built_workbook_path, data_only=False, read_only=True)
    ws = wb['2B. Asset Allocation']
    start = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == 'BEFORE & AFTER REBALANCING')
    zero_rows = []
    in_table = False
    for row in range(start, ws.max_row + 1):
        a = ws.cell(row, 1).value
        b = ws.cell(row, 2).value
        e = ws.cell(row, 5).value
        if a == 'TAX-EFFICIENT REBALANCING SEQUENCE':
            break
        if a == 'Bucket' and b == 'Before $' and e == 'After $':
            in_table = True
            continue
        if not in_table:
            continue
        if a is None:
            in_table = False
            continue
        if isinstance(a, str) and ' —  Total:' in a:
            in_table = False
            continue
        if _zero_money(b) and _zero_money(e):
            zero_rows.append((row, a))
    wb.close()
    assert zero_rows == []


def test_asset_allocation_columns_are_compact_and_wrapped(built_workbook_path):
    wb = load_workbook(built_workbook_path, data_only=False)
    ws = wb['2B. Asset Allocation']
    pinned = TEMPLATE_LAYOUT.get('2B. Asset Allocation', {}).get('cols', {})
    if pinned:
        # The reference formatting workbook (template for column widths and
        # height.xlsx) pins exact widths for this sheet at generation time,
        # overriding the heuristic <=125 compactness cap below.
        for i in range(1, 11):
            letter = get_column_letter(i)
            if letter in pinned:
                assert ws.column_dimensions[letter].width == pinned[letter]
    else:
        width_total = sum(ws.column_dimensions[get_column_letter(i)].width or 8.43 for i in range(1, 11))
        assert width_total <= 125
    assert ws['A211'].alignment.wrap_text is True
    assert (ws.row_dimensions[211].height or 0) >= 30
    assert ws['A285'].alignment.wrap_text is True
    wb.close()


def test_source_keeps_zero_filter_and_workbook_layout_pass_for_future_builds():
    summary_source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
    common_source = (ROOT / 'src' / 'reporting' / 'workbook_common.py').read_text(encoding='utf-8')
    builder_source = (ROOT / 'src' / 'reporting' / 'workbook_builder.py').read_text(encoding='utf-8')
    assert '_hide_zero_before_after_row' in summary_source
    assert 'if _hide_zero_before_after_row(before_val, after_val):' in summary_source
    assert 'if _hide_zero_before_after_row(bv, av):' in summary_source
    assert 'def optimize_workbook_layout' in common_source
    assert 'wrap_text=True' in common_source
    assert 'row_dimensions[row_idx].height' in common_source
    assert 'ordered_names' in builder_source
