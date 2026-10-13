"""Rental Properties workbook figures (WP12.7; design 2026-10-05 section 7).

Pure functions over the projection rows: no workbook, no engine run. They read the
``rental_*`` row fields (``result_contract.RENTAL_ROW_FIELDS``) and the per-property
list ``row['rental_by_property']``, plus the normalized property specs of the run for the
depreciation basis. ``sheets_rental`` writes what this module returns, and the tests
reconcile it to the rows.

A row without ``rental_net_cash_flow`` means the feature did not run that year
(:func:`rental_active` is False), so a plan with the feature off yields no report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..projection_stages.rental_property import CONVERTED_HOME, RentalBook, RentalSpec, rental_book_for
from ..rental_tax import RentalTaxConstants, property_accumulated_depreciation


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def rental_active(rows: Sequence[Mapping[str, Any]]) -> bool:
    """True when the engine ran the Rental Properties feature (its row fields exist)."""
    return any('rental_net_cash_flow' in r for r in rows)


@dataclass(frozen=True)
class YearLine:
    """One year of rental figures: the plan total, or one property when ``name`` is set."""

    year: int
    name: str
    gross_rent: float
    vacancy: float
    operating_expenses: float
    interest: float
    principal: float
    depreciation: float
    schedule_e: float  # net, before the passive-loss limit
    opening_suspended: float
    suspended: float  # carried forward at year end
    schedule_e_to_agi: float  # after the passive-loss limit (released losses included)
    loss_allowed: float  # loss deducted against other income this year (>= 0)
    tax_effect: float  # schedule_e_to_agi x the year's effective marginal rate (+ tax, - saving)
    improvements_purchase: float
    net_cash: float
    sale_net_proceeds: float
    owned: bool

    @property
    def debt_service(self) -> float:
        return self.interest + self.principal

    @property
    def collected(self) -> float:
        return self.gross_rent - self.vacancy


@dataclass(frozen=True)
class DepreciationLine:
    year: int
    name: str
    depreciable_basis: float  # building + improvements placed through the year
    land: float
    annual: float
    accumulated: float
    adjusted_basis: float  # cost basis + improvements - accumulated (year end; at sale: the sale's)
    sold: bool


@dataclass(frozen=True)
class LedgerLine:
    year: int
    name: str
    opening: float
    current_loss: float
    used: float  # carryforward and loss deducted this year within the limits
    released: float  # freed in full by the sale
    closing: float


@dataclass(frozen=True)
class SaleLine:
    year: int
    name: str
    converted: bool
    price: float
    selling_costs: float
    loan_payoff: float
    adjusted_basis: float
    accumulated_depreciation: float
    gain: float  # recognized gain (+) or loss (-)
    recapture_1250: float
    long_term_gain: float  # taxable long-term gain (after the section 121 exclusion for a converted home)
    sec121_qualifies: bool | None
    sec121_excluded: float
    tax_ltcg: float
    tax_cap_adjustment: float
    tax_state: float
    tax_1250_est: float
    net_proceeds: float

    @property
    def tax_at_sale(self) -> float:
        # The 25% cap is inside ``tax_1250_est`` (the gain is taxed at no more than 25%), so
        # ``tax_cap_adjustment`` (the engine's correction of the full-bracket tax) is a memo.
        return self.tax_ltcg + self.tax_state + self.tax_1250_est

    @property
    def after_tax_proceeds(self) -> float:
        return self.net_proceeds - self.tax_at_sale


@dataclass(frozen=True)
class MetricLine:
    name: str
    reference_year: int | None
    value: float | None
    noi: float | None
    cap_rate: float | None
    net_yield: float | None
    cash_on_cash: float | None
    after_tax_return: float | None
    held_to: str  # "sale in 2040", "plan end (equity, no sale costs or tax)" or "n/a"


@dataclass(frozen=True)
class RentalReport:
    totals: tuple[YearLine, ...]
    by_property: dict[str, tuple[YearLine, ...]]
    depreciation: dict[str, tuple[DepreciationLine, ...]]
    ledger: dict[str, tuple[LedgerLine, ...]]
    sales: tuple[SaleLine, ...]
    metrics: tuple[MetricLine, ...]
    passive_by_year: tuple[dict[str, float], ...]
    warnings: tuple[str, ...]
    constants: RentalTaxConstants  # the plan-start year's, for the filing status of the first year
    filing: str
    mfs_lived_apart: bool


def last_active_year(totals: Sequence[YearLine]) -> int | None:
    """Last year with any rental figure; the sheet lists no later (all-zero) years."""
    active = [y.year for y in totals if any(abs(v) > 0.005 for v in (
        y.gross_rent, y.operating_expenses, y.interest, y.principal, y.depreciation, y.schedule_e,
        y.schedule_e_to_agi, y.suspended, y.improvements_purchase, y.net_cash, y.sale_net_proceeds))]
    return max(active) if active else None


# ── per-year lines ──────────────────────────────────────────────────────────────
def _property_dicts(row: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(p.get('name')): p for p in (row.get('rental_by_property') or [])}


def year_totals(rows: Sequence[Mapping[str, Any]]) -> tuple[YearLine, ...]:
    out = []
    prev_closing = None
    for r in rows:
        if 'rental_net_cash_flow' not in r:
            continue
        to_agi = _f(r.get('rental_schedule_e_to_agi'))
        closing = _f(r.get('rental_suspended_loss_carryforward'))
        out.append(YearLine(
            year=int(r['year']), name='',
            gross_rent=_f(r.get('rental_gross_rent')), vacancy=_f(r.get('rental_vacancy_loss')),
            operating_expenses=_f(r.get('rental_operating_expenses')),
            interest=_f(r.get('rental_mortgage_interest')), principal=_f(r.get('rental_mortgage_principal')),
            depreciation=_f(r.get('rental_depreciation')), schedule_e=_f(r.get('rental_schedule_e_net')),
            opening_suspended=prev_closing if prev_closing is not None else 0.0, suspended=closing,
            schedule_e_to_agi=to_agi, loss_allowed=max(0.0, -to_agi),
            tax_effect=to_agi * _f(r.get('effective_marginal_rate')),
            improvements_purchase=_f(r.get('rental_improvements')) + _f(r.get('rental_purchase_cash')),
            net_cash=_f(r.get('rental_net_cash_flow')),
            sale_net_proceeds=_f(r.get('rental_sale_net_proceeds')), owned=True))
        prev_closing = closing
    return tuple(out)


def property_lines(rows: Sequence[Mapping[str, Any]], specs: Sequence[RentalSpec]) -> dict[str, tuple[YearLine, ...]]:
    """Per property and year, the same columns as the totals. The Schedule E amount after
    the passive limit follows from the ledger: net Schedule E - opening carryforward +
    closing carryforward (Form 8582: the loss deducted, or the income left after the carryforward)."""
    out: dict[str, list[YearLine]] = {}
    opening = {s.name: s.prior_suspended_loss for s in specs}
    for r in rows:
        if 'rental_net_cash_flow' not in r:
            continue
        emr = _f(r.get('effective_marginal_rate'))
        props = _property_dicts(r)
        for s in specs:
            p = props.get(s.name, {})
            owned = bool(p.get('owned'))
            sched = _f(p.get('schedule_e'))
            closing = _f(p.get('suspended_loss_carryforward')) if owned else opening[s.name]
            to_agi = sched - opening[s.name] + closing if owned else 0.0
            out.setdefault(s.name, []).append(YearLine(
                year=int(r['year']), name=s.name,
                gross_rent=_f(p.get('gross_rent')), vacancy=_f(p.get('vacancy_loss')),
                operating_expenses=_f(p.get('operating_expenses')), interest=_f(p.get('mortgage_interest')),
                principal=_f(p.get('mortgage_principal')), depreciation=_f(p.get('depreciation')),
                schedule_e=sched, opening_suspended=opening[s.name], suspended=closing,
                schedule_e_to_agi=to_agi, loss_allowed=max(0.0, -to_agi), tax_effect=to_agi * emr,
                improvements_purchase=_f(p.get('improvements_cash')) + _f(p.get('purchase_cash')),
                net_cash=_f(p.get('net_cash')) + (min(0.0, _f(p.get('sale_net_proceeds'))) if p.get('sold') else 0.0),
                sale_net_proceeds=max(0.0, _f(p.get('sale_net_proceeds'))) if p.get('sold') else 0.0,
                owned=owned))
            opening[s.name] = closing
    return {k: tuple(v) for k, v in out.items()}


# ── depreciation schedule ───────────────────────────────────────────────────────
def depreciation_schedule(rows: Sequence[Mapping[str, Any]], specs: Sequence[RentalSpec],
                          book: RentalBook) -> dict[str, tuple[DepreciationLine, ...]]:
    out: dict[str, list[DepreciationLine]] = {}
    plan_start = book.plan_start
    recovery = book.constants(plan_start, 'MFJ').recovery_years
    for s in specs:
        assets = s.assets()
        basis_gain = s.cost_basis
        land = (s.loss_basis if s.kind == CONVERTED_HOME else s.cost_basis) * s.land_share
        accumulated = property_accumulated_depreciation(assets, plan_start - 1, recovery)
        for r in rows:
            if 'rental_net_cash_flow' not in r:
                continue
            year = int(r['year'])
            p = _property_dicts(r).get(s.name, {})
            if not p.get('owned'):
                continue
            annual = _f(p.get('depreciation'))
            accumulated += annual
            improvements = sum(amt for y, _m, amt in s.improvements if y <= year)
            depreciable = assets[0].basis + sum(a.basis for a in assets[1:] if a.placed_year <= year)
            sold = bool(p.get('sold'))
            if sold and _f(p.get('accumulated_depreciation')):
                accumulated = _f(p.get('accumulated_depreciation'))
            adjusted = _f(p.get('adjusted_basis')) if sold else basis_gain + improvements - accumulated
            out.setdefault(s.name, []).append(DepreciationLine(
                year=year, name=s.name, depreciable_basis=depreciable, land=land, annual=annual,
                accumulated=accumulated, adjusted_basis=adjusted, sold=sold))
    return {k: tuple(v) for k, v in out.items()}


# ── passive-loss ledger ─────────────────────────────────────────────────────────
def ledger_lines(by_property: Mapping[str, Sequence[YearLine]], rows: Sequence[Mapping[str, Any]]
                 ) -> dict[str, tuple[LedgerLine, ...]]:
    sold_by_year: dict[tuple[str, int], bool] = {}
    for r in rows:
        for name, p in _property_dicts(r).items():
            sold_by_year[(name, int(r['year']))] = bool(p.get('sold'))
    out: dict[str, tuple[LedgerLine, ...]] = {}
    for name, lines in by_property.items():
        led = []
        for y in lines:
            if not y.owned and y.opening_suspended == 0 and y.suspended == 0:
                continue
            current_loss = max(0.0, -y.schedule_e)
            freed = y.opening_suspended + current_loss - y.suspended
            sold = sold_by_year.get((name, y.year), False)
            led.append(LedgerLine(y.year, name, y.opening_suspended, current_loss,
                                  0.0 if sold else max(0.0, freed), max(0.0, freed) if sold else 0.0,
                                  y.suspended))
        out[name] = tuple(led)
    return out


def passive_by_year(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, float], ...]:
    return tuple({
        'year': int(r['year']), 'magi': _f(r.get('rental_passive_magi')),
        'allowance_available': _f(r.get('rental_passive_allowance_available')),
        'allowance_used': _f(r.get('rental_passive_allowance_used')),
        'released': _f(r.get('rental_passive_loss_released')),
        'schedule_e_net': _f(r.get('rental_schedule_e_net')),
        'schedule_e_to_agi': _f(r.get('rental_schedule_e_to_agi')),
        'suspended': _f(r.get('rental_suspended_loss_carryforward')),
    } for r in rows if 'rental_net_cash_flow' in r)


# ── sale analysis ───────────────────────────────────────────────────────────────
def sale_lines(rows: Sequence[Mapping[str, Any]], specs: Sequence[RentalSpec],
               max_1250_rate: float) -> tuple[SaleLine, ...]:
    """``max_1250_rate``: the cap on the rate of unrecaptured section 1250 gain (reference data)."""
    out = []
    kinds = {s.name: s.kind for s in specs}
    for r in rows:
        if 'rental_net_cash_flow' not in r:
            continue
        sold = [p for p in (r.get('rental_by_property') or []) if p.get('sold')]
        if not sold:
            continue
        # A year's tax fields are totals; with several sales in the year they are shared by
        # each sale's taxable gain (a rare case, noted on the sheet).
        weights = [max(0.0, _f(p.get('unrecaptured_1250_gain'))) + max(0.0, _f(p.get('capital_gain'))
                   + _f(p.get('home_sale_capital_gain'))) for p in sold]
        total_w = sum(weights)
        for p, w in zip(sold, weights):
            share = (w / total_w) if total_w > 0 else 1.0 / len(sold)
            conv = kinds.get(str(p.get('name'))) == CONVERTED_HOME
            u1250 = _f(p.get('unrecaptured_1250_gain'))
            if conv:
                price, costs, payoff = _f(r.get('home_sale_gross')), _f(r.get('home_sale_costs')), _f(r.get('home_sale_mort_off'))
                ltcg_gain = _f(p.get('home_sale_capital_gain'))
                tax_ltcg = _f(r.get('home_sale_tax'))
                net = _f(r.get('home_sale_net'))
            else:
                price, costs, payoff = _f(p.get('sale_price')), _f(p.get('selling_costs')), _f(p.get('loan_payoff'))
                ltcg_gain = _f(p.get('capital_gain'))
                tax_ltcg = _f(r.get('rental_sale_ltcg_tax')) * share
                net = _f(p.get('sale_net_proceeds'))
            tax_1250 = max(0.0, u1250 * min(max_1250_rate, max(0.0, _marginal_ordinary(r)))) if u1250 > 0 else 0.0
            out.append(SaleLine(
                year=int(r['year']), name=str(p.get('name')), converted=conv, price=price, selling_costs=costs,
                loan_payoff=payoff, adjusted_basis=_f(p.get('adjusted_basis')),
                accumulated_depreciation=_f(p.get('accumulated_depreciation')),
                gain=_f(r.get('home_sale_gain')) if conv else _f(p.get('sale_gain')),  # converted: before the section 121 exclusion
                recapture_1250=u1250, long_term_gain=ltcg_gain,
                sec121_qualifies=p.get('sec121_qualifies') if conv else None,
                sec121_excluded=_f(p.get('sec121_excluded')),
                tax_ltcg=tax_ltcg, tax_cap_adjustment=_f(r.get('rental_sale_1250_cap_adjustment')) * share,
                tax_state=_f(r.get('rental_sale_state_tax_on_ltcg')) * share, tax_1250_est=tax_1250, net_proceeds=net))
    return tuple(out)


def _marginal_ordinary(row: Mapping[str, Any]) -> float:
    """The year's ordinary marginal rate, for the estimate of the tax on the section 1250 gain.
    ``effective_marginal_rate`` includes the Social Security and NIIT effects, so it is an
    upper bound; the 25% cap applies on top."""
    return _f(row.get('effective_marginal_rate'))


# ── metrics ─────────────────────────────────────────────────────────────────────
def irr(flows: Sequence[float]) -> float | None:
    """Annual internal rate of return of ``flows`` (first is time 0), by bisection; None
    when there is no sign change or no root in (-90%, 1000%)."""
    if not flows or not (any(f < 0 for f in flows) and any(f > 0 for f in flows)):
        return None

    def npv(rate: float) -> float:
        return sum(f / (1.0 + rate) ** i for i, f in enumerate(flows))

    lo, hi = -0.9, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-9:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def metric_lines(rows: Sequence[Mapping[str, Any]], specs: Sequence[RentalSpec],
                 by_property: Mapping[str, Sequence[YearLine]], sales: Sequence[SaleLine]) -> tuple[MetricLine, ...]:
    rental_rows = [r for r in rows if 'rental_net_cash_flow' in r]
    sale_by_name = {s.name: s for s in sales}
    out = []
    for s in specs:
        lines = by_property.get(s.name, ())
        val_by_year = {int(r['year']): _f(_property_dicts(r).get(s.name, {}).get('value')) for r in rental_rows}
        loan_by_year = {int(r['year']): _f(_property_dicts(r).get(s.name, {}).get('loan_balance')) for r in rental_rows}
        in_service = [y for y in lines if y.owned and y.gross_rent > 0 and y.year not in
                      {sl.year for sl in sales if sl.name == s.name}]
        ref = None
        if in_service:
            first = in_service[0]
            partial = first.year in (s.placed_year, s.purchase_year) and first.year > rental_rows[0]['year']
            ref = in_service[1] if partial and len(in_service) > 1 else first
        if ref is None:
            out.append(MetricLine(s.name, None, None, None, None, None, None, None, 'n/a'))
            continue
        value = val_by_year.get(ref.year) or (s.value_at_conversion if s.kind == CONVERTED_HOME else 0.0)
        noi = ref.collected - ref.operating_expenses
        loan = loan_by_year.get(ref.year, 0.0)
        equity = value - loan
        cap = noi / value if value > 0 else None
        net_yield = (noi - ref.interest) / value if value > 0 else None
        # A converted home's loan is the home's mortgage (not in the rental book), so there
        # is no equity base for cash-on-cash.
        coc = (noi - ref.debt_service) / equity if equity > 0 and s.kind != CONVERTED_HOME else None
        out.append(MetricLine(s.name, ref.year, value, noi, cap, net_yield, coc,
                              *_hold_to_sale_return(s, rows, lines, sale_by_name.get(s.name), val_by_year, loan_by_year)))
    return tuple(out)


def _hold_to_sale_return(s: RentalSpec, rows: Sequence[Mapping[str, Any]], lines: Sequence[YearLine],
                         sale: SaleLine | None, val_by_year: Mapping[int, float],
                         loan_by_year: Mapping[int, float]) -> tuple[float | None, str]:
    """Annual IRR of the owner's cash: the equity at the plan start (0 for a future purchase,
    whose down payment is in the cash flows), each year's rental cash flow after the estimated
    tax effect of Schedule E, and either the after-tax sale proceeds or, held to the plan end,
    the equity at the end (no selling costs or tax). Not computed for a converted home."""
    if s.kind == CONVERTED_HOME:
        return None, 'n/a (converted home: see the sale analysis)'
    first_year = int(rows[0]['year'])
    owned_at_start = s.purchase_year <= first_year
    equity0 = (s.current_value - s.loan_balance) if owned_at_start else 0.0
    flows = [-equity0 if owned_at_start else 0.0]
    for y in lines:
        if not y.owned:
            flows.append(0.0)
            continue
        flows.append(y.net_cash - y.tax_effect)
    if sale is not None:
        idx = sale.year - first_year + 1
        if 0 < idx < len(flows):
            flows[idx] += sale.after_tax_proceeds
            flows = flows[:idx + 1]
        held = f'sale in {sale.year}'
    else:
        last = lines[-1].year if lines else first_year
        flows[-1] += val_by_year.get(last, 0.0) - loan_by_year.get(last, 0.0)
        held = 'plan end (equity, no selling costs or tax)'
    return irr(flows), held


# ── warnings ────────────────────────────────────────────────────────────────────
def report_warnings(sales: Sequence[SaleLine], totals: Sequence[YearLine], filing: str,
                    mfs_lived_apart: bool) -> tuple[str, ...]:
    out = []
    ever_limited = [y for y in totals if y.suspended > 0.005]
    if ever_limited:
        peak = max(y.suspended for y in ever_limited)
        out.append(
            f"The passive-activity loss limit suspends rental losses in {len(ever_limited)} year(s) "
            f"(peak carryforward ${peak:,.0f}). A suspended loss only reduces tax in a later year "
            f"with enough rental or other passive income, or when the property is sold.")
    for sl in sales:
        if sl.converted and sl.sec121_qualifies is False:
            out.append(
                f"{sl.name}: the home fails the two-of-five-year ownership-and-use test at its {sl.year} sale, "
                f"so the whole gain is taxable and none of the section 121 exclusion applies.")
        elif sl.converted and sl.sec121_qualifies:
            out.append(
                f"{sl.name}: the home passes the two-of-five-year test at its {sl.year} sale. The exclusion "
                f"never covers the depreciation taken, which is taxed as unrecaptured section 1250 gain.")
    if str(filing).upper() == 'MFS' and not mfs_lived_apart:
        out.append(
            "Married filing separately is assumed to mean the spouses lived together all year, so the "
            "special allowance for rental losses is $0. Turn on the household input 'lived apart all year' if that is wrong.")
    if totals and totals[-1].suspended > 0.005:
        out.append(
            f"${totals[-1].suspended:,.0f} of suspended loss is still unused at the end of the plan "
            f"and gives no tax benefit inside it.")
    return tuple(out)


def build_report(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> RentalReport | None:
    """The report for the run, or None when the feature did not run (off, or no properties)."""
    if not rental_active(rows):
        return None
    book = rental_book_for(dict(c))
    if book is None:
        return None
    specs = book.specs
    totals = year_totals(rows)
    by_prop = property_lines(rows, specs)
    filing = str(rows[0].get('filing') or c.get('filing_status') or 'MFJ')
    constants = book.constants(int(rows[0]['year']), filing)
    sales = sale_lines(rows, specs, constants.unrecaptured_1250_max_rate)
    dep = depreciation_schedule(rows, specs, book)
    led = ledger_lines(by_prop, rows)
    mets = metric_lines(rows, specs, by_prop, sales)
    warns = report_warnings(sales, totals, filing, book.mfs_lived_apart_all_year)
    return RentalReport(totals, by_prop, dep, led, sales, mets, passive_by_year(rows), warns,
                        constants, filing, book.mfs_lived_apart_all_year)
