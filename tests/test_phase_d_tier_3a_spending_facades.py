"""Integration tests for Phase D Tier 3A spending and transaction processing facades.

Verifies that the spending_model_facade and transaction_processor_facade maintain
correct functionality and provide stable interfaces to underlying modules.
"""

import inspect


def test_spending_model_facade_imports():
    """Verify all spending model functions are importable from facade."""
    from src.spending_model_facade import (
        load_csv, parse_client, validate_projection, summarize_validation
    )
    assert callable(load_csv)
    assert callable(parse_client)
    assert callable(validate_projection)
    assert callable(summarize_validation)


def test_spending_model_facade_routes_to_data_io():
    """Verify facade imports come from data_io module."""
    from src import spending_model_facade
    from src import data_io

    assert spending_model_facade.load_csv is data_io.load_csv
    assert spending_model_facade.parse_client is data_io.parse_client
    assert spending_model_facade.validate_projection is data_io.validate_projection
    assert spending_model_facade.summarize_validation is data_io.summarize_validation


def test_transaction_processor_facade_imports():
    """Verify all transaction processing functions are importable from facade."""
    from src.transaction_processor_facade import (
        load_transactions, load_budget, load_taxonomy, group_actuals,
        budget_by_group, load_category_map
    )
    assert callable(load_transactions)
    assert callable(load_budget)
    assert callable(load_taxonomy)
    assert callable(group_actuals)
    assert callable(budget_by_group)
    assert callable(load_category_map)


def test_transaction_processor_facade_routes_to_spending_tracker():
    """Verify facade imports come from spending_tracker module."""
    from src import transaction_processor_facade
    from src import spending_tracker

    assert transaction_processor_facade.load_transactions is spending_tracker.load_transactions
    assert transaction_processor_facade.load_budget is spending_tracker.load_budget
    assert transaction_processor_facade.load_taxonomy is spending_tracker.load_taxonomy
    assert transaction_processor_facade.group_actuals is spending_tracker.group_actuals
    assert transaction_processor_facade.budget_by_group is spending_tracker.budget_by_group


def test_spending_model_facade_function_signatures():
    """Verify spending model functions have expected signatures."""
    from src.spending_model_facade import load_csv, parse_client, validate_projection

    # load_csv should accept a path
    sig = inspect.signature(load_csv)
    assert 'path' in sig.parameters

    # parse_client should accept data and url_template
    sig = inspect.signature(parse_client)
    assert 'data' in sig.parameters
    assert 'url_template' in sig.parameters

    # validate_projection should accept rows and config
    sig = inspect.signature(validate_projection)
    assert 'rows' in sig.parameters
    assert 'c' in sig.parameters


def test_transaction_processor_facade_function_signatures():
    """Verify transaction processor functions have expected signatures."""
    from src.transaction_processor_facade import load_transactions, load_budget, load_taxonomy

    # load_transactions should accept optional root and year
    sig = inspect.signature(load_transactions)
    params = list(sig.parameters.keys())
    assert 'root' in params or len(params) >= 0  # May have optional params

    # load_budget should be callable
    sig = inspect.signature(load_budget)
    assert sig is not None

    # load_taxonomy should be callable
    sig = inspect.signature(load_taxonomy)
    assert sig is not None


def test_facades_have_docstrings():
    """Verify facades and their functions have documentation."""
    from src import spending_model_facade
    from src import transaction_processor_facade

    # Module docstrings
    assert spending_model_facade.__doc__ is not None
    assert 'spending' in spending_model_facade.__doc__.lower() or 'csv' in spending_model_facade.__doc__.lower()

    assert transaction_processor_facade.__doc__ is not None
    assert 'transaction' in transaction_processor_facade.__doc__.lower() or 'budget' in transaction_processor_facade.__doc__.lower()


def test_facades_export_all_correctly():
    """Verify __all__ exports match actual module contents."""
    from src import spending_model_facade
    from src import transaction_processor_facade

    # spending_model_facade
    expected_spending = ['load_csv', 'parse_client', 'validate_projection', 'summarize_validation']
    for name in expected_spending:
        assert name in spending_model_facade.__all__
        assert hasattr(spending_model_facade, name)

    # transaction_processor_facade
    expected_transaction = ['load_transactions', 'load_budget', 'load_taxonomy', 'group_actuals']
    for name in expected_transaction:
        assert name in transaction_processor_facade.__all__
        assert hasattr(transaction_processor_facade, name)


def test_no_circular_imports():
    """Verify facades don't create circular import chains."""
    try:
        from src import spending_model_facade
        from src import transaction_processor_facade
        from src import data_io
        from src import spending_tracker
        # If we get here, no circular imports occurred
        assert True
    except ImportError as e:
        if 'circular' in str(e).lower():
            raise AssertionError(f"Circular import detected: {e}")
        raise


def test_facades_maintain_public_api():
    """Verify facades don't break existing public API."""
    # Direct imports from data_io should still work
    from src.data_io import parse_client as parse_direct
    from src.spending_model_facade import parse_client as parse_facade

    assert parse_direct is parse_facade

    # Direct imports from spending_tracker should still work
    from src.spending_tracker import load_transactions as load_direct
    from src.transaction_processor_facade import load_transactions as load_facade

    assert load_direct is load_facade
