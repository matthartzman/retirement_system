"""Housing move optimizer (grid search over sale/purchase year and location).

Where things live (all of the below is a pure carve-up of the former
single-file ``src/housing_optimizer.py``; behavior is unchanged and that
path still works as a re-export shim):

* ``models``      -- dataclasses and tunables (windows, candidates, caps,
                     search budgets). Change a bound here, nowhere else.
* ``plan_variant``-- the only place that knows the plan-config wire format
                     or calls the engine (``_apply_candidate``/``_run_engine``).
* ``constraints`` -- ``no_dual_ownership``/``family_presence`` filters and the
                     informational §121 flag. Pure, engine-free.
* ``candidates``  -- full-grid enumeration and move-2 anchor selection. Pure.
* ``search``      -- narrowed mode: engine-free coordinate-search primitives,
                     then the wrappers that bind them to real engine runs.
* ``scoring``     -- row-reading objectives and ranking.
* ``results``     -- ``housing_optimize_v1`` payload shaping.
* ``optimizer``   -- the orchestrator; delegates all of the above.
* ``api``         -- request parsing for ``POST /api/housing/optimize``.

To try something out without writing throwaway code, use the bundled
harness: ``python tools/housing_lab.py --help`` runs a real optimization
against a plan folder and prints/exports the ranked candidates.

Implements docs/superpowers/specs/2026-09-09-housing-optimization-design.md.
Given a set of candidate locations and search windows, generates plan-config
variants, runs them through the existing deterministic engine
(``planning_engines.run_scenario`` -> ``projection_stages.deterministic_engine``)
and Monte Carlo runner (``planning_engines.monte_carlo``) unmodified, filters
by ``no_dual_ownership``/``family_presence``, scores by the selected
objective, and ranks. No new tax logic is added, for move 1 or move 2: both
sales reuse the engine's own gain/§121 pathway in ``home_sale.py`` exactly as
a manually-configured plan would.

**Move 2 is a real, cascade-visible sale (§8.2 P0 of the design doc).** The
engine now has a second sale-with-capital-gain pathway --
``home_sale.py``'s ``apply_next_housing_sale``, sharing the same gain/§121
arithmetic ``apply_home_sale`` uses for the original home -- that a
``next_housing_steps`` purchase step can be pointed at via a ``sale_year``
field. ``plan_variant._apply_candidate`` sets that field instead of
computing move-2's gain/tax itself: the engine's own run produces a real
deposit its withdrawal cascade and Monte Carlo runner both see, so
``net_worth``/``lifetime_cost``/``mc_success_rate`` for a two-move candidate
are as accurate as for a one-move candidate -- no separate out-of-loop
estimate, and no ``mc_approximate`` flag (removed; see git history for the
prior out-of-loop ``Move2SaleEstimate``/``_estimate_move2_sale`` approach
this replaced).

The §121 two-of-five-year ownership/use test is not modeled by the engine at
all (``home_sale.py`` always grants the full statutory exclusion regardless
of ownership duration). Per §3.1.3 of the design doc, failing candidates are
not dropped, only flagged -- so ``sec121_exclusion_lost`` here is an
informational flag (ownership span < 2 years) that never changes a computed
dollar figure, for either move.

**Narrowed search mode (§8.2 P2).** ``optimize_housing``'s default
``search_mode='full'`` is the grid above, byte-for-byte unchanged. Opting
into ``search_mode='narrowed'`` replaces, per candidate location, the full
``(sale_year x purchase_year)`` grid with a bounded coordinate/pattern search
(``_coordinate_search_2d``): a handful of seed points (grid corners plus
center) followed by hill-climbing to the best-improving integer-year
neighbor until none improves, capped at a small evaluation budget -- and
replaces the rent-indefinitely branch's full ``sale_year`` sweep with the
same style of 1D neighbor search (``_coordinate_search_1d``). Move 2's
window is narrowed the same way when both ``search_mode='narrowed'`` and a
``move2_window`` are given. This is a local-search heuristic on whatever
score surface the real engine happens to produce -- it is not guaranteed
unimodal, so narrowed mode can converge on a local rather than the global
optimum and trades completeness for far fewer engine runs (see §7/§8.2 of
the design doc). Candidate *generation* is the only thing that differs;
scoring, filtering, and ranking (``_run_engine``/``score_candidate``/
``family_presence_ok``/``no_dual_ownership``/``rank_candidates``) are shared
unmodified with the full-grid path.

**Move-2 strategy (§8.2 P3).** ``optimize_housing``'s default
``move2_strategy='anchored'`` is §3.2's anchor-on-move-1's-top-N approach
above, byte-for-byte unchanged. Opting into ``move2_strategy='cross_product'``
builds move-2 candidates against *every* move-1 candidate that ends in
ownership (the same eligibility rule ``select_anchors`` uses, just not
narrowed to the top ``anchor_count`` -- so ``anchor_count`` is ignored under
this strategy) out of whatever ``move1_scored`` the active ``search_mode``
already produced (narrowed or full -- there is no separate re-generation).
This is the full cross-product §7 deferred, now offered as an opt-in trade of
runtime for a better shot at the global optimum. Because it can blow up
combinatorially, ``optimize_housing`` computes (exactly, for ``'full'``; by
the documented per-point evaluation-budget estimate, for ``'narrowed'``) the
number of move-2 candidates it would evaluate *before* invoking the engine on
any of them, and raises ``ValueError`` rather than silently running or
truncating an enormous job if that exceeds
``MOVE2_CROSS_PRODUCT_CAP`` (3000 -- generous enough for a real narrowed
search or a handful of eligible full-grid anchors, small enough to keep a
runaway wide-window full-grid cross-product from ever reaching the engine;
see the error message for the caller's options: narrow the window, use fewer
locations, or switch to ``search_mode='narrowed'``)."""
from __future__ import annotations

from .models import (
    MOVE2_CROSS_PRODUCT_CAP,
    MOVE2_STRATEGIES,
    OBJECTIVES,
    SEARCH_MODES,
    FamilyPresence,
    HousingCandidate,
    Location,
    Move2Window,
    ScoredCandidate,
    SearchWindow,
)
from .candidates import (
    estimate_move2_candidate_count,
    filter_candidates_by_action,
    generate_move1_candidates,
    generate_move2_candidates,
    generate_move2_concurrent_candidates,
    select_all_eligible_move1_candidates,
    select_anchors,
)
from .constraints import family_presence_ok, sec121_exclusion_flag
from .scoring import rank_candidates, score_candidate
from .search import (
    generate_move1_candidates_narrowed,
    generate_move2_candidates_narrowed,
)
from .optimizer import optimize_housing
from .api import optimize_housing_from_request

__all__ = [
    'MOVE2_CROSS_PRODUCT_CAP',
    'MOVE2_STRATEGIES',
    'OBJECTIVES',
    'SEARCH_MODES',
    'FamilyPresence',
    'HousingCandidate',
    'Location',
    'Move2Window',
    'ScoredCandidate',
    'SearchWindow',
    'estimate_move2_candidate_count',
    'family_presence_ok',
    'filter_candidates_by_action',
    'generate_move1_candidates',
    'generate_move1_candidates_narrowed',
    'generate_move2_candidates',
    'generate_move2_candidates_narrowed',
    'generate_move2_concurrent_candidates',
    'optimize_housing',
    'optimize_housing_from_request',
    'rank_candidates',
    'score_candidate',
    'sec121_exclusion_flag',
    'select_all_eligible_move1_candidates',
    'select_anchors',
]
