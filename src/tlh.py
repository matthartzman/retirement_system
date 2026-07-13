"""Tax-loss harvesting (TLH) analyzer.

Pure, side-effect-free scanner that inspects lot-level taxable holdings and
proposes harvesting opportunities, each carried with BOTH sides of the ledger:

  VALUE  — the tax benefit, split into a *permanent* component (rate arbitrage
           or basis step-up at death, where the loss offsets a gain taxed at a
           higher rate than the future gain on the lower-basis replacement) and
           a *deferral* component (PV of moving the same-rate tax later).
  COST   — transaction cost (bps on the harvested market value), plus the
           basis-reduction drag already netted out inside the value model, plus
           a flag when the resulting carryforward risks being stranded.

TLH is only meaningful in taxable/brokerage accounts (``c['taxable_ids']``);
tax-deferred and Roth accounts realize no benefit and are never scanned.

The projection engine (deterministic_engine) imports ``select_harvest_lots``
to actually harvest inside the year loop under ``tlh_policy='apply'``; the
reporting layer imports ``scan_harvest_opportunities`` for the per-lot ledger
shown on the Tax-Loss Harvesting sheet. Both share the same selection rule so
the sheet and the projection never disagree about what would be harvested.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Mapping

_REF_DIR = Path(__file__).resolve().parent.parent / 'reference_data'


# ─────────────────────────────────────────────────────────────────────────────
# Replacement-security universe (wash-sale avoidance)
# ─────────────────────────────────────────────────────────────────────────────

def load_security_master(path: str | os.PathLike | None = None) -> dict[str, dict]:
    """Return {SYMBOL: {asset_class, sleeve, style, name}} from security_master.csv."""
    p = Path(path) if path else (_REF_DIR / 'security_master.csv')
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    with p.open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            sym = str(row.get('symbol') or '').strip().upper()
            if not sym:
                continue
            out[sym] = {
                'asset_class': str(row.get('asset_class') or '').strip().upper(),
                'sleeve': str(row.get('sleeve') or '').strip(),
                'style': str(row.get('style') or '').strip(),
                'name': str(row.get('notes') or '').strip(),
            }
    return out


def suggest_replacement(symbol: str, master: Mapping[str, dict], held_symbols: set[str]) -> str:
    """Pick a not-substantially-identical replacement to avoid the 30-day wash
    sale: same asset class and sleeve, different symbol, and preferably one the
    household does not already hold anywhere (holding it would itself trip the
    wash-sale rule across accounts). Returns '' when no clean swap exists."""
    sym_u = str(symbol or '').strip().upper()
    info = master.get(sym_u)
    if not info:
        return ''
    ac, sleeve = info['asset_class'], info['sleeve']
    same_class = [s for s, m in master.items()
                  if s != sym_u and m['asset_class'] == ac and m['sleeve'] == sleeve]
    if not same_class:
        same_class = [s for s, m in master.items() if s != sym_u and m['asset_class'] == ac]
    # Prefer a replacement not currently held anywhere in the household.
    unheld = [s for s in same_class if s not in held_symbols]
    pick = sorted(unheld or same_class)
    return pick[0] if pick else ''


# ─────────────────────────────────────────────────────────────────────────────
# Lot selection — shared by the projection engine and the reporting scanner
# ─────────────────────────────────────────────────────────────────────────────

def _lot_year(purchase_date: str) -> int | None:
    s = str(purchase_date or '')
    try:
        if '/' in s:
            return int(s.split('/')[-1])
        if '-' in s:
            return int(s.split('-')[0])
        return int(s[:4])
    except Exception:
        return None


def _is_long_term(lot, year: int) -> bool:
    acq = _lot_year(lot.purchase_date)
    if acq is None:
        return True
    return int(year) - acq >= 1


def select_harvest_lots(c: Mapping[str, Any], year: int, *,
                        min_loss_dollars: float = 500.0,
                        min_loss_pct: float = 0.05,
                        annual_ceiling: float = 0.0):
    """Select loss lots worth harvesting this year, largest loss first, up to the
    annual ceiling (0 = unlimited).

    Returns a list of dicts: {account, symbol, lot, shares, basis, market_value,
    loss, long_term}. ``lot`` is the live TaxLot object so callers that harvest
    (the engine) can reset its basis/date in place. Pure otherwise — selection
    itself mutates nothing.
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
                if qty <= 0 or basis <= 0:
                    continue
                mv = qty * price
                loss = basis - mv  # positive when underwater
                if loss < min_loss_dollars or loss < basis * min_loss_pct:
                    continue
                candidates.append({
                    'account': acct, 'symbol': sym, 'lot': lot,
                    'shares': qty, 'basis': basis, 'market_value': mv,
                    'loss': loss, 'long_term': _is_long_term(lot, year),
                })

    candidates.sort(key=lambda d: d['loss'], reverse=True)
    if annual_ceiling and annual_ceiling > 0:
        selected, running = [], 0.0
        for cand in candidates:
            if running >= annual_ceiling:
                break
            selected.append(cand)
            running += cand['loss']
        return selected
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Per-opportunity cost / value ledger (reporting)
# ─────────────────────────────────────────────────────────────────────────────

def _ltcg_marginal_rate(ordinary_income: float, existing_gain: float,
                        ltcg_0_top: float, ltcg_15_top: float,
                        bracket_factor: float, niit_applies: bool) -> float:
    """Marginal LTCG rate on the next dollar of gain, given where ordinary income
    plus existing gain already sits in the stacked 0/15/20% brackets."""
    base = max(0.0, ordinary_income) + max(0.0, existing_gain)
    top0 = ltcg_0_top * bracket_factor
    top15 = ltcg_15_top * bracket_factor
    if base < top0:
        rate = 0.0
    elif base < top15:
        rate = 0.15
    else:
        rate = 0.20
    return rate + (0.038 if niit_applies else 0.0)


def scan_harvest_opportunities(c: Mapping[str, Any], year: int, *,
                               ordinary_income: float,
                               existing_lt_gain: float,
                               carryforward_in: float = 0.0,
                               annual_return: float = 0.06,
                               years_to_step_up: int = 20,
                               fraction_sold_before_death: float = 0.5,
                               ordinary_offset_rate: float = 0.24,
                               transaction_cost_bps: float = 0.0,
                               min_loss_dollars: float = 500.0,
                               min_loss_pct: float = 0.05,
                               annual_ceiling: float = 0.0) -> dict:
    """Build the per-lot cost/value ledger for the harvest opportunities in `year`.

    Value is lifetime-net-of-cost: each harvested dollar's benefit-now (the rate
    at which the loss offsets gains / ordinary income this year) is compared to
    its cost-later (the extra tax on the larger future gain on the lower-basis
    replacement, discounted, and zeroed to the extent basis is stepped up at
    death). The split makes the *permanent* portion (rate arbitrage / step-up)
    visible separately from the pure *deferral* portion.
    """
    ltcg_0_top = float(c.get('ltcg_0_top', 96_700) or 0.0)
    ltcg_15_top = float(c.get('ltcg_15_top', 600_050) or 0.0)
    try:
        bf = (1.0 + float(c.get('bracket_inf', 0.02) or 0.0)) ** (int(year) - int(c.get('plan_start', year)))
    except Exception:
        bf = 1.0
    niit_applies = bool(c.get('model_niit', True)) and (ordinary_income + existing_lt_gain) > 250_000 * bf

    r_now = _ltcg_marginal_rate(ordinary_income, existing_lt_gain,
                                ltcg_0_top, ltcg_15_top, bf, niit_applies)
    # Rate the extra future gain on the replacement will eventually face: the
    # fraction expected to be sold before death is taxed (at today's LTCG rate as
    # a planning proxy); the rest is erased by basis step-up at death.
    r_future = max(0.0, min(1.0, fraction_sold_before_death)) * r_now
    horizon = max(1, int(years_to_step_up))
    discount = 1.0 / ((1.0 + max(0.0, annual_return)) ** horizon)

    master = load_security_master()
    held = {str(s).strip().upper()
            for syms in (c.get('lots_by_account', {}) or {}).values()
            for s in (syms or {})}

    selected = select_harvest_lots(
        c, year, min_loss_dollars=min_loss_dollars,
        min_loss_pct=min_loss_pct, annual_ceiling=annual_ceiling,
    )

    # Loss "waterfall": losses offset existing LT gains first, then up to $3,000
    # of ordinary income, remainder carries forward.
    gain_pool = max(0.0, existing_lt_gain)
    ordinary_pool = 3_000.0
    opportunities = []
    totals = {
        'loss': 0.0, 'market_value': 0.0, 'gross_benefit': 0.0,
        'future_give_back': 0.0, 'transaction_cost': 0.0, 'net_value': 0.0,
    }
    for cand in selected:
        d = cand['loss']
        mv = cand['market_value']
        # Gross tax benefit: the loss offsets existing gains at the marginal LTCG
        # rate, then up to $3k of ordinary income at the ordinary rate, then the
        # remainder carries forward (benefit discounted to reflect the delay).
        rem = d
        used_gain = min(rem, gain_pool); gain_pool -= used_gain; rem -= used_gain
        used_ord = min(rem, ordinary_pool); ordinary_pool -= used_ord; rem -= used_ord
        used_cf = rem
        gross_benefit = (used_gain * r_now
                         + used_ord * max(0.0, ordinary_offset_rate)
                         + used_cf * r_now * discount)
        # Future give-back: harvesting lowers the replacement's basis by `d`, so
        # a future gain of `d` more is taxed — but only on the fraction expected
        # to be sold before death; the rest is erased by basis step-up. PV-discounted.
        future_give_back = d * r_future * discount
        txn = mv * (max(0.0, transaction_cost_bps) / 10_000.0)
        net = gross_benefit - future_give_back - txn
        opportunities.append({
            **{k: cand[k] for k in ('account', 'symbol', 'shares', 'basis', 'market_value', 'loss', 'long_term')},
            'replacement': suggest_replacement(cand['symbol'], master, held),
            'gross_benefit': gross_benefit,
            'future_give_back': future_give_back,
            'transaction_cost': txn,
            'net_value': net,
            'mostly_permanent': future_give_back <= 0.25 * gross_benefit,
            'carryforward_portion': used_cf,
        })
        totals['loss'] += d
        totals['market_value'] += mv
        totals['gross_benefit'] += gross_benefit
        totals['future_give_back'] += future_give_back
        totals['transaction_cost'] += txn
        totals['net_value'] += net

    carryforward_out = carryforward_in + max(0.0, totals['loss'] - max(0.0, existing_lt_gain) - 3_000.0)
    stranded_risk = carryforward_out > 0 and horizon <= 3
    return {
        'year': year,
        'opportunities': opportunities,
        'totals': totals,
        'marginal_ltcg_rate': r_now,
        'carryforward_out': carryforward_out,
        'stranded_carryforward_risk': stranded_risk,
    }
