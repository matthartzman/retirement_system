"""Balance-sheet liability lines, shared by the 1D Balance Sheet pages.

The engine nets the primary mortgage and the HELOC inside ``home_equity`` and subtracts the additional
liabilities (credit cards, auto / student / other loans) in ``total_nw``; ``total_liabilities`` is the sum
of every line below. The sheets list each one so Total Assets - Total Liabilities ties to the projection.
"""
from __future__ import annotations

from typing import Any, Mapping


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def balance_sheet_liabilities(yr0: Mapping[str, Any], fallback_mortgage: float) -> list[tuple[str, float, str]]:
    """``(label, amount, note)`` for the primary mortgage, HELOC, next-housing mortgage and additional
    liabilities at the plan-start row. The rental mortgages stay with the Rental Properties lines."""
    mortgage = _f(yr0['mort_bal_yr']) if 'mort_bal_yr' in yr0 else fallback_mortgage
    return [
        ('Mortgage', mortgage, 'Offsets Primary Residence gross value; not double-counted as Home Equity'),
        ('HELOC', _f(yr0.get('heloc_liability')), 'Home equity line balance'),
        ('Next-Housing Mortgage', _f(yr0.get('next_housing_mortgage_balance')), 'Offsets the next home'),
        ('Credit Cards, Loans & Other Liabilities', _f(yr0.get('additional_liabilities')),
         'Outstanding balances from the Liabilities table'),
    ]
