"""daf.py — Donor Advised Fund (DAF) parameter parsing.

Extracted from src/data_io.py's parse_client() as part of system review
2026-08-31, finding A5 / Wave 3 item 3.13 ("split parse_client into
src/parsing/ siblings; move validation out"). src/data_io.py re-exports
parse_daf for backward compatibility with existing callers.

Imports the small scalar-coercion helpers (_v, _b, _n, _y) back from
src.data_io rather than duplicating them: those helpers are still shared
primitives used throughout parse_client and are themselves slated for their
own future extraction (see the item 3.13 tracking note in
src/parsing/__init__.py). This works because src.data_io defines them before
importing this module (see the "===== BEGIN data_parser.py =====" section),
the same partial-circular-import pattern already used by
src/parsing/advanced_modules.py.
"""
from __future__ import annotations

from ..data_io import _b, _n, _v, _y


def parse_daf(data, plan_start):
    """Parse the "DAF" (Donor Advised Fund) input section.

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and ``plan_start`` (already computed
    earlier in parse_client) and returns the DAF fields that parse_client
    merges into the engine config ``c``.
    """
    daf_enabled = _b(_v(data, 'DAF', 'Settings', 'enabled', 'FALSE'))
    daf_amount = _n(_v(data, 'DAF', 'Settings', 'contribution_amount', '0'), 0)
    daf_year = _y(_v(data, 'DAF', 'Settings', 'contribution_year', str(plan_start)), plan_start)
    daf_use_amount = _n(_v(data, 'DAF', 'Settings', 'annual_grant_amount', '0'), 0)
    daf_use_start = _y(_v(data, 'DAF', 'Settings', 'grant_start_year', '2027'), 2027)
    daf_use_end = _y(_v(data, 'DAF', 'Settings', 'grant_end_year', '2035'), 2035)
    # Item 4.2 (P4): cash contributions are AGI-limited at 60%; a contribution
    # of appreciated securities is limited to 30% instead (IRC 170(b)(1)(C)/(G)).
    daf_contribution_is_appreciated = _b(_v(data, 'DAF', 'Settings', 'contribution_is_appreciated', 'FALSE'))

    return {
        'daf_enabled': daf_enabled,
        'daf_amount': daf_amount,
        'daf_year': daf_year,
        'daf_use_amount': daf_use_amount,
        'daf_use_start': daf_use_start,
        'daf_use_end': daf_use_end,
        'daf_contribution_is_appreciated': daf_contribution_is_appreciated,
    }
