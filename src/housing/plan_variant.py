"""Turning a ``HousingCandidate`` into an engine config, and running it.

This is the only module that knows the plan-config wire format
(``next_housing_steps``/``residency_schedule``/``home_sale_yr``) or calls
the engine, so a change to either is contained here. No new tax logic: the
engine's own gain/§121 pathway in ``home_sale.py`` does both sales.
"""
from __future__ import annotations

from typing import Any

from .. import planning_engines as _pe
from ..server_services.strategy_asset_service import housing_state_estimate_payload
from .models import HousingCandidate, Location

_DEFAULT_MORTGAGE_RATE = 0.0685
_DEFAULT_DOWN_PAYMENT_PCT = 0.20

# ``Location.state`` is a full state name (e.g. "Texas") -- the form
# ``core.state_for_year``/``state_income_tax`` and ``residency_schedule``
# require (``core.STATE_TAX_RULES`` is keyed this way). The housing cost
# estimate lookup (``housing_state_estimate_payload``/``STATE_ESTIMATES`` in
# strategy_asset_service.py) is keyed by two-letter abbreviation instead --
# an existing mismatch between those two features, not introduced here. This
# maps the common ones so one ``Location.state`` value serves both; an
# unmapped state still works, it just falls back to
# ``housing_state_estimate_payload``'s generic default cost estimate.
_STATE_ABBREV = {
    'Arizona': 'AZ', 'California': 'CA', 'Colorado': 'CO', 'Florida': 'FL',
    'Illinois': 'IL', 'Indiana': 'IN', 'Nevada': 'NV', 'New York': 'NY',
    'North Carolina': 'NC', 'South Dakota': 'SD', 'Tennessee': 'TN',
    'Texas': 'TX', 'Wyoming': 'WY',
}


# ---------------------------------------------------------------------------
# Location cost estimates (reuses the existing housing_state_estimate_v1
# helper -- see strategy_asset_service.py -- so purchase price/rent/tax/
# insurance/HOA figures come from the one place the UI already sources them)
# ---------------------------------------------------------------------------

def _estimate_for_location(loc: Location, housing_type: str) -> dict[str, Any]:
    payload, _status = housing_state_estimate_payload({
        'state': _STATE_ABBREV.get(loc.state, loc.state),
        'type': housing_type,
        'city_type': loc.city_type,
        'population_size': loc.population_size,
        'bedrooms': loc.bedrooms,
        'bathrooms': loc.bathrooms,
        'property_type': loc.property_type,
        'sqft_band': loc.sqft_band,
        'built_within_years': loc.built_within_years,
    })
    return payload['estimate']


def _purchase_price_for_location(loc: Location) -> float:
    if loc.target_purchase_price_range:
        lo, hi = loc.target_purchase_price_range
        return (float(lo) + float(hi)) / 2.0
    return float(_estimate_for_location(loc, 'purchase')['purchase_price'])


def _purchase_step(step_id: str, loc: Location, start_year: int, end_year: int | None) -> dict[str, Any]:
    est = _estimate_for_location(loc, 'purchase')
    return {
        'id': step_id, 'type': 'purchase',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'purchase_price': _purchase_price_for_location(loc),
        'down_payment_pct': _DEFAULT_DOWN_PAYMENT_PCT,
        'mortgage_rate_pct': float(est.get('mortgage_rate_pct', _DEFAULT_MORTGAGE_RATE) or _DEFAULT_MORTGAGE_RATE),
        'monthly_rent': 0.0,
        'insurance_annual': float(est.get('insurance_annual', 0.0) or 0.0),
        'utilities_annual': float(est.get('utilities_annual', 0.0) or 0.0),
        'maintenance_annual': float(est.get('maintenance_annual', 0.0) or 0.0),
        'real_estate_tax_pct': float(est.get('re_tax_pct', 0.0) or 0.0),
        'hoa_pct': float(est.get('hoa_pct', 0.0) or 0.0),
    }


def _rent_step(step_id: str, loc: Location, start_year: int, end_year: int | None) -> dict[str, Any]:
    est = _estimate_for_location(loc, 'rent')
    return {
        'id': step_id, 'type': 'rent',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'monthly_rent': float(est.get('monthly_rent', 0.0) or 0.0),
        'insurance_annual': float(est.get('insurance_annual', 0.0) or 0.0),
        'utilities_annual': float(est.get('utilities_annual', 0.0) or 0.0),
        'purchase_price': 0.0, 'down_payment_pct': 0.0, 'mortgage_rate_pct': 0.0,
        'maintenance_annual': 0.0, 'real_estate_tax_pct': 0.0, 'hoa_pct': 0.0,
    }


def _residency_schedule(base_state: str, transitions: list[tuple[int, str]]) -> list[dict[str, Any]]:
    """Build a full ``residency_schedule`` from an ordered list of
    ``(year, new_state)`` transitions (each state applies from ``year``
    onward, up to the next transition). Replaces any base-config schedule
    for this candidate run -- see ``core.state_for_year``.
    """
    if not transitions:
        return []
    transitions = sorted(transitions, key=lambda t: t[0])
    sched = [{'state': base_state, 'start_year': 1, 'end_year': transitions[0][0] - 1}]
    for i, (yr, st) in enumerate(transitions):
        end = transitions[i + 1][0] - 1 if i + 1 < len(transitions) else 9999
        sched.append({'state': st, 'start_year': yr, 'end_year': end})
    return sched


def _apply_candidate(c: dict[str, Any], cand: HousingCandidate) -> None:
    """Mutate engine config ``c`` in place to reflect ``cand`` -- rewrites
    ``next_housing_steps`` and ``residency_schedule`` only (§3.1/§3.2 of the
    design doc), plus the existing ``home_sale_yr`` field for move 1's sale
    of the current home. Intended as the ``mutate`` callback to
    ``planning_engines.run_scenario`` (deep-copies the base config first).
    """
    base_state = str(c.get('state', '') or '')
    c['home_sale_yr'] = cand.sale_year
    concurrent = cand.is_two_move and cand.move2_mode == 'concurrent'

    move1_end = None if concurrent else ((cand.sale_year_2 - 1) if cand.is_two_move else None)
    steps = []
    # The household leaves the original home at sale_year regardless of
    # whether/when it buys next, so that -- not purchase_year -- is when
    # residency (and, below, rent liability) at location_1 actually starts.
    transitions: list[tuple[int, str]] = [(cand.sale_year, cand.location_1.state)]
    if cand.purchase_year is None:
        steps.append(_rent_step('opt_move1', cand.location_1, cand.sale_year, move1_end))
    else:
        if cand.purchase_year > cand.sale_year:
            # Gap between selling and buying: rent at the destination
            # location_1 in the meantime, rather than modeling it as free
            # housing (the previous behavior -- no step at all covered
            # these years).
            steps.append(_rent_step('opt_move1_gap', cand.location_1, cand.sale_year, cand.purchase_year - 1))
        move1_step = _purchase_step('opt_move1', cand.location_1, cand.purchase_year, move1_end)
        if cand.is_two_move and not concurrent:
            # Real second-sale pathway (design doc §8.2 P0): the engine sells
            # this step itself -- see home_sale.py's apply_next_housing_sale
            # -- instead of this package estimating move 2's gain/tax
            # out-of-loop. `move1_end` above is already `sale_year_2 - 1`, so
            # the step also stops accruing ongoing cash flow the year before.
            # Concurrent mode never sets this: the move-1 home is never sold.
            move1_step['sale_year'] = cand.sale_year_2
        steps.append(move1_step)

    if cand.is_two_move:
        if concurrent:
            # location_2 is a second, ongoing residence alongside location_1
            # -- no residency_schedule transition (tax residency stays with
            # location_1; concurrent mode is a second home, not a move).
            move2_start = cand.concurrent_start_year_2
            if cand.purchase_year_2 is None:
                steps.append(_rent_step('opt_move2', cand.location_2, move2_start, None))
            else:
                steps.append(_purchase_step('opt_move2', cand.location_2, cand.purchase_year_2, None))
        else:
            transitions.append((cand.sale_year_2, cand.location_2.state))
            if cand.purchase_year_2 is None:
                steps.append(_rent_step('opt_move2', cand.location_2, cand.sale_year_2, None))
            else:
                if cand.purchase_year_2 > cand.sale_year_2:
                    steps.append(_rent_step(
                        'opt_move2_gap', cand.location_2, cand.sale_year_2, cand.purchase_year_2 - 1))
                steps.append(_purchase_step('opt_move2', cand.location_2, cand.purchase_year_2, None))

    c['next_housing_steps'] = steps
    c['residency_schedule'] = _residency_schedule(base_state, transitions)


def _run_engine(c0: dict[str, Any], cand: HousingCandidate) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _pe.run_scenario(c0, mutate=lambda cc: _apply_candidate(cc, cand))
