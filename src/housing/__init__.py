"""Housing move optimizer (search over the current home's disposition, each
move's acquisition year, and location).

**The 2026-09-16 refinement decoupled selling from moving** (see
docs/superpowers/specs/2026-09-16-housing-optimizer-refinement-design.md,
§5.1). A candidate is no longer one welded ``(sale_year, purchase_year)``
pair. It is an ``OriginalHome`` -- sold in a searched year, or kept -- plus a
tuple of ``Move``s, each with its own ``acquisition_year`` and an explicit
``buy``/``rent`` action. Renting for two years while the old home sits on the
market is now representable; previously it was not. ``purchase_year`` no
longer exists anywhere in this package.

``Keep`` means ``home_sale_yr = 0``: carrying costs keep accruing and **no
rental income is modelled**. Treating a kept home as an income property needs
a rental-income channel, Schedule E netting, depreciation, §1250 recapture and
a real §121 non-qualified-use test, none of which the engine has. That is
Phase 2 (§13 of the same design doc) and is deliberately out of scope here.

Where things live (all of the below is a pure carve-up of the former
single-file ``src/housing_optimizer.py``; behavior is unchanged and that
path still works as a re-export shim):

* ``models``      -- dataclasses and tunables (windows, candidates, caps,
                     search budgets). Change a bound here, nowhere else.
* ``plan_variant``-- the only place that knows the plan-config wire format
                     or calls the engine (``_apply_candidate``/``_run_engine``).
* ``constraints`` -- ``no_dual_ownership``/``family_presence`` filters and the
                     informational §121 flag. Pure, engine-free.
                     ``family_presence`` is ZIP proximity (§6.4), not residence
                     in a state: a candidate is dropped when its residence
                     in any presence year is farther than the chosen radius
                     from the family ZIP. Unknown ZIPs fail closed.
* ``candidates``  -- full-grid enumeration and move-2 anchor selection. Pure.
* ``search``      -- narrowed mode: engine-free coordinate-search primitives,
                     then the wrappers that bind them to real engine runs.
* ``scoring``     -- row-reading objectives and ranking.
* ``results``     -- ``housing_optimize_v2`` payload shaping.
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
``(sale_year x acquisition_year)`` grid with a bounded coordinate/pattern search
(``search._descend``, which now climbs the sale-year, move-1 and move-2 axes
together and collapses the sale axis entirely for a kept home): a handful of seed points (grid corners plus
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

# Re-exports are LAZY (PEP 562). The eager version imported every submodule at
# package import time, which meant `import src.housing.models` transitively
# pulled in optimizer.py and api.py: a syntax or name error anywhere in the
# package made every module in it unimportable, and a mid-refactor submodule
# took the whole package down with it. Resolving on first attribute access
# instead keeps `from src.housing import Location` working while letting a
# single submodule be imported, and tested, on its own.
_EXPORTS = {
    'MOVE2_CROSS_PRODUCT_CAP': 'models',
    'MOVE2_STRATEGIES': 'models',
    'OBJECTIVES': 'models',
    'SEARCH_MODES': 'models',
    'DISPOSITIONS': 'models',
    'AREA_TYPES': 'models',
    'FAMILY_RADII_MILES': 'models',
    'MOVE_ACTIONS': 'models',
    'FamilyPresence': 'models',
    'HousingCandidate': 'models',
    'Location': 'models',
    'Move': 'models',
    'MoveWindow': 'models',
    'OriginalHome': 'models',
    'SaleWindow': 'models',
    'ScoredCandidate': 'models',
    'dual_ownership_ok': 'candidates',
    'estimate_move2_candidate_count': 'candidates',
    'extend_with_move2': 'candidates',
    'generate_candidates': 'candidates',
    'select_all_eligible': 'candidates',
    'select_anchors': 'candidates',
    'family_presence_ok': 'constraints',
    'sec121_exclusion_flag': 'constraints',
    'rank_candidates': 'scoring',
    'score_candidate': 'scoring',
    'generate_move1_candidates_narrowed': 'search',
    'generate_move2_candidates_narrowed': 'search',
    'optimize_housing': 'optimizer',
    'optimize_housing_from_request': 'api',
    'top_cities_payload': 'api',
    'zip_lookup': 'api',
    'zip_screen_from_request': 'api',
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    from importlib import import_module
    return getattr(import_module(f'.{module}', __name__), name)


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
