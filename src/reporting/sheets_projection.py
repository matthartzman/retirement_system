"""Backwards-compatibility re-export of projection sheet builders.

All sheet builders have been extracted to concern-specific modules:
- build_sheet5 → sheets_projection_net_worth.py
- build_sheet6 → sheets_projection_cashflow.py
- build_sheet7 → sheets_projection_tax.py
- build_sheet8 → sheets_projection_charts.py

For new code, import from sheets_projection_facade instead.
This module is retained for backwards compatibility.
"""

from .sheets_projection_facade import build_sheet5, build_sheet6, build_sheet7, build_sheet8

__all__ = ['build_sheet5', 'build_sheet6', 'build_sheet7', 'build_sheet8']
