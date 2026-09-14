"""Housing trajectory sweep -- Slice 4 (H9/H10) of docs/superpowers/plans/
2026-09-09-housing-estimate-realism-and-dollar-convention-design.md, §4.

A candidate is a whole future housing *trajectory*: the current home's sale
year, Housing Step 1 (type x year), and Housing Step 2 (type x year, or "no
second move"). §4.2's honest count of the full joint cross-product is
``8 x 14 x 14 = 1,568`` full projections -- not viable -- so this module
implements the design's coordinate descent instead:

1. **Coarse pass** (§4.2 step 1): sweep one axis at a time with
   ``skip_mc=True``, each stage holding the other two axes at their
   current-best value, <=36 deterministic ``project()`` calls.
2. **Two axis orderings** (§4.2 step 3, open decision #8): the whole coarse
   pass runs twice, from ``sale_year -> step1 -> step2`` and from
   ``step1 -> step2 -> sale_year``, and the higher-scoring of the two
   resulting trajectories is what the refine pass runs on. Coordinate
   descent's known failure mode is missing a joint optimum no single-axis
   move would reach; a second ordering reduces (it does not eliminate) that
   risk for another <=36 cheap deterministic calls.
3. **Refine pass** (§4.2 step 2): real ``monte_carlo()`` on the surviving
   trajectory plus its +/-1 neighborhood on each axis -- 6 to 9 runs, not
   hundreds.

Scoring is §4.4's, mechanically identical to the block
``sheets_strategy.build_sheet10`` establishes for its own Social Security
sweep (``lcv_score = consumption_pv + after_tax_terminal_nw_pv``, PV'd at
``_roth_discount_rate``, gated on ``LCV_FEASIBILITY_GATE_THRESHOLD``), minus
SS's survivor-income term -- nothing housing-specific plays that role. Every
stage goes through ``strategy_sweep.run_sweep`` (§4.4's "Mechanism" row):
once per axis per ordering, and once for the refine pass.

Supersedes Slice 3's 2-candidate ``compare_housing_candidates``; the sheet it
feeds (``sheets_strategy.build_sheet_housing_comparison``) is upgraded in
place under the same registry entry.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import planning_engines as _pe
from . import strategy_sweep
from .after_tax import estimate_after_tax_terminal_net_worth
from .planning_engines import (
    LCV_FEASIBILITY_GATE_THRESHOLD,
    _roth_discount_rate,
    compute_baseline_lcv_and_eltr,
)
from .server_services.strategy_asset_service import (
    HOME_APPR_DEFAULT,
    INFLATION_GENERAL_DEFAULT,
    estimate_housing_cost,
)

_OPPOSITE_TYPE = {'purchase': 'rent', 'rent': 'purchase'}
HOUSING_TYPES = ('purchase', 'rent')

# §4.1: every year axis is a +/-3 window around its configured centre, clamped
# to the plan horizon. NEVER_SELL is the engine's own "no home sale" sentinel
# (data_io.py's home_sale_year default), carried as a distinguished extra
# candidate on axis (a) rather than as a year.
AXIS_WINDOW = 3
NEVER_SELL = 0

# §4.2 step 3: the two axis orderings the coarse pass is run from.
AXIS_ORDERINGS = (
    ('sale_year', 'step1', 'step2'),
    ('step1', 'step2', 'sale_year'),
)
AXES = ('sale_year', 'step1', 'step2')

# Refine-pass Monte Carlo settings, same convention build_sheet10 uses for the
# SS sweep: a reduced path count and one fixed seed reused across every
# candidate, so score differences are attributable to the trajectory rather
# than to simulation noise. `housing_sweep_mc_sims` overrides the count (tests
# use a small value to keep this -- the most expensive sheet in the workbook --
# affordable in the suite).
SWEEP_MC_SIMS = 200
SWEEP_MC_SEED = 4242

# Housing Step config (data_io.py's next_housing_steps entries) never carries
# the Housing Estimator's characteristic fields (bedrooms/bathrooms/
# property_type/sqft_band/built_within_years) -- only the dollar figures those
# characteristics produced. With no characteristics to read back off a saved
# step, every synthesized candidate is priced at the Estimator's own defaults,
# the same ones a client who never touched those fields already gets.
_DEFAULT_BEDROOMS = 3
_DEFAULT_BATHROOMS = 2.0
_DEFAULT_PROPERTY_TYPE = 'single_family'
_DEFAULT_SQFT_BAND = '1800_2500'


@dataclass(frozen=True)
class Trajectory:
    """One sweep candidate: (sale year, Step 1, Step 2).

    ``step1``/``step2`` are ``(housing_type, start_year)`` pairs, or ``None``
    for "no such move configured" -- §4.1(c)'s "no second move" candidate,
    which the axis collapses to rather than being omitted.
    """

    sale_year: int
    step1: Optional[tuple[str, int]]
    step2: Optional[tuple[str, int]]


def _with_axis(traj: Trajectory, axis: str, value: Any) -> Trajectory:
    return dataclasses.replace(traj, **{axis: value})


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _year_window(center: int, plan_start: int, plan_end: int) -> list[int]:
    lo = max(plan_start, center - AXIS_WINDOW)
    hi = min(plan_end, center + AXIS_WINDOW)
    return list(range(lo, hi + 1)) if hi >= lo else [center]


def configured_trajectory(c: dict[str, Any]) -> Optional[Trajectory]:
    """The household's plan exactly as entered -- the only grid point whose
    dollars are real rather than synthesized (§4.3). ``None`` when no Housing
    Step 1 is configured: there is no trajectory to sweep."""
    steps = c.get('next_housing_steps') or []
    if not steps or not isinstance(steps[0], dict):
        return None
    step2 = steps[1] if len(steps) > 1 and isinstance(steps[1], dict) else None
    return Trajectory(
        sale_year=_int(c.get('home_sale_yr'), 0),
        step1=(_step_type(steps[0]), _int(steps[0].get('start_year'))),
        step2=(_step_type(step2), _int(step2.get('start_year'))) if step2 else None,
    )


def _step_type(step: dict[str, Any]) -> str:
    typ = str(step.get('type', 'purchase') or 'purchase').strip().lower()
    return typ if typ in HOUSING_TYPES else 'purchase'


def build_axes(c: dict[str, Any]) -> dict[str, list[Any]]:
    """The three axes' candidate values (§4.1), in the order the coarse pass
    and the sensitivity tables iterate them."""
    steps = c.get('next_housing_steps') or []
    plan_start = _int(c.get('plan_start'), 0)
    plan_end = _int(c.get('plan_end'), plan_start)
    step1 = steps[0] if steps else None
    step2 = steps[1] if len(steps) > 1 else None

    configured_sale = _int(c.get('home_sale_yr'), 0)
    # §4.1(a)'s stated fallback: an unset home_sale_yr centres the window on
    # Step 1's own start_year, since a first move typically implies a sale
    # even when the household never separately configured one.
    sale_center = configured_sale or _int(step1.get('start_year') if step1 else 0, plan_start)
    sale_years = [NEVER_SELL] + _year_window(sale_center, plan_start, plan_end)

    return {
        'sale_year': sale_years,
        'step1': _step_axis(step1, plan_start, plan_end),
        'step2': _step_axis(step2, plan_start, plan_end),
    }


def _step_axis(step: Optional[dict[str, Any]], plan_start: int, plan_end: int) -> list[Any]:
    if not step:
        return [None]
    years = _year_window(_int(step.get('start_year')), plan_start, plan_end)
    return [(typ, year) for typ in HOUSING_TYPES for year in years]


def priced_step(c: dict[str, Any], base_step: dict[str, Any], housing_type: str, start_year: int) -> dict[str, Any]:
    """``base_step`` moved to ``(housing_type, start_year)``, with every
    dollar-denominated field re-derived through ``estimate_housing_cost``.

    §4.3's trap: ``next_housing_steps[i]['purchase_price']`` is a flat number
    computed once at CSV-parse time and does NOT carry §3.2's start-year
    translation with it, so a candidate that moves the year must re-derive the
    price rather than reuse the parsed one -- otherwise the sweep silently
    reintroduces the stale-year-price bug *inside the fix for it*. The one
    exception is the exact as-configured (type, year) point, which keeps the
    household's real entered dollars end-to-end.
    """
    if _step_type(base_step) == housing_type and _int(base_step.get('start_year')) == int(start_year):
        return dict(base_step)

    priced = estimate_housing_cost(
        state=str(base_step.get('state', '') or '').strip().upper(),
        housing_type=housing_type,
        city_type=str(base_step.get('city_type', 'suburban') or 'suburban').strip().lower(),
        population_size=_int(base_step.get('population_size'), 20000) or 20000,
        bedrooms=_DEFAULT_BEDROOMS,
        bathrooms=_DEFAULT_BATHROOMS,
        property_type=_DEFAULT_PROPERTY_TYPE,
        sqft_band=_DEFAULT_SQFT_BAND,
        built_within_years=None,
        start_year=int(start_year),
        home_appr=float(c.get('home_appr', HOME_APPR_DEFAULT) or HOME_APPR_DEFAULT),
        inflation_general=float(c.get('inf', INFLATION_GENERAL_DEFAULT) or INFLATION_GENERAL_DEFAULT),
    )

    new_step = dict(base_step)
    new_step['type'] = housing_type
    new_step['start_year'] = int(start_year)
    is_purchase = housing_type == 'purchase'
    new_step['purchase_price'] = float(priced.get('purchase_price', 0.0) or 0.0) if is_purchase else 0.0
    new_step['monthly_rent'] = 0.0 if is_purchase else float(priced.get('monthly_rent', 0.0) or 0.0)
    new_step['insurance_annual'] = float(priced.get('insurance_annual', 0.0) or 0.0)
    new_step['utilities_annual'] = float(priced.get('utilities_annual', 0.0) or 0.0)
    new_step['maintenance_annual'] = float(priced.get('maintenance_annual', 0.0) or 0.0) if is_purchase else 0.0
    new_step['real_estate_tax_pct'] = float(priced.get('re_tax_pct', 0.0) or 0.0) if is_purchase else 0.0
    new_step['hoa_pct'] = float(priced.get('hoa_pct', 0.0) or 0.0) if is_purchase else 0.0
    new_step['mortgage_rate_pct'] = float(priced.get('mortgage_rate_pct', 0.0685) or 0.0685) if is_purchase else 0.0
    new_step['down_payment_pct'] = float(base_step.get('down_payment_pct', 0.20) or 0.20) if is_purchase else 0.0
    return new_step


def trajectory_steps(c: dict[str, Any], traj: Trajectory) -> list[dict[str, Any]]:
    """``traj`` rendered as a ``next_housing_steps`` list, every step priced
    through :func:`priced_step`."""
    configured = c.get('next_housing_steps') or []
    out = []
    for index, axis_value in ((0, traj.step1), (1, traj.step2)):
        if axis_value is None or index >= len(configured):
            continue
        out.append(priced_step(c, configured[index], axis_value[0], axis_value[1]))
    return out


def _score_trajectory(
    c: dict[str, Any], traj: Trajectory, base_lcv: float, *, skip_mc: bool, mc_sims: int,
) -> dict[str, Any]:
    """Project ``traj`` and score it with §4.4's LCV/PV/feasibility block."""
    def _mutate(c2: dict[str, Any]) -> None:
        c2['home_sale_yr'] = int(traj.sale_year)
        c2['next_housing_steps'] = copy.deepcopy(trajectory_steps(c, traj))
        c2.pop('plan_result', None)
        c2.pop('roth_strategy_result', None)

    c2, proj_rows = _pe.run_scenario(c, mutate=_mutate)
    terminal_row = proj_rows[-1] if proj_rows else {}
    terminal = float(terminal_row.get('total_nw', 0.0) or 0.0)
    after_tax_terminal_nw = float(
        estimate_after_tax_terminal_net_worth(c2, terminal_row).get('after_tax_terminal_nw', terminal)
        if proj_rows else terminal
    )
    discount = _roth_discount_rate(c2)
    plan_start = _int(c2.get('plan_start'), _int(proj_rows[0].get('year') if proj_rows else 0))
    consumption_pv = sum(
        float(r.get('total_spend', 0.0) or 0.0)
        / ((1.0 + discount) ** max(0, _int(r.get('year'), plan_start) - plan_start))
        for r in proj_rows
    )
    terminal_year = _int(terminal_row.get('year'), plan_start) if proj_rows else plan_start
    after_tax_terminal_nw_pv = after_tax_terminal_nw / ((1.0 + discount) ** max(0, terminal_year - plan_start))
    # §4.4: no survivor-income term -- nothing housing-specific plays the role
    # SS's survivor-period income bonus plays, so objective_value IS lcv_score.
    lcv_score = consumption_pv + after_tax_terminal_nw_pv

    metrics = compute_baseline_lcv_and_eltr(c2, proj_rows)
    lcv = float(metrics.get('lcv', 0.0) or 0.0)
    equity_at_plan_end = (
        float(terminal_row.get('home_equity', 0.0) or 0.0)
        + float(terminal_row.get('next_housing_equity', 0.0) or 0.0)
    )

    mc_success_rate = None
    mc_p5_terminal_nw = None
    feasibility_probability = 0.0
    if not skip_mc:
        try:
            c2['mc_sims'] = mc_sims
            c2['mc_sensitivity_sims'] = 1
            with contextlib.redirect_stdout(io.StringIO()):
                mc_result = _pe.monte_carlo(c2, n_sims=mc_sims, seed=SWEEP_MC_SEED)
            mc_success_rate = float(mc_result.get('success_rate', 0.0) or 0.0)
            mc_p5_terminal_nw = float((mc_result.get('terminal_total_nw') or {}).get(5, 0.0) or 0.0)
            feasibility_probability = float(mc_result.get('essential_fully_funded_probability', 0.0) or 0.0)
        except Exception:
            pass

    return {
        'objective_value': lcv_score,
        'lcv_score': lcv_score,
        'terminal_nw': terminal,
        'after_tax_terminal_nw': after_tax_terminal_nw,
        'lcv': lcv,
        'delta_lcv': lcv - base_lcv,
        'npv_future_taxes': float(metrics.get('npv_future_taxes', 0.0) or 0.0),
        'equity_at_plan_end': equity_at_plan_end,
        'mc_success_rate': mc_success_rate,
        'mc_p5_terminal_nw': mc_p5_terminal_nw,
        'feasibility_probability': feasibility_probability,
        'feasibility_gate_met': feasibility_probability >= LCV_FEASIBILITY_GATE_THRESHOLD,
        'scored_with_monte_carlo': not skip_mc,
    }


def _coarse_descent(
    axes: dict[str, list[Any]], order: tuple[str, ...], start: Trajectory,
    evaluate: Callable[[Trajectory], dict[str, Any]],
) -> tuple[Trajectory, dict[str, list[dict]]]:
    """One coordinate-descent pass over ``order`` (§4.2 step 1).

    Each stage sweeps a single axis with the other two pinned to the running
    best -- so the winner of stage N is what stage N+1 holds fixed, not the
    household's originally configured value. Getting that carry-forward wrong
    is H9's named silent-failure mode (the sheet would still render, with a
    plausible-looking but never-actually-searched recommendation), so H13
    asserts it directly.
    """
    current = start
    axis_candidates: dict[str, list[dict]] = {}
    for axis in order:
        specs = [
            {'axis': axis, 'value': value, 'trajectory': _with_axis(current, axis, value)}
            for value in axes[axis]
        ]
        # The coarse pass is deterministic, so no candidate can clear the
        # feasibility gate (feasibility_probability is 0.0 without a Monte
        # Carlo run). run_sweep's own all-infeasible fallback -- rank the full
        # set instead of failing to produce a pick -- is exactly the wanted
        # behavior here: the gate is uninformative at this stage and only the
        # refine pass, which does run real MC, is allowed to gate.
        sweep = strategy_sweep.run_sweep(
            specs, lambda spec: evaluate(spec['trajectory']),
            sort_key=lambda d: d['objective_value'],
        )
        axis_candidates[axis] = sweep.candidates
        if sweep.candidates:
            current = sweep.best['trajectory']
    return current, axis_candidates


def _axis_neighbors(axis: str, values: list[Any], current: Any) -> list[Any]:
    """The +/-1 neighborhood of ``current`` on ``axis`` (§4.2 step 2).

    On a step axis that means the adjacent years at the same type plus the
    opposite type at the same year -- a buy/rent flip is as much a "one step
    away" move as shifting the year by one, and it is the move this sheet
    exists to evaluate.
    """
    if current is None:
        return []
    if axis == 'sale_year':
        index = values.index(current)
        return [values[j] for j in (index - 1, index + 1) if 0 <= j < len(values)]
    typ, year = current
    candidates = [(typ, year - 1), (typ, year + 1), (_OPPOSITE_TYPE[typ], year)]
    return [v for v in candidates if v in values]


def sweep_housing_trajectories(
    c: dict[str, Any], base_rows: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Run §4.2's full three-axis sweep and return everything the sheet renders.

    ``None`` when no Housing Step 1 is configured -- there is no trajectory to
    sweep. ``base_rows`` is this build's already-computed deterministic rows
    for the configured plan, used only as the Delta-LCV baseline.
    """
    configured = configured_trajectory(c)
    if configured is None:
        return None

    axes = build_axes(c)
    base_lcv = float(compute_baseline_lcv_and_eltr(c, list(base_rows or [])).get('lcv', 0.0) or 0.0)
    # Never spend more Monte Carlo paths on a refine-pass candidate than the
    # household's own plan-level run uses -- a workbook build that already
    # dialled mc_sims down (CI, the module-matrix build tests) should not have
    # this sheet silently reinstate the full 200.
    _mc_override = _int(c.get('housing_sweep_mc_sims'), 0)
    mc_sims = _mc_override or min(SWEEP_MC_SIMS, _int(c.get('mc_sims'), SWEEP_MC_SIMS) or SWEEP_MC_SIMS)

    # One cache across both orderings and the refine pass. The two orderings
    # revisit many of the same points (they start from the same configured
    # trajectory), and without this the second ordering would pay full price
    # for candidates the first already scored.
    coarse_cache: dict[Trajectory, dict[str, Any]] = {}

    def _coarse_eval(traj: Trajectory) -> dict[str, Any]:
        if traj not in coarse_cache:
            coarse_cache[traj] = _score_trajectory(c, traj, base_lcv, skip_mc=True, mc_sims=mc_sims)
        return coarse_cache[traj]

    orderings = []
    for order in AXIS_ORDERINGS:
        winner, axis_candidates = _coarse_descent(axes, order, configured, _coarse_eval)
        orderings.append({
            'order': order,
            'trajectory': winner,
            'objective_value': _coarse_eval(winner)['objective_value'],
            'axis_candidates': axis_candidates,
        })
    # §4.2 step 3: keep whichever ordering's trajectory scores higher on the
    # coarse pass's own deterministic objective, before any MC is spent.
    winning_order = max(orderings, key=lambda o: o['objective_value'])

    refine_trajectories = [winning_order['trajectory']]
    for axis in AXES:
        for value in _axis_neighbors(axis, axes[axis], getattr(winning_order['trajectory'], axis)):
            neighbor = _with_axis(winning_order['trajectory'], axis, value)
            if neighbor not in refine_trajectories:
                refine_trajectories.append(neighbor)

    mc_calls = 0

    def _refine_eval(spec: dict[str, Any]) -> dict[str, Any]:
        nonlocal mc_calls
        mc_calls += 1
        return _score_trajectory(c, spec['trajectory'], base_lcv, skip_mc=False, mc_sims=mc_sims)

    refine_sweep = strategy_sweep.run_sweep(
        [{'trajectory': traj} for traj in refine_trajectories],
        _refine_eval,
        sort_key=lambda d: d['objective_value'],
    )
    ranked = refine_sweep.candidates
    # Same 0-100 normalization convention build_sheet10 applies to its own
    # ranked table, computed on the full (pre-gate) set.
    objectives = [x['objective_value'] for x in ranked]
    score_lo = min(objectives) if objectives else 0.0
    score_span = (max(objectives) - score_lo) if objectives else 0.0
    for candidate in ranked:
        candidate['rank_score'] = (
            int(round(100.0 * (candidate['objective_value'] - score_lo) / score_span)) if score_span else 100
        )

    return {
        'configured': configured,
        'axes': axes,
        'orderings': orderings,
        'winning_order': winning_order,
        'recommended': refine_sweep.best,
        'refine_candidates': ranked,
        'all_infeasible': refine_sweep.all_infeasible,
        'step2_configured': configured.step2 is not None,
        'deterministic_calls': len(coarse_cache),
        'mc_calls': mc_calls,
    }


def describe_trajectory_step(value: Optional[tuple[str, int]]) -> str:
    """A step axis value as the sheet shows it ("Purchase / 2036")."""
    if value is None:
        return 'No second move'
    return f'{str(value[0]).title()} / {int(value[1])}'


def describe_sale_year(value: int) -> str:
    return 'Never sell' if not value else str(int(value))
