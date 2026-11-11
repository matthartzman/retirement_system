"""Tax on the gain when the plan sells its Other Assets (start-up equity, art, collectibles ...).

Each non-vehicle Other Asset is tracked on its own (helpers below): its value grows, or with a negative rate
shrinks, at its own rate, and ``appreciation_divorce_qlac.apply_appreciation_divorce_qlac`` sells it in its own
``sell_year`` (none: held for the whole plan) and deposits the year's proceeds
(``row['startup_sale_proceeds']``) into a taxable account. Until 2026-11 the gain on that sale was never taxed,
and every item was sold together in the earliest sell year. This stage sorts each sold item's gain (its own
proceeds minus its basis, never below zero) by its tax treatment (``src/other_asset_tax.py``):

* ``gains``, held more than one year: long-term capital gain. The engine adds it to the same LTCG channel as the
  home-sale and realized-ledger gains, so the investment-tax cascade taxes it at LTCG rates with NIIT and state
  tax, and it is in AGI, IRMAA MAGI and the Social Security provisional income.
* ``collectible_gains``, held more than one year: stacked on ordinary income, at the ordinary rate but never more
  than 28% (IRC 1(h)(4)).
* either kind held one year or less: ordinary income.
* ``none``: not taxed.

The collectible and short-term gains are taxed here as a fixed amount (federal, state and NIIT on top of the
year's ordinary income), carried through every later tax recombination like the rental sale's 1250 cap.
Approximations, stated so they can be lifted later: the federal stack base is the stage-9 ordinary taxable income
(IRA draws sized later in the cascade are not under it), the collectible gain does not push the year's other LTCG
into higher brackets, and it does not raise taxable Social Security. A blank basis taxes the whole proceeds.

Design: documentation/archive/superpowers/plans/2026-11-06-alt-asset-gain-tax-and-change-breakdown-design-and-plan.md
section 3.2.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, NamedTuple

from .. import other_asset_tax as _oat
from ..core import niit_tax


class OtherAssetSaleGains(NamedTuple):
    ltcg_gain: float  # long-term, regular capital-gain rates (goes into the LTCG channel)
    collectible_gain: float  # long-term collectible: ordinary rates capped at 28%
    ordinary_gain: float  # held one year or less
    items: list[dict[str, Any]]  # per item: name, treatment, proceeds, basis, gain, long_term, kind

    @property
    def stacked_gain(self) -> float:
        return self.collectible_gain + self.ordinary_gain

    @property
    def total_gain(self) -> float:
        return self.ltcg_gain + self.stacked_gain


NO_GAINS = OtherAssetSaleGains(0.0, 0.0, 0.0, [])


def startup_items(c: dict[str, Any]) -> list[dict[str, Any]]:
    """The non-vehicle Other Assets (start-up equity, art, collectibles ...) the parser tagged ``in_startup``."""
    return [i for i in c.get('other_asset_items') or [] if i.get('in_startup')]


def item_sell_year(item: dict[str, Any]) -> int:
    """The year the plan sells ``item``; 0 when it has no sell date (held for the whole plan)."""
    year = int(item.get('sell_year') or 0)
    if not year:
        sold = _oat.parse_date(item.get('sell_date', ''))
        year = sold.year if sold else 0
    return year


def _growth(item: dict[str, Any]) -> float:
    # A negative rate shrinks the value; -100% or worse leaves nothing.
    return max(0.0, 1.0 + float(item.get('annual_appreciation_pct') or 0.0))


def item_value(c: dict[str, Any], item: dict[str, Any], year: int) -> float:
    """``item``'s value at the end of ``year``: its plan-start value grown at its own rate, 0 once sold."""
    sell = item_sell_year(item)
    if sell and year >= sell >= int(c['plan_start']):
        return 0.0
    return float(item.get('value') or 0.0) * _growth(item) ** max(0, year - int(c['plan_start']) + 1)


def item_sale_proceeds(c: dict[str, Any], item: dict[str, Any]) -> float:
    """What ``item`` sells for in its sell year: its value at the end of the year before (no growth in that year)."""
    return float(item.get('value') or 0.0) * _growth(item) ** max(0, item_sell_year(item) - int(c['plan_start']))


def year_sales(c: dict[str, Any], year: int) -> list[tuple[dict[str, Any], float]]:
    """(item, proceeds) for each Other Asset the plan sells in ``year``."""
    return [(i, item_sale_proceeds(c, i)) for i in startup_items(c) if item_sell_year(i) == year]


def held_value(c: dict[str, Any], year: int) -> float:
    """End-of-``year`` value of the items not yet sold (``row['startup_val']``)."""
    return sum(item_value(c, i, year) for i in startup_items(c))


def held_value_split(c: dict[str, Any], year: int) -> tuple[float, float]:
    """End-of-``year`` value of the items not yet sold, as (start-up equity and other, art and collectibles).

    Net worth shows the two on separate lines (``row['startup_val']``, ``row['art_val']``) and adds both."""
    art = sum(item_value(c, i, year) for i in startup_items(c) if _oat.is_collectible_type(i.get('type', '')))
    return held_value(c, year) - art, art


def _sale_date(item: dict[str, Any], year: int) -> date:
    """The item's sell date when it falls in ``year``, else 31 December."""
    sold = _oat.parse_date(item.get('sell_date', ''))
    return sold if sold is not None and sold.year == year else date(year, 12, 31)


def sale_gains(c: dict[str, Any], year: int) -> OtherAssetSaleGains:
    """Gains by tax treatment on the Other Assets sold in ``year``, each from its own proceeds and basis."""
    sales = [(i, p) for i, p in year_sales(c, year) if p > 0]
    if not sales:
        return NO_GAINS
    ltcg = collectible = ordinary = 0.0
    out: list[dict[str, Any]] = []
    for item, proceeds in sales:
        basis = max(0.0, float(item.get('basis') or 0.0))
        gain = max(0.0, proceeds - basis)
        treatment = item.get('tax_treatment') or _oat.default_treatment(item.get('type', ''))
        long_term = _oat.is_long_term(_oat.parse_date(item.get('purchase_date', '')), _sale_date(item, year))
        if treatment == _oat.NONE or gain <= 0:
            kind = 'none'
        elif not long_term:
            kind, ordinary = 'ordinary', ordinary + gain
        elif treatment == _oat.COLLECTIBLE_GAINS:
            kind, collectible = 'collectible', collectible + gain
        else:
            kind, ltcg = 'ltcg', ltcg + gain
        out.append({'name': item.get('name', ''), 'treatment': treatment, 'proceeds': proceeds, 'basis': basis,
                    'gain': gain if kind != 'none' else 0.0, 'long_term': long_term, 'kind': kind,
                    'basis_entered': bool(item.get('basis_entered'))})
    return OtherAssetSaleGains(ltcg, collectible, ordinary, out)


class StackedGainTax(NamedTuple):
    federal: float
    state: float
    niit: float

    @property
    def total(self) -> float:
        return self.federal + self.state + self.niit


def stacked_gain_tax(
    gains: OtherAssetSaleGains,
    *,
    taxable_inc: float,
    fed_tax_fn: Callable[[float], float],
    state_tax_fn: Callable[[float], float],
    base_nii: float,
    magi: float,
    filing: str,
    model_niit: bool,
) -> StackedGainTax:
    """Federal, state and NIIT on the collectible and short-term gains, stacked on ``taxable_inc``.

    ``fed_tax_fn(taxable)`` is the ordinary federal tax, ``state_tax_fn(extra)`` the state tax with ``extra`` more
    investment income than the year's base minus the base itself, ``base_nii``/``magi`` the year's net investment
    income and MAGI before these gains."""
    g = gains.stacked_gain
    if g <= 0:
        return StackedGainTax(0.0, 0.0, 0.0)
    base = max(0.0, float(taxable_inc or 0.0))
    ordinary_part = gains.ordinary_gain
    # Ordinary (short-term) gain first, then the collectible gain on top of it, as on Schedule D's worksheet.
    fed_ordinary = max(0.0, fed_tax_fn(base + ordinary_part) - fed_tax_fn(base))
    fed_collectible = max(0.0, fed_tax_fn(base + g) - fed_tax_fn(base + ordinary_part))
    fed_collectible = min(fed_collectible, _oat.COLLECTIBLE_LTCG_CAP * gains.collectible_gain)
    state = max(0.0, float(state_tax_fn(g)))
    niit = (max(0.0, niit_tax(base_nii + g, magi + g, filing) - niit_tax(base_nii, magi, filing))
            if model_niit else 0.0)
    return StackedGainTax(fed_ordinary + fed_collectible, state, niit)
