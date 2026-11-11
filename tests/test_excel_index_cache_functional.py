"""W3-11 / ARC-007: the Excel fallback index is cached on workbook mtime and size."""
from __future__ import annotations

import os

from openpyxl import Workbook

from src import detailed_results as dr


def _make(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    for i in range(rows):
        ws.append([i, i * 2])
    wb.save(path)


def test_index_is_reused_until_the_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "wb.xlsx"
    _make(path, 3)
    calls = []
    real = dr._excel_workbook_detailed_index_uncached
    monkeypatch.setattr(dr, "_excel_workbook_detailed_index_uncached", lambda p: (calls.append(1), real(p))[1])
    dr._EXCEL_INDEX_CACHE.clear()
    first = dr._excel_workbook_detailed_index(path)
    second = dr._excel_workbook_detailed_index(path)
    assert len(calls) == 1 and first == second and first is not second   # a copy, so callers cannot corrupt the cache
    _make(path, 9)
    os.utime(path, ns=(os.stat(path).st_atime_ns, os.stat(path).st_mtime_ns + 5_000_000_000))
    third = dr._excel_workbook_detailed_index(path)
    assert len(calls) == 2 and third["sheets"][0]["row_count"] == 9


def test_missing_workbook_is_not_cached(tmp_path):
    assert dr._excel_workbook_detailed_index(tmp_path / "nope.xlsx")["success"] is False
