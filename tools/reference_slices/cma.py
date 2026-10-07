"""Slice: capital market assumptions + asset correlations -> tables ``cma`` and ``correlation`` (WP3.4).

Sources ``reference_src/capital_market_assumptions.csv`` and ``asset_correlations.csv``.
Every cell is the verbatim CSV string (percent signs, blank horizon = all horizons),
so the optimizer's existing row filters and number parsing run unchanged on the
rows the getters hand back; ``seq`` keeps file order. Getters: ``src/stores/ref_getters/cma.py``.
"""
from __future__ import annotations

from pathlib import Path

from ._source import read_csv

SOURCES = ("capital_market_assumptions.csv", "asset_correlations.csv")
CMA_HEADER = ("horizon_years", "preset", "asset_class", "expected_return", "volatility", "stock_index_correlation",
              "notes", "distribution_yield", "qualified_dividend_fraction", "tax_exempt_yield")
CORR_HEADER = ("horizon_years", "preset", "asset_class_a", "asset_class_b", "correlation", "notes")


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    cma = [(seq, *(r[c] for c in CMA_HEADER)) for seq, r in enumerate(read_csv(src / SOURCES[0], CMA_HEADER))]
    corr = [(seq, *(r[c] for c in CORR_HEADER)) for seq, r in enumerate(read_csv(src / SOURCES[1], CORR_HEADER))]
    return {"cma": (["seq", *CMA_HEADER], cma), "correlation": (["seq", *CORR_HEADER], corr)}
