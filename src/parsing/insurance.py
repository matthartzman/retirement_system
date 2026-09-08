"""insurance.py — "Insurance In Force" input-section helpers.

Extracted from src/data_io.py's parse_client() as part of system review
2026-08-31, finding A5 / Wave 3 item 3.13 ("split parse_client into
src/parsing/ siblings; move validation out"). src/data_io.py re-exports
_insurance_policy_premium_sum for backward compatibility with existing
callers.

Unlike parse_daf()/parse_note_receivable()/parse_advanced_modules(), this
module holds a single scalar helper rather than a full parse_x(data, ...)
section parser -- parse_client's own Insurance In Force / life-insurance
handling (see the _LIFE_POLICY_TYPES set in src/data_io.py) has not been
extracted yet and remains a candidate for a future pass into this module.

Imports the small scalar-coercion helpers (_b, _n, _v) back from
src.data_io rather than duplicating them: those helpers are still shared
primitives used throughout parse_client and are themselves slated for their
own future extraction (see the item 3.13 tracking note in
src/parsing/__init__.py). This works because src.data_io defines them before
importing this module, the same partial-circular-import pattern already
used by src/parsing/daf.py, src/parsing/note_receivable.py, and
src/parsing/advanced_modules.py.
"""
from __future__ import annotations

from ..data_io import _b, _n, _v


def _insurance_policy_premium_sum(data, policy_type):
    """Sum annual premiums for "Insurance In Force" rows of ``policy_type``.

    #224: an Insurance Policy record (Insurance page) of this type becomes
    the source of truth for that baseline once one exists with a nonzero
    premium, instead of a separately-maintained comparison number that can
    drift from it. Gated behind the same "Existing Life Insurance" optional
    module every other Insurance In Force row is gated behind (see #226-
    style optional-module gating) -- otherwise this would activate policy
    rows the rest of the app is still treating as off/inactive.
    """
    if not _b(_v(data, 'Optional Functions', '', 'existing_life_insurance', 'FALSE')):
        return 0.0
    total = 0.0
    target = policy_type.strip().lower()
    for fields in (data.get('Insurance In Force') or {}).values():
        if str(fields.get('policy_type', '')).strip().lower() != target:
            continue
        total += _n(fields.get('annual_premium', '0'), 0)
    return total
