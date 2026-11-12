"""Housing price estimate: the pure pricing core (ARC-002 / W2-07).

Moved out of ``server_services.strategy_asset_service`` so the housing package (a domain module)
no longer imports a server service. ``strategy_asset_service`` re-exports every name below for one
release, so existing callers keep working. Nothing here parses a request or touches a plan.
"""
from __future__ import annotations

from typing import Any

from .. import platform_runtime as _platform_runtime


def years_out_from(start_year: int) -> int:
    """Years from "now" (``platform_runtime.today().year``, the clock ``data_io`` pins ``c['plan_start']``
    to) to ``start_year``, floored at zero so a current-year or past move is never discounted backwards.
    The one copy of the formula: ``estimate_housing_cost`` and the housing optimizer both use it."""
    plan_start = _platform_runtime.today().year
    return max(0, int(start_year) - plan_start) if start_year else 0


# Slice 1 (dollar-convention fix) defaults, matching data_io.py's own
# plan-level defaults for these assumptions (appreciation_rate/inflation_general),
# so a caller that omits them still gets a sane translation rather than a
# crash or a silent 0% rate.
HOME_APPR_DEFAULT = 0.03
INFLATION_GENERAL_DEFAULT = 0.025

STATE_ESTIMATES = {
    "TX": dict(purchase_price=360000, monthly_rent=1700, insurance_annual=2800, utilities_annual=2800, maintenance_annual=3600, re_tax_pct=0.0181, hoa_pct=0.003),
    "IL": dict(purchase_price=310000, monthly_rent=1600, insurance_annual=1600, utilities_annual=2800, maintenance_annual=3100, re_tax_pct=0.0205, hoa_pct=0.001),
    "FL": dict(purchase_price=420000, monthly_rent=2000, insurance_annual=3500, utilities_annual=2800, maintenance_annual=4200, re_tax_pct=0.0083, hoa_pct=0.003),
    "AZ": dict(purchase_price=385000, monthly_rent=1750, insurance_annual=1600, utilities_annual=2600, maintenance_annual=3850, re_tax_pct=0.0062, hoa_pct=0.002),
}

# Slice 2 (2026-09-09 design, §3.3): replace the fixed 3BR/2BA/single-family/
# 1800-2500sqft profile implicit in the estimate above with five optional,
# defaulted characteristics, each a multiplicative factor on the state base
# price alongside city_mult/pop_mult. Values are illustrative starting points
# (design §8 decision 2), not sourced from a dataset -- same treatment as the
# pre-existing city_type/population_size multipliers.
BEDROOM_MULT = {2: 0.85, 3: 1.00, 4: 1.15, 5: 1.30}
BATHROOM_MULT = {1: 0.90, 1.5: 0.95, 2: 1.00, 2.5: 1.05, 3: 1.12, 3.5: 1.18}
PROPERTY_TYPE_MULT = {"single_family": 1.00, "townhome": 0.85, "condo": 0.75, "duplex": 0.90, "apartment": 0.60}
SQFT_BAND_MULT = {
    "under_1200": 0.75,
    "1200_1800": 0.90,
    "1800_2500": 1.00,
    "2500_3500": 1.20,
    "over_3500": 1.45,
}
SQFT_BAND_LABELS = {
    "under_1200": "under 1,200 sqft",
    "1200_1800": "1,200-1,800 sqft",
    "1800_2500": "1,800-2,500 sqft",
    "2500_3500": "2,500-3,500 sqft",
    "over_3500": "over 3,500 sqft",
}

# Lot-size band, added 2026-09-16 (design §6.3). Same footing as the bedroom,
# bathroom, property-type and sqft multipliers above: illustrative starting
# points, not sourced from a dataset. Lot size deliberately does NOT filter
# ZIPs -- the screening snapshot has no lot-area column -- so this is the only
# place it has any effect.
LOT_SIZE_BAND_MULT = {
    "under_quarter": 0.92,
    "quarter_half": 1.00,
    "half_one": 1.08,
    "one_three": 1.20,
    "over_three": 1.35,
}
LOT_SIZE_BAND_LABELS = {
    "under_quarter": "under 1/4 acre",
    "quarter_half": "1/4 to 1/2 acre",
    "half_one": "1/2 to 1 acre",
    "one_three": "1 to 3 acres",
    "over_three": "over 3 acres",
}


def built_within_years_mult(years: int | None) -> float:
    if years is None:
        return 1.00  # no preference -- same as today
    if years <= 2:
        return 1.15  # new construction
    if years <= 10:
        return 1.05
    if years <= 30:
        return 1.00
    return 0.90



def estimate_housing_cost(
    *,
    state: str,
    housing_type: str,
    city_type: str,
    population_size: int,
    bedrooms: int,
    bathrooms: float,
    property_type: str,
    sqft_band: str,
    built_within_years: int | None,
    start_year: int,
    home_appr: float,
    inflation_general: float,
    lot_size_band: str = 'quarter_half',
) -> dict[str, Any]:
    """Pure pricing core for a state/city/characteristics housing estimate --
    state base price, city/population/characteristic multipliers, condo/
    townhome HOA-floor + maintenance discount (Slice 2), and start_year-
    dollars translation (Slice 1). Extracted (Slice 3, H8) from
    ``housing_state_estimate_payload`` so a second caller (the comparison
    sheet's "opposite type" candidate, H9a) can price a synthesized housing
    step without going through an HTTP request body.

    Every input is already parsed/validated by the caller (the HTTP wrapper
    below, or any other caller) -- this function does no parsing of its own.

    Returns the ``estimate`` dict the HTTP response's ``estimate`` field is
    built from, plus one caller-only key, ``basis_note``: the "Reflects
    ``start_year`` dollars: ..." clause (empty string when ``start_year`` is
    this year or earlier), left for the caller to fold into its own
    human-readable ``note`` text rather than duplicated here -- this function
    builds no narrative strings of its own.
    """
    is_rent = housing_type == "rent"
    estimate = dict(STATE_ESTIMATES.get(state) or dict(purchase_price=350000, monthly_rent=1600, insurance_annual=1600, utilities_annual=2800, maintenance_annual=3500, re_tax_pct=0.0100, hoa_pct=0.001))
    city_multipliers = {"urban": 1.30, "city": 1.30, "suburban": 1.00, "exurban": 0.85, "rural": 0.75}
    city_mult = city_multipliers.get(city_type, 1.00)
    if population_size > 500_000:
        pop_mult = 1.20
    elif population_size > 200_000:
        pop_mult = 1.12
    elif population_size > 100_000:
        pop_mult = 1.06
    elif population_size > 50_000:
        pop_mult = 1.02
    elif population_size > 20_000:
        pop_mult = 1.00
    elif population_size > 10_000:
        pop_mult = 0.92
    else:
        pop_mult = 0.85

    combined = (
        city_mult
        * pop_mult
        * BEDROOM_MULT[bedrooms]
        * BATHROOM_MULT[bathrooms]
        * PROPERTY_TYPE_MULT[property_type]
        * SQFT_BAND_MULT[sqft_band]
        * built_within_years_mult(built_within_years)
        # .get(..., 1.00) (not direct indexing like its neighbors above): this
        # field is new and may be blank/absent in an already-saved plan
        # config, so an unrecognized value must be neutral, not a KeyError.
        * LOT_SIZE_BAND_MULT.get(lot_size_band, 1.00)
    )
    estimate["purchase_price"] = round(float(estimate["purchase_price"]) * combined / 1000) * 1000
    estimate["monthly_rent"] = round(float(estimate["monthly_rent"]) * combined / 10) * 10
    estimate["maintenance_annual"] = round(float(estimate["purchase_price"]) * 0.01 / 100) * 100
    # HOA fee prevalence/size tracks density (condos/townhomes cluster in
    # urban, denser areas), so scale it the same way as the other purchase-side
    # estimated fields rather than leaving it a flat per-state constant.
    estimate["hoa_pct"] = round(float(estimate.get("hoa_pct", 0) or 0) * combined, 4)
    if is_rent:
        estimate["insurance_annual"] = round(max(180.0, min(450.0, float(estimate.get("insurance_annual", 0) or 0) * 0.15)) / 10) * 10
        estimate["utilities_annual"] = round(float(estimate.get("utilities_annual", 0) or 0) * 0.75 / 100) * 100
        estimate["maintenance_annual"] = 0

    # Slice 2: property type also floors HOA and discounts maintenance
    # (HOA typically covers exterior/structure for condo/townhome) -- applied
    # to today's-dollars values, before Slice 1's translation below scales
    # everything forward to start_year dollars.
    if property_type in ("condo", "townhome"):
        estimate["hoa_pct"] = max(estimate.get("hoa_pct", 0.0), 0.004)
        estimate["maintenance_annual"] *= 0.4

    # --- Slice 1: today's-dollars -> start_year-dollars translation ---------
    # housing-estimate-realism-and-dollar-convention-design.md §3.2. This is a
    # one-time Estimator-side correction to what number gets written into a
    # field; it does not touch deterministic_engine.py's ongoing (within-step)
    # escalation, which stays exactly as it was (directive 3).
    #
    # plan_start mirrors data_io.py's own c['plan_start'] = platform_runtime.
    # today().year exactly, so years_out lines up with what the engine will
    # later compute for the same step once it's saved.
    years_out = years_out_from(start_year)

    today_purchase_price = estimate["purchase_price"]
    today_monthly_rent = estimate["monthly_rent"]
    basis_note = ""
    if years_out:
        price_factor = (1 + home_appr) ** years_out
        cpi_factor = (1 + inflation_general) ** years_out
        # purchase_price escalates at home_appr -- the same rate the field
        # uses for its own post-purchase growth (deterministic_engine.py),
        # so one rate governs the home's value before and after the
        # transaction. monthly_rent and the flat recurring dollar costs
        # (insurance/utilities/maintenance) escalate at CPI, per directive 2.
        # re_tax_pct/hoa_pct/mortgage_rate_pct/down_payment are percentages
        # (or rate assumptions), not monetary quantities that compound with
        # inflation -- not translated, per §3.2.
        estimate["purchase_price"] = round(estimate["purchase_price"] * price_factor / 1000) * 1000
        estimate["monthly_rent"] = round(estimate["monthly_rent"] * cpi_factor / 10) * 10
        estimate["insurance_annual"] = round(float(estimate.get("insurance_annual", 0) or 0) * cpi_factor)
        estimate["utilities_annual"] = round(float(estimate.get("utilities_annual", 0) or 0) * cpi_factor)
        estimate["maintenance_annual"] = round(float(estimate.get("maintenance_annual", 0) or 0) * cpi_factor)
        basis_note = (
            f" Reflects {start_year} dollars: today's "
            f"${(today_monthly_rent if is_rent else today_purchase_price):,.0f} projected to "
            f"${(estimate['monthly_rent'] if is_rent else estimate['purchase_price']):,.0f} "
            f"({years_out} year{'s' if years_out != 1 else ''} out)."
        )

    estimate.update({
        "mortgage_rate_pct": estimate.get("mortgage_rate_pct", 0.0685),
        "type": "rent" if is_rent else "purchase",
        "city_type": city_type or "suburban",
        "population_size": population_size,
        "state": state,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "property_type": property_type,
        "sqft_band": sqft_band,
        "built_within_years": built_within_years,
        "basis_note": basis_note,
    })
    return estimate


def _parse_bedrooms(raw: Any) -> int:
    try:
        n = int(float(raw))
    except (ValueError, TypeError):
        return 3
    return max(2, min(5, n))  # clamped to {2,3,4,5}, 5 = "5+" (design §3.3)


def _parse_bathrooms(raw: Any) -> float:
    s = str(raw if raw is not None else "").strip().rstrip("+")
    try:
        n = float(s)
    except (ValueError, TypeError):
        return 2.0
    return n if n in BATHROOM_MULT else 2.0


def _parse_property_type(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    return s if s in PROPERTY_TYPE_MULT else "single_family"


def _parse_sqft_band(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    return s if s in SQFT_BAND_MULT else "1800_2500"


def _parse_lot_size_band(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    return s if s in LOT_SIZE_BAND_MULT else "quarter_half"


def _parse_built_within_years(raw: Any) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        n = int(float(raw))
    except (ValueError, TypeError):
        return None
    return max(0, n)


def _bathrooms_label(bathrooms: float) -> str:
    return "3.5+" if bathrooms >= 3.5 else (f"{bathrooms:g}")


def housing_state_estimate_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    state = str((data or {}).get("state", "")).strip().upper()
    housing_type = str((data or {}).get("type", (data or {}).get("housing_type", "purchase")) or "purchase").strip().lower()
    city_type = str((data or {}).get("city_type", "suburban")).strip().lower()
    try:
        population_size = int((data or {}).get("population_size", 20000) or 20000)
    except (ValueError, TypeError):
        population_size = 20000
    bedrooms = _parse_bedrooms((data or {}).get("bedrooms", 3))
    bathrooms = _parse_bathrooms((data or {}).get("bathrooms", 2))
    property_type = _parse_property_type((data or {}).get("property_type", "single_family"))
    sqft_band = _parse_sqft_band((data or {}).get("sqft_band", "1800_2500"))
    lot_size_band = _parse_lot_size_band((data or {}).get("lot_size_band", "quarter_half"))
    built_within_years = _parse_built_within_years((data or {}).get("built_within_years"))
    try:
        start_year = int((data or {}).get("start_year") or 0)
    except (TypeError, ValueError):
        start_year = 0
    try:
        home_appr = float((data or {}).get("home_appr"))
    except (TypeError, ValueError):
        home_appr = HOME_APPR_DEFAULT
    try:
        inflation_general = float((data or {}).get("inflation_general"))
    except (TypeError, ValueError):
        inflation_general = INFLATION_GENERAL_DEFAULT

    estimate = estimate_housing_cost(
        state=state, housing_type=housing_type, city_type=city_type,
        population_size=population_size, bedrooms=bedrooms, bathrooms=bathrooms,
        property_type=property_type, sqft_band=sqft_band,
        built_within_years=built_within_years, start_year=start_year,
        home_appr=home_appr, inflation_general=inflation_general,
        lot_size_band=lot_size_band,
    )
    basis_note = estimate.pop("basis_note", "")
    built_clause = f", built within the last {built_within_years} years" if built_within_years is not None else ""
    estimate["note"] = (
        f"Estimated costs for a {bedrooms}{'+' if bedrooms == 5 else ''}BR/"
        f"{_bathrooms_label(bathrooms)}BA {property_type.replace('_', ' ')} home, "
        f"{SQFT_BAND_LABELS[sqft_band]}{built_clause}, in a {city_type or 'suburban'} "
        f"area (~{population_size:,} population) in {state}.{basis_note} All values are editable."
    )
    return {"success": True, "schema": "housing_state_estimate_v1", "estimate": estimate}, 200
