"""0%-bracket long-term capital gain harvesting (system review 2026-07-21, P2).

Symmetric counterpart to tlh.py: instead of harvesting losses, this realizes
APPRECIATED long-term lots up to the household's remaining 0%-LTCG-bracket
headroom for the year, resetting basis to market value tax-free. A standard
low-bracket-retiree strategy the projection previously never modeled despite
already computing every input it needs (ltcg_0_top, the bracket-stacking
formula in deterministic_engine.py's ``_ltcg_tax_on_gain_path``, and per-lot
holding periods).

Key differences from loss harvesting, both deliberate:
  - Selection order is smallest-gain-first (not largest-loss-first): the goal
    here is to fit as much realized, tax-free basis step-up as possible
    within a fixed headroom ceiling, so packing smaller lots first uses that
    limited space more completely. TLH orders largest-loss-first because it
    has no comparable ceiling to pack against (an annual ceiling is optional
    there; headroom is intrinsic to this strategy's entire premise here).
  - Wash-sale rules do NOT apply: they disallow claiming a loss when
    "substantially identical" securities are repurchased within 30 days, to
    stop investors from realizing a tax loss while keeping their position.
    That rule has no counterpart for gains -- a realized gain can be
    repurchased in the exact same security the same instant with no tax
    consequence, so (unlike tlh.py) there is no need for a suggested
    replacement security or a 30-day gap.

The projection engine (deterministic_engine.py) imports
``select_gain_harvest_lots`` to harvest inside the year loop under
``gain_harvest_policy='apply'``; the reporting layer imports
``scan_gain_harvest_opportunities`` for the per-lot ledger shown on the Gain
Harvesting sheet. Both share the same selection rule so the sheet and the
projection never disagree about what would be harvested.
"""

from __future__ import annotations

from typing import Any, Mapping

from .tlh import _is_long_term


def compute_zero_bracket_headroom(ltcg_0_top: float, bracket_factor: float, ordinary_income: float) -> float:
    """Remaining room under the 0%-LTCG bracket ceiling this year.

    Mirrors deterministic_engine.py's ``_ltcg_tax_on_gain_path`` stacking
    order exactly (ordinary income fills the bracket from the bottom, then
    long-term gains stack on top) so this headroom and the engine's own tax
    computation can never disagree about where the 0% ceiling sits.
    """
    top0 = max(0.0, float(ltcg_0_top or 0.0)) * max(0.0, float(bracket_factor or 1.0))
    return max(0.0, top0 - max(0.0, float(ordinary_income or 0.0)))


def select_gain_harvest_lots(c: Mapping[str, Any], year: int, *,
                              headroom: float,
                              min_gain_dollars: float = 0.0,
                              min_gain_pct: float = 0.0):
    """Select appreciated long-term lots worth harvesting this year, smallest
    gain first, up to ``headroom`` (in dollars of realized gain).

    Returns a list of dicts: {account, symbol, lot, shares, basis,
    market_value, gain, long_term}. ``lot`` is the live TaxLot object so
    callers that harvest (the engine) can reset its basis/date in place.
    Pure otherwise -- selection itself mutates nothing. Short-term lots are
    never selected: the 0% rate this strategy targets is specific to the
    long-term preferential-rate schedule, not ordinary income.
    """
    prices = {}
    le = c.get('lot_engine')
    if le is not None and getattr(le, 'prices', None):
        prices = le.prices
    taxable = set(c.get('taxable_ids', []) or [])
    lots_by_account = c.get('lots_by_account', {}) or {}

    candidates = []
    for acct, syms in lots_by_account.items():
        if acct not in taxable:
            continue
        for sym, lot_list in (syms or {}).items():
            price = float(prices.get(str(sym).strip().upper(), prices.get(sym, 0.0)) or 0.0)
            if price <= 0:
                continue
            for lot in lot_list:
                qty = float(getattr(lot, 'qty', 0.0) or 0.0)
                basis = float(getattr(lot, 'cost_basis', 0.0) or 0.0)
                if qty <= 0:
                    continue
                mv = qty * price
                gain = mv - basis  # positive when appreciated
                if gain <= 0 or gain < min_gain_dollars or (basis > 0 and gain < basis * min_gain_pct):
                    continue
                if not _is_long_term(lot, year):
                    continue
                candidates.append({
                    'account': acct, 'symbol': sym, 'lot': lot,
                    'shares': qty, 'basis': basis, 'market_value': mv,
                    'gain': gain, 'long_term': True,
                })

    candidates.sort(key=lambda d: d['gain'])
    if headroom is not None and headroom >= 0:
        selected, running = [], 0.0
        for cand in candidates:
            if running >= headroom:
                break
            if running + cand['gain'] > headroom:
                continue  # this lot alone would overshoot; try a smaller one
            selected.append(cand)
            running += cand['gain']
        return selected
    return candidates


def scan_gain_harvest_opportunities(c: Mapping[str, Any], year: int, *,
                                     ordinary_income: float,
                                     transaction_cost_bps: float = 0.0,
                                     min_gain_dollars: float = 0.0,
                                     min_gain_pct: float = 0.0) -> dict:
    """Build the per-lot ledger for the 0%-bracket gain-harvest opportunities
    in `year`, for the reporting sheet."""
    ltcg_0_top = float(c.get('ltcg_0_top', 96_700) or 0.0)
    try:
        bf = (1.0 + float(c.get('bracket_inf', 0.02) or 0.0)) ** (int(year) - int(c.get('plan_start', year)))
    except Exception:
        bf = 1.0
    headroom = compute_zero_bracket_headroom(ltcg_0_top, bf, ordinary_income)

    selected = select_gain_harvest_lots(
        c, year, headroom=headroom,
        min_gain_dollars=min_gain_dollars, min_gain_pct=min_gain_pct,
    )

    opportunities = []
    totals = {'gain': 0.0, 'market_value': 0.0, 'transaction_cost': 0.0, 'basis_stepped_up_to': 0.0}
    for cand in selected:
        txn = cand['market_value'] * (max(0.0, transaction_cost_bps) / 10_000.0)
        opportunities.append({
            **{k: cand[k] for k in ('account', 'symbol', 'shares', 'basis', 'market_value', 'gain', 'long_term')},
            'transaction_cost': txn,
        })
        totals['gain'] += cand['gain']
        totals['market_value'] += cand['market_value']
        totals['transaction_cost'] += txn
        totals['basis_stepped_up_to'] += cand['market_value']

    return {
        'year': year,
        'headroom': headroom,
        'ordinary_income': max(0.0, float(ordinary_income or 0.0)),
        'ltcg_0_top_this_year': ltcg_0_top * bf,
        'opportunities': opportunities,
        'totals': totals,
    }
