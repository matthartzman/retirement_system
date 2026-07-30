from __future__ import annotations

"""minimize_row_heights() previously sized a wrapped cell's row to exactly
`lines * (font_size + LINE_PAD)`, with no separate top/bottom margin term --
LINE_PAD only adds space between/around individual lines, so a cell could
compute to precisely the height its text occupies with zero cushion above
the first line or below the last. CELL_VPAD adds a small fixed margin once
per cell (not per line, so it doesn't compound with line count), including
for text merged across multiple rows, where the combined block's total
needed height (lines*line_pt + CELL_VPAD) is what gets spread evenly across
the spanned rows.
"""

import math
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from src.reporting.workbook_common import minimize_row_heights

LINE_PAD = 4.0
CELL_VPAD = 3.0
CHARS_PER_WIDTH_UNIT = 1.3


def _expected_lines(text, width, font_size=10.0):
    eff_chars_per_line = max(width * CHARS_PER_WIDTH_UNIT, 1.0)
    return sum(max(1, math.ceil(len(line) / eff_chars_per_line)) for line in (text.splitlines() or ['']))


def test_single_row_wrapped_cell_includes_fixed_vpad_beyond_line_leading():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.column_dimensions['A'].width = 20.0
    text = 'a ' * 120  # long enough to wrap across multiple lines at width 20
    cell = ws.cell(1, 1, value=text)
    cell.font = Font(size=10)
    cell.alignment = Alignment(wrap_text=True)

    minimize_row_heights(wb)

    lines = _expected_lines(text, 20.0)
    assert lines > 1, 'test text should wrap to more than one line'
    expected = lines * (10.0 + LINE_PAD) + CELL_VPAD
    assert ws.row_dimensions[1].height == round(expected, 1)


def test_row_spanning_merged_wrapped_cell_distributes_vpad_across_the_span():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.column_dimensions['A'].width = 20.0
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)
    text = 'a ' * 120
    cell = ws.cell(1, 1, value=text)
    cell.font = Font(size=10)
    cell.alignment = Alignment(wrap_text=True)

    minimize_row_heights(wb)

    lines = _expected_lines(text, 20.0)
    total_expected = lines * (10.0 + LINE_PAD) + CELL_VPAD
    per_row_expected = round(total_expected / 2, 1)
    assert ws.row_dimensions[1].height == per_row_expected
    assert ws.row_dimensions[2].height == per_row_expected
    # The two rows together give the wrapped text at least as much room as a
    # single unmerged row would have needed -- CELL_VPAD isn't lost by
    # splitting across the span.
    combined = (ws.row_dimensions[1].height or 0) + (ws.row_dimensions[2].height or 0)
    assert combined >= total_expected - 0.5


def test_single_line_cell_still_gets_the_fixed_vpad_margin():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.column_dimensions['A'].width = 30.0
    cell = ws.cell(1, 1, value='short label')
    cell.font = Font(size=10)
    cell.alignment = Alignment(wrap_text=True)

    minimize_row_heights(wb)

    expected = 1 * (10.0 + LINE_PAD) + CELL_VPAD
    assert ws.row_dimensions[1].height == round(expected, 1)
