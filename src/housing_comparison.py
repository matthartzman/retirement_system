"""Housing trajectory comparison -- Slice 3 (v0: 2-candidate, no coordinate
descent) of docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-
dollar-convention-design.md, §7.0 items H9a/H11a.

Exactly two candidates, per §7.0's Slice-3 scope:

1. **configured** -- the household's actual Housing Step 1
   (``c['next_housing_steps'][0]``), exactly as saved.
2. **alternative** -- the same year/location, but ``type`` flipped
   (purchase <-> rent), synthesized on a deep copy of the plan config and
   priced through ``estimate_housing_cost`` (H8's pure extraction from
   ``strategy_asset_service.housing_state_estimate_payload``).

Both are scored with a real ``monte_carlo()`` run (no ``skip_mc``/coarse
pass -- two candidates is cheap enough to always run real MC, per the
design's own reasoning) using the same LCV/PV/feasibility-gate scoring block
``sheets_strategy.build_sheet10`` already establishes for its own Social
Security candidate comparison (``planning_engines.compute_baseline_lcv_and_eltr``
+ ``LCV_FEASIBILITY_GATE_THRESHOLD``).

Slice 4 (not built here) later upgrades this in place into a full three-axis
(type/year/location) coordinate-descent sweep with a shortlist, sensitivity
tables, and a "recommended trajectory" summary -- see the design doc §4 and
§7.0. This module follows the same "deep-copy config, rewrite
next_housing_steps, run the engine" pattern ``housing_optimizer.py`` (a
different, separately-shipped feature) uses for its own candidate scoring.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from . import planning_engines as _pe
from .planning_engines import LCV_FEASIBILITY_GATE_THRESHOLD, compute_baseline_lcv_and_eltr
from .server_services.strategy_asset_service import (
    HOME_APPR_DEFAULT,
    INFLATION_GENERAL_DEFAULT,
    estimate_housing_cost,
)

_OPPOSITE_TYPE = {'purchase': 'rent', 'rent': 'purchase'}

# Housing Step 1's engine config (data_io.py's next_housing_steps entries)
# never carries the Housing Estimator's characteristic fields (bedrooms/
# bathrooms/property_type/sqft_band/built_within_years) -- only the dollar
# figures those characteristics produced. With no characteristics to read
# back off a saved step, the "opposite type" alternative is priced at the
# Estimator's own defaults (3BR/2BA/single-family/1800-2500sqft, no
# built-within preference) -- the same defaults a client who never touched
# those Estimator fields would already be getting.
_DEFAULT_BEDROOMS = 3
_DEFAULT_BATHROOMS = 2.0
_DEFAULT_PROPERTY_TYPE = 'single_family'
_DEFAULT_SQFT_BAND = '1800_2500'


def opposite_type_step(c: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """Build the "opposite type" alternative to ``step`` (Housing Step 1 as
    saved): same ``start_year``/``end_year``/location, ``type`` flipped, and
    every dollar-denominated field repriced by ``estimate_housing_cost`` at
    that year/location and the Estimator's default characteristics (see
    module docstring). Does not mutate ``step``.
    """
    current_type = str(step.get('type', 'purchase') or 'purchase').strip().lower()
    new_type = _OPPOSITE_TYPE.get(current_type, 'rent')
    state = str(step.get('state', '') or '').strip().upper()
    city_type = str(step.get('city_type', 'suburban') or 'suburban').strip().lower()
    try:
        population_size = int(step.get('population_size', 20000) or 20000)
    except (TypeError, ValueError):
        population_size = 20000
    try:
        start_year = int(step.get('start_year', 0) or 0)
    except (TypeError, ValueError):
        start_year = 0
    home_appr = float(c.get('home_appr', HOME_APPR_DEFAULT) or HOME_APPR_DEFAULT)
    inflation_general = float(c.get('inf', INFLATION_GENERAL_DEFAULT) or INFLATION_GENERAL_DEFAULT)

    priced = estimate_housing_cost(
        state=state, housing_type=new_type, city_type=city_type,
        population_size=population_size, bedrooms=_DEFAULT_BEDROOMS,
        bathrooms=_DEFAULT_BATHROOMS, property_type=_DEFAULT_PROPERTY_TYPE,
        sqft_band=_DEFAULT_SQFT_BAND, built_within_years=None,
        start_year=start_year, home_appr=home_appr, inflation_general=inflation_general,
    )

    new_step = dict(step)
    new_step['type'] = new_type
    is_purchase = new_type == 'purchase'
    new_step['purchase_price'] = float(priced.get('purchase_price', 0.0) or 0.0) if is_purchase else 0.0
    new_step['monthly_rent'] = 0.0 if is_purchase else float(priced.get('monthly_rent', 0.0) or 0.0)
    new_step['insurance_annual'] = float(priced.get('insurance_annual', 0.0) or 0.0)
    new_step['utilities_annual'] = float(priced.get('utilities_annual', 0.0) or 0.0)
    new_step['maintenance_annual'] = float(priced.get('maintenance_annual', 0.0) or 0.0) if is_purchase else 0.0
    new_step['real_estate_tax_pct'] = float(priced.get('re_tax_pct', 0.0) or 0.0) if is_purchase else 0.0
    new_step['hoa_pct'] = float(priced.get('hoa_pct', 0.0) or 0.0) if is_purchase else 0.0
    new_step['mortgage_rate_pct'] = float(priced.get('mortgage_rate_pct', 0.0685) or 0.0685) if is_purchase else 0.0
    new_step['down_payment_pct'] = float(step.get('down_payment_pct', 0.20) or 0.20) if is_purchase else 0.0
    return new_step


def score_config(c2: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one already-run config -- the same LCV/PV/feasibility-gate block
    ``build_sheet10`` uses for its own candidate comparison (see module
    docstring), plus a real ``monte_carlo()`` run (no ``skip_mc``)."""
    net_worth = float(rows[-1].get('total_nw', 0.0) or 0.0) if rows else 0.0
    metrics = compute_baseline_lcv_and_eltr(c2, rows)
    lcv = float(metrics.get('lcv', 0.0) or 0.0)
    npv_future_taxes = float(metrics.get('npv_future_taxes', 0.0) or 0.0)
    mc = _pe.monte_carlo(c2, base_rows=rows)
    mc_success_rate = float(mc.get('success_rate', 0.0) or 0.0)
    feasibility_probability = float(mc.get('essential_fully_funded_probability', 0.0) or 0.0)
    return {
        'net_worth': net_worth,
        'lcv': lcv,
        'npv_future_taxes': npv_future_taxes,
        'mc_success_rate': mc_success_rate,
        'feasibility_probability': feasibility_probability,
        'feasibility_gate_met': feasibility_probability >= LCV_FEASIBILITY_GATE_THRESHOLD,
    }


def _describe(step: dict[str, Any]) -> dict[str, Any]:
    return {
        'type': str(step.get('type', '') or ''),
        'start_year': step.get('start_year'),
        'state': step.get('state'),
        'city_type': step.get('city_type'),
        'population_size': step.get('population_size'),
    }


def compare_housing_candidates(c: dict[str, Any], base_rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Score the household's configured Housing Step 1 choice against the
    "opposite type" alternative at the same year/location (H9a). Returns
    ``None`` when no Step 1 housing change is configured -- nothing to
    compare. ``base_rows`` is this build's own already-computed deterministic
    rows for the configured plan, reused here (not re-run) since they already
    reflect the configured choice exactly.
    """
    steps = c.get('next_housing_steps') or []
    if not steps or not isinstance(steps[0], dict):
        return None
    configured_step = steps[0]

    configured = {**_describe(configured_step), **score_config(c, base_rows)}

    alt_step = opposite_type_step(c, configured_step)

    def _mutate(c2: dict[str, Any]) -> None:
        c2_steps = c2.get('next_housing_steps') or []
        if c2_steps:
            c2_steps[0] = copy.deepcopy(alt_step)

    c2, alt_rows = _pe.run_scenario(c, mutate=_mutate)
    alternative = {**_describe(alt_step), **score_config(c2, alt_rows)}

    return {'configured': configured, 'alternative': alternative}
