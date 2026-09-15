"""Housing optimizer value types and tunables -- no behavior.

Every dataclass the optimizer passes around (inputs, one candidate plan
variant, one scored result) plus the constants worth turning a dial on
lives here, so a refinement that only changes a bound or an enum touches
one file. See ``src.housing``'s package docstring for the design narrative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OBJECTIVES = ('net_worth', 'lifetime_cost', 'mc_success_rate')
SEARCH_MODES = ('full', 'narrowed')
MOVE2_STRATEGIES = ('anchored', 'cross_product')

# Hard cap on move-2 candidates ``move2_strategy='cross_product'`` will
# evaluate through the real engine, checked before any engine invocation
# (§8.2 P3). Chosen to comfortably cover a realistic use of cross_product --
# a handful of eligible move-1 anchors from a `search_mode='narrowed'` Pass 1,
# or a small number of eligible full-grid anchors against a modest move-2
# window -- while refusing a wide-window full-grid cross_product outright
# rather than letting it silently run for a very long time.
MOVE2_CROSS_PRODUCT_CAP = 3000

# Evaluation budgets for the bounded coordinate searches in ``search.py``
# (used as those functions' default ``max_evals``). Raising either widens
# narrowed mode's search at a proportional cost in engine runs.
NARROWED_2D_MAX_EVALS = 25
NARROWED_1D_MAX_EVALS = 8

# Upper bound on engine evaluations per (eligible move-1 candidate, location)
# pair under `search_mode='narrowed'` -- the two budgets above, one 2D search
# plus one 1D rent-branch search; see generate_move1_candidates_narrowed's
# docstring.
_NARROWED_EVALS_PER_ANCHOR_LOCATION = NARROWED_2D_MAX_EVALS + NARROWED_1D_MAX_EVALS

# ZIP -> city_type thresholds, people per square mile (spec section 5.1). The
# optimizer's cost estimate is keyed on city_type, so these decide which
# STATE_ESTIMATES bucket a resolved ZIP lands in.
DENSITY_URBAN = 3000.0
DENSITY_SUBURBAN = 1000.0
DENSITY_EXURBAN = 200.0


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Location:
    state: str
    city_type: str = 'suburban'
    population_size: int = 20000
    target_purchase_price_range: tuple[float, float] | None = None
    bedrooms: int = 3
    bathrooms: float = 2.0
    property_type: str = 'single_family'
    sqft_band: str = '1800_2500'
    built_within_years: int | None = None
    # Display/traceability only when this Location came from a ZIP search.
    # Nothing downstream reads it -- see src/housing/zip_screen/resolve.py.
    zip_code: str | None = None


@dataclass(frozen=True)
class SearchWindow:
    earliest_sale_year: int
    latest_sale_year: int
    earliest_purchase_year: int
    latest_purchase_year: int


@dataclass(frozen=True)
class Move2Window:
    latest_sale_year_2: int
    latest_purchase_year_2: int


@dataclass(frozen=True)
class FamilyPresence:
    region: str
    start_year: int
    end_year: int


@dataclass
class HousingCandidate:
    """One fully-specified plan variant: move 1, and optionally move 2.

    ``purchase_year is None`` means "rent indefinitely" after ``sale_year``
    (move 1) or after ``sale_year_2``/``concurrent_start_year_2`` (move 2,
    when ``purchase_year_2`` is also ``None``).

    ``move2_mode='sequential'`` (default): move 2 sells the move-1 home
    (``sale_year_2``) and relocates to ``location_2``, exactly as before this
    field existed. ``move2_mode='concurrent'``: the move-1 home is never sold
    -- ``location_2`` becomes a second, simultaneous residence starting at
    ``concurrent_start_year_2``. ``sale_year_2`` is always ``None`` in
    concurrent mode (nothing is ever sold under it).
    """
    location_1: Location
    sale_year: int
    purchase_year: int | None
    location_2: Location | None = None
    sale_year_2: int | None = None
    purchase_year_2: int | None = None
    move2_mode: Literal['sequential', 'concurrent'] = 'sequential'
    concurrent_start_year_2: int | None = None
    anchor_of: "HousingCandidate | None" = None

    @property
    def is_two_move(self) -> bool:
        return self.location_2 is not None


@dataclass
class ScoredCandidate:
    candidate: HousingCandidate
    net_worth: float
    lifetime_cost: float
    mc_success_rate: float | None
    sec121_exclusion_lost: list[bool]
    family_presence_via_rental: bool = False
