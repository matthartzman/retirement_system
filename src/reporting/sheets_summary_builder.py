"""Excel summary sheet builder — executive summary and assumptions.

This module provides the high-level Excel sheet builders for summary reports:
- build_sheet1: Executive Summary (headline numbers, recommendations, release notes)
- build_sheet2: Assumptions & Tax Law (configurable input tables)

Future: This facade will import from sheets_summary.py until code is physically moved.
Once the physical split is complete, this will be the canonical source for these builders.
"""

from .sheets_summary import build_sheet1, build_sheet2

__all__ = ['build_sheet1', 'build_sheet2']
