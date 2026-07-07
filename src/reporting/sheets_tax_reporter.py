"""Tax reporting and balance sheet generation.

This module provides tax and portfolio-tracking workbook functionality:
- build_sheet3: Balance Sheet (Today) — asset/liability summary with valuation

This sheet presents a comprehensive snapshot of the household's current financial
position, reconciling to the projection engine's starting balances.

Future: This facade will import from sheets_summary.py until code is physically moved.
Once the physical split is complete, this will be the canonical source for tax
reporting and balance-sheet builders.
"""

from .sheets_summary import build_sheet3

__all__ = ['build_sheet3']
