"""Keep and rent out (WP12.8): the current home's third disposition.

Design ``documentation/archive/superpowers/specs/2026-10-05-rental-property-module-design.md``
decision 2 and the housing refinement design section 13. Only when the
``rental_property_income`` feature is on: a ``rent_out`` candidate keeps the
current home (no sale in the plan) and rents it from move 1's acquisition
year through the engine's existing converted-home machinery
(``projection_stages.rental_property``, kind ``converted_home``): the carrying
costs move to Schedule E from the conversion, depreciation runs, and the
passive-loss limit applies. Nothing here computes tax; it writes one
``c['rental_properties']`` entry and reads the run's rows back for notes.

The rent is never invented: it is the rent typed into the request, else the
rent of the plan's own converted-home entry (Rental Properties page). With
neither, ``rent_out`` is not searched.

Off, :func:`rent_out_plan` returns ``None`` and every caller behaves exactly
as before this module existed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..module_catalog import feature_enabled
from .models import RENT_OUT, RENT_THEN_SELL, RENTAL_DISPOSITIONS, HousingCandidate

FEATURE_KEY = 'rental_property_income'
CONVERTED_HOME = 'converted_home'
DEFAULT_NAME = 'Current home (rented out)'
DEFAULT_MONTH = 7  # conversion and sale month when none is given (owner decision 2026-10-13)
# How far past the conversion the section 121 window is searched. The
# two-of-five test always fails within five years of the move-out.
_SEC121_SCAN_YEARS = 6


@dataclass(frozen=True)
class RentOutPlan:
    """The feature is on. ``template`` is the converted-home property every
    ``rent_out`` candidate writes (its conversion year set per candidate);
    ``None`` when no rent is known, so ``rent_out`` is not searched."""
    template: dict[str, Any] | None


def _is_converted(p: Any) -> bool:
    return isinstance(p, dict) and str(p.get('kind') or '').strip().lower().replace(' ', '_') == CONVERTED_HOME


def rent_out_plan(c: dict[str, Any], monthly_rent: float | None = None) -> RentOutPlan | None:
    """``None`` when the feature is off. ``monthly_rent`` (today's dollars) is the
    typed value; it overrides the plan's converted-home entry's rent and keeps
    that entry's other inputs (expenses, vacancy, land share)."""
    if not feature_enabled(c, 'rental_property_income'):
        return None
    if float(c.get('home_val', 0.0) or 0.0) <= 0:
        return RentOutPlan(None)  # no home to rent out
    existing = next((p for p in (c.get('rental_properties') or []) if _is_converted(p)), None)
    if monthly_rent is not None:
        if not math.isfinite(monthly_rent) or monthly_rent <= 0:
            raise ValueError('Monthly rent for keep-and-rent-out must be more than 0.')
        base = dict(existing) if existing else {'name': DEFAULT_NAME, 'kind': CONVERTED_HOME,
                                                'conversion_month': DEFAULT_MONTH, 'sale_month': DEFAULT_MONTH}
        return RentOutPlan({**base, 'monthly_rent': float(monthly_rent)})
    if existing and float(existing.get('monthly_rent') or 0.0) > 0:
        return RentOutPlan(dict(existing))
    return RentOutPlan(None)


def apply_rent_out(c: dict[str, Any], cand: HousingCandidate, plan: RentOutPlan) -> None:
    """Rewrite ``c['rental_properties']`` for ``cand``: the plan's converted-home
    entry is dropped (the disposition decides it, and a conversion year that is
    not the move year would rent the home while the household still lives in
    it); a ``rent_out`` candidate adds the template converted in move 1's
    acquisition year. Standalone properties are untouched."""
    props = [p for p in (c.get('rental_properties') or []) if not _is_converted(p)]
    if cand.original_home.disposition in RENTAL_DISPOSITIONS and plan.template is not None:
        year = cand.move1.acquisition_year
        entry = {**plan.template, 'conversion_year': year}
        # Inputs tied to the plan's own conversion date do not carry to another
        # year: the value at conversion is re-projected by the engine, and
        # improvements or overrides before this conversion never happen.
        entry.pop('value_at_conversion', None)
        entry['improvements'] = [i for i in entry.get('improvements') or []
                                 if isinstance(i, dict) and int(i.get('year') or 0) >= year]
        entry['overrides'] = _overrides_from(entry.get('overrides'), year)
        if entry.get('rental_end_year') is not None and int(entry['rental_end_year']) < year:
            entry.pop('rental_end_year')
        if entry.get('purchase_year') is not None and int(entry['purchase_year']) > year:
            entry.pop('purchase_year')
            entry.pop('purchase_month', None)
        props.append(entry)
    c['rental_properties'] = props


def plan_converted_home(c: dict[str, Any]) -> dict[str, Any] | None:
    """The plan's own converted-home entry (Rental Properties page), if any."""
    return next((p for p in (c.get('rental_properties') or []) if _is_converted(p)), None)


def without_plan_converted_home(c: dict[str, Any]) -> dict[str, Any]:
    """A shallow copy of ``c`` without the plan's own converted-home entry: the same
    normalisation ``apply_rent_out`` gives every sell / keep candidate (M6), so the
    do-nothing baseline compares like for like with them."""
    c2 = dict(c)
    c2['rental_properties'] = [p for p in (c.get('rental_properties') or []) if not _is_converted(p)]
    return c2


def baseline_comparison_notes(entry: dict[str, Any], as_entered: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Why the baseline leaves out the plan's own converted home (M6), with the as-entered figures."""
    name = str(entry.get('name') or DEFAULT_NAME)
    return [
        f"Do-nothing baseline and sell / keep candidates leave out the plan's own converted home "
        f"'{name}' (the disposition decides it); only rent-out candidates rent the home.",
        f"The plan as entered, with '{name}' rented, would end at net worth "
        f"${as_entered['net_worth']:,.0f} (lifetime cost ${as_entered['lifetime_cost']:,.0f}, exact tax delta); "
        f"the baseline above is ${baseline['net_worth']:,.0f} (${baseline['lifetime_cost']:,.0f}).",
    ]


def _overrides_from(overrides: Any, year: int) -> Any:
    """The per-year overrides from ``year`` on, in either stored shape (a
    ``{year: {...}}`` map or a list of ``{year, ...}`` rows)."""
    if isinstance(overrides, dict):
        return {y: v for y, v in overrides.items() if int(y) >= year}
    return [o for o in overrides or [] if isinstance(o, dict) and int(o.get('year') or 0) >= year]


def _converted_rows(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """``(row, converted-home property figures)`` for each year the home is a rental."""
    out = []
    for r in rows:
        for p in r.get('rental_by_property') or []:
            if p.get('kind') == CONVERTED_HOME and p.get('owned'):
                out.append((r, p))
    return out


# M7: every rent-out row says which tax its lifetime cost carries.
EXACT_TAX_NOTE = 'lifetime cost uses exact tax delta'
ESTIMATED_TAX_NOTE = 'estimated tax on rent'


def exact_rent_tax(rows: list[dict[str, Any]], rows_without: list[dict[str, Any]]) -> float:
    """The engine's own tax on the converted home (M7): lifetime ``total_tax`` of
    the run with it rented less the same run with the converted-home entry left
    out (negative when the rental lowers tax)."""
    def _tax(rs: list[dict[str, Any]]) -> float:
        # the sale's own tax is counted separately in the lifetime cost (H6: rent then sell)
        return sum(float(r.get('total_tax', 0.0) or 0.0) - float(r.get('home_sale_tax', 0.0) or 0.0) for r in rs)
    return _tax(rows) - _tax(rows_without)


def converted_after_tax_net_cash(rows: list[dict[str, Any]], tax: float | None = None) -> float:
    """Lifetime after-tax rental net cash of the converted home: rent collected
    less its operating costs, debt service and improvements, less an estimate
    of the income tax on it -- the year's Schedule E amount that reached AGI
    (its Schedule E less the change in its suspended passive loss) times the
    row's effective marginal rate (a loss that reached AGI is a tax saving).
    The carrying costs left ``housing_total_yr`` at the conversion, so the
    lifetime housing cost counts them through this. 0 without a converted home
    (feature off). Net worth needs no estimate: the engine taxes the rent.

    ``tax`` (M7) replaces the estimate with a known lifetime tax on the rental
    (:func:`exact_rent_tax`)."""
    if tax is not None:
        return sum(float(p.get('net_cash', 0.0) or 0.0) for _r, p in _converted_rows(rows)) - tax
    total, prior_suspended = 0.0, 0.0
    for r, p in _converted_rows(rows):
        suspended = float(p.get('suspended_loss_carryforward', 0.0) or 0.0)
        to_agi = float(p.get('schedule_e', 0.0) or 0.0) - (suspended - prior_suspended)
        rate = float(r.get('effective_marginal_rate') or 0.0)
        total += float(p.get('net_cash', 0.0) or 0.0) - to_agi * rate
        prior_suspended = suspended
    return total


def last_sale_year_keeping_sec121(entry: dict[str, Any], filing: str = 'MFJ') -> int | None:
    """The last year a sale (in ``sale_month``) of the converted home in
    ``entry`` still meets the section 121 two-of-five test, or ``None`` when it
    never does. The same test and inputs the engine's home sale applies
    (``rental_tax.section_121_two_of_five``; owned and lived in from the
    purchase, else -- the engine's default -- five years before the conversion,
    January, to the conversion). Read from ``rental_tax`` directly so this
    package stays off the projection-stage internals."""
    from datetime import date

    from ..rental_tax import rental_tax_constants, section_121_two_of_five
    from ..tax_law import default_tax_law_dataset
    conv_year = int(entry['conversion_year'])
    placed = date(conv_year, int(entry.get('conversion_month') or DEFAULT_MONTH), 1)
    bought = entry.get('purchase_year')
    owned_from = (date(int(bought), int(entry.get('purchase_month') or DEFAULT_MONTH), 1) if bought
                  else date(conv_year - 5, 1, 1))
    sale_month = int(entry.get('sale_month') or DEFAULT_MONTH)
    dataset = default_tax_law_dataset()
    last = None
    for year in range(conv_year, conv_year + _SEC121_SCAN_YEARS):
        sale = date(year, sale_month, 1)
        if sale <= placed:
            continue
        k = rental_tax_constants(dataset, year, filing)
        if section_121_two_of_five(sale, owned_from, [(owned_from, placed)],
                                   required_days=k.section_121_required_days,
                                   lookback_years=k.section_121_lookback_years):
            last = year
    return last


def _sale_notes(rows: list[dict[str, Any]], sale_year: int, last_ok: int | None) -> list[str]:
    """H6: what the sale of the rented home in ``sale_year`` did, read back from the run: the
    section 121 test, the depreciation recaptured, the taxable gain, and the two-year IRMAA effect
    of the gain (H1) when the plan reaches that year."""
    by_year = {int(r.get('year', 0) or 0): r for r in rows}
    sale = by_year.get(sale_year)
    if sale is None:
        return []
    notes = []
    if sale.get('home_sale_sec121_two_of_five'):
        notes.append(f'§121 two-of-five met for the {sale_year} sale: ${float(sale.get("home_sale_sec121_excluded", 0.0)):,.0f} excluded')
    else:
        window = f' (last year with the exclusion: {last_ok})' if last_ok else ''
        notes.append(f'§121 two-of-five NOT met for the {sale_year} sale: no exclusion{window}')
    recapture = float(sale.get('home_sale_unrecaptured_1250_gain', 0.0) or 0.0)
    if recapture > 0:
        notes.append(f'§1250 recapture on the sale: ${recapture:,.0f} (taxed up to 25%)')
    gain = float(sale.get('sale_cap_gain_in_agi', 0.0) or 0.0)
    later = by_year.get(sale_year + 2)
    if gain > 0 and later is not None:
        notes.append(f'sale gain ${gain:,.0f} is in {sale_year} AGI; IRMAA tier {later.get("irmaa_tier", 0)} '
                     f'in {sale_year + 2} (MAGI ${float(later.get("irmaa_magi_used", 0.0)):,.0f})')
    return notes


def rent_out_notes(c: dict[str, Any], cand: HousingCandidate,
                   rows: list[dict[str, Any]]) -> list[str]:
    """Notes for a ``rent_out`` candidate: the section 121 two-of-five window
    (the last year a sale keeps the exclusion, or that it already fails), the
    depreciation a sale would recapture, and a passive loss still suspended at
    the end. ``c`` is the config the run used. Warn only (owner decision
    2026-10-13): nothing is dropped or re-scored, and the plan sells nothing,
    so no per-move §121 flag is set."""
    if cand.original_home.disposition not in RENTAL_DISPOSITIONS:
        return []
    entry = next((p for p in (c.get('rental_properties') or []) if _is_converted(p)), None)
    if entry is None:
        return []
    sale_year = cand.original_home.sale_year if cand.original_home.disposition == RENT_THEN_SELL else None
    notes = [f'rented out from {cand.move1.acquisition_year}' + (f', sold in {sale_year}' if sale_year else '')]
    filing = str((rows[0].get('filing') if rows else None) or 'MFJ')
    last_ok = last_sale_year_keeping_sec121(entry, filing)
    if sale_year is not None:
        notes.extend(_sale_notes(rows, sale_year, last_ok))
    elif last_ok is None:
        notes.append('§121 two-of-five test fails: no exclusion on any sale of the rented home')
    else:
        notes.append(f'§121 two-of-five: exclusion only if sold by {last_ok}')
    conv = _converted_rows(rows)
    depreciation = sum(float(p.get('depreciation', 0.0) or 0.0) for _r, p in conv)
    if depreciation > 0 and sale_year is None:
        notes.append(f'§1250 recapture: ${depreciation:,.0f} depreciation taken '
                     f'{conv[0][0].get("year")}-{conv[-1][0].get("year")}, taxed up to 25% on a sale')
    suspended = float((conv[-1][1].get('suspended_loss_carryforward', 0.0) or 0.0) if conv else 0.0)
    if suspended > 0 and sale_year is None:
        notes.append(f'passive loss suspended: ${suspended:,.0f} at plan end')
    return notes
