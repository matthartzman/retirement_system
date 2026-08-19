"""Asset allocation helpers and recommendation engine.

This module provides allocation-focused workbook functionality:
- Asset class bucket definitions and ETF candidates
- Tax-aware rebalance trade optimization
- Allocation-drift analysis and recommendation scoring
- build_sheet4: Asset Allocation & Rebalance Recommendation

Includes tax-loss harvesting analysis, account-location fit scoring, and
trade-execution guidance with wash-sale flagging and symbol substitution.

System review 2026-08-04, architect finding `reporting-facade-theater`
(Wave 4.10): this was a facade re-importing from sheets_summary.py; it is now
the canonical source for allocation logic. sheets_summary_builder.py (sheets
1-2) imports _workbook_pricing_source_label and _rebalance_settings from here
since both sheets reuse this module's pricing-source/rebalance-settings
helpers.
"""

from .workbook_common import (
    BLUE,
    DGRAY,
    FMT_DOLLAR,
    FMT_PCT,
    Font,
    GRAY,
    LGRAY,
    NAVY,
    ORANGE,
    PRICE_CACHE,
    WHITE,
    _ao,
    _td,
    datetime,
    defaultdict,
    fetch_price,
    price_source,
    pricing_diagnostics,
    pricing_source_summary,
    qc,
    section_title,
    write_cell,
    write_hdr,
)
from .. import allocation_policy as _ap
from ..person_labels import display_account

# ── Asset Allocation (Sheet 4) shared constants and helpers ──────────────────
# Hoisted out of build_sheet4 (previously ~1,400 lines in one function): pure
# lookup tables and small helpers with no dependency on build_sheet4's local
# state, used only by that sheet's build. Behavior is unchanged from the
# nested versions this replaces — see documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md
# Phase 2a.

ASSET_ALLOCATION_BUCKET_MAP = {
    # US Large Cap
    'ITOT': 'US Large Cap', 'VTI': 'US Large Cap', 'VOO': 'US Large Cap', 'SPY': 'US Large Cap',
    'IVV': 'US Large Cap', 'SCHB': 'US Large Cap', 'SPTM': 'US Large Cap', 'QQQ': 'US Large Cap', 'SCHX': 'US Large Cap',
    # US Mid Cap
    'VO': 'US Mid Cap', 'IJH': 'US Mid Cap', 'SCHM': 'US Mid Cap', 'IWR': 'US Mid Cap',
    # US Small Cap
    'AVUV': 'US Small Cap', 'VBR': 'US Small Cap', 'IWM': 'US Small Cap',
    'SCHA': 'US Small Cap', 'VB': 'US Small Cap', 'AVDV': 'US Small Cap', 'IJR': 'US Small Cap',
    # International Developed
    'IXUS': 'International', 'VXUS': 'International', 'EFA': 'International',
    'IEFA': 'International', 'SCHF': 'International', 'VEA': 'International',
    # Emerging Markets
    'VWO': 'Emerging Markets', 'EEM': 'Emerging Markets', 'IEMG': 'Emerging Markets',
    # Bonds
    'BND': 'Bonds', 'AGG': 'Bonds', 'SCHZ': 'Bonds', 'TLT': 'Bonds',
    'VBTLX': 'Bonds', 'BNDX': 'Bonds', 'IEF': 'Bonds', 'HYG': 'Bonds', 'LQD': 'Bonds',
    # Short-Term Bonds
    'SHY': 'Short-Term Bonds', 'SGOV': 'Short-Term Bonds', 'BIL': 'Short-Term Bonds',
    'USFR': 'Short-Term Bonds', 'TFLO': 'Short-Term Bonds',
    # TIPS
    'TIPS': 'TIPS', 'TIP': 'TIPS', 'VTIP': 'TIPS', 'SCHP': 'TIPS', 'STIP': 'TIPS',
    # Municipal Bonds
    'MUB': 'Municipal Bonds', 'VTEB': 'Municipal Bonds', 'TFI': 'Municipal Bonds', 'SUB': 'Municipal Bonds',
    # REITs
    'VNQ': 'REITs', 'SCHH': 'REITs', 'IYR': 'REITs', 'VGSLX': 'REITs',
    # Commodities
    'PDBC': 'Commodities', 'DJP': 'Commodities', 'GSG': 'Commodities',
    # Managed Futures
    'DBMF': 'Managed Futures', 'KMLM': 'Managed Futures', 'CTA': 'Managed Futures',
    # Private Credit / Loan-like income
    'BKLN': 'Private Credit', 'SRLN': 'Private Credit', 'CLOA': 'Private Credit',
    'JAAA': 'Private Credit', 'BIZD': 'Private Credit',
    # Cash
    'CASH': 'Cash',
}

_ASSET_ALLOCATION_REAL_ESTATE_BUCKETS = {'REITs'}

def _candidate_symbols(*buckets):
    """ETF candidates for the given asset-class buckets, de-duplicated in order."""
    out = []
    for b in buckets:
        for sym in _ap.ETF_CANDIDATES.get(b, []):
            if sym not in out:
                out.append(sym)
    return out

def _hide_zero_before_after_row(before_value, after_value):
    """True when both before/after dollar amounts round to zero (sub-$0.50 dust)."""
    try:
        return abs(float(before_value or 0)) < 0.50 and abs(float(after_value or 0)) < 0.50
    except Exception:
        return False

def _status_for_bucket(bucket, pct, tgt, fi_covered_full, re_covered_full):
    if bucket in _ap.FIXED_INCOME_CLASSES and fi_covered_full:
        return '✓ Covered by fixed-income coverage'
    if bucket in _ASSET_ALLOCATION_REAL_ESTATE_BUCKETS and re_covered_full:
        return '✓ Covered by real-estate coverage'
    if not tgt:
        return ''
    delta = pct - tgt
    return '✓' if abs(delta) < 0.03 else f'{"Over" if delta>0 else "Under"} {abs(delta):.1%}'

def _after_status_for_total_mix(label, asset_type, after_pct, tgt, fi_covered_full, re_covered_full):
    if asset_type == 'Non-liquid':
        if 'Fixed' in str(label) and fi_covered_full:
            return '✓ Covered'
        if ('Real Estate' in str(label) or 'Home Equity' in str(label)) and re_covered_full:
            return '✓ Covered'
        if not tgt:
            return 'Shown for context; no liquid target'
        _delta = after_pct - tgt
        return '✓ Covered' if after_pct >= tgt else ('✓ Mostly covered' if after_pct >= tgt * 0.8 else f'Under {abs(_delta):.1%}')
    return _status_for_bucket(label, after_pct, tgt, fi_covered_full, re_covered_full)

def _workbook_pricing_source_label():
    """Return a concise workbook-level label for the actual price source used."""
    try:
        _summary = pricing_source_summary()
    except Exception:
        _diag = pricing_diagnostics()
        _summary = _diag.get('pricing_source_summary', {}) if isinstance(_diag, dict) else {}
    _category = str(_summary.get('category') or _summary.get('label') or 'UNKNOWN').upper()
    _mode = str(_summary.get('pricing_mode') or '').upper()
    _cache_as_of = str(_summary.get('cache_as_of_local') or _summary.get('cache_as_of_utc') or '').strip()
    if _category == 'CACHE' and _cache_as_of:
        _label = f'CACHE — as of {_cache_as_of}'
    elif _category == 'LIVE':
        _label = 'LIVE — provider quote(s) used during workbook build'
    elif _category == 'OFFLINE':
        _label = 'OFFLINE — cost-basis/cash fallback pricing'
    else:
        _label = _category
    if _mode and _mode != _category:
        _label += f' (configured mode: {_mode})'
    _note = str(_summary.get('note') or '').strip()
    _counts = _summary.get('source_counts') or {}
    if isinstance(_counts, dict) and _counts:
        _count_text = ', '.join(f'{k}: {v}' for k, v in sorted(_counts.items()))
        _note = (_note + ' ' if _note else '') + f'Ticker-level source counts: {_count_text}.'
    return _label, _note

def _safe_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default

def _trade_tax_rates(c):
    """Approximate marginal rates used for taxable-account rebalance decisions.

    The workbook recommendation engine is not a tax return. These rates are
    deliberately conservative decision inputs so the trade table can compare
    after-tax benefit before recommending taxable-account sales.
    """
    ordinary = _safe_float(c.get('roth_target_bracket_rate', c.get('roth_brk', 0.24)), 0.24)
    ordinary = min(max(ordinary, 0.12), 0.37)
    ltcg = _safe_float(c.get('rebalance_ltcg_rate', 0.15), 0.15)
    ltcg = min(max(ltcg, 0.0), 0.20)
    # Item 291 Class 5. Was three layers of dead code, not one: (1) `_td`
    # here is the `taxes` module (imported from .workbook_common) -- but
    # STATE_TAX_RULES is never defined IN taxes.py, only computed as a
    # module-level variable in core.py (`STATE_TAX_RULES = _td.load_state_tax([])`),
    # so `getattr(_td, 'STATE_TAX_RULES', {})` always returned the `{}`
    # default, unconditionally, for every state; (2) `state_key` was
    # uppercased ("ILLINOIS") against proper-case keys ("Illinois") even if
    # `rules` had ever been non-empty; (3) the fallback compared against the
    # 2-letter code 'IL', but c['state'] stores the full name, so it also
    # never matched. `state` was therefore silently 0.0 for every state,
    # Illinois included, regardless of the household's real marginal state
    # rate. This function only feeds the Asset Allocation sheet's taxable-
    # sale recommendation helper (_estimate_taxable_sale) -- not the
    # deterministic/MC projection engine -- so fixing this carries no
    # golden-master risk. load_state_tax([]) is the exact mechanism core.py
    # itself uses to build STATE_TAX_RULES (see core.py's own module-level
    # assignment) -- called directly here rather than importing core to
    # avoid coupling this reporting helper to core's full import surface.
    state = 0.0
    try:
        state_key = str(c.get('state', '') or '').strip()
        rules = _td.load_state_tax([]) or {}
        if state_key in rules:
            state = _safe_float(rules.get(state_key, {}).get('rate', 0.0), 0.0)
    except Exception:
        state = 0.0
    niit = 0.038 if bool(c.get('model_niit', True)) else 0.0
    return {
        'ordinary': ordinary,
        'ltcg': ltcg,
        'state': max(0.0, state),
        'niit': niit,
        'short_term': min(0.60, ordinary + max(0.0, state) + niit),
        'long_term': min(0.40, ltcg + max(0.0, state) + niit),
    }

def _lot_purchase_year(lot):
    s = str(getattr(lot, 'purchase_date', '') or '').strip()
    try:
        if '/' in s:
            return int(s.split('/')[-1])
        if '-' in s:
            return int(s.split('-')[0])
        return int(s[:4]) if s[:4] else None
    except Exception:
        return None

def _lot_is_long_term(lot, current_year):
    y = _lot_purchase_year(lot)
    if y is None or current_year is None:
        return True
    return int(current_year) - int(y) >= 1

def _estimate_taxable_sale(c, acct, sym, sell_amt, price):
    """Estimate after-tax cost/benefit of a taxable sale using lot data.

    Returns a dict with estimated tax cost, selected long/short gains/losses,
    a human-readable note, and a `selected_lots` list.  The selected lots are
    deliberately part of the Asset Allocation recommendation so a taxable sell
    is not merely a symbol-level instruction; the workbook shows the specific
    lot order, shares/proceeds, gain/loss, term, and estimated tax impact.
    Losses are returned as negative tax cost because they may create a
    tax-loss-harvesting benefit, subject to wash-sale review.
    """
    sell_amt = max(0.0, _safe_float(sell_amt, 0.0))
    price = max(0.0, _safe_float(price, 0.0))
    rates = _trade_tax_rates(c)
    current_year = int(_safe_float(c.get('plan_start'), datetime.date.today().year) or datetime.date.today().year)
    _lot_source = c.get('rebalance_lots_by_account') or c.get('lots_by_account') or {}
    lots = list(((_lot_source.get(acct) or {}).get(sym)) or [])
    fallback_gain_fraction = _safe_float(c.get('trust_gain_fraction', 0.50), 0.50)

    if sell_amt <= 0:
        return {'tax_cost': 0.0, 'tax_cost_pct': 0.0, 'lt_gain': 0.0, 'st_gain': 0.0, 'lt_loss': 0.0, 'st_loss': 0.0, 'selected_lots': [], 'note': 'No taxable sale.'}

    def _fallback_result(message):
        gain = sell_amt * fallback_gain_fraction
        tax_cost = gain * rates['long_term']
        return {
            'tax_cost': tax_cost,
            'tax_cost_pct': tax_cost / sell_amt if sell_amt else 0.0,
            'lt_gain': gain, 'st_gain': 0.0, 'lt_loss': 0.0, 'st_loss': 0.0,
            'selected_lots': [{
                'account': acct, 'symbol': sym, 'purchase_date': 'Lot data unavailable',
                'shares': sell_amt / price if price > 0 else '', 'proceeds': sell_amt,
                'basis': sell_amt * (1 - fallback_gain_fraction), 'gain_loss': gain,
                'term': 'Assumed LT', 'tax_rate': rates['long_term'], 'tax_impact': tax_cost,
                'guidance': message,
            }],
            'note': f'{message}; assumes {fallback_gain_fraction:.0%} embedded LTCG at ~{rates["long_term"]:.1%} tax drag.',
        }

    if not lots or price <= 0:
        return _fallback_result('Lot data unavailable')

    candidates = []
    for lot in lots:
        qty = max(0.0, _safe_float(getattr(lot, 'qty', 0.0), 0.0))
        basis = max(0.0, _safe_float(getattr(lot, 'cost_basis', 0.0), 0.0))
        mv = qty * price
        if qty <= 0 or mv <= 0:
            continue
        gain_per_dollar = (mv - basis) / mv
        is_lt = _lot_is_long_term(lot, current_year)
        # Sort by after-tax drag: harvest losses first, then low/long-term gain,
        # then high-basis short-term lots only if needed.
        rate = rates['long_term'] if is_lt else rates['short_term']
        tax_drag_per_dollar = gain_per_dollar * rate
        candidates.append({
            'lot': lot, 'mv': mv, 'basis': basis, 'gain_per_dollar': gain_per_dollar,
            'is_lt': is_lt, 'tax_rate': rate, 'tax_drag_per_dollar': tax_drag_per_dollar,
        })

    if not candidates:
        return _fallback_result('Lot records had no market value')

    candidates.sort(key=lambda x: (x['tax_drag_per_dollar'], 0 if x['is_lt'] else 1, -x['basis'] / x['mv']))
    remaining = sell_amt
    lt_gain = st_gain = lt_loss = st_loss = 0.0
    selected_lots = []
    for item in candidates:
        if remaining <= 0:
            break
        take = min(remaining, item['mv'])
        if take <= 0:
            continue
        lot = item['lot']
        gain = take * item['gain_per_dollar']
        take_basis = take - gain
        take_shares = take / price if price > 0 else ''
        term = 'LT' if item['is_lt'] else 'ST'
        tax_impact = gain * item['tax_rate']
        selected_lots.append({
            'account': acct, 'symbol': sym,
            'purchase_date': str(getattr(lot, 'purchase_date', '') or ''),
            'shares': take_shares, 'proceeds': take, 'basis': take_basis,
            'gain_loss': gain, 'term': term, 'tax_rate': item['tax_rate'],
            'tax_impact': tax_impact,
            'guidance': 'Harvest loss / lowest tax drag first' if gain < -1 else ('Long-term lot selected' if item['is_lt'] else 'Short-term lot only as needed'),
        })
        if item['is_lt']:
            if gain >= 0:
                lt_gain += gain
            else:
                lt_loss += gain
        else:
            if gain >= 0:
                st_gain += gain
            else:
                st_loss += gain
        remaining -= take

    if remaining > 1:
        # Fallback for any residual not covered by current lot records.
        gain = remaining * fallback_gain_fraction
        lt_gain += gain
        selected_lots.append({
            'account': acct, 'symbol': sym, 'purchase_date': 'Unlotted residual',
            'shares': remaining / price if price > 0 else '', 'proceeds': remaining,
            'basis': remaining - gain, 'gain_loss': gain, 'term': 'Assumed LT',
            'tax_rate': rates['long_term'], 'tax_impact': gain * rates['long_term'],
            'guidance': 'Residual exceeds available lot records; fallback embedded-gain estimate used.',
        })

    tax_cost = lt_gain * rates['long_term'] + st_gain * rates['short_term'] + lt_loss * rates['long_term'] + st_loss * rates['short_term']
    pieces = []
    if lt_gain > 1:
        pieces.append(f'LT gain ${lt_gain:,.0f}')
    if st_gain > 1:
        pieces.append(f'ST gain ${st_gain:,.0f}')
    if lt_loss < -1:
        pieces.append(f'LT loss ${abs(lt_loss):,.0f}')
    if st_loss < -1:
        pieces.append(f'ST loss ${abs(st_loss):,.0f}')
    if not pieces:
        pieces.append('near-basis lot sale')
    if tax_cost < -1:
        note = 'Tax-loss-harvest candidate; verify no same/substantially-identical buys within ±30 days.'
    elif st_gain > 1:
        note = 'Includes short-term gain; optimizer only sells if drift benefit justifies ordinary-rate tax drag.'
    elif tax_cost > 1:
        note = 'Long-term/low-drag taxable sale selected after after-tax cost check.'
    else:
        note = 'Tax-neutral taxable sale selected.'
    return {
        'tax_cost': tax_cost,
        'tax_cost_pct': tax_cost / sell_amt if sell_amt else 0.0,
        'lt_gain': lt_gain, 'st_gain': st_gain, 'lt_loss': lt_loss, 'st_loss': st_loss,
        'selected_lots': selected_lots,
        'note': f'{"; ".join(pieces)}. {note}',
    }

def _lot_guidance_summary(lot_rows, max_lots=3):
    rows = list(lot_rows or [])
    if not rows:
        return ''
    parts = []
    for lot in rows[:max_lots]:
        date = str(lot.get('purchase_date') or 'lot')
        shares = lot.get('shares')
        sh_txt = f'{shares:,.2f} sh' if isinstance(shares, (int, float)) else str(shares or '')
        gl = _safe_float(lot.get('gain_loss'), 0.0)
        term = str(lot.get('term') or '')
        parts.append(f'{date}: {sh_txt}, {term}, gain/loss ${gl:,.0f}')
    more = len(rows) - max_lots
    if more > 0:
        parts.append(f'+{more} more lot(s)')
    return 'Suggested lots: ' + '; '.join(parts)

def _taxable_sell_decision(c, acct, sym, sell_amt, price, drift_pct, account_tax):
    """Return (allowed, tax_estimate, note) for a candidate sell.

    Tax-advantaged accounts are always allowed. Taxable accounts are screened on
    after-tax cost so recommendations do not create unnecessary realized gains.
    """
    if account_tax not in ('taxable', 'trust'):
        return True, {'tax_cost': 0.0, 'tax_cost_pct': 0.0, 'note': 'No current tax inside this account type.'}, 'No current tax inside tax-advantaged account.'

    est = _estimate_taxable_sale(c, acct, sym, sell_amt, price)
    drag = _safe_float(est.get('tax_cost_pct'), 0.0)
    max_drag = _safe_float(c.get('rebalance_max_tax_drag_pct', 0.015), 0.015)
    force_drift = _safe_float(c.get('rebalance_force_taxable_sell_drift_pct', 0.08), 0.08)
    review_drift = _safe_float(c.get('rebalance_taxable_review_drift_pct', 0.05), 0.05)
    st_gain = _safe_float(est.get('st_gain'), 0.0)

    if est.get('tax_cost', 0.0) < -1:
        return True, est, 'Tax-loss harvest improves after-tax rebalance; wash-sale window must be reviewed.'
    if drag <= max_drag:
        return True, est, f'After-tax cost {drag:.1%} is within configured limit {max_drag:.1%}.'
    if drift_pct >= force_drift and st_gain <= 1:
        return True, est, f'Large taxable drift {drift_pct:.1%}; sale allowed despite {drag:.1%} estimated tax drag.'
    if drift_pct >= review_drift and drag <= max_drag * 2 and st_gain <= 1:
        return True, est, f'Moderate taxable drift {drift_pct:.1%}; low/long-term tax drag acceptable.'
    return False, est, f'Deferred: estimated tax drag {drag:.1%} exceeds {max_drag:.1%}; use contributions, dividends, tax-advantaged accounts, or staged sales first.'

def _wash_sale_review_note(trade, all_trades):
    """Add a conservative wash-sale review note when a loss sale has replacement buys."""
    if trade.get('action') != 'SELL' or trade.get('tax_cost', 0.0) >= -1:
        return ''
    sym = trade.get('sym')
    bucket = trade.get('bucket')
    same_sym_buy = any(t.get('action') == 'BUY' and t.get('sym') == sym for t in all_trades)
    same_bucket_buy = any(t.get('action') == 'BUY' and t.get('bucket') == bucket for t in all_trades)
    if same_sym_buy:
        return ' Wash-sale review: same-symbol buy appears in recommended trades.'
    if same_bucket_buy:
        return ' Wash-sale review: replacement buys in same sleeve; confirm not substantially identical.'
    return ' Wash-sale review: also check spouse/all accounts ±30 days.'

def _is_cash_position_trade(trade):
    """Return True when a trade row represents the cash position itself.

    A BUY of CASH is not a security purchase that consumes cash; it means the
    optimizer intentionally leaves sale proceeds / existing cash in the cash
    sleeve. Summary net-cash calculations must therefore exclude it from
    security-buy totals and report projected ending cash separately.
    """
    return str((trade or {}).get('sym', '')).upper() == 'CASH' or str((trade or {}).get('bucket', '')).strip().lower() == 'cash'

def _projected_account_cash_after_trades(acct, holdings, trades, bucket_map, url_template):
    """Compute beginning cash, ending cash, and change using executable trades.

    Informational USE CASH / RAISE CASH rows and cash-position BUY rows are not
    counted as spending. Ending cash is beginning account cash plus sells minus
    non-cash security buys.
    """
    start_cash = 0.0
    for sym, shares in (holdings or {}).items():
        if str(sym).upper() == 'CASH' or bucket_map.get(sym) == 'Cash':
            try:
                start_cash += _safe_float(shares, 0.0) * fetch_price(sym, url_template)
            except Exception:
                start_cash += _safe_float(shares, 0.0)
    sells = sum(_safe_float(t.get('amount'), 0.0) for t in (trades or []) if str(t.get('action', '')).upper() == 'SELL')
    security_buys = sum(
        _safe_float(t.get('amount'), 0.0)
        for t in (trades or [])
        if str(t.get('action', '')).upper() == 'BUY' and not _is_cash_position_trade(t)
    )
    ending_cash = start_cash + sells - security_buys
    return start_cash, ending_cash, ending_cash - start_cash

def _append_cash_movement_rows(trades, invest_positions, acct_tax, min_trade=500):
    """Add informational CASH rows so cash deployment/raising is visible.

    Buy/sell recommendations already affect projected cash in the before/after
    tables.  These rows do not change calculations; they make the trade table
    reconcile to the Cash row in Total Portfolio Mix by account.
    """
    if not trades:
        return trades
    out = list(trades)
    by_acct = defaultdict(lambda: {'sells': 0.0, 'buys': 0.0})
    for t in trades:
        action = str(t.get('action', '')).upper()
        if action == 'SELL':
            by_acct[t.get('acct', '')]['sells'] += _safe_float(t.get('amount'), 0.0)
        elif action == 'BUY':
            by_acct[t.get('acct', '')]['buys'] += _safe_float(t.get('amount'), 0.0)
    existing_cash_by_acct = {acct: _safe_float((holdings or {}).get('CASH', 0.0), 0.0) for acct, holdings in (invest_positions or {}).items()}
    for acct in sorted(by_acct.keys()):
        sells = by_acct[acct]['sells']
        buys = by_acct[acct]['buys']
        net = sells - buys
        tax_type = acct_tax.get(acct, 'cash') if acct_tax else 'cash'
        if net < -min_trade:
            amt = round(abs(net))
            available = existing_cash_by_acct.get(acct, 0.0)
            out.append({
                'acct': acct, 'sym': 'CASH', 'action': 'USE CASH', 'amount': amt,
                'shares': '', 'bucket': 'Cash', 'tax_cost': 0,
                'tax_logic': 'Uses existing account cash to fund recommended buys; no security sale or realized tax cost.',
                'note': f'Reflects the Cash row in Total Portfolio Mix. Existing account cash before trades: ${available:,.0f}; projected account cash decreases by ${amt:,.0f}.',
            })
        elif net > min_trade:
            amt = round(net)
            out.append({
                'acct': acct, 'sym': 'CASH', 'action': 'RAISE CASH', 'amount': amt,
                'shares': '', 'bucket': 'Cash', 'tax_cost': 0,
                'tax_logic': 'Net proceeds remain in account cash after recommended sells and buys.',
                'note': f'Reflects the Cash row in Total Portfolio Mix. Projected account cash increases by ${amt:,.0f}; no cross-account transfer is assumed.',
            })
    return out

def _rebalance_settings(c):
    """Return configurable global-rebalance controls with conservative defaults.

    These controls intentionally address the practical risks of a mathematical
    household optimizer: tax cost, turnover, account concentration, Roth/pre-tax
    over-tilts, wash-sale review, ETF substitution, and solver fallback.
    """
    def _pct(key, default):
        return min(max(_safe_float(c.get(key, default), default), 0.0), 1.0)
    mode = str(c.get('trade_optimizer_mode', 'GLOBAL_TAX_AWARE') or 'GLOBAL_TAX_AWARE').strip().upper()
    if mode in ('GLOBAL', 'GLOBAL_TAX', 'TAX_AWARE_GLOBAL'):
        mode = 'GLOBAL_TAX_AWARE'
    if mode not in ('GLOBAL_TAX_AWARE', 'HEURISTIC'):
        mode = 'GLOBAL_TAX_AWARE'
    wash_policy = str(c.get('rebalance_wash_sale_policy', 'FLAG_ONLY') or 'FLAG_ONLY').strip().upper()
    if wash_policy not in ('FLAG_ONLY', 'AVOID_SAME_SYMBOL', 'STRICT_AVOID'):
        wash_policy = 'FLAG_ONLY'
    taxable_gain_policy = str(c.get('rebalance_allow_taxable_gain_sales', 'DRIFT_THRESHOLD') or 'DRIFT_THRESHOLD').strip().upper()
    if taxable_gain_policy not in ('NEVER', 'DRIFT_THRESHOLD', 'WITHIN_BUDGET', 'ALWAYS'):
        taxable_gain_policy = 'DRIFT_THRESHOLD'
    strength = str(c.get('rebalance_asset_location_strength', 'BALANCED') or 'BALANCED').strip().upper()
    if strength not in ('LIGHT', 'BALANCED', 'STRONG'):
        strength = 'BALANCED'
    return {
        'mode': mode,
        'min_trade_amount': max(0.0, _safe_float(c.get('rebalance_min_trade_amount', 500), 500)),
        'max_turnover_pct': _pct('rebalance_max_turnover_pct', 0.20),
        'max_tax_cost_bps': max(0.0, _safe_float(c.get('rebalance_max_tax_cost_bps', 25), 25)),
        'taxable_gain_budget_annual': max(0.0, _safe_float(c.get('rebalance_taxable_gain_budget_annual', 2500), 2500)),
        'wash_sale_policy': wash_policy,
        'taxable_gain_policy': taxable_gain_policy,
        'asset_location_strength': strength,
        'max_account_single_asset_pct': _pct('rebalance_max_account_single_asset_pct', 0.45),
        'max_roth_high_growth_pct': _pct('rebalance_max_roth_high_growth_pct', 0.85),
        'max_pre_tax_fixed_income_pct': _pct('rebalance_max_pre_tax_fixed_income_pct', 0.85),
        'max_trades_per_account': int(max(1, _safe_float(c.get('rebalance_max_trades_per_account', 8), 8))),
        'legacy_gain_deferral_pct': _pct('rebalance_legacy_gain_deferral_pct', 0.20),
        'drift_penalty_per_dollar': max(0.01, _safe_float(c.get('rebalance_drift_penalty_per_dollar', 1.0), 1.0)),
        'turnover_penalty_per_dollar': max(0.0, _safe_float(c.get('rebalance_turnover_penalty_per_dollar', 0.02), 0.02)),
        'solver_fallback_policy': str(c.get('rebalance_solver_fallback_policy', 'HEURISTIC') or 'HEURISTIC').strip().upper(),
    }

def _bucket_location_fit(bucket, tax_type, strength='BALANCED'):
    """Return 0..1 preference for placing an asset class in an account type."""
    b = _ap.canonical_asset_class(bucket)
    tax = str(tax_type or 'taxable').lower()
    base = 0.55
    if tax == 'pre_tax':
        if b in {'Bonds', 'Short-Term Bonds', 'TIPS', 'REITs', 'Private Credit', 'Commodities', 'Managed Futures'}:
            base = 0.95
        elif b in {'Municipal Bonds'}:
            base = 0.25
        elif b in {'US Small Cap', 'Emerging Markets'}:
            base = 0.50
        else:
            base = 0.65
    elif tax == 'roth':
        if b in {'US Small Cap', 'Emerging Markets', 'US Mid Cap', 'US Large Cap', 'International'}:
            base = 0.95
        elif b in {'Managed Futures', 'Commodities', 'REITs', 'Private Credit'}:
            base = 0.75
        elif b in {'Bonds', 'Short-Term Bonds', 'TIPS', 'Municipal Bonds'}:
            base = 0.35
        else:
            base = 0.60
    elif tax in {'taxable', 'trust'}:
        if b in {'US Large Cap', 'US Mid Cap', 'International', 'Emerging Markets', 'US Small Cap'}:
            base = 0.90
        elif b in {'Municipal Bonds', 'Short-Term Bonds', 'TIPS', 'Managed Futures'}:
            base = 0.70
        elif b in {'REITs', 'Private Credit', 'Commodities', 'Bonds'}:
            base = 0.35
        else:
            base = 0.55
    elif tax == 'hsa':
        if b in {'US Small Cap', 'US Large Cap', 'US Mid Cap', 'International', 'Emerging Markets'}:
            base = 0.90
        elif b in {'Bonds', 'Short-Term Bonds', 'TIPS', 'Managed Futures', 'Commodities'}:
            base = 0.65
        else:
            base = 0.55
    if strength == 'LIGHT':
        return 0.5 + (base - 0.5) * 0.5
    if strength == 'STRONG':
        return min(1.0, max(0.0, 0.5 + (base - 0.5) * 1.5))
    return base

def _bucket_is_high_growth(bucket):
    return _ap.canonical_asset_class(bucket) in {'US Large Cap', 'US Mid Cap', 'US Small Cap', 'International', 'Emerging Markets', 'REITs', 'Commodities', 'Managed Futures', 'Private Credit'}

def _bucket_is_fixed_income(bucket):
    return _ap.canonical_asset_class(bucket) in set(getattr(_ap, 'FIXED_INCOME_CLASSES', {'Bonds', 'Short-Term Bonds', 'TIPS', 'Municipal Bonds'})) | {'Private Credit'}

def _location_weight(strength):
    return {'LIGHT': 0.01, 'BALANCED': 0.03, 'STRONG': 0.07}.get(strength, 0.03)

def _choose_account_etf_for_bucket(bucket, acct, current_by_acct_sym, pref_symbols, etf_candidates, underrepresented_buckets):
    """Choose one ETF per account for each sleeve, especially missing sleeves."""
    candidates = list(etf_candidates.get(bucket, []))
    if not candidates:
        return None
    held = [s for s in candidates if current_by_acct_sym.get((acct, s), 0.0) > 0]
    if held:
        return max(held, key=lambda s: current_by_acct_sym.get((acct, s), 0.0))
    location_fit = [s for s in pref_symbols if s in candidates]
    # Explicitly collapse unrepresented sleeves to one chosen ETF per account.
    if bucket in underrepresented_buckets:
        return (location_fit or candidates)[0]
    return (location_fit or candidates)[0]

def _can_sell_taxable_under_policy(settings, est, drift_pct):
    policy = settings['taxable_gain_policy']
    tax_cost = _safe_float(est.get('tax_cost'), 0.0)
    tax_drag = _safe_float(est.get('tax_cost_pct'), 0.0)
    if tax_cost <= 0:
        return True, 'Tax loss or no realized gain is allowed by global optimizer policy.'
    if policy == 'ALWAYS':
        return True, 'Taxable gain sale allowed by policy.'
    if policy == 'NEVER':
        return False, 'Taxable gain sale blocked by policy.'
    max_drag = settings['max_tax_cost_bps'] / 10000.0
    if policy == 'WITHIN_BUDGET':
        return tax_drag <= max_drag, f'Taxable gain sale must fit {settings["max_tax_cost_bps"]:.0f} bps drag limit and annual budget.'
    force_drift = _safe_float(settings.get('force_drift_pct', 0.08), 0.08)
    return tax_drag <= max_drag or drift_pct >= force_drift, 'Taxable gain sale allowed only when low-drag or drift threshold is large.'

def _build_global_tax_aware_rebalance_trades(c, invest_positions, bucket_map, etf_candidates, bucket_targets, actual_buckets, total_port, acct_tax, location_pref, underrepresented_buckets, url_template=''):
    """Solve a household-level tax-location trade problem with a linear objective.

    The model is intentionally conservative: it optimizes household drift and
    asset location globally, but account cash constraints remain local because
    dollars generally cannot transfer between taxable, traditional, Roth, HSA,
    and 401(k)/IRA accounts. The model falls back gracefully if SciPy's solver is
    unavailable or infeasible.
    """
    settings = _rebalance_settings(c)
    diagnostics = []
    min_trade = settings['min_trade_amount']
    if total_port <= 0:
        return [], [], [('Global optimizer', 'Skipped', 'No liquid portfolio value available.')]
    try:
        import numpy as _np
        from scipy.optimize import linprog as _linprog
    except ImportError as exc:
        return None, None, [('Global optimizer', 'Solver unavailable', f'{exc}; fallback requested.')]

    # Price and market value tables.
    positions = []
    current_by_bucket = defaultdict(float)
    current_by_acct_sym = defaultdict(float)
    current_by_acct_bucket = defaultdict(float)
    acct_totals = defaultdict(float)
    acct_total_values = defaultdict(float)
    acct_cash = defaultdict(float)
    for acct, holdings in invest_positions.items():
        for sym, shares in holdings.items():
            price = 1.0 if sym == 'CASH' else fetch_price(sym, url_template)
            value = max(0.0, _safe_float(shares, 0.0) * max(0.0, _safe_float(price, 0.0)))
            bucket = 'Cash' if sym == 'CASH' else bucket_map.get(sym, 'Other')
            current_by_bucket[bucket] += value
            current_by_acct_sym[(acct, sym)] += value
            current_by_acct_bucket[(acct, bucket)] += value
            acct_total_values[acct] += value
            if sym == 'CASH':
                acct_cash[acct] += value
            else:
                acct_totals[acct] += value
                if value > min_trade:
                    positions.append({'acct': acct, 'sym': sym, 'bucket': bucket, 'price': price, 'value': value, 'is_cash_source': False})

    target_by_bucket = {b: max(0.0, _safe_float(w, 0.0)) * total_port for b, w in bucket_targets.items()}
    for b in list(current_by_bucket.keys()):
        target_by_bucket.setdefault(b, 0.0)
    target_buckets = sorted([b for b, v in target_by_bucket.items() if b not in ('Uncategorized', 'Other') or current_by_bucket.get(b, 0.0) > min_trade])
    if not target_buckets:
        return [], [], [('Global optimizer', 'Skipped', 'No target buckets available.')]

    sell_vars = []
    deferred = []
    total_taxable_gain_cost_limit = settings['taxable_gain_budget_annual']
    max_tax_drag = settings['max_tax_cost_bps'] / 10000.0
    cash_target_pct = _safe_float(c.get('cash_target_pct', bucket_targets.get('Cash', 0.05)), bucket_targets.get('Cash', 0.05))
    # Candidate cash deployments: existing account cash above its configured reserve
    # is an explicit source of funds in the global optimizer.  This prevents the
    # top Cash status from being solved only implicitly through a negative
    # account subtotal; the trade table later adds a visible CASH row for any
    # cash deployed or raised.
    for acct in sorted(invest_positions.keys()):
        acct_total_value = max(0.0, acct_total_values.get(acct, 0.0))
        reserve = acct_total_value * max(0.0, cash_target_pct)
        deployable_cash = max(0.0, acct_cash.get(acct, 0.0) - reserve)
        if deployable_cash > min_trade:
            sell_vars.append({
                'acct': acct, 'sym': 'CASH', 'bucket': 'Cash', 'price': 1.0,
                'value': deployable_cash, 'tax_type': acct_tax.get(acct, 'cash'),
                'fit': 1.0, 'tax_est': {'tax_cost': 0.0, 'note': ''},
                'tax_logic': 'Deploys existing account cash above the configured reserve; no security sale or realized tax cost.',
                'tax_cost_per_dollar': 0.0, 'objective': 0.0, 'is_cash_source': True,
            })
    # Candidate sells: every current non-cash position, subject to taxable policy.
    for p in positions:
        acct = p['acct']; sym = p['sym']; bucket = p['bucket']; val = p['value']; price = p['price']
        tax_type = acct_tax.get(acct, 'taxable')
        fit = _bucket_location_fit(bucket, tax_type, settings['asset_location_strength'])
        drift_pct = max(0.0, (current_by_bucket.get(bucket, 0.0) - target_by_bucket.get(bucket, 0.0)) / total_port)
        allow, est, tax_note = _taxable_sell_decision(c, acct, sym, val, price, drift_pct, tax_type)
        if tax_type in ('taxable', 'trust'):
            pol_ok, pol_note = _can_sell_taxable_under_policy(settings, est, drift_pct)
            allow = allow and pol_ok
            tax_note = f'{tax_note} {pol_note}'
            # Guard against legacy concentrated positions with large embedded gains.
            if est.get('tax_cost', 0.0) > 0 and val / total_port >= settings['legacy_gain_deferral_pct'] and est.get('tax_cost_pct', 0.0) > max_tax_drag:
                allow = False
                tax_note = 'Deferred: large embedded-gain legacy position exceeds configured legacy-gain deferral threshold.'
        if not allow:
            if current_by_bucket.get(bucket, 0.0) > target_by_bucket.get(bucket, 0.0) + min_trade:
                deferred.append({'acct': acct, 'sym': sym, 'amount': round(min(val, current_by_bucket[bucket] - target_by_bucket.get(bucket, 0.0))),
                                 'bucket': bucket, 'tax_cost': round(est.get('tax_cost', 0.0)),
                                 'tax_cost_pct': est.get('tax_cost_pct', 0.0), 'note': tax_note})
            continue
        # Taxable losses have a negative objective coefficient. Gains are capped by budget/drag controls.
        tax_cost_per_dollar = _safe_float(est.get('tax_cost', 0.0), 0.0) / val if val > 0 else 0.0
        if tax_type in ('taxable', 'trust') and tax_cost_per_dollar > max_tax_drag and settings['taxable_gain_policy'] not in ('ALWAYS',):
            continue
        loc_reward = (1.0 - fit) * _location_weight(settings['asset_location_strength'])
        objective = settings['turnover_penalty_per_dollar'] + max(tax_cost_per_dollar, -0.25) - loc_reward
        sell_vars.append({**p, 'tax_type': tax_type, 'fit': fit, 'tax_est': est, 'tax_logic': tax_note,
                          'tax_cost_per_dollar': tax_cost_per_dollar, 'objective': objective})

    buy_vars = []
    for acct in sorted(invest_positions.keys()):
        tax_type = acct_tax.get(acct, 'taxable')
        pref_symbols = location_pref.get(tax_type, location_pref.get('taxable', []))
        acct_total = max(acct_total_values.get(acct, acct_totals.get(acct, 0.0)), 0.0)
        if acct_total < min_trade:
            continue
        high_growth_current = sum(v for (a, b), v in current_by_acct_bucket.items() if a == acct and _bucket_is_high_growth(b))
        fixed_income_current = sum(v for (a, b), v in current_by_acct_bucket.items() if a == acct and _bucket_is_fixed_income(b))
        trades_left = settings['max_trades_per_account']
        for bucket, tgt_val in target_by_bucket.items():
            if bucket in ('Uncategorized', 'Other') or tgt_val <= min_trade:
                continue
            sym = _choose_account_etf_for_bucket(bucket, acct, current_by_acct_sym, pref_symbols, etf_candidates, underrepresented_buckets)
            if not sym:
                continue
            fit = _bucket_location_fit(bucket, tax_type, settings['asset_location_strength'])
            max_by_symbol_cap = max(0.0, acct_total * settings['max_account_single_asset_pct'] - current_by_acct_sym.get((acct, sym), 0.0))
            if max_by_symbol_cap <= min_trade:
                continue
            if tax_type == 'roth' and _bucket_is_high_growth(bucket):
                max_by_roth_growth = max(0.0, acct_total * settings['max_roth_high_growth_pct'] - high_growth_current)
                max_by_symbol_cap = min(max_by_symbol_cap, max_by_roth_growth if max_by_roth_growth > 0 else max_by_symbol_cap)
            if tax_type == 'pre_tax' and _bucket_is_fixed_income(bucket):
                max_by_pretax_fi = max(0.0, acct_total * settings['max_pre_tax_fixed_income_pct'] - fixed_income_current)
                max_by_symbol_cap = min(max_by_symbol_cap, max_by_pretax_fi if max_by_pretax_fi > 0 else max_by_symbol_cap)
            if max_by_symbol_cap <= min_trade:
                continue
            objective = settings['turnover_penalty_per_dollar'] + (1.0 - fit) * _location_weight(settings['asset_location_strength'])
            buy_vars.append({'acct': acct, 'sym': sym, 'bucket': bucket, 'tax_type': tax_type, 'fit': fit,
                             'upper': max_by_symbol_cap, 'objective': objective})
            trades_left -= 1
            if trades_left <= 0:
                break

    if not sell_vars and not buy_vars:
        return [], deferred, [('Global optimizer', 'No trades', 'No feasible household-level tax-location trades passed the configured constraints.')]

    n_s = len(sell_vars); n_b = len(buy_vars); n_d = len(target_buckets) * 2
    total_vars = n_s + n_b + n_d
    cvec = _np.zeros(total_vars)
    for i, v in enumerate(sell_vars):
        cvec[i] = v['objective']
    for j, v in enumerate(buy_vars):
        cvec[n_s + j] = v['objective']
    drift_weight = settings['drift_penalty_per_dollar']
    for k in range(n_d):
        cvec[n_s + n_b + k] = drift_weight

    # Bucket equality constraints: current + buys - sells - over + under = target.
    A_eq = []
    b_eq = []
    for bi, bucket in enumerate(target_buckets):
        row = _np.zeros(total_vars)
        for i, v in enumerate(sell_vars):
            if v['bucket'] == bucket:
                row[i] -= 1.0
        for j, v in enumerate(buy_vars):
            if v['bucket'] == bucket:
                row[n_s + j] += 1.0
        over_idx = n_s + n_b + bi * 2
        under_idx = over_idx + 1
        row[over_idx] -= 1.0
        row[under_idx] += 1.0
        A_eq.append(row)
        b_eq.append(target_by_bucket.get(bucket, 0.0) - current_by_bucket.get(bucket, 0.0))

    A_ub = []
    b_ub = []
    # Per-account self-funding: buys in an account cannot exceed non-cash sells
    # plus explicit CASH deployment variables.  This makes cash a first-class
    # optimization source instead of a hidden RHS allowance, so the Cash bucket
    # can be reduced in the household target equations and then disclosed in the
    # trade table.
    for acct in sorted(invest_positions.keys()):
        row = _np.zeros(total_vars)
        for i, v in enumerate(sell_vars):
            if v['acct'] == acct:
                row[i] -= 1.0
        for j, v in enumerate(buy_vars):
            if v['acct'] == acct:
                row[n_s + j] += 1.0
        A_ub.append(row); b_ub.append(0.0)
        # Cash deployment must actually fund buys in the same account; it cannot
        # be used by the solver as disappearing cash solely to improve the Cash
        # bucket slack.
        cash_src_indices = [i for i, v in enumerate(sell_vars) if v['acct'] == acct and v.get('is_cash_source')]
        if cash_src_indices:
            row2 = _np.zeros(total_vars)
            for i in cash_src_indices:
                row2[i] += 1.0
            for j, v in enumerate(buy_vars):
                if v['acct'] == acct:
                    row2[n_s + j] -= 1.0
            A_ub.append(row2); b_ub.append(0.0)
    # Total turnover.  Deploying existing cash is not a security sale and should
    # not consume the turnover budget.
    row = _np.zeros(total_vars)
    for i, v in enumerate(sell_vars):
        if not v.get('is_cash_source'):
            row[i] = 1.0
    A_ub.append(row); b_ub.append(total_port * settings['max_turnover_pct'])
    # Taxable gain budget.
    row = _np.zeros(total_vars)
    has_tax_budget = False
    for i, v in enumerate(sell_vars):
        cost = max(0.0, v['tax_cost_per_dollar'])
        if cost > 0:
            row[i] = cost
            has_tax_budget = True
    if has_tax_budget and total_taxable_gain_cost_limit > 0:
        A_ub.append(row); b_ub.append(total_taxable_gain_cost_limit)

    bounds = []
    for v in sell_vars:
        bounds.append((0.0, max(0.0, v['value'])))
    for v in buy_vars:
        bounds.append((0.0, max(0.0, v['upper'])))
    for _ in range(n_d):
        bounds.append((0.0, None))

    try:
        res = _linprog(cvec, A_ub=_np.array(A_ub) if A_ub else None, b_ub=_np.array(b_ub) if b_ub else None,
                       A_eq=_np.array(A_eq), b_eq=_np.array(b_eq), bounds=bounds, method='highs')
    except Exception as exc:
        return None, None, [('Global optimizer', 'Solver error', f'{exc}; fallback requested.')]
    if not getattr(res, 'success', False):
        return None, None, [('Global optimizer', 'Infeasible', f'{getattr(res, "message", "unknown solver message")}; fallback requested.')]

    x = res.x
    raw_trades = []
    account_trade_counts = defaultdict(int)
    for i, v in enumerate(sell_vars):
        amt = float(x[i])
        if amt < min_trade:
            continue
        # Cash deployment is disclosed later as an account-level CASH row based
        # on net buys minus sells.  Do not count it as a security trade or wash-sale input.
        if v.get('is_cash_source'):
            continue
        if account_trade_counts[v['acct']] >= settings['max_trades_per_account']:
            continue
        account_trade_counts[v['acct']] += 1
        est_full = v.get('tax_est') or {}
        # Re-estimate on the actual optimized sale amount so the displayed lot
        # guidance ties exactly to the recommended dollars/shares, rather than
        # scaling a full-position estimate.
        if v.get('tax_type') in ('taxable', 'trust'):
            est_for_amt = _estimate_taxable_sale(c, v['acct'], v['sym'], amt, v['price'])
        else:
            est_for_amt = {'tax_cost': 0.0, 'selected_lots': [], 'note': 'No current tax inside this account type.'}
        lot_summary = _lot_guidance_summary(est_for_amt.get('selected_lots'))
        note_parts = [est_for_amt.get('note') or est_full.get('note') or '']
        if lot_summary:
            note_parts.append(lot_summary)
        note_parts.append(f'Global optimizer fit score {v["fit"]:.0%}; household target/location/tax tradeoff selected this sale.')
        raw_trades.append({'acct': v['acct'], 'sym': v['sym'], 'action': 'SELL', 'amount': round(amt),
                           'shares': round(amt / v['price'], 2) if v['price'] > 0 else '',
                           'bucket': v['bucket'], 'tax_cost': round(est_for_amt.get('tax_cost', 0.0)),
                           'tax_logic': v['tax_logic'],
                           'lot_guidance': est_for_amt.get('selected_lots', []),
                           'note': ' '.join(str(x).strip() for x in note_parts if str(x or '').strip())})
    for j, v in enumerate(buy_vars):
        amt = float(x[n_s + j])
        if amt < min_trade:
            continue
        if account_trade_counts[v['acct']] >= settings['max_trades_per_account']:
            continue
        account_trade_counts[v['acct']] += 1
        # fetch_price respects OFFLINE mode by using cached/fallback pricing without live calls;
        # do not bypass the provider cache with the in-process PRICE_CACHE dict.
        price = fetch_price(v['sym'], url_template)
        note = f'Global optimizer selected this account for {v["bucket"]} based on tax treatment, household drift, and location fit {v["fit"]:.0%}.'
        if v['bucket'] in underrepresented_buckets:
            note += f' Single ETF selected for this unrepresented {v["bucket"]} sleeve in this account; ETF alternatives remain informational only.'
        if settings['wash_sale_policy'] != 'FLAG_ONLY':
            note += f' Wash-sale policy={settings["wash_sale_policy"]}; review replacement exposure.'
        raw_trades.append({'acct': v['acct'], 'sym': v['sym'], 'action': 'BUY', 'amount': round(amt),
                           'shares': round(amt / price, 2) if price > 0 else '',
                           'bucket': v['bucket'], 'tax_cost': 0,
                           'tax_logic': 'Buy side has no realized gain; global optimizer places exposure by account tax treatment and constraints.',
                           'note': note})

    cash_deployed = 0.0
    for i, v in enumerate(sell_vars):
        if v.get('is_cash_source'):
            cash_deployed += max(0.0, float(x[i]))
    realized_tax_cost = sum(_safe_float(t.get('tax_cost'), 0.0) for t in raw_trades if t.get('action') == 'SELL')
    turnover = sum(_safe_float(t.get('amount'), 0.0) for t in raw_trades if t.get('action') == 'SELL')
    diagnostics.extend([
        ('Trade optimizer mode', settings['mode'], 'Household-level linear objective; account cash constraints are respected because assets generally cannot transfer directly across account types.'),
        ('Optimization objective', 'Drift + tax cost + turnover + account-location penalty', 'Balances diversification and after-tax asset-location rather than optimizing each account in isolation.'),
        ('Configured max turnover', f'{settings["max_turnover_pct"]:.1%}', f'Actual recommended sell turnover: {turnover / total_port:.1%}; cash deployed from existing account cash: ${cash_deployed:,.0f}.'),
        ('Taxable gain budget', f'${settings["taxable_gain_budget_annual"]:,.0f}', f'Estimated realized tax cost in recommended sells: ${realized_tax_cost:,.0f}.'),
        ('Taxable gain sale policy', settings['taxable_gain_policy'], 'Addresses tax-tail-wagging-dog, legacy gains, and taxable income timing risk.'),
        ('Asset-location strength', settings['asset_location_strength'], 'Controls how hard the optimizer pushes Roth growth, pre-tax income assets, and taxable tax-efficient equity.'),
        ('Concentration / tilt caps', f'single asset {settings["max_account_single_asset_pct"]:.0%}; Roth growth {settings["max_roth_high_growth_pct"]:.0%}; pre-tax fixed income {settings["max_pre_tax_fixed_income_pct"]:.0%}', 'Hard caps reduce odd account-level allocations and over-concentration.'),
        ('Wash-sale handling', settings['wash_sale_policy'], 'The workbook flags review items; it does not certify tax compliance or see outside-account/spouse trades.'),
    ])
    if deferred:
        diagnostics.append(('Deferred taxable sales', str(len(deferred)), 'High-tax-drag or policy-blocked taxable sales are shown below instead of forced into the recommendation.'))
    if not raw_trades:
        diagnostics.append(('Global optimizer result', 'No trades above minimum', 'The linear optimum did not produce trades that exceeded the configured minimum-trade threshold.'))
    return raw_trades, deferred, diagnostics

def build_sheet4(ws, c, rows=None):
    """Asset Allocation"""
    ws.sheet_view.showGridLines = False
    # Per-account detail (holdings, before/after) is row-grouped and collapsed
    # by default -- the account/summary row sits above its own detail here,
    # so the +/- expand control belongs above the group, not below it.
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.sheet_view.showOutlineSymbols = True
    section_title(ws, 1, 'ASSET ALLOCATION & LOCATION', 8)
    _selected_mode = _ap.normalize_allocation_mode(c.get('allocation_selection_mode', 'user_target'))
    _allocation_recommendation_source = (
        'Optimizer-defined allocation'
        if _selected_mode == _ap.ALLOCATION_MODE_OPTIMIZER
        else 'User-defined allocation'
    )
    _allocation_recommendation_source_note = (
        'Selected in the UI and stored in Plan Data CSV as '
        f'allocation_selection_mode={_selected_mode}; this source drives the selected target %, '
        'liquid target-vs-actual table, and rebalance recommendations.'
    )
    write_hdr(ws, 2, 1, 'Asset Allocation Recommendation Source', BLUE, WHITE, span=8)
    write_cell(ws, 3, 1, _allocation_recommendation_source, bold=True, bg='E2F0D9' if _selected_mode == _ap.ALLOCATION_MODE_OPTIMIZER else 'EAF2FF')
    write_cell(ws, 3, 2, _allocation_recommendation_source_note)
    ws.merge_cells(start_row=3, start_column=2, end_row=3, end_column=8)
    _pricing_label, _pricing_note = _workbook_pricing_source_label()
    write_hdr(ws, 4, 1, 'Workbook Pricing Source', BLUE, WHITE, span=8)
    write_cell(ws, 5, 1, _pricing_label, bold=True, bg='EAF2FF')
    write_cell(ws, 5, 2, _pricing_note or 'Actual quote source used for this workbook build.')
    ws.merge_cells(start_row=5, start_column=2, end_row=5, end_column=8)

    # Exclude checking/savings accounts from allocation analysis
    _skip_accts = {a['id'] for a in c.get('account_registry', []) if a.get('tax') == 'cash'}
    _invest_positions = {acct: h for acct, h in c['positions'].items() if acct not in _skip_accts}

    # ── Allocation Coverage Policy: Non-Liquid Assets as Asset Classes ───────
    # User-controlled switches determine whether guaranteed income, notes, and
    # home equity reduce the amount of liquid fixed income/REIT exposure that
    # the optimizer recommends. Existing holdings remain visible even when a
    # class is disabled from recommendations.

    _coverage = _ao.compute_allocation_coverage(c)
    pv_fixed_income = _coverage.get('fixed_income_coverage_pv', 0.0)
    home_equity = _coverage.get('home_equity_allocation_value', 0.0)
    home_equity_for_reit = _coverage.get('home_equity_reit_coverage_value', 0.0)

    # Total liquid portfolio value
    liquid_total = sum(
        sum(shares * fetch_price(sym, '')
            for sym, shares in holdings.items())
        for holdings in _invest_positions.values()
    )

    # Total portfolio including enabled non-liquid coverage assets
    total_portfolio = liquid_total + pv_fixed_income + home_equity

    # Non-liquid asset labels
    nonliquid_assets = []
    if pv_fixed_income > 0:
        srcs = ', '.join(_coverage.get('fixed_income_included_sources', [])) or 'enabled sources'
        nonliquid_assets.append((f'Fixed Income Coverage ({srcs})', pv_fixed_income, 'Non-liquid'))
    if home_equity > 0:
        if home_equity_for_reit > 0:
            nonliquid_assets.append(('Real Estate Coverage (Home Equity)', home_equity, 'Non-liquid'))
        else:
            nonliquid_assets.append(('Home Equity (shown, not counted toward REIT target)', home_equity, 'Non-liquid'))

    # Bucket definitions — map symbols to asset class buckets. Hoisted to
    # module level as ASSET_ALLOCATION_BUCKET_MAP (see top of file).
    BUCKET_MAP = ASSET_ALLOCATION_BUCKET_MAP

    ETF_CANDIDATES = _ap.ETF_CANDIDATES

    # ── Compute Allocation Recommendations ─────────────────────────────
    # _opt is the selected recommendation based on the UI toggle.  The
    # optimizer recommendation is always computed too so it remains visible as
    # a second-opinion recommendation even when the user-specified target mix
    # is selected.
    _opt = _ao.compute_optimal_allocation(c, projection_rows=rows)
    _optimizer_view = _ao.compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER, projection_rows=rows)
    _user_view = _ao.compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_USER, projection_rows=rows)
    _opt_equity_pct = _opt['equity_pct']
    _opt_risk_score = _opt['risk_score']
    _opt_human_capital = _opt['human_capital']
    _opt_bond_pv = _opt['bond_pv']
    _opt_diagnostics = _opt['diagnostics']

    # Total portfolio targets (from optimizer)
    TOTAL_TARGETS = _opt['total_targets']

    # How much of fixed income & real estate targets are already covered by non-liquid
    _fi_target_amt = TOTAL_TARGETS.get('Bonds/Fixed Income', 0.15) * total_portfolio if total_portfolio > 0 else 0
    _re_target_amt = TOTAL_TARGETS.get('REITs/Real Estate', 0.05) * total_portfolio if total_portfolio > 0 else 0
    _fi_covered = min(pv_fixed_income, _fi_target_amt)
    _re_covered = min(home_equity_for_reit, _re_target_amt)
    _fi_remaining = max(0, _fi_target_amt - _fi_covered)  # bonds still needed in liquid
    _re_remaining = max(0, _re_target_amt - _re_covered)  # REITs still needed in liquid

    # Build actual bucket set from liquid holdings (excluding Cash)
    _held_buckets = set()
    for acct, holdings in _invest_positions.items():
        for sym in holdings:
            if sym != 'CASH':
                _held_buckets.add(BUCKET_MAP.get(sym, 'Uncategorized'))

    # Liquid portfolio targets from optimizer (growth/diversifier sleeve + residual FI/RE)
    _opt_liquid = _opt.get('liquid_targets', {})
    DEFAULT_LIQUID = dict(_opt_liquid)

    # Show target buckets even when the account does not currently hold them,
    # so newly modeled or enabled sleeves such as Emerging Markets,
    # Managed Futures, TIPS, and Short-Term Bonds can surface as actionable
    # recommendations. If an enabled class receives a 0.0% optimized target,
    # keep it visible so the user understands it was considered. Users can
    # force a minimum via minimum_target_pct in Asset Allocation Policy.
    _enabled_display_classes = [
        cls for cls in _ao.ASSET_CLASSES
        if _ao.allocation_class_enabled(c, cls)
    ]
    BUCKET_TARGETS = {b: w for b, w in DEFAULT_LIQUID.items() if w > 0.0025 or b in _held_buckets or b in _enabled_display_classes}
    for b in _held_buckets:
        BUCKET_TARGETS.setdefault(b, 0.0)
    for b in _enabled_display_classes:
        BUCKET_TARGETS.setdefault(b, 0.0)
    if 'Uncategorized' in _held_buckets:
        BUCKET_TARGETS['Uncategorized'] = 0.0
    # Normalize liquid targets to sum to 1.0
    _bt_sum = sum(BUCKET_TARGETS.values()) or 1.0
    BUCKET_TARGETS = {b: w / _bt_sum for b, w in BUCKET_TARGETS.items()}

    # Compute actual
    actual_buckets = defaultdict(float)
    url_template = ''
    total_port = 0.0
    for acct, holdings in _invest_positions.items():
        for sym, shares in holdings.items():
            price = fetch_price(sym, url_template)
            val = shares * price
            bucket = BUCKET_MAP.get(sym, 'Other')
            actual_buckets[bucket] += val
            total_port += val

    r = 7
    # ══════════════════════════════════════════════════════════════════════
    # PART 1: TARGETS — what the household should own (Section A)
    # ══════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'PART 1 · TARGETS — recommended allocation and why', 10); r += 2

    # ── Total Portfolio Mix (liquid + non-liquid) ─────────────────────────
    # This top-level table starts with the current portfolio and is backfilled
    # later with projected after-trade columns once recommended trades are
    # generated.  Keeping both states here avoids forcing users to scroll to
    # the detailed before/after section to understand the household mix impact.
    # Delta pp / Action fold in what used to be a separate "Liquid Portfolio:
    # Target vs Actual" table (system review 2026-08-04 follow-up) -- that
    # table's rows were a near-subset of this one's liquid rows, just sorted
    # differently and missing the non-liquid coverage rows.
    write_hdr(ws, r, 1, 'Total Portfolio Mix (Liquid + Non-Liquid)', NAVY, WHITE, span=11)
    r += 1
    hdrs_total = ['Asset Class', 'Current Value', 'Current %', 'After Trades Value',
                  'After Trades %', 'Type', 'Target %', 'Current Status', 'After Trade Status',
                  'Δ pp (After)', 'Action']
    for i, h in enumerate(hdrs_total, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    _total_mix_rows = {}
    _total_mix_types = {}
    _total_mix_targets = {}
    _total_mix_current_values = {}
    _total_mix_total_row = None

    FIXED_INCOME_BUCKETS = set(_ap.FIXED_INCOME_CLASSES)
    REAL_ESTATE_BUCKETS = {'REITs'}
    liquid_fi_value = sum(actual_buckets.get(b, 0.0) for b in FIXED_INCOME_BUCKETS)
    liquid_reit_value = sum(actual_buckets.get(b, 0.0) for b in REAL_ESTATE_BUCKETS)
    fi_tgt = TOTAL_TARGETS.get('Bonds/Fixed Income', 0.0)
    re_tgt = TOTAL_TARGETS.get('REITs/Real Estate', 0.0)
    fi_total_pct = (pv_fixed_income + liquid_fi_value) / total_portfolio if total_portfolio > 0 else 0
    re_total_pct = (home_equity_for_reit + liquid_reit_value) / total_portfolio if total_portfolio > 0 else 0
    fi_covered_full = fi_tgt > 0 and fi_total_pct >= fi_tgt - 0.0005
    re_covered_full = re_tgt > 0 and re_total_pct >= re_tgt - 0.0005

    # Liquid holdings by bucket, plus cash, sorted by current value descending.
    # Action mirrors the current-vs-target drift check that used to live only
    # in the separate "Liquid Portfolio: Target vs Actual" table.
    mix_rows = []
    for bucket in BUCKET_TARGETS.keys():
        if bucket == 'Cash':
            continue
        act_val = actual_buckets.get(bucket, 0)
        pct = act_val / total_portfolio if total_portfolio > 0 else 0
        tgt = TOTAL_TARGETS.get(bucket, TOTAL_TARGETS.get(bucket.replace('/Value',''), 0))
        status = _status_for_bucket(bucket, pct, tgt, fi_covered_full, re_covered_full)
        if bucket in FIXED_INCOME_BUCKETS and fi_covered_full:
            action = 'Covered'
        elif bucket in REAL_ESTATE_BUCKETS and re_covered_full:
            action = 'Covered'
        else:
            action = 'Rebalance' if abs(pct - tgt) > 0.02 else 'Hold'
        mix_rows.append((bucket, act_val, pct, 'Liquid', tgt, status, False, action))

    cash_total = sum(h.get('CASH', 0) * 1.0 for h in _invest_positions.values())
    cash_tgt = TOTAL_TARGETS.get('Cash', 0.0)
    cash_pct = cash_total / total_portfolio if total_portfolio > 0 else 0
    cash_status = _status_for_bucket('Cash', cash_pct, cash_tgt, fi_covered_full, re_covered_full)
    if cash_total > 0 or cash_tgt > 0:
        cash_action = 'Rebalance' if (cash_tgt and abs(cash_pct - cash_tgt) > 0.02) else 'Hold'
        mix_rows.append(('Cash', cash_total, cash_pct, 'Liquid', cash_tgt, cash_status, False, cash_action))

    # Non-liquid assets. Fixed-income and real-estate coverage are evaluated at
    # the overall coverage sleeve level, so liquid sub-sleeves are not marked
    # Under when the non-liquid coverage already exceeds the recommended target.
    # Non-liquid rows have no trade to place, so Action reads Covered/Monitor/
    # "—" rather than Rebalance/Hold.
    for label, value, asset_type in nonliquid_assets:
        pct = value / total_portfolio if total_portfolio > 0 else 0
        tgt_key = 'Bonds/Fixed Income' if 'Fixed' in label else 'REITs/Real Estate'
        tgt = TOTAL_TARGETS.get(tgt_key, 0)
        if 'Fixed' in label and fi_covered_full:
            status = '✓ Covered'
            action = 'Covered'
        elif ('Real Estate' in label or 'Home Equity' in label) and re_covered_full:
            status = '✓ Covered'
            action = 'Covered'
        elif not tgt:
            status = 'Shown for context; no liquid target'
            action = '—'
        else:
            delta = pct - tgt
            status = '✓ Covered' if pct >= tgt else ('✓ Mostly covered' if pct >= tgt * 0.8 else f'Under {abs(delta):.1%}')
            action = 'Covered' if pct >= tgt else 'Monitor'
        mix_rows.append((label, value, pct, 'Non-liquid', tgt, status, True, action))

    for label, value, pct, asset_type, tgt, status, bold_row, action in sorted(mix_rows, key=lambda x: (-x[1], str(x[0]))):
        _total_mix_rows[label] = r
        _total_mix_types[label] = asset_type
        _total_mix_targets[label] = tgt
        _total_mix_current_values[label] = value
        write_cell(ws, r, 1, label, bold=bold_row)
        write_cell(ws, r, 2, value, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 3, pct, fmt=FMT_PCT, align='right')
        # After-trade columns are populated after trades are generated.
        write_cell(ws, r, 4, '')
        write_cell(ws, r, 5, '')
        write_cell(ws, r, 6, asset_type, bg='FFF2CC' if asset_type == 'Non-liquid' else None)
        write_cell(ws, r, 7, tgt if tgt else '', fmt=FMT_PCT if tgt else None, align='right')
        write_cell(ws, r, 8, status)
        write_cell(ws, r, 9, '')
        write_cell(ws, r, 10, '')
        write_cell(ws, r, 11, action)
        r += 1

    # Total row
    _total_mix_total_row = r
    write_cell(ws, r, 1, 'TOTAL PORTFOLIO', bold=True)
    write_cell(ws, r, 2, total_portfolio, fmt=FMT_DOLLAR, align='right', bold=True)
    write_cell(ws, r, 3, 1.0, fmt=FMT_PCT, align='right', bold=True)
    write_cell(ws, r, 4, '', bold=True)
    write_cell(ws, r, 5, '', bold=True)
    r += 1

    # Coverage summary
    r += 1
    fi_pct = pv_fixed_income / total_portfolio if total_portfolio > 0 else 0
    re_pct = home_equity_for_reit / total_portfolio if total_portfolio > 0 else 0
    fi_tgt = TOTAL_TARGETS.get('Bonds/Fixed Income', 0.15)
    re_tgt = TOTAL_TARGETS.get('REITs/Real Estate', 0.05)
    write_cell(ws, r, 1, 'Non-Liquid Coverage:', bold=True)
    r += 1
    _fi_src = ', '.join(_coverage.get('fixed_income_included_sources', [])) or 'none selected'
    _fi_excl = ', '.join(_coverage.get('fixed_income_excluded_sources', []))
    _fi_note = f' Included sources: {_fi_src}.' + (f' Excluded: {_fi_excl}.' if _fi_excl else '')
    write_cell(ws, r, 1, f'Fixed Income Coverage: selected guaranteed/bond-like assets cover {fi_pct:.1%} of total portfolio '
               f'(target {fi_tgt:.0%}). {"✓ Fully covered — no bonds/TIPS/short-term bonds needed in liquid portfolio." if fi_covered_full else f"Gap: hold {max(0,fi_tgt-fi_total_pct):.1%} across enabled fixed-income sleeves."}' + _fi_note)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    r += 1
    _home_policy = 'counted toward REIT/real-estate target' if home_equity_for_reit > 0 else 'not counted toward REIT/real-estate target'
    if re_tgt <= 0 and home_equity_for_reit > 0:
        _re_status_text = 'No selected liquid REIT target; home equity is shown for context and is not under target.'
    elif re_covered_full:
        _re_status_text = '✓ Fully covered — no REITs needed in liquid portfolio.'
    else:
        _re_status_text = f'Gap/target handled by enabled REIT setting: {max(0,re_tgt-re_total_pct):.1%}.'
    write_cell(ws, r, 1, f'Real Estate Coverage: home equity is {_home_policy}; coverage equals {re_pct:.1%} of total portfolio '
               f'(target {re_tgt:.0%}). {_re_status_text}')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    r += 2

    # ── Allocation Selection and Optimizer Diagnostics ───────────────────
    # Recommendation Source / Pricing Source are not repeated here -- they're
    # already the two banners at the very top of the sheet (rows 2-5). System
    # review 2026-08-04 follow-up: three renderings of the same two facts in
    # the first 15 rows was the sheet's clearest redundancy.
    write_hdr(ws, r, 1, 'Allocation Selection and Optimizer Recommendation', BLUE, WHITE, span=6); r += 1
    write_cell(ws, r, 1, 'Selected Mode', bold=True)
    write_cell(ws, r, 2, _ap.allocation_mode_label(_selected_mode))
    write_cell(ws, r, 3, 'Toggle in the guided UI between the optimizer recommendation and the user-specified target_pct allocation.')
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
    r += 1
    write_cell(ws, r, 1, 'Why consider optimizer?', bold=True)
    write_cell(ws, r, 2, getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', ''))
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
    r += 2
    write_cell(ws, r, 1, 'Asset Class', bold=True, bg=DGRAY, fg=WHITE)
    write_cell(ws, r, 2, 'User Target %', bold=True, bg=DGRAY, fg=WHITE)
    write_cell(ws, r, 3, 'Optimizer Target %', bold=True, bg=DGRAY, fg=WHITE)
    write_cell(ws, r, 4, 'Selected Target %', bold=True, bg=DGRAY, fg=WHITE)
    write_hdr(ws, r, 5, 'Comment', DGRAY, WHITE, span=2)
    r += 1
    write_cell(ws, r, 1, 'Orange italic percentages show the initial target for a class fully satisfied by an alternate existing asset; those covered classes are excluded from the 100% liquid target completeness.', fg=ORANGE)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    r += 1
    _user_liq = _user_view.get('liquid_targets', {})
    _opt_liq = _optimizer_view.get('liquid_targets', {})
    _selected_liq = _opt.get('liquid_targets', {})
    _user_cov = (_user_view.get('diagnostics') or {}).get('coverage_adjustments') or {}
    _opt_cov = (_optimizer_view.get('diagnostics') or {}).get('coverage_adjustments') or {}
    _selected_cov = (_opt.get('diagnostics') or {}).get('coverage_adjustments') or {}
    _selected_total_targets = _opt.get('total_targets') or {}
    _all_rec_classes = list(dict.fromkeys(
        list(_ap.DEFAULT_ALLOCATION_TARGETS.keys()) +
        list(_opt_liq.keys()) + list(_selected_liq.keys()) +
        list(_user_cov.keys()) + list(_opt_cov.keys()) + list(_selected_cov.keys()) +
        list((_opt.get('diagnostics') or {}).get('covered_existing_asset_classes') or [])
    ))
    for _cls in _all_rec_classes:
        _action = _ap.normalize_selection_action((c.get('asset_class_selection_action') or {}).get(_cls, 'include'))
        _selected_cov_info = _selected_cov.get(_cls) or {}
        _covered_selected = bool(_selected_cov_info.get('fully_covered')) or (_cls in ((_opt.get('diagnostics') or {}).get('covered_existing_asset_classes') or []) and not _selected_liq.get(_cls, 0.0))
        _initial_selected_target = float(_selected_cov_info.get('original_target_pct', _selected_total_targets.get(_cls, 0.0)) or 0.0)
        write_cell(ws, r, 1, _cls)
        _u_cell = write_cell(ws, r, 2, _user_liq.get(_cls, 0.0), fmt=FMT_PCT, align='right')
        if _user_cov.get(_cls, {}).get('fully_covered') and float(_user_cov.get(_cls, {}).get('original_target_pct', 0.0) or 0.0) > 0:
            _u_cell.value = float(_user_cov[_cls].get('original_target_pct') or 0.0)
            _u_cell.font = Font(name='Arial', italic=True, color=ORANGE, size=10)
        _o_cell = write_cell(ws, r, 3, _opt_liq.get(_cls, 0.0), fmt=FMT_PCT, align='right')
        if (_opt_cov.get(_cls, {}).get('fully_covered') and float(_opt_cov.get(_cls, {}).get('original_target_pct', 0.0) or 0.0) > 0) or (_cls in ((_optimizer_view.get('diagnostics') or {}).get('covered_existing_asset_classes') or []) and _selected_total_targets.get(_cls, 0.0) > 0):
            _o_cell.value = float(_opt_cov.get(_cls, {}).get('original_target_pct', _optimizer_view.get('total_targets', {}).get(_cls, 0.0)) or 0.0)
            _o_cell.font = Font(name='Arial', italic=True, color=ORANGE, size=10)
        _sel_value = _selected_liq.get(_cls, 0.0)
        if _covered_selected and _initial_selected_target > 0:
            _sel_value = _initial_selected_target
        _sel_cell = write_cell(ws, r, 4, _sel_value, fmt=FMT_PCT, align='right', bg='E2F0D9' if _selected_mode==_ap.ALLOCATION_MODE_OPTIMIZER else 'EAF2FF')
        if _covered_selected and _initial_selected_target > 0:
            _sel_cell.font = Font(name='Arial', italic=True, color=ORANGE, size=10)
        if _action == getattr(_ap, 'SELECTION_EXCLUDE', 'exclude'):
            _comment = 'Excluded from recommendation by UI selection.'
        elif _covered_selected:
            _src = _selected_cov_info.get('source') or _ap.normalize_existing_asset_source((c.get('asset_class_alternate_first') or {}).get(_cls, 'existing asset'))
            _comment = f'Covered by {_src}; initial target is shown but not counted in the 100% liquid recommendation.'
        elif _selected_liq.get(_cls, 0) > 0:
            _comment = 'Included in selected liquid target recommendation.'
        elif _opt_liq.get(_cls, 0) > 0:
            _comment = 'Visible in optimizer comparison; not in selected target.'
        else:
            _comment = 'No selected liquid target.'
        write_cell(ws, r, 5, _comment)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        r += 1
    r += 1

    write_hdr(ws, r, 1, 'Allocation Policy Inputs', BLUE, WHITE, span=6); r += 1
    _diag_rows = [
        ('Risk Tolerance Score', f'{_opt_risk_score:.1f} / 10',
         'Auto-derived' if c.get('risk_tolerance', 0) <= 0 else 'User-provided'),
        ('Target Growth/Diversifier Allocation', f'{_opt_equity_pct:.1%}',
         'Selected allocation mode drives this target; optimizer recommendation remains visible above for comparison.'),
        ('Human Capital (PV earnings)', f'${_opt_human_capital:,.0f}',
         f'{max(0,_opt_diagnostics.get("years_to_retirement", 0)):.0f} years to retirement × stability {_opt_diagnostics.get("stability_factor", "n/a")}'),
        ('Fixed-Income Coverage PV', f'${_opt_bond_pv:,.0f}',
         f'Sources counted toward fixed-income target: {", ".join(_opt_diagnostics.get("fixed_income_coverage_sources", [])) or "none"}; funded ratio from guaranteed income: {_opt["funded_ratio"]:.1%}'),
        ('Home Equity REIT Coverage', 'YES' if _opt_diagnostics.get('home_equity_counts_toward_reit') else 'NO',
         'Controls whether primary residence equity satisfies the REIT/real-estate target before recommending liquid REITs'),
        ('Withdrawal Rate', f'{_opt_diagnostics.get("withdrawal_rate", 0):.1%}',
         'Annual spending / liquid portfolio'),
        ('Glide Path Mode', str(_opt_diagnostics.get('glide_path_mode', 'n/a')).title(),
         'Target-date: de-risk approaching retirement; Static: fixed allocation'),
        ('Inflation-Sensitive Spending', f'{_opt_diagnostics.get("inflation_sensitive_pct", 0):.0%}',
         'Higher → more broad commodities/TIPS/managed futures; precious-metal sleeves are excluded from the recommendation model'),
    ]
    if _opt_diagnostics.get('disabled_asset_classes'):
        _diag_rows.append(('Disabled Recommended Classes', ', '.join(_opt_diagnostics.get('disabled_asset_classes', [])),
                           'Disabled classes remain visible if currently held but are excluded from target recommendations'))
    if _opt_diagnostics.get('concentration'):
        for cls, pct in _opt_diagnostics['concentration'].items():
            _diag_rows.append((f'Concentration: {cls}', f'{pct:.0%}', 'Reduces allocation to correlated assets'))

    for label, value, note in _diag_rows:
        write_cell(ws, r, 1, label, bold=True)
        write_cell(ws, r, 2, value)
        write_cell(ws, r, 3, note)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
        r += 1

    r += 1

    # ── Liquid sleeve detail (feeds ETF Ideas below) ──────────────────────
    # System review 2026-08-04 follow-up: this used to be its own "Liquid
    # Portfolio: Target vs Actual" table -- Target %/Actual $/Actual %/Action
    # are the same data already in Total Portfolio Mix above (Action is now a
    # column there). Only underrepresented_buckets is still needed here.
    write_cell(ws, r, 1, f'Asset allocation recommendation source: {_allocation_recommendation_source}. The Total Portfolio Mix table above and rebalance guidance below use this source. Cash is included as its own class. The UI requires user-specified target percentages to total 100% before saving or building.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    r += 2
    liquid_display_buckets = sorted(set(BUCKET_TARGETS.keys()), key=lambda b: (-actual_buckets.get(b, 0), str(b)))
    underrepresented_buckets = []
    for bucket in liquid_display_buckets:
        tgt = BUCKET_TARGETS.get(bucket, 0)
        act_val = actual_buckets.get(bucket, 0)
        covered = (bucket in FIXED_INCOME_BUCKETS and fi_covered_full) or (bucket in REAL_ESTATE_BUCKETS and re_covered_full)
        if (bucket not in ('Cash', 'Uncategorized', 'Other') and tgt >= 0.005 and
                act_val < max(100, total_port * 0.0025) and not covered):
            underrepresented_buckets.append(bucket)

    if underrepresented_buckets:
        write_hdr(ws, r, 1, 'ETF Ideas for Recommended but Unrepresented Sleeves', BLUE, WHITE, span=6); r += 1
        write_cell(ws, r, 1, 'Sleeve', bold=True, bg=DGRAY, fg=WHITE)
        write_cell(ws, r, 2, 'Target %', bold=True, bg=DGRAY, fg=WHITE)
        write_cell(ws, r, 3, 'Current $', bold=True, bg=DGRAY, fg=WHITE)
        write_hdr(ws, r, 4, 'Possible ETFs / specific vehicles', DGRAY, WHITE, span=2)
        write_cell(ws, r, 6, 'How used in trade guidance', bold=True, bg=DGRAY, fg=WHITE)
        r += 1
        for bucket in underrepresented_buckets:
            ideas = ETF_CANDIDATES.get(bucket, [])[:3]
            if ideas:
                rec_text = ', '.join(ideas)
                use_text = f'Trade guidance selects one ETF per account for this unrepresented {bucket} sleeve; other listed ETFs are alternatives only.'
            else:
                rec_text = f'Use a low-cost, diversified {bucket} fund available at the custodian'
                use_text = 'Buy recommendations use the most specific available custodian fund for this sleeve.'
            write_cell(ws, r, 1, bucket, bold=True)
            write_cell(ws, r, 2, BUCKET_TARGETS.get(bucket, 0), fmt=FMT_PCT, align='right')
            write_cell(ws, r, 3, actual_buckets.get(bucket, 0), fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 4, rec_text); ws.merge_cells(start_row=r,start_column=4,end_row=r,end_column=5)
            write_cell(ws, r, 6, use_text)
            r += 1
        r += 1

    # Asset Location Guidance was a static, client-independent 3-row table
    # (which account type should hold which kind of asset, and why) -- moved
    # to Sheet 23 Methodology's "Asset Location Guidance" section (system
    # review 2026-08-04 follow-up), alongside the plan's other evergreen
    # how-to content, rather than re-rendered unchanged on every build.
    write_cell(ws, r, 1, 'Asset Location Guidance (which account type should hold which asset class, and why): see Sheet 23 Methodology.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    r += 2

    # Weighted expense ratio
    r += 2
    total_val = total_port
    total_exp = 0.0
    exp_map = {'IXUS':0.0007,'ITOT':0.0003,'PDBC':0.0044,'AVUV':0.0025,
               'VXUS':0.0006,'VTI':0.0003,'VBR':0.0013,'CASH':0}
    for acct, holdings in _invest_positions.items():
        for sym, shares in holdings.items():
            price = fetch_price(sym, url_template)
            val = shares * price
            exp = exp_map.get(sym, 0)
            total_exp += val * exp
    wtd_exp = total_exp / total_val if total_val else 0
    write_cell(ws, r, 1, 'Weighted Portfolio Expense Ratio', bold=True)
    write_cell(ws, r, 2, wtd_exp, fmt=FMT_PCT, bold=True)
    write_cell(ws, r, 3, f'Annual fee drag: ${total_val*wtd_exp:,.0f}')

    # ══════════════════════════════════════════════════════════════════════
    # PART 2: TRADES — what to actually execute (Sections B + C)
    # ══════════════════════════════════════════════════════════════════════
    r += 3
    section_title(ws, r, 'PART 2 · TRADES — holdings and recommended trades', 10); r += 2

    # ══════════════════════════════════════════════════════════════════════
    # SECTION B: Holdings Detail by Account
    # ══════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'HOLDINGS DETAIL BY ACCOUNT', 10); r += 1
    hdrs_detail = ['Account','Symbol','Shares','Price','Market Value','Weight','Bucket','Pricing Source']
    for i, h in enumerate(hdrs_detail, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    # Build a full holdings table: [{acct, sym, shares, price, value, bucket}]
    holdings_table = []
    for acct in sorted(_invest_positions.keys()):
        for sym, shares in sorted(_invest_positions[acct].items()):
            price = fetch_price(sym, url_template)
            val = shares * price
            bucket = BUCKET_MAP.get(sym, 'Other')
            holdings_table.append({
                'acct': acct, 'sym': sym, 'shares': shares,
                'price': price, 'value': val, 'bucket': bucket,
                'source': price_source(sym)
            })

    acct_totals = defaultdict(float)
    acct_sources = defaultdict(set)
    for h in holdings_table:
        acct_totals[h['acct']] += h['value']
        acct_sources[h['acct']].add(h.get('source', 'unknown'))

    prev_acct = ''
    for h in holdings_table:
        if h['acct'] != prev_acct:
            if prev_acct:  # spacer between accounts
                r += 1
            acct_total = acct_totals[h['acct']]
            sources = ', '.join(sorted(acct_sources[h['acct']]))
            write_cell(ws, r, 1, display_account(h['acct'], c), bold=True, bg='E2EFDA')
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
            write_cell(ws, r, 5, acct_total, fmt=FMT_DOLLAR, align='right', bold=True, bg='E2EFDA')
            write_cell(ws, r, 6, 'Account Total', bold=True, bg='E2EFDA')
            write_cell(ws, r, 7, 'Sources:', bold=True, bg='E2EFDA')
            write_cell(ws, r, 8, sources, bg='E2EFDA')
            r += 1
            prev_acct = h['acct']
        write_cell(ws, r, 1, '')
        write_cell(ws, r, 2, h['sym'])
        write_cell(ws, r, 3, h['shares'], fmt='#,##0.000', align='right')
        write_cell(ws, r, 4, h['price'], fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 5, h['value'], fmt=FMT_DOLLAR, align='right')
        wt = h['value'] / total_port if total_port > 0 else 0
        write_cell(ws, r, 6, wt, fmt=FMT_PCT, align='right')
        write_cell(ws, r, 7, h['bucket'])
        write_cell(ws, r, 8, h.get('source', 'unknown'))
        # Per-symbol rows collapse under their account's total row (system
        # review 2026-08-04 follow-up); the account total stays visible.
        ws.row_dimensions[r].outlineLevel = 1
        ws.row_dimensions[r].hidden = True
        r += 1

    write_cell(ws, r, 1, 'TOTAL', bold=True)
    write_cell(ws, r, 5, total_port, fmt=FMT_DOLLAR, align='right', bold=True)
    write_cell(ws, r, 6, 1.0, fmt=FMT_PCT, align='right', bold=True)


    # ══════════════════════════════════════════════════════════════════════
    # SECTION C: Rebalancing Trades (Location-Aware, Within-Account)
    # ══════════════════════════════════════════════════════════════════════
    r += 3
    section_title(ws, r, 'REBALANCING TRADES', 10); r += 1
    write_cell(ws, r, 1, 'Trades use a configurable household-level tax-location optimizer with account-level tax optimization when enabled. Security-buy subtotals exclude CASH target/hold rows so the Ending Cash After Trades line reconciles to the Cash row in Total Portfolio Mix. The global mode minimizes selected-target drift, estimated tax cost, turnover, and account-location inefficiency across all accounts while respecting account cash constraints, tax-lot sales including short-term vs long-term gains, minimum trades, turnover caps, concentration caps, taxable-gain budget, and wash-sale review settings. The heuristic mode remains available as a fallback.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 2

    # Location preference: which symbols should each account type ideally hold?
    # These lists are generated from the candidate ETF map (via the module-level
    # _candidate_symbols helper) so unrepresented but recommended sleeves flow
    # into the actual buy guidance instead of appearing only as narrative notes.
    LOCATION_PREF = {
        'pre_tax': _candidate_symbols('Bonds', 'Short-Term Bonds', 'TIPS', 'REITs', 'Private Credit', 'Commodities', 'Managed Futures', 'Emerging Markets', 'International', 'US Equity', 'US Small/Value'),
        'roth':    _candidate_symbols('US Small/Value', 'Emerging Markets', 'US Equity', 'International', 'Managed Futures', 'Commodities', 'REITs', 'Private Credit'),
        'taxable': _candidate_symbols('US Equity', 'International', 'Emerging Markets', 'US Small/Value', 'Short-Term Bonds', 'TIPS', 'Managed Futures'),
        'hsa':     _candidate_symbols('US Small/Value', 'US Equity', 'Bonds', 'Short-Term Bonds', 'TIPS', 'Commodities', 'Managed Futures'),
        'cash':    [],
    }

    # Portfolio-level target weights by symbol. Represented sleeves may still
    # show multiple existing/candidate ETFs, but unrepresented recommended sleeves
    # are collapsed to one account-level ETF below so trade guidance does not
    # create three starter positions for the same missing asset class.
    SYMBOL_WEIGHTS = {}
    _sym_for_bucket = {}
    for bucket, symbols in ETF_CANDIDATES.items():
        if not symbols:
            continue
        base = [0.50, 0.30, 0.20]
        weights = base[:len(symbols)]
        denom_w = sum(weights) or 1.0
        _sym_for_bucket[bucket] = [(sym, wt / denom_w) for sym, wt in zip(symbols, weights)]

    for bucket, tgt_pct in BUCKET_TARGETS.items():
        if bucket in ('Cash', 'Uncategorized'): continue
        for sym, share in _sym_for_bucket.get(bucket, []):
            SYMBOL_WEIGHTS[sym] = SYMBOL_WEIGHTS.get(sym, 0) + tgt_pct * share
    sw_total = sum(SYMBOL_WEIGHTS.values()) or 1.0
    SYMBOL_WEIGHTS = {s: w / sw_total for s, w in SYMBOL_WEIGHTS.items()}

    _acct_tax = {}
    for a in c.get('account_registry', []):
        _acct_tax[a['id']] = a.get('tax', 'taxable')
    TAX_LABELS = {'pre_tax': 'Tax-deferred', 'roth': 'Tax-free (Roth)', 'taxable': 'Taxable', 'hsa': 'HSA', 'cash': 'Cash'}

    all_trades = []
    deferred_taxable_trades = []
    global_optimizer_diagnostics = []
    _rebalance_cfg = _rebalance_settings(c)

    if _rebalance_cfg.get('mode') == 'GLOBAL_TAX_AWARE':
        _global_trades, _global_deferred, global_optimizer_diagnostics = _build_global_tax_aware_rebalance_trades(
            c, _invest_positions, BUCKET_MAP, ETF_CANDIDATES, BUCKET_TARGETS, actual_buckets,
            total_port, _acct_tax, LOCATION_PREF, underrepresented_buckets, url_template
        )
        if _global_trades is not None and _global_deferred is not None:
            all_trades = _global_trades
            deferred_taxable_trades = _global_deferred
        elif _rebalance_cfg.get('solver_fallback_policy', 'HEURISTIC') == 'HEURISTIC':
            global_optimizer_diagnostics = (global_optimizer_diagnostics or []) + [
                ('Fallback engine', 'HEURISTIC', 'Global solver was unavailable or infeasible; workbook used the previous account-level tax-aware heuristic.')
            ]
        if _global_trades is None or _global_deferred is None:
            for acct in sorted(_invest_positions.keys()):
                acct_holdings = _invest_positions.get(acct, {})
                tax_type = _acct_tax.get(acct, 'taxable')
                pref_symbols = LOCATION_PREF.get(tax_type, LOCATION_PREF['taxable'])
                if not pref_symbols: continue

                acct_total = 0
                current_by_sym = {}
                for sym, shares in acct_holdings.items():
                    if sym == 'CASH': continue
                    price = fetch_price(sym, url_template)
                    val = shares * price
                    current_by_sym[sym] = val
                    acct_total += val
                if acct_total < 500: continue

                # Target: preferred symbols weighted by portfolio-level weight.
                # For unrepresented recommended sleeves, collapse all candidate examples
                # to a single ETF per account. This avoids opening three small starter
                # positions just because the candidate list contains examples.
                acct_target = {}
                pref_sum = sum(SYMBOL_WEIGHTS.get(s, 0) for s in pref_symbols if SYMBOL_WEIGHTS.get(s, 0) > 0)
                if pref_sum > 0:
                    for sym in pref_symbols:
                        sw = SYMBOL_WEIGHTS.get(sym, 0)
                        if sw > 0:
                            acct_target[sym] = (sw / pref_sum) * acct_total

                def _single_etf_for_unrepresented_bucket(bucket):
                    candidates = list(ETF_CANDIDATES.get(bucket, []))
                    if not candidates:
                        return None
                    held = [s for s in candidates if current_by_sym.get(s, 0) > 0]
                    if held:
                        return max(held, key=lambda s: current_by_sym.get(s, 0))
                    location_fit = [s for s in pref_symbols if s in candidates]
                    return (location_fit or candidates)[0]

                for _bucket in underrepresented_buckets:
                    _candidates = [s for s in ETF_CANDIDATES.get(_bucket, []) if s in acct_target]
                    if len(_candidates) <= 1:
                        continue
                    _chosen = _single_etf_for_unrepresented_bucket(_bucket)
                    if not _chosen:
                        continue
                    _bucket_target_total = sum(acct_target.pop(s, 0) for s in _candidates)
                    acct_target[_chosen] = acct_target.get(_chosen, 0) + _bucket_target_total

                acct_sells = []
                acct_buys = []

                for sym, current_val in current_by_sym.items():
                    target_val = acct_target.get(sym, 0)
                    if current_val > target_val + 100:
                        sell_amt = round(current_val - target_val)
                        price = fetch_price(sym, url_template)
                        drift_pct = (current_val - target_val) / acct_total if acct_total > 0 else 0.0
                        allow_sell, tax_est, tax_note = _taxable_sell_decision(c, acct, sym, sell_amt, price, drift_pct, tax_type)
                        if not allow_sell:
                            deferred_taxable_trades.append({
                                'acct': acct, 'sym': sym, 'amount': sell_amt,
                                'bucket': BUCKET_MAP.get(sym, 'Other'),
                                'tax_cost': round(tax_est.get('tax_cost', 0.0)),
                                'tax_cost_pct': tax_est.get('tax_cost_pct', 0.0),
                                'note': tax_note,
                            })
                            continue
                        _lot_summary = _lot_guidance_summary(tax_est.get('selected_lots'))
                        _note = ' '.join(str(x).strip() for x in [tax_est.get('note', ''), _lot_summary] if str(x or '').strip())
                        acct_sells.append({'acct': acct, 'sym': sym, 'action': 'SELL',
                            'amount': sell_amt, 'shares': round(sell_amt / price, 2) if price > 0 else '',
                            'bucket': BUCKET_MAP.get(sym, 'Other'), 'tax_cost': round(tax_est.get('tax_cost', 0.0)),
                            'tax_logic': tax_note, 'lot_guidance': tax_est.get('selected_lots', []), 'note': _note})

                sell_proceeds = sum(t['amount'] for t in acct_sells)

                # Hold back sell proceeds to build toward cash target
                # Prefer building cash in taxable/trust accounts (configurable)
                cash_pref_types = c.get('cash_accumulation_tax_types', ['taxable', 'trust'])
                is_cash_pref = tax_type in cash_pref_types
                cash_target_val = c.get('cash_target_pct', 0.05) * acct_total
                current_cash = sum(sh * 1.0 for sym, sh in acct_holdings.items() if sym == 'CASH')
                cash_shortfall = max(0, cash_target_val - current_cash)

                # In preferred cash accounts, hold back more; in others, hold back proportionally
                if is_cash_pref:
                    cash_holdback = min(sell_proceeds * 0.5, cash_shortfall)  # up to 50% of proceeds
                else:
                    cash_holdback = min(sell_proceeds * 0.2, cash_shortfall)  # up to 20% in non-preferred

                buy_budget = max(0, sell_proceeds - cash_holdback)

                buy_needs = []
                for sym, target_val in acct_target.items():
                    current_val = current_by_sym.get(sym, 0)
                    if target_val > current_val + 100:
                        buy_needs.append((sym, round(target_val - current_val)))

                total_buy_need = sum(amt for _, amt in buy_needs)
                if total_buy_need > 0 and buy_budget > 0:
                    scale = min(1.0, buy_budget / total_buy_need)
                    for sym, need in buy_needs:
                        buy_amt = round(need * scale)
                        if buy_amt > 50:
                            # In offline validation, avoid quote calls solely for candidate buy tickers.
                            # In normal CACHE/LIVE mode, fetch a candidate price so share estimates populate.
                            # fetch_price respects OFFLINE mode by using cached/fallback pricing without live calls;
                            # do not bypass the provider cache with the in-process PRICE_CACHE dict.
                            price = fetch_price(sym, url_template)
                            _buy_bucket = BUCKET_MAP.get(sym, 'Other')
                            _note = ''
                            if _buy_bucket in underrepresented_buckets:
                                _note = f'Adds underrepresented {_buy_bucket} sleeve; single ETF selected for this account'
                            acct_buys.append({'acct': acct, 'sym': sym, 'action': 'BUY',
                                'amount': buy_amt, 'shares': round(buy_amt / price, 2) if price > 0 else '',
                                'bucket': _buy_bucket, 'tax_cost': 0, 'tax_logic': 'Buy side has no realized gain; placement follows account-level asset-location preference.', 'note': _note})

                total_buy = sum(t['amount'] for t in acct_buys)
                net_cash = sell_proceeds - total_buy
                if net_cash > 50 and acct_sells:
                    reason = 'builds cash toward target' if cash_holdback > 50 else 'residual'
                    _existing_note = acct_sells[0].get('note', '')
                    acct_sells[0]['note'] = (_existing_note + ' ' if _existing_note else '') + f'${net_cash:,} → cash ({reason})'

                if acct_sells or acct_buys:
                    all_trades.extend(acct_sells)
                    all_trades.extend(acct_buys)

    else:
        for acct in sorted(_invest_positions.keys()):
            acct_holdings = _invest_positions.get(acct, {})
            tax_type = _acct_tax.get(acct, 'taxable')
            pref_symbols = LOCATION_PREF.get(tax_type, LOCATION_PREF['taxable'])
            if not pref_symbols: continue

            acct_total = 0
            current_by_sym = {}
            for sym, shares in acct_holdings.items():
                if sym == 'CASH': continue
                price = fetch_price(sym, url_template)
                val = shares * price
                current_by_sym[sym] = val
                acct_total += val
            if acct_total < 500: continue

            # Target: preferred symbols weighted by portfolio-level weight.
            # For unrepresented recommended sleeves, collapse all candidate examples
            # to a single ETF per account. This avoids opening three small starter
            # positions just because the candidate list contains examples.
            acct_target = {}
            pref_sum = sum(SYMBOL_WEIGHTS.get(s, 0) for s in pref_symbols if SYMBOL_WEIGHTS.get(s, 0) > 0)
            if pref_sum > 0:
                for sym in pref_symbols:
                    sw = SYMBOL_WEIGHTS.get(sym, 0)
                    if sw > 0:
                        acct_target[sym] = (sw / pref_sum) * acct_total

            def _single_etf_for_unrepresented_bucket(bucket):
                candidates = list(ETF_CANDIDATES.get(bucket, []))
                if not candidates:
                    return None
                held = [s for s in candidates if current_by_sym.get(s, 0) > 0]
                if held:
                    return max(held, key=lambda s: current_by_sym.get(s, 0))
                location_fit = [s for s in pref_symbols if s in candidates]
                return (location_fit or candidates)[0]

            for _bucket in underrepresented_buckets:
                _candidates = [s for s in ETF_CANDIDATES.get(_bucket, []) if s in acct_target]
                if len(_candidates) <= 1:
                    continue
                _chosen = _single_etf_for_unrepresented_bucket(_bucket)
                if not _chosen:
                    continue
                _bucket_target_total = sum(acct_target.pop(s, 0) for s in _candidates)
                acct_target[_chosen] = acct_target.get(_chosen, 0) + _bucket_target_total

            acct_sells = []
            acct_buys = []

            for sym, current_val in current_by_sym.items():
                target_val = acct_target.get(sym, 0)
                if current_val > target_val + 100:
                    sell_amt = round(current_val - target_val)
                    price = fetch_price(sym, url_template)
                    drift_pct = (current_val - target_val) / acct_total if acct_total > 0 else 0.0
                    allow_sell, tax_est, tax_note = _taxable_sell_decision(c, acct, sym, sell_amt, price, drift_pct, tax_type)
                    if not allow_sell:
                        deferred_taxable_trades.append({
                            'acct': acct, 'sym': sym, 'amount': sell_amt,
                            'bucket': BUCKET_MAP.get(sym, 'Other'),
                            'tax_cost': round(tax_est.get('tax_cost', 0.0)),
                            'tax_cost_pct': tax_est.get('tax_cost_pct', 0.0),
                            'note': tax_note,
                        })
                        continue
                    _lot_summary = _lot_guidance_summary(tax_est.get('selected_lots'))
                    _note = ' '.join(str(x).strip() for x in [tax_est.get('note', ''), _lot_summary] if str(x or '').strip())
                    acct_sells.append({'acct': acct, 'sym': sym, 'action': 'SELL',
                        'amount': sell_amt, 'shares': round(sell_amt / price, 2) if price > 0 else '',
                        'bucket': BUCKET_MAP.get(sym, 'Other'), 'tax_cost': round(tax_est.get('tax_cost', 0.0)),
                        'tax_logic': tax_note, 'lot_guidance': tax_est.get('selected_lots', []), 'note': _note})

            sell_proceeds = sum(t['amount'] for t in acct_sells)

            # Hold back sell proceeds to build toward cash target
            # Prefer building cash in taxable/trust accounts (configurable)
            cash_pref_types = c.get('cash_accumulation_tax_types', ['taxable', 'trust'])
            is_cash_pref = tax_type in cash_pref_types
            cash_target_val = c.get('cash_target_pct', 0.05) * acct_total
            current_cash = sum(sh * 1.0 for sym, sh in acct_holdings.items() if sym == 'CASH')
            cash_shortfall = max(0, cash_target_val - current_cash)

            # In preferred cash accounts, hold back more; in others, hold back proportionally
            if is_cash_pref:
                cash_holdback = min(sell_proceeds * 0.5, cash_shortfall)  # up to 50% of proceeds
            else:
                cash_holdback = min(sell_proceeds * 0.2, cash_shortfall)  # up to 20% in non-preferred

            buy_budget = max(0, sell_proceeds - cash_holdback)

            buy_needs = []
            for sym, target_val in acct_target.items():
                current_val = current_by_sym.get(sym, 0)
                if target_val > current_val + 100:
                    buy_needs.append((sym, round(target_val - current_val)))

            total_buy_need = sum(amt for _, amt in buy_needs)
            if total_buy_need > 0 and buy_budget > 0:
                scale = min(1.0, buy_budget / total_buy_need)
                for sym, need in buy_needs:
                    buy_amt = round(need * scale)
                    if buy_amt > 50:
                        # In offline validation, avoid quote calls solely for candidate buy tickers.
                        # In normal CACHE/LIVE mode, fetch a candidate price so share estimates populate.
                        _pricing_mode = str(pricing_diagnostics().get('pricing_mode', '')).upper()
                        price = PRICE_CACHE.get(sym, 0) if _pricing_mode == 'OFFLINE' else fetch_price(sym, url_template)
                        _buy_bucket = BUCKET_MAP.get(sym, 'Other')
                        _note = ''
                        if _buy_bucket in underrepresented_buckets:
                            _note = f'Adds underrepresented {_buy_bucket} sleeve; single ETF selected for this account'
                        acct_buys.append({'acct': acct, 'sym': sym, 'action': 'BUY',
                            'amount': buy_amt, 'shares': round(buy_amt / price, 2) if price > 0 else '',
                            'bucket': _buy_bucket, 'tax_cost': 0, 'tax_logic': 'Buy side has no realized gain; placement follows account-level asset-location preference.', 'note': _note})

            total_buy = sum(t['amount'] for t in acct_buys)
            net_cash = sell_proceeds - total_buy
            if net_cash > 50 and acct_sells:
                reason = 'builds cash toward target' if cash_holdback > 50 else 'residual'
                _existing_note = acct_sells[0].get('note', '')
                acct_sells[0]['note'] = (_existing_note + ' ' if _existing_note else '') + f'${net_cash:,} → cash ({reason})'

            if acct_sells or acct_buys:
                all_trades.extend(acct_sells)
                all_trades.extend(acct_buys)

    # Add wash-sale review notes after all buys/sells are known.
    for _t in all_trades:
        _wash_note = _wash_sale_review_note(_t, all_trades)
        if _wash_note:
            _t['note'] = (str(_t.get('note', '') or '') + _wash_note).strip()

    # Add informational cash rows after wash-sale review so existing cash that
    # funds buys, or proceeds retained as cash, is explicit in the trade table.
    all_trades = _append_cash_movement_rows(all_trades, _invest_positions, _acct_tax, _rebalance_settings(c)['min_trade_amount'])

    # Write trades table grouped by account subsections so each account's sells,
    # buys, tax treatment, subtotal, and net cash effect are reviewed together.
    trade_hdrs = ['Account', 'Tax Treatment', 'Symbol', 'Action', 'Amount', 'Shares', 'Bucket', 'Est. Tax Cost', 'Tax Logic', 'Note']

    if all_trades:
        action_order = {'SELL': 0, 'BUY': 1, 'USE CASH': 2, 'RAISE CASH': 2}
        all_trades = sorted(
            all_trades,
            key=lambda t: (
                str(t.get('acct', '')),
                action_order.get(str(t.get('action', '')).upper(), 9),
                str(t.get('bucket', '')),
                str(t.get('sym', '')),
            ),
        )
        trades_by_acct = defaultdict(list)
        for t in all_trades:
            trades_by_acct[t.get('acct', '')].append(t)

        grand_sells = 0; grand_security_buys = 0; grand_start_cash = 0; grand_ending_cash = 0
        for acct in sorted(trades_by_acct.keys()):
            acct_trades = trades_by_acct[acct]
            tax_type = _acct_tax.get(acct, 'taxable')
            acct_sells = sum(_safe_float(t.get('amount'), 0.0) for t in acct_trades if t.get('action') == 'SELL')
            acct_security_buys = sum(_safe_float(t.get('amount'), 0.0) for t in acct_trades if t.get('action') == 'BUY' and not _is_cash_position_trade(t))
            acct_cash_target = sum(_safe_float(t.get('amount'), 0.0) for t in acct_trades if t.get('action') == 'BUY' and _is_cash_position_trade(t))
            acct_cash_deployed = sum(_safe_float(t.get('amount'), 0.0) for t in acct_trades if t.get('action') == 'USE CASH')
            acct_cash_raised = sum(_safe_float(t.get('amount'), 0.0) for t in acct_trades if t.get('action') == 'RAISE CASH')
            acct_start_cash, acct_ending_cash, acct_cash_change = _projected_account_cash_after_trades(
                acct, _invest_positions.get(acct, {}), acct_trades, BUCKET_MAP, url_template
            )
            # acct_cash_target is shown as a Cash target/hold row, but ending cash
            # remains beginning cash plus sells minus non-cash buys so it ties
            # exactly to Total Portfolio Mix after trades.

            write_hdr(
                ws, r, 1,
                f'{display_account(acct, c)} — {TAX_LABELS.get(tax_type, tax_type)} — Sells ${acct_sells:,.0f} | Security Buys ${acct_security_buys:,.0f} | Ending Cash After Trades ${acct_ending_cash:,.0f}',
                BLUE, WHITE, span=10,
            )
            r += 1
            for i, th in enumerate(trade_hdrs, 1):
                write_hdr(ws, r, i, th, DGRAY, WHITE)
            # Line-item trades collapse under the account header/subtotal bars
            # (system review 2026-08-04 follow-up).
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1

            for t in acct_trades:
                is_sell = t['action'] == 'SELL'
                is_cash_move = str(t.get('action', '')).upper() in ('USE CASH', 'RAISE CASH')
                bg = 'FCE4D6' if is_sell else ('FFF2CC' if is_cash_move else 'E2EFDA')
                write_cell(ws, r, 1, display_account(t['acct'], c))
                write_cell(ws, r, 2, TAX_LABELS.get(tax_type, tax_type))
                write_cell(ws, r, 3, t['sym'], bold=True)
                write_cell(ws, r, 4, t['action'], bold=True, bg=bg)
                write_cell(ws, r, 5, t['amount'], fmt=FMT_DOLLAR, align='right')
                write_cell(ws, r, 6, t['shares'], fmt='#,##0.00', align='right')
                write_cell(ws, r, 7, t['bucket'])
                write_cell(ws, r, 8, t.get('tax_cost', 0), fmt=FMT_DOLLAR, align='right',
                           bg='E2EFDA' if t.get('tax_cost', 0) < 0 else ('FCE4D6' if t.get('tax_cost', 0) > 0 else None))
                write_cell(ws, r, 9, t.get('tax_logic', ''))
                write_cell(ws, r, 10, t.get('note', ''))
                if is_sell:
                    grand_sells += t['amount']
                elif t.get('action') == 'BUY' and not _is_cash_position_trade(t):
                    grand_security_buys += t['amount']
                ws.row_dimensions[r].outlineLevel = 1
                ws.row_dimensions[r].hidden = True
                r += 1

            grand_start_cash += acct_start_cash
            grand_ending_cash += acct_ending_cash
            write_cell(ws, r, 1, f'{display_account(acct, c)} Subtotal', bold=True, bg=LGRAY)
            write_cell(ws, r, 4, 'SELL', bold=True, bg=LGRAY)
            write_cell(ws, r, 5, acct_sells, fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
            write_cell(ws, r, 6, 'SECURITY BUY', bold=True, bg=LGRAY)
            write_cell(ws, r, 7, acct_security_buys, fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
            write_cell(ws, r, 8, 'Ending Cash After Trades', bold=True, bg=LGRAY)
            write_cell(ws, r, 9, acct_ending_cash, fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
            # Account-level subtotal; positive adds to account cash, negative deploys existing account cash.
            # Positive = cash added; negative = existing account cash deployed. No cross-account transfers are assumed.
            cash_note = f'Beginning cash ${acct_start_cash:,.0f}; cash change ${acct_cash_change:,.0f}. CASH target/hold rows are not counted as security buys.'
            if acct_cash_deployed > 0 or acct_cash_raised > 0:
                cash_note += f' Explicit CASH rows: deployed ${acct_cash_deployed:,.0f}; raised ${acct_cash_raised:,.0f}.'
            write_cell(ws, r, 10, cash_note, bg=LGRAY)
            r += 1

            # For taxable/trust SELL recommendations, show the lot-level
            # execution guidance directly below the account trade block. This
            # is the actionable tax-lot detail; the System/QC section only
            # reports data coverage.
            lot_rows_to_show = []
            for _trade in acct_trades:
                if str(_trade.get('action', '')).upper() != 'SELL':
                    continue
                for _lot in list(_trade.get('lot_guidance') or []):
                    lot_rows_to_show.append((_trade, _lot))
            if lot_rows_to_show:
                r += 1
                write_hdr(ws, r, 1, f'{acct} — Recommended sell lot guidance', ORANGE, WHITE, span=10)
                r += 1
                _lot_hdrs = ['Symbol', 'Purchase Date', 'Term', 'Shares to Sell', 'Proceeds', 'Cost Basis', 'Gain / Loss', 'Est. Tax Impact', 'Rate', 'Guidance']
                for i, h in enumerate(_lot_hdrs, 1):
                    write_hdr(ws, r, i, h, DGRAY, WHITE)
                # Lot-level detail collapses under the orange banner above
                # (system review 2026-08-04 follow-up).
                ws.row_dimensions[r].outlineLevel = 1
                ws.row_dimensions[r].hidden = True
                r += 1
                for _trade, _lot in lot_rows_to_show:
                    _gain_loss = _safe_float(_lot.get('gain_loss'), 0.0)
                    _tax_impact = _safe_float(_lot.get('tax_impact'), 0.0)
                    write_cell(ws, r, 1, _trade.get('sym'), bold=True)
                    write_cell(ws, r, 2, _lot.get('purchase_date', ''))
                    write_cell(ws, r, 3, _lot.get('term', ''))
                    write_cell(ws, r, 4, _lot.get('shares', ''), fmt='#,##0.00', align='right')
                    write_cell(ws, r, 5, _lot.get('proceeds', 0), fmt=FMT_DOLLAR, align='right')
                    write_cell(ws, r, 6, _lot.get('basis', 0), fmt=FMT_DOLLAR, align='right')
                    write_cell(ws, r, 7, _gain_loss, fmt=FMT_DOLLAR, align='right', bg='E2EFDA' if _gain_loss < -1 else ('FCE4D6' if _gain_loss > 1 else None))
                    write_cell(ws, r, 8, _tax_impact, fmt=FMT_DOLLAR, align='right', bg='E2EFDA' if _tax_impact < -1 else ('FCE4D6' if _tax_impact > 1 else None))
                    write_cell(ws, r, 9, _lot.get('tax_rate', 0), fmt=FMT_PCT, align='right')
                    write_cell(ws, r, 10, _lot.get('guidance', ''))
                    ws.row_dimensions[r].outlineLevel = 1
                    ws.row_dimensions[r].hidden = True
                    r += 1
                write_cell(ws, r, 1, 'Advisor review note', bold=True, fg='666666')
                write_cell(ws, r, 2, 'Specific-lot instructions should be reviewed against broker lot IDs, wash-sale windows, outside accounts, spouse accounts, and any same/substantially-identical replacement trades before execution.', fg='666666')
                ws.row_dimensions[r].outlineLevel = 1
                ws.row_dimensions[r].hidden = True
                ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=10)
                r += 1
            r += 1

        # Include accounts that had no recommended trades in the household cash
        # reconciliation so the grand total matches the Cash row in Total
        # Portfolio Mix after trades.
        no_trade_cash_start = 0.0
        no_trade_cash_ending = 0.0
        for _acct in sorted(set(_invest_positions.keys()) - set(trades_by_acct.keys())):
            _start_cash, _ending_cash, _cash_change = _projected_account_cash_after_trades(
                _acct, _invest_positions.get(_acct, {}), [], BUCKET_MAP, url_template
            )
            no_trade_cash_start += _start_cash
            no_trade_cash_ending += _ending_cash
        grand_start_cash += no_trade_cash_start
        grand_ending_cash += no_trade_cash_ending

        write_cell(ws, r, 1, 'Grand Total', bold=True)
        write_cell(ws, r, 4, 'SELL', bold=True); write_cell(ws, r, 5, grand_sells, fmt=FMT_DOLLAR, align='right', bold=True)
        r += 1
        write_cell(ws, r, 4, 'SECURITY BUY', bold=True); write_cell(ws, r, 5, grand_security_buys, fmt=FMT_DOLLAR, align='right', bold=True)
        r += 1
        write_cell(ws, r, 4, 'Cash Change', bold=True)
        write_cell(ws, r, 5, grand_ending_cash - grand_start_cash, fmt=FMT_DOLLAR, align='right', bold=True)
        write_cell(ws, r, 7, 'Change in cash = sells minus non-cash security buys; CASH target/hold rows are not counted as buys.')
        r += 1
        write_cell(ws, r, 4, 'Ending Cash After Trades', bold=True)
        write_cell(ws, r, 5, grand_ending_cash, fmt=FMT_DOLLAR, align='right', bold=True, bg='E2EFDA')
        _cash_reconcile_note = 'This should reconcile to the Cash row in Total Portfolio Mix after trades. No cross-account transfers are assumed.'
        if no_trade_cash_ending > 0:
            _cash_reconcile_note += f' Includes ${no_trade_cash_ending:,.0f} of unchanged cash in investment accounts without recommended trades.'
        write_cell(ws, r, 7, _cash_reconcile_note)
    else:
        write_cell(ws, r, 1, 'Portfolio is within tolerance — no trades needed.')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)

    r += 2
    write_hdr(ws, r, 1, 'Tax optimization diagnostics', ORANGE if deferred_taxable_trades else BLUE, WHITE, span=10)
    r += 1
    if global_optimizer_diagnostics:
        _diag_hdrs = ['Control / objective', 'Setting / result', 'What it protects against']
        for i, h in enumerate(_diag_hdrs, 1):
            write_hdr(ws, r, i, h, DGRAY, WHITE, span=1 if i < 3 else 8)
        r += 1
        for label, value, note in global_optimizer_diagnostics:
            write_cell(ws, r, 1, label, bold=True)
            write_cell(ws, r, 2, value)
            write_cell(ws, r, 3, note)
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=10)
            r += 1
        r += 1
    if deferred_taxable_trades:
        write_cell(ws, r, 1, 'Tax-aware deferred taxable sales: candidate taxable-account sells below were not recommended now because estimated realized-tax drag was high relative to the rebalance benefit. Use new contributions, dividends, tax-advantaged trades, or staged sales first.', fg=ORANGE)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
        _defer_hdrs = ['Account', 'Symbol', 'Deferred Amount', 'Bucket', 'Est. Tax Cost', 'Tax Drag', 'Reason']
        for i, h in enumerate(_defer_hdrs, 1):
            write_hdr(ws, r, i, h, DGRAY, WHITE)
        r += 1
        for d in deferred_taxable_trades:
            write_cell(ws, r, 1, display_account(d.get('acct'), c))
            write_cell(ws, r, 2, d.get('sym'), bold=True)
            write_cell(ws, r, 3, d.get('amount', 0), fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 4, d.get('bucket'))
            write_cell(ws, r, 5, d.get('tax_cost', 0), fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 6, d.get('tax_cost_pct', 0), fmt=FMT_PCT, align='right')
            write_cell(ws, r, 7, d.get('note'))
            ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=10)
            r += 1
    else:
        write_cell(ws, r, 1, 'Tax-aware deferred taxable sales: none. Recommended taxable sells, if any, passed the lot-level after-tax cost screen; tax-advantaged trades remain preferred for future rebalancing.')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1


    # ══════════════════════════════════════════════════════════════════════
    # PART 3: DETAIL & VERIFICATION — did it work, how good is it (Sections D + F)
    # ══════════════════════════════════════════════════════════════════════
    # Normalized bucket targets for the before/after comparison
    _nct = {k: v for k, v in BUCKET_TARGETS.items() if k not in ('Cash', 'Uncategorized')}
    _nct_sum = sum(_nct.values()) or 1.0
    NORM_TARGETS = {k: v / _nct_sum for k, v in _nct.items()}
    r += 3
    section_title(ws, r, 'PART 3 · DETAIL & VERIFICATION — before/after and risk analytics', 10); r += 2

    # ══════════════════════════════════════════════════════════════════════
    # SECTION D: Before & After Allocation (per account + portfolio-wide)
    # ══════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'BEFORE & AFTER REBALANCING', 10); r += 1
    write_cell(ws, r, 1, 'Shows current allocation, projected allocation after executing recommended trades, '
               'and remaining gap vs target. Positive delta = still over-allocated; negative = still under-allocated.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 2

    # Compute after-trade holdings per account per bucket
    # Start from current, apply trades
    after_by_acct_bucket = {}  # {acct: {bucket: value}}
    before_by_acct_bucket = {}
    acct_totals = {}

    for acct in sorted(_invest_positions.keys()):
        before_by_acct_bucket[acct] = defaultdict(float)
        after_by_acct_bucket[acct] = defaultdict(float)
        acct_total = 0
        for sym, shares in _invest_positions.get(acct, {}).items():
            price = fetch_price(sym, url_template)
            val = shares * price
            bucket = 'Cash' if sym == 'CASH' else BUCKET_MAP.get(sym, 'Other')
            before_by_acct_bucket[acct][bucket] += val
            after_by_acct_bucket[acct][bucket] += val
            acct_total += val
        acct_totals[acct] = acct_total

    # Apply trades to compute after state
    for t in all_trades:
        acct = t['acct']
        bucket = t['bucket']
        if t['action'] == 'SELL':
            after_by_acct_bucket[acct][bucket] -= t['amount']
            after_by_acct_bucket[acct]['Cash'] = after_by_acct_bucket[acct].get('Cash', 0) + t['amount']
        elif t['action'] == 'BUY':
            after_by_acct_bucket[acct][bucket] += t['amount']
            after_by_acct_bucket[acct]['Cash'] = after_by_acct_bucket[acct].get('Cash', 0) - t['amount']

    all_buckets_ordered = sorted(set(BUCKET_TARGETS.keys()) | {'Cash'}, key=lambda b: (-actual_buckets.get(b, 0), str(b)))
    if 'Uncategorized' in _held_buckets and 'Uncategorized' not in all_buckets_ordered:
        all_buckets_ordered.append('Uncategorized')

    # Rows with no actual before/after dollars add noise in the Before & After
    # Rebalancing section (module-level _hide_zero_before_after_row, see top of
    # file), especially when a target exists but non-liquid coverage already
    # eliminates the need for a liquid sleeve. Sub-dollar dust is treated as
    # zero because the workbook rounds dollar amounts to whole dollars.

    # ── Per-account before/after tables ───────────────────────────────────
    # Collapsed by default via Excel row outlining (system review 2026-08-04
    # follow-up): with N accounts this was N copies of a 10-col table stacked
    # open. The account total row stays visible as the group's summary row;
    # its detail collapses under a "+" until expanded. The two blank-header
    # spacer columns from the old 10-col layout are gone -- the "changed"
    # highlight is carried by the After $/% cell shading alone.
    for acct in sorted(_invest_positions.keys()):
        at = acct_totals.get(acct, 0)
        if at < 500:
            continue

        r += 1
        write_hdr(ws, r, 1, f'{display_account(acct, c)}  —  Total: ${at:,.0f}', BLUE, WHITE, span=8)
        r += 1

        ba_hdrs = ['Bucket', 'Before $', 'Before %', 'After $', 'After %', 'Target %', 'Delta pp', 'Status']
        for i, h in enumerate(ba_hdrs, 1):
            write_hdr(ws, r, i, h, DGRAY, WHITE)
        ws.row_dimensions[r].outlineLevel = 1
        ws.row_dimensions[r].hidden = True
        r += 1

        for bucket in all_buckets_ordered:
            before_val = before_by_acct_bucket[acct].get(bucket, 0)
            after_val = max(0, after_by_acct_bucket[acct].get(bucket, 0))
            if _hide_zero_before_after_row(before_val, after_val):
                continue
            before_pct = before_val / at if at > 0 else 0
            after_pct = after_val / at if at > 0 else 0

            if bucket == 'Cash' or bucket == 'Other':
                tgt_pct = 0  # cash is residual
            else:
                tgt_pct = NORM_TARGETS.get(bucket, 0)

            delta_pp = after_pct - tgt_pct
            if bucket in ('Cash', 'Uncategorized'):
                status = ''
                delta_pp = 0
            elif bucket in FIXED_INCOME_BUCKETS and fi_covered_full:
                status = '✓ Covered by fixed-income coverage'
                delta_pp = 0
            elif bucket in REAL_ESTATE_BUCKETS and re_covered_full:
                status = '✓ Covered by real-estate coverage'
                delta_pp = 0
            elif abs(delta_pp) < 0.02:
                status = '✓ On target'
            elif delta_pp > 0:
                status = f'Over +{delta_pp:.1%}'
            else:
                status = f'Under {delta_pp:.1%}'

            _changed = abs(after_val - before_val) > 50

            write_cell(ws, r, 1, bucket)
            write_cell(ws, r, 2, before_val, fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 3, before_pct, fmt=FMT_PCT, align='right')
            write_cell(ws, r, 4, after_val, fmt=FMT_DOLLAR, align='right',
                       bg='E2EFDA' if _changed else None)
            write_cell(ws, r, 5, after_pct, fmt=FMT_PCT, align='right',
                       bg='E2EFDA' if _changed else None)
            write_cell(ws, r, 6, tgt_pct if bucket not in ('Cash', 'Uncategorized') else '',
                       fmt=FMT_PCT if bucket not in ('Cash', 'Uncategorized') else None, align='right')
            write_cell(ws, r, 7, delta_pp if bucket not in ('Cash', 'Uncategorized') else '',
                       fmt='+0.0%;-0.0%' if bucket not in ('Cash', 'Uncategorized') else None, align='right',
                       bg='FCE4D6' if abs(delta_pp) > 0.02 and bucket not in ('Cash', 'Uncategorized') else None)
            write_cell(ws, r, 8, status)
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1

    # ── Portfolio-wide after-trade totals ─────────────────────────────────
    # System review 2026-08-04 follow-up: this used to also render its own
    # "PORTFOLIO TOTAL" 10-column table -- liquid-only, same bucket universe
    # as Total Portfolio Mix's After Trades columns, just missing the
    # non-liquid coverage rows. That table is gone; the Δ pp (After) column
    # on Total Portfolio Mix (Part 1, above) now carries the one figure it
    # added (After Trade Status already existed there).
    port_before = defaultdict(float)
    port_after = defaultdict(float)
    for acct in before_by_acct_bucket:
        for bucket, val in before_by_acct_bucket[acct].items():
            port_before[bucket] += val
        for bucket, val in after_by_acct_bucket[acct].items():
            port_after[bucket] += max(0, val)

    # Backfill the top Total Portfolio Mix table with the projected household
    # allocation after executing recommended trades.  Non-liquid coverage rows
    # stay unchanged; liquid rows use the same projected after-trade buckets as
    # the detailed before/after section above. (module-level
    # _after_status_for_total_mix, see top of file)

    for _label, _row in (_total_mix_rows or {}).items():
        _asset_type = _total_mix_types.get(_label, 'Liquid')
        _tgt = _total_mix_targets.get(_label, 0.0)
        if _asset_type == 'Non-liquid':
            _after_val = _total_mix_current_values.get(_label, 0.0)
        else:
            _after_val = port_after.get(_label, 0.0)
        _after_pct = _after_val / total_portfolio if total_portfolio > 0 else 0.0
        _after_status = _after_status_for_total_mix(_label, _asset_type, _after_pct, _tgt, fi_covered_full, re_covered_full)
        _changed = abs(_after_val - _total_mix_current_values.get(_label, 0.0)) > 50
        _covered = (_label in FIXED_INCOME_BUCKETS and fi_covered_full) or (_label in REAL_ESTATE_BUCKETS and re_covered_full)
        _after_delta_pp = (_after_pct - _tgt) if (_asset_type == 'Liquid' and _tgt and not _covered) else ''
        write_cell(ws, _row, 4, _after_val, fmt=FMT_DOLLAR, align='right', bg='E2EFDA' if _changed else None)
        write_cell(ws, _row, 5, _after_pct, fmt=FMT_PCT, align='right', bg='E2EFDA' if _changed else None)
        write_cell(ws, _row, 9, _after_status, bg='E2EFDA' if _changed else None)
        write_cell(ws, _row, 10, _after_delta_pp, fmt='+0.0%;-0.0%' if _after_delta_pp != '' else None,
                   align='right', bg='FCE4D6' if isinstance(_after_delta_pp, float) and abs(_after_delta_pp) > 0.02 else None)

    if _total_mix_total_row:
        write_cell(ws, _total_mix_total_row, 4, total_portfolio, fmt=FMT_DOLLAR, align='right', bold=True)
        write_cell(ws, _total_mix_total_row, 5, 1.0, fmt=FMT_PCT, align='right', bold=True)

    r += 1
    write_cell(ws, r, 1, 'Note: remaining Δ pp (After) values on Total Portfolio Mix above represent work for '
               'future contributions, new deposits, or cross-account rebalancing that requires distributions '
               'and contributions (taxable events).')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)

    # Pie charts are built on a separate sheet (see build_allocation_charts)
    # Store the chart data for the chart builder
    # Compute cash change from executable trades.  CASH target/hold rows are
    # not security buys, so excluding them keeps chart cash aligned with the
    # Cash row in Total Portfolio Mix and the trade-table Ending Cash line.
    _net_cash_from_trades = sum(t['amount'] for t in all_trades if t['action'] == 'SELL') - \
                            sum(t['amount'] for t in all_trades if t['action'] == 'BUY' and not _is_cash_position_trade(t))

    c['_alloc_chart_data'] = {
        'buckets': [],
        'before_vals': [],
        'after_vals': [],
    }
    chart_buckets = sorted(set(BUCKET_TARGETS.keys()) | {'Cash'}, key=lambda b: (-port_before.get(b, actual_buckets.get(b, 0)), str(b)))
    if pv_fixed_income > 0:
        chart_buckets.append('Fixed Income (Non-Liquid)')
    if home_equity > 0:
        chart_buckets.append('Real Estate (Non-Liquid)')

    for bkt in chart_buckets:
        c['_alloc_chart_data']['buckets'].append(bkt)
        if bkt == 'Cash':
            bv = sum(h.get('CASH', 0) for h in _invest_positions.values())
            av = bv + _net_cash_from_trades  # add cash from sales
        elif 'Fixed Income' in bkt:
            bv = av = pv_fixed_income
        elif 'Real Estate' in bkt:
            bv = av = home_equity
        else:
            bv = port_before.get(bkt, 0)
            av = max(0, port_after.get(bkt, 0))
        c['_alloc_chart_data']['before_vals'].append(max(0, bv))
        c['_alloc_chart_data']['after_vals'].append(max(0, av))

    # Tax-Efficient Rebalancing Sequence was six fully static, client-
    # independent steps (same text every build) -- moved to Sheet 23
    # Methodology's "Tax-Efficient Rebalancing Sequence" section (system
    # review 2026-08-04 follow-up), alongside Asset Location Guidance and the
    # rest of the plan's evergreen how-to content.
    r += 1
    write_cell(ws, r, 1, 'Tax-Efficient Rebalancing Sequence (contribute → rebalance in tax-advantaged accounts → '
               'reinvest dividends → tax-loss harvest → sell taxable as last resort → go gradual): see Sheet 23 Methodology.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 2

    # ══════════════════════════════════════════════════════════════════════
    # SECTION F: Efficient Frontier & Sharpe Ratio
    # ══════════════════════════════════════════════════════════════════════
    # Additive-only: surfaces the portfolio-analytics helpers in
    # src/optimization.py (efficient_frontier, risk_free_rate, sharpe_ratio,
    # and the 'sharpe' key on allocation_portfolio_stats) without touching any
    # existing allocation rows/formatting above. A full Excel scatter chart is
    # heavier to wire through the shared chart builder, so this ships as a
    # clearly-labeled data table (volatility, return, Sharpe per frontier
    # point) with the recommended portfolio's closest point highlighted.
    r += 1
    section_title(ws, r, 'EFFICIENT FRONTIER & SHARPE RATIO', 10); r += 1
    write_cell(ws, r, 1,
               "Long-only mean-variance efficient frontier traced over this household's eligible "
               "asset classes (same eligibility/inclusion logic as the recommended allocation above). "
               "The Sharpe ratio is risk-adjusted return: (expected return − risk-free rate) ÷ "
               "volatility. Higher Sharpe means more return per unit of risk.")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 2

    try:
        _ef_rf = _ao.risk_free_rate(c)
        _ef_recommended = _ao.allocation_portfolio_stats(c)
        _ef_points = _ao.efficient_frontier(c, n_points=15)
    except Exception as _ef_ex:
        _ef_rf = 0.0
        _ef_recommended = None
        _ef_points = []
    try:
        _ef_optimizer = _ao.allocation_portfolio_stats(c, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER)
    except Exception:
        _ef_optimizer = None
    try:
        _ef_max_sharpe = _ao.allocation_portfolio_stats(c, force_mode=_ap.ALLOCATION_MODE_MAX_SHARPE)
    except Exception:
        _ef_max_sharpe = None
    try:
        _ef_tangency = _ao.allocation_portfolio_stats(c, force_mode=_ap.ALLOCATION_MODE_TANGENCY)
    except Exception:
        _ef_tangency = None
    _ef_selected_label = _ap.allocation_mode_label(c.get('allocation_selection_mode', 'user_target'))

    write_hdr(ws, r, 1, 'Recommended Portfolio — Risk/Return Summary', BLUE, WHITE, span=10)
    r += 1
    if _ef_recommended:
        _ef_stat_rows = [
            ('Expected Return', _ef_recommended.get('expected_return', 0.0), FMT_PCT),
            ('Volatility (Std Dev)', _ef_recommended.get('volatility', 0.0), FMT_PCT),
            ('Geometric (Compounded) Return', _ef_recommended.get('geometric_return', 0.0), FMT_PCT),
            ('Risk-Free Rate', _ef_rf, FMT_PCT),
            ('Sharpe Ratio', _ef_recommended.get('sharpe', 0.0), '0.00'),
        ]
        for _label, _val, _fmt in _ef_stat_rows:
            _is_sharpe = _label == 'Sharpe Ratio'
            write_cell(ws, r, 1, _label, bold=True)
            write_cell(ws, r, 2, _val, fmt=_fmt, align='right', bg='E2EFDA' if _is_sharpe else None,
                       bold=_is_sharpe)
            r += 1
    else:
        write_cell(ws, r, 1, 'Recommended-portfolio risk/return statistics unavailable for this household.')
        r += 1

    r += 1
    write_hdr(ws, r, 1, 'Sharpe Ratio Across Allocation Modes', BLUE, WHITE, span=10)
    r += 1
    write_cell(ws, r, 1,
               'Max Sharpe (risk-budgeted) keeps the same risk level (equity/bond/cash split) as the '
               'optimizer recommendation but picks the equity sleeve with the best risk-adjusted return. '
               'Pure Tangency has no risk budget at all — it is the single portfolio with the highest '
               'possible Sharpe ratio, shown for reference. Both use the same Selection-driven candidate '
               'classes as the optimizer recommendation (2B. Asset Allocation): a class set to Exclude is '
               'never a candidate, and a class set to Consider alternate first and mapped to a covered '
               'source (guaranteed income, home equity, ...) is left out once that source meets the '
               'target — so large annuities/home equity already covering the bond/real-estate sleeves '
               'keeps both scoped to the classes they don\'t already decide. Pure Tangency can still '
               'recommend a very different risk level than this household\'s risk tolerance calls for '
               'within its candidate classes.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 1
    _mode_hdrs = ['Mode', 'Expected Return', 'Volatility', 'Sharpe Ratio']
    for i, h in enumerate(_mode_hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    for _mode_label, _stats in (
        (f'Currently Selected ({_ef_selected_label})', _ef_recommended),
        ('Optimizer Recommendation', _ef_optimizer),
        ('Max Sharpe (Risk-Budgeted)', _ef_max_sharpe),
        ('Pure Tangency', _ef_tangency),
    ):
        if not _stats:
            continue
        _is_tan = _mode_label == 'Pure Tangency'
        _row_bg = 'E2EFDA' if _is_tan else None
        write_cell(ws, r, 1, _mode_label, bold=True, bg=_row_bg)
        write_cell(ws, r, 2, _stats.get('expected_return', 0.0), fmt=FMT_PCT, align='right', bg=_row_bg)
        write_cell(ws, r, 3, _stats.get('volatility', 0.0), fmt=FMT_PCT, align='right', bg=_row_bg)
        write_cell(ws, r, 4, _stats.get('sharpe', 0.0), fmt='0.00', align='right', bg=_row_bg, bold=True)
        r += 1
    r += 1

    write_hdr(ws, r, 1, 'Efficient Frontier — Volatility vs. Return vs. Sharpe', BLUE, WHITE, span=10)
    r += 1
    if _ef_points:
        _ef_hdrs = ['Point #', 'Volatility', 'Expected Return', 'Sharpe Ratio', '']
        for i, h in enumerate(_ef_hdrs, 1):
            write_hdr(ws, r, i, h, DGRAY, WHITE)
        r += 1

        def _nearest_idx(_stats):
            if not _stats or not _ef_points:
                return None
            _vol = _stats.get('volatility')
            if _vol is None:
                return None
            return min(range(len(_ef_points)), key=lambda i: abs(_ef_points[i]['volatility'] - _vol))

        _markers = {
            _nearest_idx(_ef_recommended): 'Recommended',
            _nearest_idx(_ef_max_sharpe): 'Max Sharpe',
            _nearest_idx(_ef_tangency): 'Tangency',
        }
        _markers.pop(None, None)
        _markers_by_idx = {}
        for _idx, _tag in _markers.items():
            _markers_by_idx.setdefault(_idx, []).append(_tag)
        for _idx, _p in enumerate(_ef_points):
            _tags = _markers_by_idx.get(_idx)
            _row_bg = 'FFF2CC' if _tags else None
            write_cell(ws, r, 1, _idx + 1, align='center', bg=_row_bg)
            write_cell(ws, r, 2, _p['volatility'], fmt=FMT_PCT, align='right', bg=_row_bg)
            write_cell(ws, r, 3, _p['return'], fmt=FMT_PCT, align='right', bg=_row_bg)
            write_cell(ws, r, 4, _p['sharpe'], fmt='0.00', align='right', bg=_row_bg)
            write_cell(ws, r, 5, ('← Closest volatility to: ' + ', '.join(_tags)) if _tags else '', bg=_row_bg)
            r += 1
        r += 1
        write_cell(ws, r, 1,
                   'Each row minimizes portfolio variance for a target expected return (long-only, '
                   'weights sum to 100%). Highlighted rows have the volatility closest to a portfolio '
                   'above, shown for reference only — the frontier itself is not a trade recommendation. '
                   'Pure Tangency and Max Sharpe are computed directly (not sampled from this grid), so '
                   'their exact Sharpe ratio may exceed the closest grid row\'s.')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
    else:
        write_cell(ws, r, 1, 'Efficient frontier unavailable for this household (fewer than two eligible asset classes).')
        r += 1

    qc('4. Asset Allocation', 'Efficient frontier and Sharpe ratio computed for recommended allocation',
       bool(_ef_points) and _ef_recommended is not None,
       (f"{len(_ef_points)} frontier points; Sharpe={_ef_recommended.get('sharpe', 0.0):.2f}"
        if _ef_recommended else 'unavailable'))


__all__ = [
    'ASSET_ALLOCATION_BUCKET_MAP',
    'build_sheet4',
    '_candidate_symbols',
    '_hide_zero_before_after_row',
    '_status_for_bucket',
    '_after_status_for_total_mix',
    '_workbook_pricing_source_label',
    '_safe_float',
    '_trade_tax_rates',
    '_lot_purchase_year',
    '_lot_is_long_term',
    '_estimate_taxable_sale',
    '_lot_guidance_summary',
    '_taxable_sell_decision',
    '_wash_sale_review_note',
    '_is_cash_position_trade',
    '_projected_account_cash_after_trades',
    '_append_cash_movement_rows',
    '_rebalance_settings',
    '_bucket_location_fit',
    '_bucket_is_high_growth',
    '_bucket_is_fixed_income',
    '_location_weight',
]

