"""Rental properties in the projection (WP12.2, design 2026-10-05 sections 4, 5 and 8).

Behind the ``rental_property_income`` feature (default off). Off, or with no
``c['rental_properties']``, :func:`rental_book_for` returns ``None`` and the engine
runs exactly as before: no rental row fields, no changed number.

The tax rules are the pure core in ``src/rental_tax.py`` (rules document
``documentation/reference/RENTAL_TAX_RULES.md``). This module is the year loop around
it: one :class:`RentalBook` carries the cross-year state (suspended passive losses, loan
balances, sold flags) and produces, per year,

1. :meth:`RentalBook.year_flows` (income stage): rent, operating expenses, debt service,
   depreciation, Schedule E net per property, the sale of a property in its sale year,
   end-of-year value and loan balance, and the year's net cash;
2. :meth:`RentalBook.passive_result` / :meth:`RentalBook.settle_passive` (AGI stage):
   the passive-activity loss limit for a MAGI the caller computes before passive losses
   (``roth_conversion_and_agi_tax.rental_passive_magi``); ``settle_passive`` commits the
   carryforward, ``passive_result`` only previews it (Roth-conversion sizing).

Input (one dict per property in ``c['rental_properties']``, produced from source rows by
the parse boundary ``src.parsing.rental_properties.parse_rental_properties``, WP12.3).
Amounts are today's dollars unless noted; rates are fractions. Missing keys take the
defaults shown.

======================== ================================================================
``name``                 label (default ``Rental N``)
``kind``                 ``standalone`` (default) or ``converted_home`` (the plan's own
                         home, see "Converted home" below)
``purchase_year``        year bought (default: the plan start year). A year after the plan
                         start is a future purchase: the down payment and closing costs
                         are cash out that year; up to the plan start it is already owned
``purchase_month``       1-12 (default 7)
``purchase_price``       price paid
``closing_costs``        capitalized closing costs (0)
``land_share``           land part of the cost basis (0.20)
``current_value``        value as of ``value_as_of_year`` (default ``purchase_price``)
``value_as_of_year``     default: the plan start year (a future purchase: its year)
``appreciation``         annual value growth (default ``c['home_appr']``)
``monthly_rent``         rent at the plan start year
``vacancy_rate``         share of rent not collected (0)
``rent_growth``          annual (default ``c['inf']``)
``rental_start_year``    default: ``purchase_year``; ``rental_end_year`` (none)
``property_tax``         annual; ``property_tax_growth`` (default ``expense_growth``)
``insurance``, ``hoa``, ``utilities``, ``other_expenses``: annual
``maintenance_pct``, ``management_pct``: share of collected rent
``expense_growth``       annual (default ``c['inf']``)
``loan_balance``         balance at the start of ``loan_balance_year`` (default: the plan
                         start year, or the purchase year for a future purchase); the
                         loan payments start in that year
``loan_rate``            annual rate; ``loan_monthly_payment`` or ``loan_term_years``
                         (remaining term from ``loan_balance_year``, default 30)
``placed_in_service_year`` / ``placed_in_service_month``: default the rental start
                         year, and the purchase month when that is the purchase year
                         (else 1). Depreciation runs only while rented: through
                         ``rental_end_year`` when the rental ends before the sale
``improvements``         list of ``{year, amount, month (7)}``: cash in ``year``, then
                         depreciated as a separate asset (owner decision: month 7)
``active_participation`` True
``prior_suspended_loss`` passive loss carried into the plan start year (0)
``sale_year``            none = kept; ``sale_month`` (7, mid-year: owner decision); ``sale_price`` (default: the
                         value at the start of the sale year); ``selling_cost_pct``
                         (default ``c['home_sell_cost_pct']``)
``overrides``            ``{year: {gross_rent, operating_expenses}}`` replacing the formulas
======================== ================================================================

Converted home (WP12.3, design sections 3, 4.2, 4.5, 4.7, 4.8): one property of kind
``converted_home`` is the plan's current home turned into a rental on the first of
``conversion_month`` (7) of ``conversion_year`` (required). Its value, mortgage, sale year
and sale price stay the home's (``home_val``, the mortgage schedule, ``home_sale_yr``,
``home_sale_px``), so its rental row value and loan balance are 0 (no double count in net
worth). Extra keys: ``value_at_conversion`` (default: the home value projected to the
conversion date) and ``adjusted_basis_at_conversion`` (default: ``home_basis``, else half
the home value, as the home sale does): depreciation basis = the lesser of the two, land
excluded (one land share for both, owner decision); a loss at sale is measured from it
(dual basis). ``purchase_year`` / ``purchase_month`` (default five years before the
conversion, January) is when the home was bought and lived in, for the section 121
two-of-five-year test; residence ends at the conversion. From the conversion, the rented
share of the year of the home's carrying costs (mortgage payment, real-estate tax,
Housing budget utilities, maintenance and other) moves from spending to this property
(:meth:`RentalBook.with_carrying_costs`): interest on Schedule E, principal as debt
service. At the home's planned sale (``sale_month``, 7) the home-sale stage applies the
two-of-five test and depreciation recapture (``home_sale.ConvertedHomeTerms``); an estate
sale at the second death keeps today's step-up and the suspended losses lapse. Loan, sale
and purchase-price keys are ignored for a converted home.

Simplifications (all listed for the WP12.4 assumptions section): the owner split is not
modelled (the property stays in the household through both deaths); a rental-to-personal
change of use is not modelled; married filing separately assumes the spouses lived
together (allowance 0, owner decision 2026-10-13) unless the household input
``c['mfs_lived_apart']`` is true; the MAGI for the passive limit is the
first-pass AGI before the withdrawal cascade, like the engine's other AGI-dependent
deductions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Any, Callable, NamedTuple

from .. import core as _aa
from .home_sale import ConvertedHomeTerms, HomeSaleEconomics, _add_account_flow, _tag_deposit_source
from ..module_catalog import feature_enabled
from ..rental_tax import (
    DepreciableAsset,
    PassiveActivity,
    PassiveLossResult,
    RentalTaxConstants,
    accumulated_depreciation,
    annual_depreciation,
    apply_passive_loss_limits,
    converted_home_depreciable_basis,
    depreciable_basis,
    property_accumulated_depreciation,
    property_depreciation,
    rental_sale,
    rental_tax_constants,
    schedule_e_net,
    section_121_two_of_five,
)

STANDALONE = "standalone"
CONVERTED_HOME = "converted_home"
DEFAULT_LAND_SHARE = 0.20
# Owner decision 2026-10-13: a missing month (improvement, sale, conversion) is mid-year,
# month 7; purchase and placed-in-service months use the same default.
DEFAULT_MONTH = 7
DEFAULT_SALE_MONTH = DEFAULT_MONTH
DEFAULT_LOAN_TERM_YEARS = 30


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int | None = None) -> int | None:
    try:
        return default if value is None or value == "" else int(float(value))
    except (TypeError, ValueError):
        return default


def _month(value: Any, default: int) -> int:
    m = _i(value, default)
    return m if m is not None and 1 <= m <= 12 else default


@dataclass(frozen=True)
class RentalSpec:
    """One standalone property's inputs, normalized from its ``c['rental_properties']`` dict."""

    name: str
    purchase_year: int
    purchase_month: int
    purchase_price: float
    closing_costs: float
    land_share: float
    current_value: float
    value_as_of_year: int
    appreciation: float
    monthly_rent: float
    vacancy_rate: float
    rent_growth: float
    rental_start_year: int
    rental_end_year: int | None
    property_tax: float
    property_tax_growth: float
    fixed_expenses: float  # insurance + HOA + utilities + other, per year
    variable_expense_pct: float  # maintenance + management, share of collected rent
    expense_growth: float
    loan_balance: float
    loan_balance_year: int
    loan_rate: float
    loan_monthly_payment: float
    placed_year: int
    placed_month: int
    improvements: tuple[tuple[int, int, float], ...]  # (year, month, amount)
    active_participation: bool
    prior_suspended_loss: float
    sale_year: int | None
    sale_month: int
    sale_price: float | None
    selling_cost_pct: float
    overrides: dict[int, dict[str, float]]
    # WP12.3, converted home only: purchase_year/month are the conversion date,
    # purchase_price the adjusted basis at conversion.
    kind: str = STANDALONE
    value_at_conversion: float = 0.0
    owned_from: tuple[int, int] = (0, 1)  # (year, month) bought and lived in
    loan_liability_id: str = ''  # H2: the Liabilities row this property's loan is (resolved links only)
    # H3, converted home: the household moves back in on 1st of ``reversion_month`` of ``rental_end_year``.
    moves_back_in: bool = False
    reversion_month: int = DEFAULT_MONTH
    # H4: '' (not set: proceeds to the default account), joint, member_1 or member_2; and member 1's share.
    owner: str = ''
    member_1_share: float | None = None

    @property
    def reversion_date(self) -> date | None:
        """H3: the day the household moves back in (None unless the converted home reverts)."""
        if self.kind != CONVERTED_HOME or not self.moves_back_in or self.rental_end_year is None:
            return None
        return date(self.rental_end_year, self.reversion_month, 1)

    @property
    def cost_basis(self) -> float:
        """Purchase price + capitalized closing costs, land included (basis for gain)."""
        return self.purchase_price + self.closing_costs

    @property
    def loss_basis(self) -> float:
        """Converted home: lesser of value and adjusted basis at conversion, land included."""
        return min(self.value_at_conversion, self.cost_basis)

    def assets(self) -> tuple[DepreciableAsset, ...]:
        if self.kind == CONVERTED_HOME:
            basis = converted_home_depreciable_basis(self.value_at_conversion, self.cost_basis, self.land_share)
        else:
            basis = depreciable_basis(self.purchase_price, self.closing_costs, self.land_share)
        building = DepreciableAsset(basis, self.placed_year, self.placed_month)
        return (building,) + tuple(DepreciableAsset(amt, y, m) for y, m, amt in self.improvements)


def _loan_payment(balance: float, annual_rate: float, term_years: int) -> float:
    n = max(1, term_years) * 12
    r = annual_rate / 12.0
    if balance <= 0:
        return 0.0
    return balance / n if r <= 1e-12 else balance * r / (1 - (1 + r) ** (-n))


def _improvements(raw: dict[str, Any]) -> tuple[tuple[int, int, float], ...]:
    out = []
    for imp in raw.get("improvements") or []:
        if not isinstance(imp, dict):
            continue
        y, amt = _i(imp.get("year")), _f(imp.get("amount"))
        if y is not None and amt > 0:
            out.append((y, _month(imp.get("month"), DEFAULT_MONTH), amt))
    return tuple(out)


def _overrides(raw: dict[str, Any]) -> dict[int, dict[str, float]]:
    out = {}
    for y, ov in (raw.get("overrides") or {}).items():
        if _i(y) is not None and isinstance(ov, dict):
            out[_i(y)] = {k: _f(v) for k, v in ov.items() if k in ("gross_rent", "operating_expenses")}
    return out


def _share_or_none(raw: dict[str, Any]) -> float | None:
    v = raw.get("member_1_share")
    return None if v in (None, "") else min(1.0, max(0.0, _f(v)))


def member_1_share_of(spec: RentalSpec) -> float:
    """H4: member 1's ownership share: Member 1 100%, Member 2 0%, Joint the entered share or 50%."""
    if spec.owner == "member_1":
        return 1.0
    if spec.owner == "member_2":
        return 0.0
    return 0.5 if spec.member_1_share is None else spec.member_1_share


def _linked_payment(link: dict[str, Any], from_year: int) -> float:
    """Monthly payment of a linked Liabilities row, as the liability loop would pay it:
    the stated payment, else level over the years to ``payoff_year``, else interest only."""
    pay = _f(link.get('monthly_payment'))
    if pay > 0:
        return pay
    bal, rate, payoff = _f(link.get('balance')), _f(link.get('interest_rate')), _i(link.get('payoff_year'), 0) or 0
    if payoff >= from_year:
        return _loan_payment(bal, rate, payoff - from_year + 1)
    return bal * rate / 12.0


class LoanLinks(NamedTuple):
    """H2: which Liabilities rows the rental rows use as their loan."""
    standalone: dict[int, dict[str, Any]]  # raw row index -> liability row
    converted: tuple[dict[str, Any], ...]  # liability rows linked to the converted home
    warnings: tuple[str, ...]


def resolve_loan_links(c: dict[str, Any]) -> LoanLinks:
    """Resolve each rental row's ``loan_liability_id``: first claim on a Liabilities row
    wins; an unknown id, a student loan or a second claim warns and leaves the row on its
    own loan fields."""
    raw_rows = [p for p in (c.get('rental_properties') or []) if isinstance(p, dict)]
    libs = {str(li.get('liability_id') or '').strip(): li for li in (c.get('liabilities') or [])
            if str(li.get('liability_id') or '').strip()}
    standalone: dict[int, dict[str, Any]] = {}
    converted: list[dict[str, Any]] = []
    warnings: list[str] = []
    claimed: set[str] = set()
    for i, raw in enumerate(raw_rows):
        lid = str(raw.get('loan_liability_id') or '').strip()
        if not lid:
            continue
        name = str(raw.get('name') or f'Rental {i + 1}')
        li = libs.get(lid)
        if li is None:
            warnings.append(f"{name}: loan '{lid}' not found in Liabilities; using the loan fields on the property")
        elif str(li.get('type') or '') == 'student_loan':
            warnings.append(f"{name}: loan '{lid}' is a student loan, not a property loan; ignored")
        elif lid in claimed:
            warnings.append(f"{name}: loan '{lid}' is already used by another property; using its own loan fields")
        else:
            claimed.add(lid)
            if str(raw.get('kind') or STANDALONE).strip().lower().replace(' ', '_') == CONVERTED_HOME:
                converted.append(li)
            else:
                standalone[i] = li
    return LoanLinks(standalone, tuple(converted), tuple(warnings))


def linked_liability_ids(c: dict[str, Any]) -> frozenset[str]:
    """Ids of Liabilities rows a standalone rental now carries (the general liability loop
    and the opening liability sum skip them). Empty when the feature is off."""
    if not feature_enabled(c, 'rental_property_income'):
        return frozenset()
    return frozenset(str(li.get('liability_id')) for li in resolve_loan_links(c).standalone.values())


def converted_link_interest(links: tuple[dict[str, Any], ...], balances: dict[str, float], year: int) -> float:
    """Full-year interest on the converted home's linked liabilities at their start-of-year
    balances, inside each row's start and payoff years (the liability loop's own window)."""
    total = 0.0
    for li in links:
        bal = _f(balances.get(str(li.get('liability_id')), 0.0))
        start, payoff = _i(li.get('start_year'), 0) or 0, _i(li.get('payoff_year'), 0) or 0
        if bal <= 1e-6 or (start and year < start) or (payoff and year > payoff):
            continue
        total += bal * _f(li.get('interest_rate'))
    return total


def _parse_converted_home(raw: dict[str, Any], index: int, c: dict[str, Any]) -> RentalSpec | None:
    """WP12.3: the plan's home converted to a rental (see the module docstring)."""
    conv_year = _i(raw.get("conversion_year"))
    home_val = _f(c.get("home_val"))
    if conv_year is None or home_val <= 0:
        return None
    plan_start = int(c["plan_start"])
    conv_month = _month(raw.get("conversion_month"), DEFAULT_MONTH)
    appr = _f(c.get("home_appr"), 0.0)
    projected = home_val * (1.0 + appr) ** max(0.0, conv_year - plan_start + (conv_month - 1) / 12.0)
    expense_growth = _f(raw.get("expense_growth"), _f(c.get("inf"), 0.0))
    bought = _i(raw.get("purchase_year"))
    owned_from = (bought, _month(raw.get("purchase_month"), DEFAULT_MONTH)) if bought else (conv_year - 5, 1)
    return RentalSpec(
        name=str(raw.get("name") or f"Rental {index + 1}"),
        purchase_year=conv_year, purchase_month=conv_month,
        purchase_price=_f(raw.get("adjusted_basis_at_conversion"), _f(c.get("home_basis")) or home_val * 0.5),
        closing_costs=0.0,
        land_share=min(1.0, max(0.0, _f(raw.get("land_share"), DEFAULT_LAND_SHARE))),
        current_value=0.0, value_as_of_year=conv_year, appreciation=_f(c.get("home_appr"), 0.0),
        monthly_rent=_f(raw.get("monthly_rent")),
        vacancy_rate=min(1.0, max(0.0, _f(raw.get("vacancy_rate")))),
        rent_growth=_f(raw.get("rent_growth"), _f(c.get("inf"), 0.0)),
        rental_start_year=conv_year, rental_end_year=_i(raw.get("rental_end_year")),
        property_tax=_f(raw.get("property_tax")),
        property_tax_growth=_f(raw.get("property_tax_growth"), expense_growth),
        fixed_expenses=sum(_f(raw.get(k)) for k in ("insurance", "hoa", "utilities", "other_expenses")),
        variable_expense_pct=_f(raw.get("maintenance_pct")) + _f(raw.get("management_pct")),
        expense_growth=expense_growth,
        loan_balance=0.0, loan_balance_year=conv_year, loan_rate=0.0, loan_monthly_payment=0.0,
        placed_year=conv_year, placed_month=conv_month,
        improvements=_improvements(raw),
        active_participation=bool(raw.get("active_participation", True)),
        prior_suspended_loss=max(0.0, _f(raw.get("prior_suspended_loss"))),
        sale_year=None, sale_month=_month(raw.get("sale_month"), DEFAULT_SALE_MONTH), sale_price=None,
        selling_cost_pct=_f(c.get("home_sell_cost_pct"), 0.0),
        overrides=_overrides(raw),
        kind=CONVERTED_HOME,
        value_at_conversion=_f(raw.get("value_at_conversion"), projected),
        owned_from=owned_from,
        moves_back_in=bool(raw.get("moves_back_in")) and _i(raw.get("rental_end_year")) is not None,
        reversion_month=_month(raw.get("reversion_month"), DEFAULT_MONTH),
        owner=str(raw.get("owner") or ""), member_1_share=_share_or_none(raw),
    )


def parse_rental_spec(raw: dict[str, Any], index: int, c: dict[str, Any],
                      link: dict[str, Any] | None = None) -> RentalSpec | None:
    """Normalize one property dict; ``None`` for an unknown kind or a converted home
    without a conversion year or without a home in the plan."""
    kind = str(raw.get("kind") or STANDALONE).strip().lower().replace(" ", "_")
    if kind == CONVERTED_HOME:
        return _parse_converted_home(raw, index, c)
    if kind != STANDALONE:
        return None
    plan_start = int(c["plan_start"])
    purchase_year = _i(raw.get("purchase_year"), plan_start)
    purchase_month = _month(raw.get("purchase_month"), DEFAULT_MONTH)
    price = _f(raw.get("purchase_price"))
    future = purchase_year > plan_start
    expense_growth = _f(raw.get("expense_growth"), _f(c.get("inf"), 0.0))
    loan_balance_year = _i(raw.get("loan_balance_year"), max(plan_start, purchase_year))
    loan_balance = _f(raw.get("loan_balance"))
    loan_rate = _f(raw.get("loan_rate"))
    payment = _f(raw.get("loan_monthly_payment"))
    if payment <= 0 and loan_balance > 0:
        payment = _loan_payment(loan_balance, loan_rate, _i(raw.get("loan_term_years"), DEFAULT_LOAN_TERM_YEARS))
    if link is not None:  # H2: the Liabilities row is the one source of the loan
        loan_balance_year = max(plan_start, purchase_year, int(link.get('start_year') or 0))
        loan_balance = _f(link.get('balance'))
        loan_rate = _f(link.get('interest_rate'))
        payment = _linked_payment(link, loan_balance_year)
    sale_price = raw.get("sale_price")
    rental_start = _i(raw.get("rental_start_year"), purchase_year)
    placed_year = _i(raw.get("placed_in_service_year"), max(rental_start, purchase_year))
    return RentalSpec(
        name=str(raw.get("name") or f"Rental {index + 1}"),
        purchase_year=purchase_year,
        purchase_month=purchase_month,
        purchase_price=price,
        closing_costs=_f(raw.get("closing_costs")),
        land_share=min(1.0, max(0.0, _f(raw.get("land_share"), DEFAULT_LAND_SHARE))),
        current_value=_f(raw.get("current_value"), price),
        value_as_of_year=_i(raw.get("value_as_of_year"), purchase_year if future else plan_start),
        appreciation=_f(raw.get("appreciation"), _f(c.get("home_appr"), 0.0)),
        monthly_rent=_f(raw.get("monthly_rent")),
        vacancy_rate=min(1.0, max(0.0, _f(raw.get("vacancy_rate")))),
        rent_growth=_f(raw.get("rent_growth"), _f(c.get("inf"), 0.0)),
        rental_start_year=rental_start,
        rental_end_year=_i(raw.get("rental_end_year")),
        property_tax=_f(raw.get("property_tax")),
        property_tax_growth=_f(raw.get("property_tax_growth"), expense_growth),
        fixed_expenses=sum(_f(raw.get(k)) for k in ("insurance", "hoa", "utilities", "other_expenses")),
        variable_expense_pct=_f(raw.get("maintenance_pct")) + _f(raw.get("management_pct")),
        expense_growth=expense_growth,
        loan_balance=loan_balance,
        loan_balance_year=loan_balance_year,
        loan_rate=loan_rate,
        loan_monthly_payment=payment,
        placed_year=placed_year,
        placed_month=_month(raw.get("placed_in_service_month"),
                            purchase_month if placed_year == purchase_year else 1),
        improvements=_improvements(raw),
        active_participation=bool(raw.get("active_participation", True)),
        prior_suspended_loss=max(0.0, _f(raw.get("prior_suspended_loss"))),
        sale_year=_i(raw.get("sale_year")),
        sale_month=_month(raw.get("sale_month"), DEFAULT_SALE_MONTH),
        sale_price=None if sale_price in (None, "") else _f(sale_price),
        selling_cost_pct=_f(raw.get("selling_cost_pct"), _f(c.get("home_sell_cost_pct"), 0.0)),
        overrides=_overrides(raw),
        loan_liability_id=str(link.get('liability_id') or '') if link is not None else '',
        owner=str(raw.get("owner") or ""), member_1_share=_share_or_none(raw),
    )


@dataclass
class _PropertyState:
    suspended: float
    loan_balance: float
    sold: bool = False


@dataclass(frozen=True)
class PropertyYear:
    """One property's figures for one year (zeros when not owned)."""

    name: str
    owned: bool
    in_service: bool
    gross_rent: float
    vacancy_loss: float
    operating_expenses: float
    mortgage_interest: float
    mortgage_principal: float
    depreciation: float
    schedule_e: float  # net income (+) / loss (-) before the passive limit
    improvements_cash: float
    purchase_cash: float  # down payment + closing costs in a plan-year purchase
    net_cash: float  # rent collected - expenses - debt service - improvements - purchase cash
    value: float  # end of year (0 once sold)
    loan_balance: float  # end of year
    sold: bool = False
    sale_price: float = 0.0
    selling_costs: float = 0.0
    loan_payoff: float = 0.0
    adjusted_basis: float = 0.0
    accumulated_depreciation: float = 0.0
    sale_gain: float = 0.0
    unrecaptured_1250_gain: float = 0.0
    capital_gain: float = 0.0
    ordinary_loss: float = 0.0
    sale_net_proceeds: float = 0.0  # price - selling costs - loan payoff (may be < 0)
    # WP12.3, converted home sold through the home-sale stage: its LTCG after the
    # section 121 exclusion is taxed there (``capital_gain`` stays 0), price,
    # costs and proceeds are on the ``home_sale_*`` row fields.
    kind: str = STANDALONE
    home_sale_capital_gain: float = 0.0
    sec121_excluded: float = 0.0
    sec121_qualifies: bool | None = None
    # H5, death year only: the decedent's suspended loss allowed on the final return, the part
    # lost for good, the whole decedent share removed from the passive ledger, and the basis change.
    death_loss_released: float = 0.0
    death_loss_lost: float = 0.0
    death_suspended_removed: float = 0.0
    death_basis_change: float = 0.0


DEATH_KEYS = ("death_loss_released", "death_loss_lost", "death_suspended_removed", "death_basis_change")


class _Seg(NamedTuple):
    """H5: a slice of a depreciable asset: its basis, when placed in service, and when it
    left the decedent's hands (year, month) or None while it is still depreciated."""
    basis: float
    placed_year: int
    placed_month: int
    off_year: int | None = None
    off_month: int | None = None


class DeathEvent(NamedTuple):
    """H5: a death that steps up the basis of the decedent's ``fraction`` of a property."""
    year: int
    fraction: float
    fmv: float
    adjusted_basis: float  # whole property, before the step
    delta_basis: float  # fraction x (fmv - adjusted basis); negative = step-down
    basis_after: float  # cost + improvements basis after the step


class RentalYear(NamedTuple):
    year: int
    properties: tuple[PropertyYear, ...]
    activities: tuple[PassiveActivity, ...]

    def total(self, attr: str) -> float:
        return sum(getattr(p, attr) for p in self.properties)


@dataclass
class RentalBook:
    """Cross-year rental state for one projection run."""

    specs: tuple[RentalSpec, ...]
    plan_start: int
    mfs_lived_apart_all_year: bool = False  # owner decision 2026-10-13: unknown = lived together
    _state: dict[str, _PropertyState] = field(default_factory=dict)
    _constants: dict[tuple[int, str], RentalTaxConstants] = field(default_factory=dict)
    # WP12.3 converted home: the home-sale year and its economics, and the last
    # year rented after an estate sale (no gain, see the module docstring).
    _converted_sale: tuple[int, HomeSaleEconomics] | None = None
    _converted_last_year: int | None = None
    # H2: Liabilities rows linked to the converted home, and the link warnings.
    converted_links: tuple[dict[str, Any], ...] = ()
    link_warnings: tuple[str, ...] = ()
    # H5: the household's deaths (first only for a couple dying in different years), who died first
    # (1 or 2) and whether joint property is community property (both halves stepped up).
    first_death_year: int | None = None
    second_death_year: int | None = None
    first_decedent: int = 1
    community: bool = False
    _walks: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for s in self.specs:
            self._state[s.name] = _PropertyState(suspended=s.prior_suspended_loss,
                                                 loan_balance=s.loan_balance)

    # ── constants ───────────────────────────────────────────────────────
    def constants(self, year: int, filing: str) -> RentalTaxConstants:
        key = (int(year), str(filing))
        if key not in self._constants:
            from ..tax_law import default_tax_law_dataset
            self._constants[key] = rental_tax_constants(
                default_tax_law_dataset(), year, str(filing),
                mfs_lived_apart_all_year=self.mfs_lived_apart_all_year)
        return self._constants[key]

    # ── stage 1: the year's flows (income stage) ────────────────────────
    def year_flows(self, year: int) -> RentalYear:
        # The recovery period is one row for every filing status.
        recovery = self.constants(year, "MFJ").recovery_years
        props, acts = [], []
        for s in self.specs:
            st = self._state[s.name]
            if s.kind == CONVERTED_HOME:
                py = self._converted_year(s, st, year, recovery)
            else:
                py = self._property_year(s, st, year, recovery)
            props.append(py)
            act = self._activity(s, st, py)
            if act is not None:
                acts.append(act)
        return RentalYear(year, tuple(props), tuple(acts))

    @staticmethod
    def _activity(s: RentalSpec, st: _PropertyState, py: PropertyYear) -> PassiveActivity | None:
        if not (py.in_service or py.sold or st.suspended > 0 and py.owned):
            return None
        return PassiveActivity(
            name=s.name, net_income=py.schedule_e, prior_suspended=st.suspended - py.death_suspended_removed,
            active_participation=s.active_participation, fully_disposed=py.sold,
            disposition_gain=max(0.0, py.sale_gain) if py.sold else 0.0)

    # ── converted home (WP12.3) ─────────────────────────────────────────
    def converted_spec(self) -> RentalSpec | None:
        return next((s for s in self.specs if s.kind == CONVERTED_HOME), None)

    @staticmethod
    def _converted_by(s: RentalSpec, year: int) -> bool:
        """The conversion date falls before a sale in ``year`` (at ``sale_month``)."""
        return year > s.placed_year or (year == s.placed_year and s.sale_month > s.placed_month)

    def _rent_window(self, s: RentalSpec, year: int) -> tuple[int, int] | None:
        """(first, last) month the converted home is rented in ``year``, or None."""
        st = self._state[s.name]
        if st.sold or year < s.placed_year or (s.rental_end_year is not None and year > s.rental_end_year):
            return None
        if self._converted_last_year is not None and year > self._converted_last_year:
            return None
        first = s.placed_month if year == s.placed_year else 1
        selling = self._converted_sale is not None and self._converted_sale[0] == year
        last = s.sale_month if selling else 12
        if s.reversion_date is not None and year == s.rental_end_year:
            last = min(last, s.reversion_month - 1)  # H3: rented until the month before the move-back
        return (first, last) if last >= first else None

    def converted_home_share(self, year: int) -> float:
        """Share of ``year`` the plan's home is rented (0 without a converted home): the
        part of its carrying costs the spending stage moves to Schedule E."""
        s = self.converted_spec()
        win = None if s is None else self._rent_window(s, year)
        return 0.0 if win is None else (win[1] - win[0] + 1) / 12.0

    def converted_home_sale_terms(self, year: int, filing: str) -> ConvertedHomeTerms | None:
        """What a sale of the plan's home in ``year`` needs for the converted-home rules
        (depreciation recapture, dual basis, section 121 two-of-five test), or None when
        there is no converted home or the sale comes before the conversion."""
        s = self.converted_spec()
        if s is None or self._state[s.name].sold or not self._converted_by(s, year):
            return None
        recovery = self.constants(year, "MFJ").recovery_years
        dep_through = year if s.rental_end_year is None else min(year, s.rental_end_year)
        sale_date = date(year, s.sale_month, 1)
        rev = s.reversion_date
        moved_back = rev is not None and rev < sale_date  # H3: back in before the sale
        if moved_back:
            stop = s.reversion_month if dep_through == rev.year else None
        else:
            stop = s.sale_month if dep_through == year else None
        accumulated = property_accumulated_depreciation(s.assets(), dep_through, recovery, disposed_month=stop)
        k = self.constants(year, filing)
        owned_from = date(s.owned_from[0], s.owned_from[1], 1)
        conversion = date(s.placed_year, s.placed_month, 1)
        residence = [(owned_from, conversion)] + ([(rev, sale_date)] if moved_back else [])
        qualifies = section_121_two_of_five(
            sale_date, owned_from, residence,
            required_days=k.section_121_required_days, lookback_years=k.section_121_lookback_years)
        owned_days = (sale_date - owned_from).days
        ratio = (rev - conversion).days / owned_days if moved_back and owned_days > 0 else 0.0
        return ConvertedHomeTerms(
            accumulated_depreciation=accumulated,
            improvements=sum(amt for y, _m, amt in s.improvements if y <= year),
            loss_basis=s.loss_basis, qualifies=qualifies, nonqualified_ratio=ratio)

    def record_home_sale(self, year: int, economics: HomeSaleEconomics | None) -> None:
        """The plan's home left the household in ``year`` (home-sale stage, before the
        year's flows). A converted-home sale carries its economics; an estate sale after
        the conversion ends the rental this year; a sale before the conversion means it
        never happens."""
        s = self.converted_spec()
        if s is None:
            return
        if economics is not None and economics.converted is not None:
            self._converted_sale = (year, economics)
        elif self._converted_by(s, year):
            self._converted_last_year = year
        else:
            self._state[s.name].sold = True

    @staticmethod
    def _dep_stop_month(s: RentalSpec, year: int, selling: bool) -> int | None:
        """Month depreciation of the converted home stops in ``year`` (mid-month disposal
        convention): the sale month, or the move-back month when the household moves back
        in (H3) before any sale that year; None for a full year."""
        rev = s.reversion_date
        if rev is not None and year == rev.year and not (selling and s.sale_month < s.reversion_month):
            return s.reversion_month
        return s.sale_month if selling else None

    def _converted_estate(self, s: RentalSpec, st: _PropertyState, year: int, recovery: float) -> dict[str, float]:
        """H5: the estate sale of the converted home at the second death (the last year rented): the
        suspended loss is allowed on the final return only to the extent it exceeds the step-up of the
        home to fair market value (IRC 469(g)(2)); it no longer simply lapses. Owner set only."""
        if not s.owner or self._converted_last_year != year or st.sold or st.suspended <= 0:
            return {}
        fmv = s.value_at_conversion * (1.0 + s.appreciation) ** (year + 0.5 - s.placed_year - (s.placed_month - 1) / 12.0)
        improvements = sum(amt for y, _m, amt in s.improvements if y <= year)
        accumulated = property_accumulated_depreciation(s.assets(), year, recovery, disposed_month=DEFAULT_MONTH)
        delta = fmv - (s.cost_basis + improvements - accumulated)
        allowed = max(0.0, st.suspended - max(0.0, delta))
        return {"death_suspended_removed": st.suspended, "death_loss_released": allowed,
                "death_loss_lost": st.suspended - allowed, "death_basis_change": delta}

    def _converted_year(self, s: RentalSpec, st: _PropertyState, year: int, recovery: float) -> PropertyYear:
        win = self._rent_window(s, year)
        selling = self._converted_sale is not None and self._converted_sale[0] == year and not st.sold
        if win is None and not selling:
            return PropertyYear(s.name, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                kind=s.kind)
        gross_rent = opex = depreciation = sched_e = improvements_cash = collected = 0.0
        if win is not None:
            n = year - self.plan_start
            frac = (win[1] - win[0] + 1) / 12.0
            ov = s.overrides.get(year, {})
            gross_rent = ov.get("gross_rent", s.monthly_rent * 12.0 * (1.0 + s.rent_growth) ** n * frac)
            collected = gross_rent * (1.0 - s.vacancy_rate)
            opex = ov.get("operating_expenses", (
                s.property_tax * (1.0 + s.property_tax_growth) ** n * frac
                + s.fixed_expenses * (1.0 + s.expense_growth) ** n * frac
                + s.variable_expense_pct * collected))
            depreciation = property_depreciation(s.assets(), year, recovery,
                                                 disposed_month=self._dep_stop_month(s, year, selling))
            sched_e = schedule_e_net(gross_rent, s.vacancy_rate, opex, 0.0, depreciation)
            improvements_cash = sum(amt for y, _m, amt in s.improvements if y == year)
        net_cash = collected - opex - improvements_cash
        death = self._converted_estate(s, st, year, recovery) if win is not None else {}
        base = dict(name=s.name, owned=True, in_service=win is not None, gross_rent=gross_rent, **death,
                    vacancy_loss=gross_rent - collected, operating_expenses=opex, mortgage_interest=0.0,
                    mortgage_principal=0.0, depreciation=depreciation, schedule_e=sched_e,
                    improvements_cash=improvements_cash, purchase_cash=0.0, net_cash=net_cash,
                    value=0.0, loan_balance=0.0, kind=s.kind)
        if not selling:
            return PropertyYear(**base)
        econ = self._converted_sale[1]
        terms = econ.converted
        recognized = econ.unrecaptured_1250_gain + econ.taxable_gain - econ.ordinary_loss
        return PropertyYear(
            **base, sold=True, accumulated_depreciation=terms.accumulated_depreciation,
            adjusted_basis=econ.adjusted_basis, sale_gain=recognized,
            unrecaptured_1250_gain=econ.unrecaptured_1250_gain, ordinary_loss=econ.ordinary_loss,
            home_sale_capital_gain=econ.taxable_gain, sec121_excluded=econ.sec121_excluded,
            sec121_qualifies=terms.qualifies)

    def with_carrying_costs(self, ry: RentalYear, costs: dict[str, float] | None,
                            mortgage_interest: float, linked_interest: float = 0.0) -> RentalYear:
        """``ry`` with the converted home's share of the home's carrying costs (moved out
        of spending by ``spending_and_rmd``) added: real-estate tax, utilities,
        maintenance and other as operating expenses, the mortgage payment as debt service
        split into ``mortgage_interest`` (deductible, at most the payment) and principal.
        ``linked_interest`` (H2) is interest on Liabilities rows linked to the home: a
        deduction only, its payment stays in the liability loop (no cash moves)."""
        s = self.converted_spec()
        if s is None or not costs:
            return ry
        payment = float(costs.get("mortgage_payment", 0.0))
        interest = min(payment, max(0.0, mortgage_interest))
        added = sum(float(costs.get(k, 0.0)) for k in ("real_estate_tax", "utilities", "maintenance", "other"))
        props, acts = [], []
        for p in ry.properties:
            if p.name == s.name and p.in_service:
                p = replace(p, operating_expenses=p.operating_expenses + added,
                            mortgage_interest=p.mortgage_interest + interest,
                            mortgage_principal=p.mortgage_principal + payment - interest,
                            schedule_e=p.schedule_e - added - interest, net_cash=p.net_cash - added - payment)
                if linked_interest:
                    p = replace(p, mortgage_interest=p.mortgage_interest + linked_interest,
                                schedule_e=p.schedule_e - linked_interest)
            props.append(p)
        for spec in self.specs:
            py = next(p for p in props if p.name == spec.name)
            act = self._activity(spec, self._state[spec.name], py)
            if act is not None:
                acts.append(act)
        return RentalYear(ry.year, tuple(props), tuple(acts))

    # ── H5: death handling ──────────────────────────────────────────────
    def _decedent_fraction(self, s: RentalSpec, member: int) -> float:
        """The share of ``s`` that member (1 or 2) owns and that a death steps up: sole owner 1 or 0;
        joint: both halves in a community-property regime, else the member's ownership share."""
        m1 = member_1_share_of(s)
        if s.owner == "joint" and self.community:
            return 1.0
        return m1 if member == 1 else 1.0 - m1

    def _death_schedule(self, s: RentalSpec) -> list[tuple[int, float]]:
        """(year, fraction stepped up) for each death that hits ``s``: only a standalone property
        with an owner set, between its purchase and its sale. After a first death the survivor owns
        all that is left, so the second death steps up all of it."""
        if not s.owner or s.kind != STANDALONE:
            return []
        out: list[tuple[int, float]] = []
        if self.first_death_year is not None:
            f = self._decedent_fraction(s, self.first_decedent)
            if f > 1e-12:
                out.append((self.first_death_year, f))
        if self.second_death_year is not None:
            out.append((self.second_death_year, 1.0))
        return [(y, f) for y, f in out
                if y >= s.purchase_year and (s.sale_year is None or y < s.sale_year)]

    def _walk(self, s: RentalSpec) -> tuple[tuple[DeathEvent, ...], tuple[_Seg, ...]]:
        """The death events of ``s`` in order and the depreciable slices they leave: each live
        slice is split into the decedent's part (off the books in the death year, its depreciation
        erased) and the survivor's part (same schedule); the decedent's part of fair market value
        becomes a new asset placed in service at the death (month 7), land excluded."""
        if s.name in self._walks:
            return self._walks[s.name]
        schedule = self._death_schedule(s)
        segs = [_Seg(a.basis, a.placed_year, a.placed_month) for a in s.assets()]
        events: list[DeathEvent] = []
        recovery = self.constants(s.purchase_year, "MFJ").recovery_years
        basis = s.cost_basis
        added_through = s.purchase_year - 1
        for year, f in schedule:
            basis += sum(amt for y, _m, amt in s.improvements if added_through < y <= year)
            added_through = year
            accumulated = sum(accumulated_depreciation(g.basis, g.placed_year, g.placed_month, year, recovery,
                                                        disposed_month=DEFAULT_MONTH)
                              for g in segs if g.off_year is None and g.placed_year <= year)
            fmv = self._value_eoy(s, year - 1) * (1.0 + s.appreciation) ** 0.5
            adjusted = basis - accumulated
            delta = f * (fmv - adjusted)
            basis = basis * (1.0 - f) + f * fmv
            new: list[_Seg] = []
            for g in segs:
                if g.off_year is not None or g.placed_year > year:
                    new.append(g)
                    continue
                new.append(_Seg(g.basis * (1.0 - f), g.placed_year, g.placed_month))
                if f > 0:
                    new.append(_Seg(g.basis * f, g.placed_year, g.placed_month, year, DEFAULT_MONTH))
            if f > 0:
                new.append(_Seg(f * fmv * (1.0 - s.land_share), year, DEFAULT_MONTH))
            segs = new
            events.append(DeathEvent(year, f, fmv, adjusted, delta, basis))
        self._walks[s.name] = (tuple(events), tuple(segs))
        return self._walks[s.name]

    def _depreciation(self, s: RentalSpec, year: int, recovery: float, disposed_month: int | None) -> float:
        events, segs = self._walk(s)
        if not events:
            return property_depreciation(s.assets(), year, recovery, disposed_month=disposed_month)
        total = 0.0
        for g in segs:
            if g.off_year is not None and year > g.off_year:
                continue
            dm = g.off_month if g.off_year == year else disposed_month
            if g.off_year == year and disposed_month is not None:
                dm = min(dm, disposed_month)
            if dm is not None and g.placed_year == year and dm < g.placed_month:
                continue
            total += annual_depreciation(g.basis, g.placed_year, g.placed_month, year, recovery, disposed_month=dm)
        return total

    def _accumulated(self, s: RentalSpec, through_year: int, recovery: float, disposed_month: int | None) -> float:
        """Depreciation still on the books (the decedent's part is erased) through ``through_year``."""
        events, segs = self._walk(s)
        if not events:
            return property_accumulated_depreciation(s.assets(), through_year, recovery, disposed_month=disposed_month)
        total = 0.0
        for g in segs:
            if g.off_year is not None or g.placed_year > through_year:
                continue
            total += accumulated_depreciation(g.basis, g.placed_year, g.placed_month, through_year, recovery,
                                              disposed_month=disposed_month)
        return total

    def _sale_basis(self, s: RentalSpec, year: int) -> tuple[float, float]:
        """(cost basis, improvements) for the gain at a sale in ``year``: after a death the stepped
        basis (improvements are inside it)."""
        events = [e for e in self._walk(s)[0] if e.year <= year]
        if not events:
            return s.cost_basis, sum(amt for y, _m, amt in s.improvements if y <= year)
        last = events[-1]
        return last.basis_after, sum(amt for y, _m, amt in s.improvements if last.year < y <= year)

    def _death_in(self, s: RentalSpec, st: _PropertyState, year: int) -> dict[str, float]:
        """H5 fields for ``year`` if a death steps up ``s`` in it: the decedent's share of the
        suspended loss, how much is allowed on the final return (the excess over the basis
        increase, IRC 469(g)(2)), how much is lost, and the basis change."""
        event = next((e for e in self._walk(s)[0] if e.year == year), None)
        if event is None or st.sold:
            return {}
        share = st.suspended * event.fraction
        allowed = max(0.0, share - max(0.0, event.delta_basis))
        return {"death_suspended_removed": share, "death_loss_released": allowed,
                "death_loss_lost": share - allowed, "death_basis_change": event.delta_basis}

    def _value_eoy(self, s: RentalSpec, year: int) -> float:
        years = year - s.value_as_of_year + 1
        if s.purchase_year > self.plan_start and s.value_as_of_year == s.purchase_year:
            years -= s.purchase_month / 12.0  # a future purchase grows from its purchase month
        return s.current_value * (1.0 + s.appreciation) ** max(0.0, years)

    def _property_year(self, s: RentalSpec, st: _PropertyState, year: int, recovery: float) -> PropertyYear:
        if st.sold or year < s.purchase_year or (s.sale_year is not None and year > s.sale_year):
            return PropertyYear(s.name, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        selling = s.sale_year == year
        # Months owned this year: from the purchase month in a plan-year purchase, to the
        # sale month in the sale year.
        first_month = s.purchase_month if year == s.purchase_year and year > self.plan_start else 1
        last_month = s.sale_month if selling else 12
        owned_frac = max(0, last_month - first_month + 1) / 12.0
        in_service = (s.rental_start_year <= year
                      and (s.rental_end_year is None or year <= s.rental_end_year)
                      and year >= s.placed_year)
        n = year - self.plan_start
        ov = s.overrides.get(year, {})
        if in_service:
            start_month = max(first_month, s.placed_month) if year == s.placed_year else first_month
            rent_frac = max(0, last_month - start_month + 1) / 12.0
            gross_rent = ov.get("gross_rent", s.monthly_rent * 12.0 * (1.0 + s.rent_growth) ** n * rent_frac)
        else:
            gross_rent = 0.0
        collected = gross_rent * (1.0 - s.vacancy_rate)
        opex = ov.get("operating_expenses", (
            s.property_tax * (1.0 + s.property_tax_growth) ** n * owned_frac
            + s.fixed_expenses * (1.0 + s.expense_growth) ** n * owned_frac
            + s.variable_expense_pct * collected))
        # Loan payments start the month after a plan-year purchase closes.
        pay_from = first_month + 1 if year == s.purchase_year and year > self.plan_start else first_month
        interest, principal = self._amortize(s, st, year, pay_from, last_month)
        disposed_month = s.sale_month if selling else None
        depreciation = self._depreciation(s, year, recovery, disposed_month) if in_service else 0.0
        sched_e = schedule_e_net(gross_rent, s.vacancy_rate, opex, interest, depreciation) if in_service else 0.0
        improvements_cash = sum(amt for y, _m, amt in s.improvements if y == year)
        purchase_cash = 0.0
        if year == s.purchase_year and year > self.plan_start:
            purchase_cash = s.purchase_price + s.closing_costs - s.loan_balance
        net_cash = collected - opex - interest - principal - improvements_cash - purchase_cash
        death = self._death_in(s, st, year)
        if not selling:
            return PropertyYear(s.name, True, in_service, gross_rent, gross_rent - collected, opex, interest,
                                principal, depreciation, sched_e, improvements_cash, purchase_cash, net_cash,
                                self._value_eoy(s, year), st.loan_balance, **death)
        # ── sale year ──
        price = s.sale_price if s.sale_price is not None else self._value_eoy(s, year - 1)
        selling_costs = price * s.selling_cost_pct
        # Allowed or allowable while rented: through the sale, or through the
        # last rental year when the rental ended earlier.
        dep_through = year if s.rental_end_year is None else min(year, s.rental_end_year)
        accumulated = self._accumulated(
            s, dep_through, recovery, s.sale_month if dep_through == year else None)
        cost_basis, improvements_total = self._sale_basis(s, year)
        sale = rental_sale(price, selling_costs, cost_basis, improvements_total, accumulated)
        payoff = st.loan_balance
        st.loan_balance = 0.0
        proceeds = price - selling_costs - payoff
        return PropertyYear(
            s.name, True, in_service, gross_rent, gross_rent - collected, opex, interest, principal,
            depreciation, sched_e, improvements_cash, purchase_cash, net_cash, 0.0, 0.0,
            sold=True, sale_price=price, selling_costs=selling_costs, loan_payoff=payoff,
            adjusted_basis=sale.adjusted_basis, accumulated_depreciation=accumulated,
            sale_gain=sale.gain, unrecaptured_1250_gain=sale.unrecaptured_1250_gain,
            capital_gain=sale.capital_gain, ordinary_loss=sale.ordinary_loss, sale_net_proceeds=proceeds)

    def _amortize(self, s: RentalSpec, st: _PropertyState, year: int, first_month: int,
                  last_month: int) -> tuple[float, float]:
        """Interest and principal paid this year (monthly), reducing the carried balance."""
        if year < s.loan_balance_year or st.loan_balance <= 0:
            return 0.0, 0.0
        r = s.loan_rate / 12.0
        interest = principal = 0.0
        bal = st.loan_balance
        for _ in range(max(0, last_month - first_month + 1)):
            if bal <= 1e-9:
                break
            i = bal * r
            p = min(bal, max(0.0, s.loan_monthly_payment - i))
            interest += i
            principal += p
            bal -= p
        st.loan_balance = max(0.0, bal)
        return interest, principal

    # ── stage 2: passive-loss limit (AGI stage) ─────────────────────────
    def passive_result(self, ry: RentalYear, magi: float, filing: str) -> PassiveLossResult:
        """The passive-activity limit for ``magi`` (computed before passive losses). Pure:
        does not move the carryforward (used for the Roth-conversion sizing preview)."""
        return apply_passive_loss_limits(ry.activities, magi, self.constants(ry.year, filing))

    def settle_passive(self, ry: RentalYear, magi: float, filing: str) -> PassiveLossResult:
        """:meth:`passive_result`, then carry each property's suspended loss to next year
        and mark sold properties."""
        res = self.passive_result(ry, magi, filing)
        by_name = {a.name: a for a in res.activities}
        for p in ry.properties:
            st = self._state[p.name]
            if p.name in by_name:
                st.suspended = by_name[p.name].suspended
            if p.sold:
                st.sold = True
                st.suspended = 0.0
        return res


def rental_book_for(c: dict[str, Any]) -> RentalBook | None:
    """The run's :class:`RentalBook`, or ``None`` when the feature is off or no
    standalone property is entered (the engine then skips every rental step)."""
    if not feature_enabled(c, 'rental_property_income'):
        return None
    raw = [p for p in (c.get('rental_properties') or []) if isinstance(p, dict)]
    links = resolve_loan_links(c)
    specs = tuple(s for s in (parse_rental_spec(p, i, c, links.standalone.get(i)) for i, p in enumerate(raw))
                  if s is not None)
    converted = [s for s in specs if s.kind == CONVERTED_HOME]
    if len(converted) > 1:  # one plan home: the first converted-home entry wins
        specs = tuple(s for s in specs if s.kind != CONVERTED_HOME or s is converted[0])
    if not specs:
        return None
    names = [s.name for s in specs]
    if len(set(names)) != len(names):  # the passive ledger is keyed by name
        specs = tuple(replace(s, name=f"{s.name} ({i + 1})") for i, s in enumerate(specs))
    lived_apart = c.get('mfs_lived_apart')
    if isinstance(lived_apart, str):
        lived_apart = lived_apart.strip().lower() in ('true', 'yes', 'y', '1')
    hd, wd = int(c.get('h_death_yr') or 0), int(c.get('w_death_yr') or 0)
    couple = int(c.get('household_size', len(c.get('members') or []) or 1)) > 1
    regime = str(c.get('basis_step_up_property_regime', 'COMMON_LAW') or 'COMMON_LAW').upper()
    return RentalBook(specs=specs, plan_start=int(c['plan_start']),
                      mfs_lived_apart_all_year=bool(lived_apart),
                      converted_links=links.converted, link_warnings=links.warnings,
                      first_death_year=min(hd, wd) if couple and hd and wd and hd != wd else None,
                      second_death_year=max(hd, wd) or None, first_decedent=1 if hd < wd else 2,
                      community=regime in ('COMMUNITY_PROPERTY', 'FULL_STEP_UP'))


def ordinary_income(ry: RentalYear, passive: PassiveLossResult) -> float:
    """What the rentals add to ordinary income (AGI) this year: the Schedule E amount the
    passive limit allows (released losses included), the unrecaptured section 1250 gain on
    a sale (ordinary rates capped at 25%, see :func:`unrecaptured_1250_cap_adjustment`)
    and a section 1231 sale loss (ordinary, negative)."""
    return (passive.net_to_agi + ry.total("unrecaptured_1250_gain") - ry.total("ordinary_loss")
            - ry.total("death_loss_released"))


def unrecaptured_1250_cap_adjustment(amount: float, taxable_inc: float, year: int, filing: str,
                                     brackets: list[tuple[float, float, float]],
                                     fed_tax_fn: Callable[[float, int, str], float],
                                     max_rate: float,
                                     qualified_dividends: float = 0.0) -> float:
    """The (non-positive) federal tax change that caps the unrecaptured section 1250 gain
    at ``max_rate``: the gain sits in ordinary taxable income at the top of the ORDINARY
    stack and was taxed at full bracket rates; each dollar is owed at most ``max_rate``.

    WI-023 / FIN-003: qualified dividends are taxed in the preferential stack above the
    ordinary income, so the ordinary stack is ``taxable_inc`` less the dividends and
    ``fed_tax_fn`` must be the ORDINARY-schedule tax (no dividend stacking)."""
    from ..rental_tax import unrecaptured_1250_tax
    from .. import tax_kernel as _tk
    taxable_inc, _qd = _tk.split_qualified_dividends(taxable_inc, qualified_dividends)
    slice_amt = min(max(0.0, amount), max(0.0, taxable_inc))
    if slice_amt <= 0:
        return 0.0
    below = taxable_inc - slice_amt
    ordinary = fed_tax_fn(taxable_inc, year, filing) - fed_tax_fn(below, year, filing)
    capped = unrecaptured_1250_tax(slice_amt, below, [(lo, hi, rate) for lo, hi, rate in brackets], max_rate)
    return min(0.0, capped - ordinary)


def _sale_deposit_parts(c: dict[str, Any], row: dict[str, Any], spec: RentalSpec | None) -> list[tuple[str, float]]:
    """H4: (account, fraction) parts for one sale's proceeds. No owner set: the single default
    account as always. Otherwise member 1's share to member 1's first taxable account and the
    rest to member 2's (a deceased owner's part goes to the survivor; a member without a
    taxable account falls back to the household's first one)."""
    default = c.get('home_sale_acct') or _aa.first_taxable(c)
    if spec is None or not spec.owner:
        return [(default, 1.0)]
    share1 = member_1_share_of(spec)
    h_alive, w_alive = row.get('h_alive', True), row.get('w_alive', True)
    if h_alive and not w_alive:
        share1 = 1.0
    elif w_alive and not h_alive:
        share1 = 0.0
    parts: dict[str, float] = {}
    for idx, frac in ((0, share1), (1, 1.0 - share1)):
        if frac > 1e-12:
            acct = _aa.first_taxable(c, idx) or default
            parts[acct] = parts.get(acct, 0.0) + frac
    return list(parts.items()) or [(default, 1.0)]


def deposit_sale_proceeds(c: dict[str, Any], row: dict[str, Any], bal: dict[str, float],
                          bal_basis_free: dict[str, float], ry: RentalYear,
                          book: RentalBook | None = None) -> float:
    """Deposit each sold property's positive net proceeds to the taxable account(s) a
    ``next_housing_steps`` sale uses (``home_sale_acct``, else the first taxable account), or
    split by owner (H4, see :func:`_sale_deposit_parts`); basis-free cash, the gain is taxed
    this year. Returns the total deposited.
    A negative net (loan above the proceeds) is a cash need in :func:`net_cash_flow`."""
    total = 0.0
    for p in ry.properties:
        amt = max(0.0, p.sale_net_proceeds) if p.sold else 0.0
        if amt <= 0:
            continue
        spec = next((s for s in book.specs if s.name == p.name), None) if book is not None else None
        for acct, frac in _sale_deposit_parts(c, row, spec):
            if acct not in bal:
                acct = _aa.first_taxable(c)
            part = amt * frac
            _aa.deposit(bal, acct, part)
            _add_account_flow(row['_account_deposits'], acct, part)
            _tag_deposit_source(row, acct, f'Rental Sale Proceeds ({p.name})', part)
            if acct in bal_basis_free:
                bal_basis_free[acct] += part
        total += amt
    return total


def annotate_owners(row: dict[str, Any], book: RentalBook) -> None:
    """H4: add ``owner`` and ``member_1_share`` to the by-property rows of properties with an owner set."""
    owners = {s.name: s for s in book.specs if s.owner}
    for p in row.get('rental_by_property') or []:
        s = owners.get(p.get('name'))
        if s is not None:
            p['owner'], p['member_1_share'] = s.owner, member_1_share_of(s)


def net_cash_flow(ry: RentalYear) -> float:
    """The year's rental cash into (+) or out of (-) the household budget: operating net
    cash plus any underwater sale shortfall (positive sale proceeds are deposited)."""
    return ry.total("net_cash") + sum(min(0.0, p.sale_net_proceeds) for p in ry.properties if p.sold)


def write_flow_fields(row: dict[str, Any], ry: RentalYear, deposited: float) -> None:
    """Row fields for the year's flows (present only when the feature runs)."""
    row['rental_gross_rent'] = ry.total("gross_rent")
    row['rental_vacancy_loss'] = ry.total("vacancy_loss")
    row['rental_operating_expenses'] = ry.total("operating_expenses")
    row['rental_mortgage_interest'] = ry.total("mortgage_interest")
    row['rental_mortgage_principal'] = ry.total("mortgage_principal")
    row['rental_depreciation'] = ry.total("depreciation")
    row['rental_schedule_e_net'] = ry.total("schedule_e")
    row['rental_improvements'] = ry.total("improvements_cash")
    row['rental_purchase_cash'] = ry.total("purchase_cash")
    row['rental_net_cash_flow'] = net_cash_flow(ry)
    row['rental_property_value'] = ry.total("value")
    row['rental_mortgage_balance'] = ry.total("loan_balance")
    row['rental_equity'] = row['rental_property_value'] - row['rental_mortgage_balance']
    row['rental_sale_price'] = ry.total("sale_price")
    row['rental_sale_selling_costs'] = ry.total("selling_costs")
    row['rental_sale_loan_payoff'] = ry.total("loan_payoff")
    row['rental_sale_gain'] = ry.total("sale_gain")
    row['rental_sale_unrecaptured_1250_gain'] = ry.total("unrecaptured_1250_gain")
    row['rental_sale_capital_gain'] = ry.total("capital_gain")
    row['rental_sale_ordinary_loss'] = ry.total("ordinary_loss")
    row['rental_sale_net_proceeds'] = deposited
    row['rental_by_property'] = [{k: v for k, v in asdict(p).items() if k not in DEATH_KEYS or v} for p in ry.properties]
    if ry.total("death_loss_released") or ry.total("death_loss_lost") or ry.total("death_basis_change"):
        row['rental_death_loss_released'] = ry.total("death_loss_released")
        row['rental_death_loss_lost'] = ry.total("death_loss_lost")
        row['rental_death_basis_change'] = ry.total("death_basis_change")


def write_passive_fields(row: dict[str, Any], passive: PassiveLossResult, magi: float,
                         sizing: PassiveLossResult | None, sizing_magi: float | None) -> None:
    """Row fields for the passive-loss limit, and the Roth-sizing difference log (design
    section 4: sizing used the MAGI before the conversion, this is the actual MAGI)."""
    row['rental_passive_magi'] = magi
    row['rental_passive_allowance_available'] = passive.special_allowance_available
    row['rental_passive_allowance_used'] = passive.special_allowance_used
    row['rental_passive_loss_released'] = passive.released_loss
    row['rental_schedule_e_to_agi'] = passive.net_to_agi
    row['rental_suspended_loss_carryforward'] = passive.total_suspended
    suspended = {a.name: a.suspended for a in passive.activities}
    for p in row.get('rental_by_property') or []:
        p['suspended_loss_carryforward'] = suspended.get(p['name'], 0.0)
    if sizing is not None and sizing_magi is not None:
        row['rental_passive_magi_for_conversion_sizing'] = sizing_magi
        row['rental_schedule_e_to_agi_for_conversion_sizing'] = sizing.net_to_agi
        # Bounded by construction: the two MAGIs differ only by the conversion, so the
        # allowance moves by at most phase-out rate x conversion.
        row['rental_conversion_sizing_difference'] = passive.net_to_agi - sizing.net_to_agi


class RentalSaleTax(NamedTuple):
    ltcg_gain: float  # home-sale LTCG + the rentals' long-term gain (the cascade's seed)
    ltcg_tax: float  # federal LTCG tax on that combined gain
    fixed_adjustment: float  # 1250 cap (<= 0) + state tax on the long-term part (>= 0)


def apply_sale_tax(c: dict[str, Any], row: dict[str, Any], ry: RentalYear, book: RentalBook, *, year: int,
                   filing: str, taxable_inc: float, home_sale_ltcg_gain: float, home_sale_ltcg_tax: float,
                   fed_brackets: list[tuple[float, float, float]],
                   compute_fed_tax_fn: Callable[[float, int, str], float], state_tax: float,
                   state_tax_fn: Callable[[float], float], investment_inc: float,
                   qualified_dividends: float = 0.0) -> RentalSaleTax:
    """The tax on a rental sale beyond what ordinary income already carries (the
    unrecaptured 1250 gain and a 1231 loss are in ``portfolio_ordinary`` by now):

    * federal LTCG on the long-term part, stacked with any home-sale gain on top of
      ordinary taxable income (``tax_kernel.ltcg_tax_on_gain``);
    * the 25% cap on the unrecaptured 1250 gain (:func:`unrecaptured_1250_cap_adjustment`);
    * state tax on the long-term part as ordinary income (design section 4.7);
      ``state_tax_fn(investment_inc)`` is the stage's state-tax call with only the
      investment-income argument free.
    """
    from .. import tax_kernel as _tk
    ltcg = ry.total("capital_gain")
    u1250 = ry.total("unrecaptured_1250_gain")
    gain, tax, cap_adj, state_adj = home_sale_ltcg_gain, home_sale_ltcg_tax, 0.0, 0.0
    if ltcg > 0:
        gain = home_sale_ltcg_gain + ltcg
        tax = _tk.ltcg_tax_on_gain(c, gain, max(0.0, taxable_inc), year)
        state_adj = state_tax_fn(investment_inc + ltcg) - state_tax
    if u1250 > 0:
        cap_adj = unrecaptured_1250_cap_adjustment(
            u1250, taxable_inc, year, filing, fed_brackets, compute_fed_tax_fn,
            book.constants(year, filing).unrecaptured_1250_max_rate, qualified_dividends)
    row['rental_sale_ltcg_tax'] = tax - home_sale_ltcg_tax
    row['rental_sale_1250_cap_adjustment'] = cap_adj
    row['rental_sale_state_tax_on_ltcg'] = state_adj
    row['rental_tax_adjustment'] = cap_adj + state_adj
    return RentalSaleTax(gain, tax, cap_adj + state_adj)


def true_up_1250_cap(row: dict[str, Any], ry: RentalYear, book: RentalBook, *, year: int, filing: str,
                     taxable_inc: float, fed_brackets: list[tuple[float, float, float]],
                     compute_fed_tax_fn: Callable[[float, int, str], float],
                     qualified_dividends: float = 0.0) -> float:
    """Re-cap the unrecaptured 1250 gain at the converged ``taxable_inc`` (after the
    cascade's elective draws pushed it up the brackets); returns the change to the
    sale-year tax and updates the row's adjustment fields. 0 outside a sale year."""
    u1250 = ry.total("unrecaptured_1250_gain")
    if u1250 <= 0:
        return 0.0
    cap_adj = unrecaptured_1250_cap_adjustment(
        u1250, taxable_inc, year, filing, fed_brackets, compute_fed_tax_fn,
        book.constants(year, filing).unrecaptured_1250_max_rate, qualified_dividends)
    delta = cap_adj - row['rental_sale_1250_cap_adjustment']
    row['rental_sale_1250_cap_adjustment'] = cap_adj
    row['rental_tax_adjustment'] += delta
    return delta
