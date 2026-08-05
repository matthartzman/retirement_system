"""Workbook Formatting column labels must truncate, not wrap.

Settings -> Workbook Formatting lists one row per Excel column with its
display title. Long titles used to wrap the row instead of truncating,
and Tab from a width field must still jump to the next column's width
field (not the browser's default DOM-order focus target).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_column_title_css_truncates_with_ellipsis():
    css = (ROOT / "frontend" / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert ".wf-col-row .wf-col-title{" in css
    rule = css.split(".wf-col-row .wf-col-title{", 1)[1].split("}", 1)[0]
    assert "white-space:nowrap" in rule
    assert "overflow:hidden" in rule
    assert "text-overflow:ellipsis" in rule
    assert "max-width:" in rule


def test_column_title_has_hover_tooltip_for_full_text():
    js = (ROOT / "frontend" / "js" / "dashboard_decomp_workbook_formatting.js").read_text(
        encoding="utf-8"
    )
    assert 'class="wf-col-title" title="${title}"' in js


def test_tab_key_handler_jumps_between_width_fields_only():
    js = (ROOT / "frontend" / "js" / "dashboard_decomp_workbook_formatting.js").read_text(
        encoding="utf-8"
    )
    assert "function wfWidthInputKeydown(event)" in js
    assert '.wf-col-width input[type=number]' in js
    assert 'onkeydown="wfWidthInputKeydown(event)"' in js

    main_js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    # The page-wide generic Tab handler must defer to wfWidthInputKeydown
    # instead of racing it, or focus ends up on the wrong field.
    assert 'el.closest(".wf-col-width")' in main_js
