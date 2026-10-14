"""Rental property tax core (WP12.1): pure functions, no I/O, no engine imports.

Rules, worked examples, assumptions and open questions:
``documentation/reference/RENTAL_TAX_RULES.md``. Every threshold and rate comes from the
tax-law reference data (``reference_src/tax_law_v10.json``) through ``rental_tax_constants``,
which reads a ``TaxLawDataset`` the caller passes in (``src.tax_law.default_tax_law_dataset()``).

Covered:
- MACRS residential rental depreciation: 27.5-year straight line, mid-month convention, IRS
  Pub. 946 Table A-6 percentages by placed-in-service month (partial first, last and sale year).
- Schedule E net: rent x (1 - vacancy) - operating expenses - mortgage interest - depreciation.
- Passive-activity loss limit (IRC 469, Form 8582): passive income offset, the rental
  active-participation special allowance with its MAGI phase-out (MFS rules from the data),
  suspended-loss carryforward per property, release on a full taxable disposition (469(g)).
- Sale: amount realized, adjusted basis, gain or loss (dual basis for a converted home),
  unrecaptured section 1250 gain = min(gain, depreciation) (taxed at ordinary rates capped at
  25%), the rest long-term capital gain; a loss is a section 1231 ordinary loss.
- Converted home: depreciable basis = lesser of value at conversion and adjusted basis,
  land excluded; section 121 two-of-five-year test and exclusion, depreciation never excluded.

Money amounts are floats in dollars and are not rounded (the engine works unrounded).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import TYPE_CHECKING, Iterable, Sequence

if TYPE_CHECKING:  # type only; this module never loads data itself
    from .tax_law import TaxLawDataset

_MFS = "MFS"


# --------------------------------------------------------------------------- constants

@dataclass(frozen=True)
class RentalTaxConstants:
    """The reference-data values the rental rules need, resolved for one year and filing status."""

    recovery_years: float  # residential rental recovery period (27.5)
    special_allowance: float  # active-participation allowance before phase-out (25,000 / 12,500 / 0)
    phaseout_start: float  # MAGI where the allowance starts to phase out (100,000 / 50,000)
    phaseout_rate: float  # allowance reduction per dollar of MAGI over the start (0.5)
    unrecaptured_1250_max_rate: float  # 0.25
    section_121_exclusion: float  # 250,000 / 500,000 (MFJ)
    section_121_required_days: int  # 730 days of ownership and of use
    section_121_lookback_years: int  # 5-year window ending on the sale date


def rental_tax_constants(dataset: "TaxLawDataset", year: int, filing_status: str = "MFJ", *,
                         mfs_lived_apart_all_year: bool = False) -> RentalTaxConstants:
    """Resolve ``RentalTaxConstants`` from the tax-law dataset (``dataset.lookup`` rules: the
    latest row in force for ``year``; a status without its own row uses the MFJ row).

    Married filing separately: the allowance and phase-out start are the MFS rows when the
    spouses lived apart all year (IRC 469(i)(5)(A)); otherwise the allowance is the
    ``passive_rental_special_allowance_mfs_not_living_apart`` row (zero, 469(i)(5)(B)).
    """
    def v(name: str) -> float:
        return dataset.lookup(name, year, filing_status=filing_status).value

    allowance = v("passive_rental_special_allowance")
    if filing_status == _MFS and not mfs_lived_apart_all_year:
        allowance = v("passive_rental_special_allowance_mfs_not_living_apart")
    return RentalTaxConstants(
        recovery_years=float(v("residential_rental_recovery_years")),
        special_allowance=float(allowance),
        phaseout_start=float(v("passive_rental_phaseout_start")),
        phaseout_rate=float(v("passive_rental_phaseout_rate")),
        unrecaptured_1250_max_rate=float(v("unrecaptured_1250_max_rate")),
        section_121_exclusion=float(v("section_121_exclusion")),
        section_121_required_days=int(v("section_121_required_days")),
        section_121_lookback_years=int(v("section_121_lookback_years")),
    )


# --------------------------------------------------------------------------- depreciation

def _check_month(month: int, what: str) -> None:
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError(f"{what} must be a month number 1-12, got {month!r}")


def _check_share(share: float, what: str) -> None:
    if not 0.0 <= share <= 1.0:
        raise ValueError(f"{what} must be between 0 and 1, got {share!r}")


@lru_cache(maxsize=None)
def macrs_mid_month_percentages(placed_month: int, recovery_years: float) -> tuple[float, ...]:
    """IRS Pub. 946 Table A-6 column (residential rental, 27.5 years, mid-month, straight line)
    for property placed in service in ``placed_month``: the percentage of basis for recovery
    year 1, 2, ... (3.485 means 3.485%).

    Year 1 = (12 - month + 0.5) / 12 / life. Each later year is the unrecovered percentage
    divided by the remaining recovery period, rounded to 3 decimals (half up); the last year
    takes what is left. This reproduces the published table exactly (3.636% in years 2-9,
    3.637/3.636 alternating from year 10, columns summing to 100.000%).
    """
    _check_month(placed_month, "placed_month")
    if recovery_years <= 1:
        raise ValueError(f"recovery_years must exceed 1, got {recovery_years!r}")
    q = Decimal("0.001")
    life = Decimal(str(recovery_years))
    first = (Decimal(12) - Decimal(placed_month) + Decimal("0.5")) / Decimal(12)
    pct = (Decimal(100) * first / life).quantize(q, ROUND_HALF_UP)
    out = [pct]
    unrecovered = Decimal(100) - pct
    remaining = life - first
    while unrecovered > 0:
        pct = unrecovered if remaining <= 1 else min(unrecovered, (unrecovered / remaining).quantize(q, ROUND_HALF_UP))
        out.append(pct)
        unrecovered -= pct
        remaining -= 1
    return tuple(float(p) for p in out)


def annual_depreciation(basis: float, placed_year: int, placed_month: int, tax_year: int, recovery_years: float, *,
                        disposed_month: int | None = None) -> float:
    """Depreciation of one asset for ``tax_year`` (Table A-6 percentage x basis).

    ``disposed_month`` set means the asset is sold in ``tax_year`` (mid-month convention):
    the full-year amount x (disposed_month - 0.5) / 12 (Pub. 946, "Dispositions"); in the final,
    already partial recovery year the result never exceeds that year's table amount; sold in the
    placed-in-service year, (disposed_month - placed_month) / 12 of a full year.
    """
    if basis <= 0 or tax_year < placed_year:
        return 0.0
    pcts = macrs_mid_month_percentages(placed_month, recovery_years)
    k = tax_year - placed_year
    if k >= len(pcts):
        return 0.0
    pct = pcts[k]
    if disposed_month is not None:
        _check_month(disposed_month, "disposed_month")
        full_year = 100.0 / recovery_years
        if k == 0:
            if disposed_month < placed_month:
                raise ValueError("disposed_month is before placed_month in the placed-in-service year")
            pct = full_year * (disposed_month - placed_month) / 12.0
        elif k == len(pcts) - 1:
            pct = min(pct, full_year * (disposed_month - 0.5) / 12.0)
        else:
            pct = pct * (disposed_month - 0.5) / 12.0
    return basis * pct / 100.0


def accumulated_depreciation(basis: float, placed_year: int, placed_month: int, through_year: int,
                             recovery_years: float, *, disposed_month: int | None = None) -> float:
    """Depreciation allowed or allowable from ``placed_year`` through ``through_year`` inclusive;
    ``disposed_month`` applies to ``through_year`` (the sale year)."""
    return sum(annual_depreciation(basis, placed_year, placed_month, y, recovery_years,
                                   disposed_month=disposed_month if y == through_year else None)
               for y in range(placed_year, through_year + 1))


@dataclass(frozen=True)
class DepreciableAsset:
    """A building or a capital improvement: depreciable basis (land excluded) and when placed in service."""

    basis: float
    placed_year: int
    placed_month: int


def property_depreciation(assets: Iterable[DepreciableAsset], tax_year: int, recovery_years: float, *,
                          disposed_month: int | None = None) -> float:
    """Total depreciation for ``tax_year`` over the building and its improvements."""
    return sum(annual_depreciation(a.basis, a.placed_year, a.placed_month, tax_year, recovery_years,
                                   disposed_month=disposed_month) for a in assets)


def property_accumulated_depreciation(assets: Iterable[DepreciableAsset], through_year: int, recovery_years: float, *,
                                      disposed_month: int | None = None) -> float:
    """Accumulated depreciation through ``through_year`` over the building and its improvements."""
    return sum(accumulated_depreciation(a.basis, a.placed_year, a.placed_month, through_year, recovery_years,
                                        disposed_month=disposed_month) for a in assets)


def depreciable_basis(purchase_price: float, closing_costs: float, land_share: float) -> float:
    """Building basis of a purchased rental: (price + capitalized closing costs) x (1 - land share)."""
    _check_share(land_share, "land_share")
    return (purchase_price + closing_costs) * (1.0 - land_share)


def converted_home_depreciable_basis(value_at_conversion: float, adjusted_basis_at_conversion: float,
                                     land_share: float) -> float:
    """Building basis of a home converted to a rental: the lesser of fair market value and
    adjusted basis on the conversion date, land excluded (Pub. 527 ch. 4, Reg. 1.168(i)-4(b)).
    One land share is applied to both amounts (an assumption, see the rules document)."""
    _check_share(land_share, "land_share")
    return min(value_at_conversion, adjusted_basis_at_conversion) * (1.0 - land_share)


# --------------------------------------------------------------------------- Schedule E

def schedule_e_net(gross_rent: float, vacancy_rate: float, operating_expenses: float, mortgage_interest: float,
                   depreciation: float) -> float:
    """Net rental income (positive) or loss (negative) for one property and year."""
    _check_share(vacancy_rate, "vacancy_rate")
    return gross_rent * (1.0 - vacancy_rate) - operating_expenses - mortgage_interest - depreciation


# --------------------------------------------------------------------------- passive-activity loss limit

def special_allowance(magi: float, constants: RentalTaxConstants, *, active_participation: bool = True) -> float:
    """Rental real estate allowance after the MAGI phase-out (IRC 469(i); Form 8582 lines 5-8).

    ``magi`` is modified AGI for this rule (computed by the caller without passive losses)."""
    if not active_participation:
        return 0.0
    reduction = constants.phaseout_rate * max(0.0, magi - constants.phaseout_start)
    return max(0.0, constants.special_allowance - reduction)


@dataclass(frozen=True)
class PassiveActivity:
    """One rental property's passive-activity inputs for a year.

    ``net_income``: this year's Schedule E net (negative = loss). ``prior_suspended``: loss
    carried in from earlier years (a positive amount). ``disposition_gain``: gain on a sale this
    year, passive income for the limit only (it reaches AGI through the capital-gain path, not
    through Schedule E). ``fully_disposed``: the entire interest was sold this year in a fully
    taxable transaction to an unrelated party.
    """

    name: str
    net_income: float
    prior_suspended: float = 0.0
    active_participation: bool = True
    fully_disposed: bool = False
    disposition_gain: float = 0.0


@dataclass(frozen=True)
class PassiveActivityResult:
    name: str
    overall: float  # net_income + disposition_gain - prior_suspended
    allowed: float  # Schedule E amount entering AGI this year (income > 0, allowed loss < 0)
    suspended: float  # loss carried to next year (>= 0)
    released: bool  # loss freed in full by a full disposition (IRC 469(g))


@dataclass(frozen=True)
class PassiveLossResult:
    activities: tuple[PassiveActivityResult, ...]
    special_allowance_available: float  # after the MAGI phase-out
    special_allowance_used: float
    passive_income_offset: float  # overall loss absorbed by passive income (overall-gain properties + other)
    released_loss: float  # loss freed by full dispositions
    net_to_agi: float  # sum of ``allowed`` (Schedule E total into AGI)
    total_suspended: float


def apply_passive_loss_limits(activities: Sequence[PassiveActivity], magi: float, constants: RentalTaxConstants, *,
                              other_passive_income: float = 0.0) -> PassiveLossResult:
    """Apply the passive-activity loss limit to a year's rental properties (Form 8582 order).

    1. A fully disposed property with an overall loss is released in full (469(g)).
    2. A property with an overall gain (income, its own carryforward, any disposition gain) has
       all its own losses allowed; its net gain is passive income.
    3. Overall losses are allowed up to passive income plus the special allowance; the allowance
       is limited to the net loss of active-participation properties and to the overall net loss
       (Form 8582 line 4) and is shared among active-participation loss properties in proportion
       to their losses (Worksheet 4); the passive-income offset is then shared among all loss
       properties in proportion to their remaining loss (Worksheet 5). The rest is suspended.
    """
    if other_passive_income < 0:
        raise ValueError("other_passive_income must be >= 0 (other passive losses are out of scope)")
    for a in activities:
        if a.prior_suspended < 0 or a.disposition_gain < 0:
            raise ValueError(f"{a.name}: prior_suspended and disposition_gain must be >= 0")
        if a.disposition_gain and not a.fully_disposed:
            raise ValueError(f"{a.name}: disposition_gain needs fully_disposed (partial sales are out of scope)")

    overall = [a.net_income + a.disposition_gain - a.prior_suspended for a in activities]
    released_idx = {i for i, a in enumerate(activities) if a.fully_disposed and overall[i] < 0}
    gain_idx = [i for i in range(len(activities)) if i not in released_idx and overall[i] >= 0]
    loss_idx = [i for i in range(len(activities)) if i not in released_idx and overall[i] < 0]

    income_total = sum(overall[i] for i in gain_idx) + other_passive_income
    active_income = sum(overall[i] for i in gain_idx if activities[i].active_participation)
    loss = {i: -overall[i] for i in loss_idx}
    active_loss = sum(loss[i] for i in loss_idx if activities[i].active_participation)
    total_loss = sum(loss.values())

    available = special_allowance(magi, constants)
    sa = {i: 0.0 for i in loss_idx}
    offset = {i: 0.0 for i in loss_idx}
    used = 0.0
    if total_loss > income_total:  # Form 8582 line 3 is a loss
        line_1d = active_income - active_loss
        line_4 = min(-line_1d, total_loss - income_total) if line_1d < 0 else 0.0
        used = min(line_4, available)
        if used > 0:
            for i in loss_idx:
                if activities[i].active_participation:
                    sa[i] = used * loss[i] / active_loss
        remaining = {i: loss[i] - sa[i] for i in loss_idx}
        remaining_total = sum(remaining.values())
        if remaining_total > 0:
            for i in loss_idx:
                offset[i] = income_total * remaining[i] / remaining_total
    else:  # passive income covers every loss
        offset = dict(loss)

    results = []
    for i, a in enumerate(activities):
        own = a.net_income - a.prior_suspended  # the Schedule E part (disposition gain goes elsewhere)
        if i in released_idx or i in gain_idx:
            results.append(PassiveActivityResult(a.name, overall[i], own, 0.0, i in released_idx))
        else:
            allowed_loss = sa[i] + offset[i]
            suspended = max(0.0, loss[i] - allowed_loss)
            # a property with a disposition gain never reaches here (fully disposed -> released or gain)
            results.append(PassiveActivityResult(a.name, overall[i], -allowed_loss, suspended, False))
    released_loss = sum(-overall[i] for i in released_idx)
    return PassiveLossResult(
        activities=tuple(results),
        special_allowance_available=available,
        special_allowance_used=used,
        passive_income_offset=sum(offset.values()),
        released_loss=released_loss,
        net_to_agi=sum(r.allowed for r in results),
        total_suspended=sum(r.suspended for r in results),
    )


# --------------------------------------------------------------------------- sale

@dataclass(frozen=True)
class RentalSaleResult:
    amount_realized: float  # sale price - selling costs
    adjusted_basis: float  # cost basis + improvements - accumulated depreciation (basis for gain)
    loss_adjusted_basis: float | None  # converted home: loss basis + improvements - depreciation; else None
    gain: float  # recognized gain (> 0) or loss (< 0); 0 between the two bases of a converted home
    unrecaptured_1250_gain: float  # min(gain, accumulated depreciation)
    capital_gain: float  # the rest of the gain (section 1231 -> long-term capital gain)
    ordinary_loss: float  # section 1231 loss as a positive amount (ordinary)


def split_sale_gain(gain: float, accumulated_depreciation: float) -> tuple[float, float]:
    """(unrecaptured section 1250 gain, long-term capital gain) for a positive gain."""
    if gain <= 0:
        return 0.0, 0.0
    recapture = min(gain, max(0.0, accumulated_depreciation))
    return recapture, gain - recapture


def rental_sale(sale_price: float, selling_costs: float, cost_basis: float, improvements: float,
                accumulated_depreciation: float, *, loss_basis: float | None = None) -> RentalSaleResult:
    """Gain or loss on selling a rental.

    ``cost_basis``: purchase price + closing costs, land included (for a converted home, the
    home's adjusted basis on the conversion date). ``improvements``: capital improvements made
    while a rental. Adjusted basis = cost_basis + improvements - accumulated depreciation.
    ``loss_basis`` (converted home only): the lesser of value and adjusted basis on the
    conversion date, land included; a loss is measured from it (Reg. 1.165-9(b)(2)), so a sale
    between the two bases gives neither gain nor loss.
    """
    realized = sale_price - selling_costs
    gain_basis = cost_basis + improvements - accumulated_depreciation
    loss_adjusted = None if loss_basis is None else loss_basis + improvements - accumulated_depreciation
    gain = realized - gain_basis
    if gain < 0 and loss_adjusted is not None:
        gain = min(0.0, realized - loss_adjusted)
    recapture, ltcg = split_sale_gain(gain, accumulated_depreciation)
    return RentalSaleResult(realized, gain_basis, loss_adjusted, gain, recapture, ltcg, max(0.0, -gain))


def unrecaptured_1250_tax(amount: float, ordinary_taxable_income: float,
                          ordinary_brackets: Sequence[tuple[float, float | None, float]], max_rate: float) -> float:
    """Tax on unrecaptured section 1250 gain stacked on top of ordinary taxable income: each
    dollar at the lesser of its ordinary bracket rate and ``max_rate`` (Schedule D Tax
    Worksheet effect). ``ordinary_brackets``: (lower, upper or None/inf, rate)."""
    if amount <= 0:
        return 0.0
    lo_slice, hi_slice = max(0.0, ordinary_taxable_income), max(0.0, ordinary_taxable_income) + amount
    tax = 0.0
    for lower, upper, rate in ordinary_brackets:
        top = math.inf if upper is None else upper
        width = min(hi_slice, top) - max(lo_slice, lower)
        if width > 0:
            tax += width * min(rate, max_rate)
    return tax


# --------------------------------------------------------------------------- section 121 (converted homes only)

def _years_before(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 February
        return d.replace(year=d.year - years, day=28)


def section_121_two_of_five(sale_date: date, owned_from: date, residence_periods: Iterable[tuple[date, date]], *,
                            required_days: int, lookback_years: int) -> bool:
    """IRC 121(a): owned and used as the principal residence for at least ``required_days``
    (730) each within the ``lookback_years`` (5) ending on the sale date. Ownership runs from
    ``owned_from`` to the sale; ``residence_periods`` are (move-in, move-out) dates, move-out
    exclusive. The two periods need not overlap (Reg. 1.121-1(c))."""
    window_start = _years_before(sale_date, lookback_years)
    owned_days = max(0, (sale_date - max(owned_from, window_start)).days)
    used_days = 0
    for start, end in residence_periods:
        lo, hi = max(start, window_start), min(end, sale_date)
        used_days += max(0, (hi - lo).days)
    return owned_days >= required_days and used_days >= required_days


@dataclass(frozen=True)
class Section121Result:
    excluded: float  # gain excluded under section 121
    unrecaptured_1250_gain: float  # gain equal to depreciation: never excluded (121(d)(6))
    capital_gain: float  # taxable long-term capital gain left after the exclusion


def section_121_converted_home(gain: float, accumulated_depreciation: float, *, qualifies: bool,
                               exclusion: float, nonqualified_ratio: float = 0.0) -> Section121Result:
    """Split a converted home's sale gain: depreciation taken first (unrecaptured 1250, taxable),
    then the exclusion (when the two-of-five test is met) up to ``exclusion``, the rest LTCG.
    Rental use after the last residence use is not nonqualified use (121(b)(5)(C)(ii)(I)),
    so ``nonqualified_ratio`` is 0 unless the household moved back in (H3): then that share of
    the gain left after the depreciation split (121(b)(5)(A)) is not excludable (taxable LTCG)."""
    recapture, rest = split_sale_gain(gain, accumulated_depreciation)
    eligible = rest * (1.0 - min(1.0, max(0.0, nonqualified_ratio)))
    excluded = min(eligible, exclusion) if qualifies else 0.0
    return Section121Result(excluded, recapture, rest - excluded)
