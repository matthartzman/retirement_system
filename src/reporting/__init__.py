"""Reporting package: workbook, PDF, dashboard, and report-generation modules.

The executable workbook entry point is src.reporting.workbook_builder.main.

Public API:
- workbook_builder: Main workbook generation entry point
- sheets_projection_facade: All 4 projection sheet builders (5-8)
- sheets_summary_builder: Executive summary & assumptions (sheets 1-2)
- sheets_allocation_helpers: Allocation & tax-aware trading helpers (sheet 4)
- sheets_tax_reporter: Balance sheet & tax reporting (sheet 3)
"""

from .workbook_builder import main as build_workbook
from .sheets_projection_facade import build_sheet5, build_sheet6, build_sheet7, build_sheet8
from .sheets_summary_builder import build_sheet1, build_sheet2
from .sheets_tax_reporter import build_sheet3
from .sheets_allocation_helpers import build_sheet4

__all__ = [
    'build_workbook',
    'build_sheet1', 'build_sheet2', 'build_sheet3', 'build_sheet4',
    'build_sheet5', 'build_sheet6', 'build_sheet7', 'build_sheet8',
]
