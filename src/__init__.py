"""Retirement Plan System source package.

Public facades for key subsystems:
- spending_model_facade: CSV parsing and plan data functions
- transaction_processor_facade: Transaction loading and budget management
"""
from .version import VERSION as __version__, PRODUCT_NAME, RELEASE_LABEL

__all__ = [
    'VERSION',
    '__version__',
    'PRODUCT_NAME',
    'RELEASE_LABEL',
]
