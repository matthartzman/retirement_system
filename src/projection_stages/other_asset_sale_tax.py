"""Tax on the gain when the plan sells its Other Assets (start-up equity, art, collectibles ...).

``appreciation_divorce_qlac.apply_appreciation_divorce_qlac`` sells every non-vehicle Other Asset together in
``startup_sale_year`` and deposits the proceeds (``row['startup_sale_proceeds']``) into a taxable account. Until
2026-11 the gain on that sale was never taxed. This stage splits the proceeds over the items sold, in proportion
to their value at plan start, and sorts each item's gain (proceeds share minus basis, never below zero) by its
tax treatment (``src/other_asset_tax.py``):

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
into higher brackets, and it does not raise taxable Social Security. A blank basis taxes the whole share.

Design: documentation/future/superpowers/plans/2026-11-06-alt-asset-gain-tax-and-change-breakdown-design-and-plan.md
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


def _sale_date(c: dict[str, Any], year: int) -> date:
    """The date the lumped sale happens: the earliest item sell date in that year, else 31 December."""
    dates = [_oat.parse_date(i.get('sell_date', '')) for i in c.get('other_asset_items') or [] if i.get('in_startup')]
    dates = [d for d in dates if d is not None and d.year == year]
    return min(dates) if dates else date(year, 12, 31)


def sale_gains(c: dict[str, Any], year: int, proceeds: float) -> OtherAssetSaleGains:
    """Split ``proceeds`` of this year's Other Asset sale into gains by tax treatment (see the module docstring)."""
    proceeds = float(proceeds or 0.0)
    items = [i for i in c.get('other_asset_items') or [] if i.get('in_startup')]
    if proceeds <= 0 or not items:
        return NO_GAINS
    weights = [max(0.0, float(i.get('value') or 0.0)) for i in items]
    total_w = sum(weights)
    if total_w <= 0:
        return NO_GAINS
    sold = _sale_date(c, year)
    ltcg = collectible = ordinary = 0.0
    out: list[dict[str, Any]] = []
    for item, w in zip(items, weights):
        share = proceeds * w / total_w
        basis = max(0.0, float(item.get('basis') or 0.0))
        gain = max(0.0, share - basis)
        treatment = item.get('tax_treatment') or _oat.default_treatment(item.get('type', ''))
        long_term = _oat.is_long_term(_oat.parse_date(item.get('purchase_date', '')), sold)
        if treatment == _oat.NONE or gain <= 0:
            kind = 'none'
        elif not long_term:
            kind, ordinary = 'ordinary', ordinary + gain
        elif treatment == _oat.COLLECTIBLE_GAINS:
            kind, collectible = 'collectible', collectible + gain
        else:
            kind, ltcg = 'ltcg', ltcg + gain
        out.append({'name': item.get('name', ''), 'treatment': treatment, 'proceeds': share, 'basis': basis,
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
