"""Housing optimizer value types and tunables -- no behavior.

Every dataclass the optimizer passes around (inputs, one candidate plan
variant, one scored result) plus the constants worth turning a dial on
lives here, so a refinement that only changes a bound or an enum touches
one file. See ``src.housing``'s package docstring for the design narrative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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

# Evaluation budget for the bounded coordinate searches in ``search.py``
# (used as those functions' default ``max_evals``), applied per axis. Raising
# it widens narrowed mode's search at a proportional cost in engine runs.
NARROWED_MAX_EVALS_PER_AXIS = 25

# Upper bound on engine evaluations per (eligible move-1 candidate, location)
# pair under `search_mode='narrowed'`; see generate_move1_candidates_narrowed's
# docstring.
_NARROWED_EVALS_PER_ANCHOR_LOCATION = NARROWED_MAX_EVALS_PER_AXIS * 2

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
    lot_size_band: str = 'quarter_half'
    built_within_years: int | None = None
    # Display/traceability only when this Location came from a ZIP search.
    # Nothing downstream reads it -- see src/housing/zip_screen/resolve.py.
    zip_code: str | None = None


DISPOSITIONS = ('sell', 'keep', 'auto')
AREA_TYPES = ('any', 'urban', 'suburban', 'exurban', 'rural')
FAMILY_RADII_MILES = (10, 25, 50, 100)
MOVE_ACTIONS = ('auto', 'buy', 'rent')


@dataclass(frozen=True)
class SaleWindow:
    earliest_sale_year: int
    latest_sale_year: int


@dataclass(frozen=True)
class MoveWindow:
    earliest_acquisition_year: int
    latest_acquisition_year: int


@dataclass(frozen=True)
class FamilyPresence:
    """Proximity to a fixed ZIP, not residence in a state (design §6.4)."""
    zip_code: str
    radius_miles: int
    from_year: int
    through_year: int


@dataclass(frozen=True)
class OriginalHome:
    """What happens to the home the household owns today.

    ``disposition`` is resolved per candidate: 'sell' carries a searched
    ``sale_year``; 'keep' carries ``None`` and leaves ``home_sale_yr`` at 0.
    'auto' is a request-level value only -- it never reaches a candidate,
    because generation expands it into both concrete dispositions.
    """
    disposition: str
    sale_year: int | None = None


@dataclass(frozen=True)
class Move:
    """One acquisition. Independent of any sale (design §5.1).

    ``action`` is 'buy' or 'rent' -- never 'auto', which is a request-level
    value expanded during generation. ``acquisition_year`` is the closing year
    for a purchase and the lease-start year for a rental; the old model's
    ``purchase_year=None``-means-rent convention is gone, so a rental now has
    a real year and an explicit action.
    """
    index: int
    acquisition_year: int
    action: str
    location: Location
    mode: str = 'sequential'   # 'sequential' | 'concurrent' (index 2 only)


@dataclass
class HousingCandidate:
    original_home: OriginalHome
    moves: tuple[Move, ...]
    anchor_of: "HousingCandidate | None" = None

    @property
    def move1(self) -> Move:
        return self.moves[0]

    @property
    def move2(self) -> Move | None:
        return self.moves[1] if len(self.moves) > 1 else None

    @property
    def is_two_move(self) -> bool:
        return len(self.moves) > 1


@dataclass
class ScoredCandidate:
    candidate: HousingCandidate
    net_worth: float
    lifetime_cost: float
    mc_success_rate: float | None
    sec121_exclusion_lost: list[bool]
    notes: list[str] = field(default_factory=list)
