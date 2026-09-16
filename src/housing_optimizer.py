"""Back-compat shim: the housing optimizer now lives in ``src/housing/``.

The module was carved into a package (see ``src.housing``'s docstring for
the map) without any behavior change. This path is kept because
``src/server/plan_routes.py``, the existing test modules, and the design
docs all reference it; new code should import from ``src.housing``
directly.

Private names are re-exported too -- existing tests reach for
``_apply_candidate``/``_run_engine`` and friends, and there is no value in
churning them.

Re-export is LAZY, mirroring ``src.housing.__getattr__``. A star import
resolved every name in ``__all__`` at import time, which pulled in every
submodule -- so a single submodule mid-refactor (``api`` during the
2026-09-16 decoupling) made this shim, and every test module that imports it,
unimportable even for names that had nothing to do with it.
"""
from __future__ import annotations

from importlib import import_module

from .housing import __all__ as _public_all

# Private names existing tests reach for, mapped to the submodule that owns
# them. Resolved on first access, never eagerly.
_PRIVATE = {
    '_STATE_ABBREV': 'plan_variant',
    '_apply_candidate': 'plan_variant',
    '_estimate_for_location': 'plan_variant',
    '_purchase_price_for_location': 'plan_variant',
    '_purchase_step': 'plan_variant',
    '_rent_step': 'plan_variant',
    '_residency_schedule': 'plan_variant',
    '_run_engine': 'plan_variant',
    '_step_for': 'plan_variant',
    'DEFAULT_DOWN_PAYMENT_PCT': 'plan_variant',
    'residence_timeline': 'constraints',
    '_lifetime_cost': 'scoring',
    '_pass1_objective': 'scoring',
    '_pass1_value': 'scoring',
    '_descend': 'search',
    '_actions': 'candidates',
    '_format_candidate': 'results',
    '_format_location': 'results',
    '_format_move': 'results',
    'format_output': 'results',
    'NARROWED_MAX_EVALS_PER_AXIS': 'models',
    'NARROWED_MOVE1_AXES': 'models',
    'NARROWED_MOVE2_AXES': 'models',
    'MoveWindow': 'models',
    'SaleWindow': 'models',
    'OriginalHome': 'models',
    'Move': 'models',
}

__all__ = list(_public_all)


def __getattr__(name):
    module = _PRIVATE.get(name)
    if module is not None:
        return getattr(import_module(f'.housing.{module}', __package__), name)
    from . import housing
    return getattr(housing, name)


def __dir__():
    return sorted(set(globals()) | set(_PRIVATE) | set(_public_all))
