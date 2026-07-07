"""Spending model facade — public API for spending-related data_io functions.

This module provides a clean, stable interface to spending-related CSV parsing
and plan data functions without exposing internal data_io implementation details.

Functions:
- load_csv: Load and normalize CSV data from file
- parse_client: Parse CSV data into plan configuration dictionary
- validate_projection: Validate projection results for data integrity
- summarize_validation: Generate validation summary report
"""

from .data_io import load_csv, parse_client, validate_projection, summarize_validation

__all__ = [
    'load_csv',
    'parse_client',
    'validate_projection',
    'summarize_validation',
]
