"""Back-compat shim: the housing optimizer now lives in ``src/housing/``.

The module was carved into a package (see ``src.housing``'s docstring for
the map) without any behavior change. This path is kept because
``src/server/plan_routes.py``, the existing test modules, and the design
docs all reference it; new code should import from ``src.housing``
directly.

Private names are re-exported too -- existing tests reach for
``_coordinate_search_2d``/``_run_engine`` and friends, and there is no
value in churning them.
"""
from __future__ import annotations

from .housing import *  # noqa: F401,F403 -- public API, see src/housing/__init__.py
from .housing import __all__ as _public_all
from .housing.models import (  # noqa: F401
    NARROWED_MAX_EVALS_PER_AXIS,
    _NARROWED_EVALS_PER_ANCHOR_LOCATION,
)
from .housing.plan_variant import (  # noqa: F401
    _STATE_ABBREV,
    _apply_candidate,
    _estimate_for_location,
    _purchase_price_for_location,
    _purchase_step,
    _rent_step,
    _residency_schedule,
    _run_engine,
)
from .housing.constraints import _location_timeline  # noqa: F401
from .housing.scoring import _lifetime_cost, _pass1_objective, _pass1_value  # noqa: F401
from .housing.search import (  # noqa: F401
    _coordinate_search_1d,
    _coordinate_search_2d,
    _score_move1_point,
    _score_move2_point,
)
from .housing.results import _format_candidate, _format_move, _format_output  # noqa: F401
from .housing.api import (  # noqa: F401
    _parse_family_presence,
    _parse_location,
    _parse_move2_window,
    _parse_search_window,
)

__all__ = list(_public_all)
