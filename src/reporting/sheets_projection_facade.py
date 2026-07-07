"""Projection sheets facade — entry point for all projection sheet builders.

This module provides the public interface for projection sheet generation:
- build_sheet5: Net Worth Projection
- build_sheet6: Cash Flow Projection
- build_sheet7: Lifetime Tax Projection
- build_sheet8: Charts Dashboard

The actual builders are located in separate concern-specific modules:
- sheets_projection_net_worth.py (build_sheet5)
- sheets_projection (build_sheet6, build_sheet7, build_sheet8 — pending extraction)

This facade maintains backwards compatibility during module extraction.
"""

from .sheets_projection_net_worth import build_sheet5
from .sheets_projection import build_sheet6, build_sheet7, build_sheet8

__all__ = ['build_sheet5', 'build_sheet6', 'build_sheet7', 'build_sheet8']
