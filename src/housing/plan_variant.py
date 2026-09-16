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
from .models import HousingCandidate, Location, Move

_DEFAULT_MORTGAGE_RATE = 0.0685

# Only a fallback for a caller that passes nothing; the optimizer always
# passes the request's own value through ``_apply_candidate``.
DEFAULT_DOWN_PAYMENT_PCT = 0.20

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
    """Price range midpoint, else the ZIP-scaled screening estimate
    (Location.est_price), else a flat state-level estimate. The middle tier
    makes a buy move's actual cost basis match the ZIP-specific number the
    results table shows -- see Location.est_price's docstring in models.py."""
    if loc.target_purchase_price_range:
        lo, hi = loc.target_purchase_price_range
        return (float(lo) + float(hi)) / 2.0
    if loc.est_price:
        return float(loc.est_price)
    return float(_estimate_for_location(loc, 'purchase')['purchase_price'])


def _purchase_step(step_id: str, loc: Location, start_year: int, end_year: int | None,
                   *, down_payment_pct: float | None = None,
                   mortgage_rate_pct: float | None = None) -> dict[str, Any]:
    """``step_id`` stays first and the emitted dict's KEYS are unchanged --
    only the two financing values now come from the request instead of a
    module constant, so the optimizer and the spending screen price the same
    house alike. ``mortgage_rate_pct=None`` falls back to the location
    estimate's own rate, which is the pre-2026-09-16 behavior.
    """
    est = _estimate_for_location(loc, 'purchase')
    est_rate = float(est.get('mortgage_rate_pct', _DEFAULT_MORTGAGE_RATE) or _DEFAULT_MORTGAGE_RATE)
    return {
        'id': step_id, 'type': 'purchase',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'purchase_price': _purchase_price_for_location(loc),
        'down_payment_pct': float(DEFAULT_DOWN_PAYMENT_PCT if down_payment_pct is None else down_payment_pct),
        'mortgage_rate_pct': est_rate if mortgage_rate_pct is None else float(mortgage_rate_pct),
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


def _apply_candidate(c: dict[str, Any], cand: HousingCandidate, *,
                     down_payment_pct: float | None = None,
                     mortgage_rate_pct: float | None = None) -> None:
    """Mutate engine config ``c`` IN PLACE to reflect ``cand`` -- rewrites
    ``next_housing_steps`` and ``residency_schedule`` only (§3.1/§3.2 of the
    design doc), plus ``home_sale_yr`` for the original home. Returns None:
    the caller keeps the config it passed in. Intended as the ``mutate``
    callback to ``planning_engines.run_scenario`` (which deep-copies the base
    config first), which is why it mutates rather than returns.

    Sale and acquisition are independent now (§5.1/§5.2): a step is a purchase
    or a rental because ``Move.action`` says so, not because
    ``purchase_year`` happened to be None, and the original home is kept or
    sold because ``OriginalHome.disposition`` says so.
    """
    base_state = str(c.get('state', '') or '')
    home = cand.original_home
    # 'keep' leaves home_sale_yr at 0 -- the engine's sentinel for "never
    # sold". A kept home has no sale year to write.
    c['home_sale_yr'] = 0 if home.disposition == 'keep' else (home.sale_year or 0)

    m1, m2 = cand.move1, cand.move2
    concurrent = m2 is not None and m2.mode == 'concurrent'
    sequential2 = m2 is not None and not concurrent

    # Residency follows the PRIMARY residence, which starts at each move's
    # acquisition year. A concurrent move 2 is a second home, not a
    # relocation, so it contributes no transition.
    transitions: list[tuple[int, str]] = [(m1.acquisition_year, m1.location.state)]
    if sequential2:
        transitions.append((m2.acquisition_year, m2.location.state))

    # A sequential move 2 ends move 1's step the year before it starts; that
    # end_year, plus the ``sale_year`` field below, is what triggers
    # home_sale.py's apply_next_housing_sale. Concurrent mode leaves move 1
    # open-ended (0) so both residences run indefinitely.
    move1_end = (m2.acquisition_year - 1) if sequential2 else None

    steps = []
    move1_step = _step_for(m1, 'opt_move1', move1_end,
                           down_payment_pct=down_payment_pct,
                           mortgage_rate_pct=mortgage_rate_pct)
    if sequential2 and m1.action == 'buy':
        # Real second-sale pathway (§8.2 P0): the engine sells this step
        # itself in move 2's acquisition year rather than this package
        # estimating the gain/tax out of loop (§5.2).
        move1_step['sale_year'] = m2.acquisition_year
    steps.append(move1_step)

    if m2 is not None:
        steps.append(_step_for(m2, 'opt_move2', None,
                               down_payment_pct=down_payment_pct,
                               mortgage_rate_pct=mortgage_rate_pct))

    c['next_housing_steps'] = steps
    c['residency_schedule'] = _residency_schedule(base_state, transitions)


def _step_for(move: Move, step_id: str, end_year: int | None, *,
              down_payment_pct: float | None,
              mortgage_rate_pct: float | None) -> dict[str, Any]:
    if move.action == 'rent':
        return _rent_step(step_id, move.location, move.acquisition_year, end_year)
    return _purchase_step(step_id, move.location, move.acquisition_year, end_year,
                          down_payment_pct=down_payment_pct,
                          mortgage_rate_pct=mortgage_rate_pct)


def _run_engine(c0: dict[str, Any], cand: HousingCandidate, *,
                down_payment_pct: float | None = None,
                mortgage_rate_pct: float | None = None
                ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Returns the ``(mutated_config, rows)`` PAIR ``run_scenario`` produces --
    the config is the deep copy ``_apply_candidate`` actually wrote to, and is
    what ``score_candidate``/``monte_carlo`` must be handed, not ``c0``."""
    return _pe.run_scenario(c0, mutate=lambda cc: _apply_candidate(
        cc, cand, down_payment_pct=down_payment_pct,
        mortgage_rate_pct=mortgage_rate_pct))
