"""Capital market assumptions and asset correlations from ``reference.db`` (WP3.4).

Tables ``cma`` and ``correlation`` (built by ``tools/reference_slices/cma.py``) hold
the verbatim CSV strings. Each getter returns fresh ``dict`` rows in file order,
every value a ``str``, exactly what ``csv.DictReader`` gave the old file loaders.
"""
from __future__ import annotations

from ..ref_access import reference
from ..ref_data import RefData

CMA_COLUMNS = ("horizon_years", "preset", "asset_class", "expected_return", "volatility", "stock_index_correlation",
               "notes", "distribution_yield", "qualified_dividend_fraction", "tax_exempt_yield")
CORRELATION_COLUMNS = ("horizon_years", "preset", "asset_class_a", "asset_class_b", "correlation", "notes")


def _rows(table: str, cols: tuple[str, ...], ref: RefData | None) -> list[dict[str, str]]:
    ref = reference() if ref is None else ref
    sel = ", ".join(f'"{c}"' for c in cols)
    return [{c: r[c] for c in cols} for r in ref.query(f'SELECT {sel} FROM "{table}" ORDER BY seq')]


def capital_market_rows(ref: RefData | None = None) -> list[dict[str, str]]:
    return _rows("cma", CMA_COLUMNS, ref)


def correlation_rows(ref: RefData | None = None) -> list[dict[str, str]]:
    return _rows("correlation", CORRELATION_COLUMNS, ref)
