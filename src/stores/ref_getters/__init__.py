"""Typed getters over ``reference.db``, one module per slice (WP3).

Convention (see documentation/reference/REFERENCE_DB_SLICES.md):

- ``src/stores/ref_getters/<slice>.py`` defines plain functions
  ``def <getter>(ref: RefData | None = None) -> <old loader's type>``. With no
  argument they use the process-wide ``reference()``; tests pass a ``RefData``.
- A getter returns exactly the structure the old file loader returned (same
  container types, key order, int/float, tuples) and builds fresh objects on
  every call, because callers mutate what loaders hand them. A getter that
  caches must hand out copies.
- Getters only call ``ref.query(...)``; they never open files. Source parsing
  lives in ``tools/reference_slices/`` (dev-only), not here.
- Consumers import the function from its slice module; nothing is attached to
  ``RefData`` itself, so slices never edit a shared class.

``GOLDEN_GETTERS`` maps every golden fixture in ``tests/fixtures/reference_golden/``
(``<name>.json``) to the zero-argument view that must reproduce it. A getter that
takes arguments registers a wrapper here that covers its argument space (for
example ``lambda ref: {p: cma(p, ref) for p in PRESETS}``).
"""
from __future__ import annotations

from typing import Any, Callable

from ..ref_data import RefData
from . import cma as _cma
from . import mortality_real_loss as _mrl
from . import security_master as _security_master
from . import state_tax as _state_tax
from . import tax_law as _tax_law
from . import tax_update_dashboard as _tax_update_dashboard

GOLDEN_GETTERS: dict[str, Callable[[RefData], Any]] = {
    "capital_market_rows": _cma.capital_market_rows,
    "correlation_rows": _cma.correlation_rows,
    "mortality_qx_table": _mrl.mortality_qx_table,
    "real_loss_rows": _mrl.real_loss_rows,
    "security_master_rows": _security_master.security_master_rows,
    "state_tax_rows": _state_tax.state_tax_rows,
    "state_tax_rules": _state_tax.state_tax_rules,
    "tax_law": _tax_law.tax_law_dataset,
    "tax_law_freshness": _tax_law.tax_law_freshness,
    "tax_update_dashboard": _tax_update_dashboard.tax_update_dashboard,
}
