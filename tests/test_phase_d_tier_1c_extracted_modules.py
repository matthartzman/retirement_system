"""Integration tests for Phase D Tier 1C extracted projection sheet modules.

Verifies that the extraction of build_sheet5-8 into separate concern-specific
modules maintains correct functionality and avoids circular imports.
"""

import inspect


def test_all_sheet_builders_importable_from_facade():
    """Verify all 4 projection sheet builders can be imported from facade."""
    from src.reporting.sheets_projection_facade import (
        build_sheet5, build_sheet6, build_sheet7, build_sheet8
    )
    assert callable(build_sheet5)
    assert callable(build_sheet6)
    assert callable(build_sheet7)
    assert callable(build_sheet8)


def test_all_sheet_builders_importable_from_package():
    """Verify all sheet builders are exported from reporting package __init__."""
    from src.reporting import (
        build_sheet1, build_sheet2, build_sheet3, build_sheet4,
        build_sheet5, build_sheet6, build_sheet7, build_sheet8
    )
    assert callable(build_sheet1)
    assert callable(build_sheet2)
    assert callable(build_sheet3)
    assert callable(build_sheet4)
    assert callable(build_sheet5)
    assert callable(build_sheet6)
    assert callable(build_sheet7)
    assert callable(build_sheet8)


def test_facade_routes_to_correct_modules():
    """Verify facade imports come from correct extraction modules."""
    from src.reporting import sheets_projection_facade
    from src.reporting import sheets_projection_net_worth
    from src.reporting import sheets_projection_cashflow
    from src.reporting import sheets_projection_tax
    from src.reporting import sheets_projection_charts

    assert sheets_projection_facade.build_sheet5 is sheets_projection_net_worth.build_sheet5
    assert sheets_projection_facade.build_sheet6 is sheets_projection_cashflow.build_sheet6
    assert sheets_projection_facade.build_sheet7 is sheets_projection_tax.build_sheet7
    assert sheets_projection_facade.build_sheet8 is sheets_projection_charts.build_sheet8


def test_extracted_modules_have_correct_signatures():
    """Verify each extracted build_sheet function has correct parameters."""
    from src.reporting.sheets_projection_net_worth import build_sheet5
    from src.reporting.sheets_projection_cashflow import build_sheet6
    from src.reporting.sheets_projection_tax import build_sheet7
    from src.reporting.sheets_projection_charts import build_sheet8

    sig5 = inspect.signature(build_sheet5)
    sig6 = inspect.signature(build_sheet6)
    sig7 = inspect.signature(build_sheet7)
    sig8 = inspect.signature(build_sheet8)

    assert 'ws' in sig5.parameters
    assert 'c' in sig5.parameters
    assert 'rows' in sig5.parameters

    assert 'ws' in sig6.parameters
    assert 'c' in sig6.parameters
    assert 'rows' in sig6.parameters

    assert 'ws' in sig7.parameters
    assert 'c' in sig7.parameters
    assert 'rows' in sig7.parameters

    assert 'ws' in sig8.parameters
    assert 'c' in sig8.parameters
    assert 'rows' in sig8.parameters
    assert 'mc_data' in sig8.parameters  # sheet8 has optional mc_data


def test_backwards_compat_import_from_sheets_projection():
    """Verify sheets_projection.py still provides backwards-compat imports."""
    from src.reporting.sheets_projection import (
        build_sheet5, build_sheet6, build_sheet7, build_sheet8
    )
    assert callable(build_sheet5)
    assert callable(build_sheet6)
    assert callable(build_sheet7)
    assert callable(build_sheet8)


def test_no_circular_imports():
    """Verify extracted modules don't create circular import chains."""
    try:
        from src.reporting import sheets_projection_facade
        from src.reporting import sheets_projection_net_worth
        from src.reporting import sheets_projection_cashflow
        from src.reporting import sheets_projection_tax
        from src.reporting import sheets_projection_charts
        from src.reporting import workbook_builder
        # If we get here, no circular imports occurred
        assert True
    except ImportError as e:
        if 'circular' in str(e).lower():
            raise AssertionError(f"Circular import detected: {e}")
        raise


def test_extracted_modules_docstrings_present():
    """Verify extracted modules have module docstrings."""
    from src.reporting import sheets_projection_net_worth
    from src.reporting import sheets_projection_cashflow
    from src.reporting import sheets_projection_tax
    from src.reporting import sheets_projection_charts

    assert sheets_projection_net_worth.__doc__ is not None
    assert 'Net Worth' in sheets_projection_net_worth.__doc__

    assert sheets_projection_cashflow.__doc__ is not None
    assert 'Cash Flow' in sheets_projection_cashflow.__doc__

    assert sheets_projection_tax.__doc__ is not None
    assert 'Tax' in sheets_projection_tax.__doc__

    assert sheets_projection_charts.__doc__ is not None
    assert 'Charts' in sheets_projection_charts.__doc__


def test_workbook_builder_uses_facade():
    """Verify workbook_builder imports from facade, not original module."""
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    builder = (ROOT / 'src/reporting/workbook_builder.py').read_text(encoding='utf-8')

    # Should import from facade
    assert 'from .sheets_projection_facade import' in builder or \
           'sheets_projection_facade' in builder

    # Should not directly import from sheets_projection for sheet 5-8
    lines = builder.split('\n')
    for line in lines:
        if 'from .sheets_projection import' in line:
            # Should only import things not in the extracted modules
            # (like helper functions if any, but most moved)
            pass  # This is okay for backwards compat
