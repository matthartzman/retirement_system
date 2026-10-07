"""State tax reference from ``reference.db`` (WP3.3).

Table ``state_tax`` (built by ``tools/reference_slices/state_tax.py``) holds the
verbatim CSV strings. ``state_tax_rows`` returns them as the old ``csv.DictReader``
did; ``state_tax_rules`` reproduces the overlay ``taxes.load_state_tax`` built from
that file on top of ``STATE_TAX_DEFAULTS``.
"""
from __future__ import annotations

from typing import Any

from ..ref_access import reference
from ..ref_data import RefData

COLUMNS = ("state", "rate", "type", "exempt_retirement", "exempt_ss", "prop_rate", "sales_rate", "estate",
           "estate_exempt", "retirement_exempt_over_65", "source", "estate_calc")


def state_tax_rows(ref: RefData | None = None) -> list[dict[str, str]]:
    """Raw rows in file order, every value a ``str``."""
    ref = reference() if ref is None else ref
    cols = ", ".join(f'"{c}"' for c in COLUMNS)
    return [{c: r[c] for c in COLUMNS} for r in ref.query(f'SELECT {cols} FROM "state_tax" ORDER BY seq')]


def state_tax_rules(ref: RefData | None = None) -> dict[str, dict[str, Any]]:
    """``STATE_TAX_DEFAULTS`` overlaid with the reference rows (parsed like the old CSV loader)."""
    from ...taxes import STATE_TAX_DEFAULTS, _parse_bool, _parse_float
    rules = {k: dict(v) for k, v in STATE_TAX_DEFAULTS.items()}
    for row in state_tax_rows(ref):
        state = (row.get('state', '') or '').strip()
        if not state or state.startswith('#'):
            continue
        rules[state] = {
            'rate':                     _parse_float(row.get('rate', '0')),
            'type':                     (row.get('type', 'flat') or 'flat').strip(),
            'exempt_retirement':         _parse_bool(row.get('exempt_retirement', 'FALSE')),
            'exempt_ss':                _parse_bool(row.get('exempt_ss', 'TRUE')),
            'prop_rate':                _parse_float(row.get('prop_rate', '0')),
            'sales_rate':               _parse_float(row.get('sales_rate', '0')),
            'estate':                   _parse_bool(row.get('estate', 'FALSE')),
            'estate_exempt':            _parse_float(row.get('estate_exempt', '0')),
            'estate_calc':              (row.get('estate_calc', '') or '').strip() or 'none',
            'retirement_exempt_over_65': _parse_float(row.get('retirement_exempt_over_65', '0')),
            'source':                   (row.get('source', '') or '').strip(),
        }
    return rules
