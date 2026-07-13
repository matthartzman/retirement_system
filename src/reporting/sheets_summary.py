from .workbook_common import *
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



# ── Tax-aware trade optimization helpers ─────────────────────────────────────
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
    state = 0.0
    try:
        state_key = str(c.get('state', '') or '').strip().upper()
        rules = getattr(_td, 'STATE_TAX_RULES', {}) or {}
        if state_key in rules:
            state = _safe_float(rules.get(state_key, {}).get('rate', 0.0), 0.0)
    except Exception:
        state = 0.0
    if not state and str(c.get('state', '') or '').strip().upper() == 'IL':
        state = 0.0495
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
    except Exception as exc:
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

def _tlh_recommendation_row(c, rows, rec_no):
    """Executive Summary recommendation row for tax-loss harvesting.

    When tlh_policy is 'apply', the value is the actual lifetime tax value
    realized in the projection net of transaction cost. Otherwise it's the
    net value of opportunities available today (analyze_only/off), so the
    line still appears when there's something worth acting on.
    """
    from .. import tlh as _tlh
    policy = str(c.get('tlh_policy', 'off') or 'off')
    if policy == 'apply':
        lifetime_value = sum(float(r.get('tlh_tax_value', 0) or 0) - float(r.get('tlh_transaction_cost', 0) or 0)
                              for r in rows)
        if lifetime_value <= 0:
            return None
        return (rec_no, 'Tax-Loss Harvesting (Active)',
                'Qualifying loss lots in taxable accounts are harvested annually against gains, then up to $3,000/yr of ordinary income, with carryforward tracked.',
                f"~{c.get('tlh_transaction_cost_bps', 2):.0f} bps transaction cost",
                f"~${lifetime_value:,.0f} lifetime tax value (net of cost)", 'Sheet 2I')
    plan_start = int(c.get('plan_start', rows[0]['year'] if rows else 2026))
    first_row = rows[0] if rows else {}
    scan = _tlh.scan_harvest_opportunities(
        c, plan_start,
        ordinary_income=float(first_row.get('taxable_inc', 0) or 0),
        existing_lt_gain=float(first_row.get('ltcg_gain', 0) or 0),
        annual_return=float(c.get('ret', 0.06) or 0.06),
        years_to_step_up=max(1, int(c.get('h_death_yr', plan_start + 20)) - plan_start),
        fraction_sold_before_death=float(c.get('tlh_fraction_sold_before_death', 0.5) or 0.5),
        transaction_cost_bps=float(c.get('tlh_transaction_cost_bps', 2.0) or 0.0),
        min_loss_dollars=float(c.get('tlh_min_loss_dollars', 500.0) or 0.0),
        min_loss_pct=float(c.get('tlh_min_loss_pct', 0.05) or 0.0),
        annual_ceiling=float(c.get('tlh_annual_ceiling', 0.0) or 0.0),
    )
    net = scan['totals']['net_value']
    if net <= 0:
        return None
    return (rec_no, 'Tax-Loss Harvesting Opportunity Available',
            f"{len(scan['opportunities'])} loss lot(s) in taxable accounts meet the harvesting threshold this year.",
            f"~${scan['totals']['transaction_cost']:,.0f} transaction cost",
            f"~${net:,.0f} net lifetime value; set tlh_policy=apply to automate", 'Sheet 2I')


def build_sheet1(ws, c, rows, mc_data):
    """Executive Summary"""
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 55
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 20

    section_title(ws, 1, f"EXECUTIVE SUMMARY — {c['h_name']} & {c['w_name']} Family", 6)

    write_hdr(ws, 2, 1, 'Plan Overview', BLUE, WHITE, span=6)
    data = [
        ('Plan Prepared',          str(datetime.date.today())),
        ('Clients',                f"{c['h_name']} (DOB: {c['h_dob_yr']}) & {c['w_name']} (DOB: {c['w_dob_yr']})"),
        ('Residence State',        c['state']),
        ('Plan Horizon',           f"{c['plan_start']} – {c['plan_end']}"),
        ('Statutory Version',      'OBBBA (One Big Beautiful Bill Act), signed July 4 2025'),
        ('Workbook Pricing Source', _workbook_pricing_source_label()[0]),
    ]
    r = 3
    for label, value in data:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, value)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    # Headline Numbers
    r += 1
    write_hdr(ws, r, 1, 'Headline Numbers', NAVY, WHITE, span=6); r+=1
    yr0 = rows[0]; yrn = rows[-1]
    success = mc_data.get('success_rate', 0.0)
    lifetime_tax = sum(row['total_tax'] for row in rows)
    terminal_nw  = yrn['total_nw']
    roth_benefit = sum(row.get('roth_conv',0)*0.22 for row in rows)   # approx

    headlines = [
        ('Starting Net Worth (Y0)',        yr0['total_nw'],  FMT_DOLLAR),
        ('Terminal Net Worth (Yn)',         terminal_nw,       FMT_DOLLAR),
        ('Lifetime Federal Tax (estimated)',lifetime_tax,       FMT_DOLLAR),
        ('Plan Success Rate (Monte Carlo)', success,           FMT_PCT),
        ('Model Risk Rating', (mc_data.get('model_risk') or {}).get('rating', mc_data.get('model_risk_rating','')), None),
        ('Advisor-ready status', (c.get('advisor_readiness') or {}).get('status','ILLUSTRATION_ONLY'), None),
        ('MC Success 95% CI Low',       mc_data.get('success_rate_ci_low', success), FMT_PCT),
        ('MC Success 95% CI High',      mc_data.get('success_rate_ci_high', success), FMT_PCT),
        ('Estimated Tax Saved — Roth Strategy', roth_benefit,  FMT_DOLLAR),
        ('Recommended SS Claim Age',        70,                None),
    ]
    for label, value, fmt in headlines:
        c1 = write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        c2 = write_cell(ws, r, 2, value, fmt=fmt, bold=True, bg=GRAY)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    # Recommendations
    r += 1
    write_hdr(ws, r, 1, 'Priority Recommendations & Action Items', ORANGE, WHITE, span=6); r+=1
    hdrs = ['#','Recommendation','Rationale','Est. Cost ($/yr)','Est. Value ($/yr)','Source Sheet']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r+=1
    recs = [
        # (No, Recommendation, Rationale, Cost/yr, Value/yr, Sheet)
        (1,'Claim Social Security at Age 70',
           'Maximizes benefit by 32% vs age 67; break-even ~12 yrs; survivor gets 100% of higher benefit',
           '$0','~$9,700/yr incremental vs age 67','Sheet 10'),
        (2,'Roth conversions through the configured conversion window',
           'Use the selected Roth strategy from Sheet 11; forced conversions are separated from voluntary optimizer choices.',
           'Tax cost depends on selected strategy','Compare candidate scores, lifetime tax, terminal value, and legacy/estate components on Sheet 11','Sheet 11'),
        (3,'Credit Shelter Trust at First Death',
           'Preserves IL $4M exemption at first death; assets bypass survivor estate for IL tax purposes',
           '$2,500–$5,000 (legal)','~$320K IL estate tax avoided on $4M (8% avg rate)','Sheet 14'),
        (4,'DAF contribution in the highest-income planning year',
           'Fund DAF in high-income year; claim deduction while SALT still elevated; grant out over 2027-2035',
           '$0 (charitable intent)','~$9,600 tax deduction at 24% marginal rate','Sheet 12'),
        (5,'Hybrid Life/LTC Policy — Start 2027',
           'Face value $250K–$500K covers facility care risk; avoids $113K–$213K annual deficit in worst case',
           '$8,000–$15,000/yr premiums','Protects $500K–$2M of estate from LTC depletion','Sheet 19'),
        (6,'S-Corporation vs LLC (Current: S-Corp)',
           'S-Corp reasonable salary $80K on $290K income saves ~$30K SE tax minus $2,500 admin cost',
           '$2,500/yr admin cost','~$27,500/yr net SE tax savings','Sheet 9'),
        (7,'QTIP Trust to Manage Annuity Post-First-Death',
           'Annuity income flows to QTIP for survivor benefit; controls ultimate disposition to heirs',
           '$3,000–$5,000 (legal)','Qualifies for marital deduction; defers estate tax','Sheet 14'),
        (8,'Set Reserve Requirement by Year Range',
           'Use start year, end year, and years of expenses to retain; default is 0 years',
           '$0 (allocation only)','Can reduce sequence-of-returns risk when a reserve is intentionally selected','Sheet 6'),
        (9,'Illinois Residency Review',
           'Moving to FL/TX saves $0 income tax (IL exempts retirement income) but saves IL estate tax',
           'Relocation costs','~$320K IL estate tax if estate > $4M; no income tax savings','Sheet 13'),
    ]
    _tlh_rec = _tlh_recommendation_row(c, rows, len(recs) + 1)
    if _tlh_rec:
        recs.append(_tlh_rec)
    for rec in recs:
        for i, val in enumerate(rec, 1):
            write_cell(ws, r, i, val, bold=(i==1), align='left' if i>1 else 'center')
        r+=1

    # Release notes
    r+=1
    write_cell(ws, r, 1, 'Release Notes', bold=True, bg=LGRAY)
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)
    r+=1
    _pricing_label, _pricing_note = _workbook_pricing_source_label()
    notes = [
        f"Built: {datetime.date.today()}",
        f"Workbook pricing source: {_pricing_label}. {_pricing_note}",
        "Law assumptions are data-driven in tax_data.py / tax_constants.csv; see Methodology for tax-year provenance.",
        "Annuity Model: Age-86 principal recovery; 20% dividends reinvested, 80% cash; flat guaranteed payment continues post-recovery",
        "Auto Depreciation: Straight-line over 7 years (CSV: Other Assets > Autos > depreciation_years)",
        "Live ETF prices use FMP → Yahoo → Alpha Vantage → Stooq → cache → cost basis; ticker-level pricing source is shown on holdings reports.",
    ]
    for note in notes:
        write_cell(ws, r, 1, note, bg=GRAY)
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)
        r+=1

    qc('1. Executive Summary','Headline numbers present', True, f"NW: ${terminal_nw:,.0f}")


def build_sheet2(ws, c, rows):
    """Assumptions & Tax Law"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'ASSUMPTIONS & TAX LAW — Editable Input Tables', 8)

    def write_section(start_row, title, items):
        r = start_row
        write_hdr(ws, r, 1, title, BLUE, WHITE, span=4); r+=1
        write_hdr(ws, r, 1, 'Parameter', DGRAY, WHITE)
        write_hdr(ws, r, 2, 'Value', DGRAY, WHITE)
        write_hdr(ws, r, 3, 'Units', DGRAY, WHITE)
        write_hdr(ws, r, 4, 'Note', DGRAY, WHITE); r+=1
        for label, value, units, note in items:
            write_cell(ws, r, 1, label, bg=LGRAY)
            cell = ws.cell(row=r, column=2, value=value)
            input_style(ws, cell)
            # Apply number format based on units
            if units in ('decimal', '%', 'pct'):
                cell.number_format = '0.0%'  # 0.025 → 2.5%
            elif units == 'USD':
                if isinstance(value, (int, float)) and value != float('inf'):
                    cell.number_format = '$#,##0'  # 23200 → $23,200
            elif units == 'years':
                cell.number_format = '0'
            write_cell(ws, r, 3, units)
            write_cell(ws, r, 4, note)
            r+=1
        return r+1

    r = 2
    _heard = c.get('model_heard_assumptions') or {}
    def _onoff(v):
        return 'On' if bool(v) else 'Off'
    def _pct(v):
        try:
            n = float(v or 0.0)
            if abs(n) <= 1.0:
                n *= 100.0
            return f'{n:.2f}%'
        except Exception:
            return 'not set'
    def _money(v):
        try:
            return f'${float(v or 0.0):,.0f}'
        except Exception:
            return 'not set'
    if _heard:
        _ss = _heard.get('social_security') or {}
        _hc = _heard.get('wellness') or {}
        _taxable = _heard.get('taxable_income') or {}
        _roth = _heard.get('roth_and_irmaa') or {}
        _estate = _heard.get('tax_and_estate') or {}
        _mc = _heard.get('monte_carlo') or {}
        _alloc = _heard.get('allocation') or {}
        _rep = _heard.get('reporting') or {}
        _cya = _heard.get('current_year_actuals') or {}
        if _cya:
            _remaining_pct = _pct(_cya.get('remaining_fraction'))
            if _cya.get('flows_blended'):
                _overrides = []
                if _cya.get('earned_remainder_overridden'):_overrides.append('earned income')
                if _cya.get('spend_remainder_overridden'):_overrides.append('spending')
                _override_note = f" Remainder-of-year {' and '.join(_overrides)} used a manual override instead of the linear pro-rated estimate." if _overrides else ''
                _cya_text = f"{_cya.get('current_year')}: income/spending actual through {_cya.get('ytd_end')}, projected for the remaining {_remaining_pct} of the year; account growth/contributions prorated to that same remainder.{_override_note}"
            elif _cya.get('flow_blend_skipped_by_user_choice'):
                _cya_text = f"{_cya.get('current_year')}: modeled as fully hypothetical by user choice (ytd_blend_enabled = FALSE) — real income/spending actuals tracked through {_cya.get('ytd_end')} were excluded; income/spending shown as a full-year projection. Account growth/contributions are still prorated to the remaining {_remaining_pct} of the year, since that proration is date math, not real-data blending."
            else:
                _cya_text = f"{_cya.get('current_year')}: account growth/contributions prorated to the remaining {_remaining_pct} of the year; income/spending shown as a full-year projection (add YTD actuals in Settings to blend real results)."
        else:
            _cya_text = 'Not available for this build.'
        _heard_items = [
            ('Current-year actuals blend', _cya_text, 'text', 'Action: keep YTD transactions and each account\'s Prior Year End Balance current every January so the current-year row reflects real results, not just a full-year assumption.'),
            ('Time horizon', _heard.get('plan_years'), 'text', 'Sets the years included in every income, tax, spending, and terminal-net-worth calculation.'),
            ('Social Security income', f"Claim ages {str(c.get('h_nick') or c.get('h_name') or 'Member 1')}/{str(c.get('w_nick') or c.get('w_name') or 'Member 2')}: {_ss.get('husband_claim_age')}/{_ss.get('wife_claim_age')}; funding haircut {_pct(_ss.get('funding_discount_pct'))} starting {_ss.get('funding_discount_year')}", 'text', 'Action: set the funding haircut to 0% for one scenario if you want to isolate this drag on terminal net worth.'),
            ('Wellness cash flow', f"Bridge monthly {_money(_hc.get('bridge_premium_monthly_today') or (float(_hc.get('bridge_premium_today') or 0)/12))}; Medicare B/D/G monthly {_money(float(_hc.get('part_b_monthly_today') or 0)+float(_hc.get('part_d_monthly_today') or 0)+float(_hc.get('part_g_monthly_today') or 0))}; OOP {_money(_hc.get('oop_estimate_today'))}; ACA PTC {_onoff(_hc.get('aca_ptc_enabled'))}", 'text', 'Action: if terminal net worth fell, temporarily zero bridge/Medicare/OOP costs to quantify wellness impact, then restore realistic values.'),
            ('Taxable portfolio income', _taxable.get('portfolio_distributions_mode'), 'text', 'Annual dividends/interest can raise AGI, Social Security taxation, IRMAA, NIIT, and reduce Roth-conversion room. Action: review asset location and distribution yields.'),
            ('Roth / IRMAA guardrails', f"Policy {_roth.get('roth_policy')}; IRMAA mode {_roth.get('irmaa_guardrail_mode')}; target {_roth.get('irmaa_target_tier')}; headroom {_pct(_roth.get('irmaa_headroom_usage_pct'))}", 'text', 'Action: if conversions look unexpectedly low, check the IRMAA guardrail and ACA PTC-loss weight before overriding the Roth policy.'),
            ('Estate and survivor treatment', f"Basis step-up {_onoff(_estate.get('basis_step_up_at_death'))}; CST {_onoff(_estate.get('credit_shelter_trust_enabled'))}; CST funded/excluded {_money(_estate.get('cst_funded_total'))}; portability {_onoff(_estate.get('federal_portability_enabled'))}", 'text', 'Action: compare one rebuild with CST or estate objective off if you need to isolate estate-policy impact.'),
            ('Monte Carlo risk mode', f"{_mc.get('engine_mode', 'not set')} with {_mc.get('simulation_count', 'not set')} main paths and {_mc.get('sensitivity_simulation_count', 'not set')} sensitivity paths", 'text', 'Action: raise path counts for final advisor review; raise max_build_seconds if exact scalar MC runs too long.'),
            ('Allocation and real-dollar reporting', f"Allocation mode {_alloc.get('selection_mode')}; real-dollar rows {_onoff(_rep.get('real_dollar_rows_available'))} using base year {_rep.get('real_dollar_base_year')}", 'text', 'Action: use real-dollar outputs for purchasing-power comparisons and nominal outputs only for like-for-like workbook runs.'),
        ]
        r = write_section(r, 'What the Model Used — Plain-English Impact Checks', _heard_items)

    r = write_section(r, 'Economic Assumptions', [
        ('Inflation (General)',        c['inf'],       'decimal', '2.50% annual'),
        ('SS COLA',                    c['ss_cola'],   'decimal', '2.00% annual'),
        ('Medicare Inflation',         c['med_inf'],   'decimal', '5.50% annual'),
        ('Portfolio Nominal Return',   c['ret'],       'decimal', 'No-volatility deterministic reference return; MC may use asset-class covariance and sampled geometric returns'),
        ('Fed Bracket Inflator',       c['brk_inf'],   'decimal', '2.00%/yr'),
        ('SS Taxable Fraction',        c['ss_taxable'],'decimal', '85%'),
        ('Roth Conversion Target Bracket', c['roth_brk'], 'decimal', 'Configured target bracket used when the selected strategy fills bracket headroom.'),
        ('Roth Legacy Objective Mode', c.get('roth_legacy_objective_mode', 'OFF'), 'text', 'OFF, LOW, BALANCED, or STRONG; weights future tax-rate risk and inheritance tax burden in Roth conversion selection.'),
        ('Roth Future Tax Stress', c.get('roth_future_tax_rate_stress_pct', 0.0), 'decimal', 'Additional ordinary-tax-rate stress used only in the Roth conversion objective.'),
        ('Heir Ordinary Tax Assumption', c.get('roth_heir_ordinary_tax_rate_assumption', 0.0), 'decimal', 'Estimated heir ordinary rate used to score inherited pre-tax balances.'),
    ])

    # Version 7.5.2: make optimizer assumptions visible in the workbook. These
    # values affect the recommended allocation engine only. They do not change
    # deterministic projection return, Monte Carlo return distribution, or live
    # market pricing unless those separate assumptions are edited.
    _cm_diag = _ao.apply_capital_market_config(c)
    _asset_items = [
        ('Capital Market Assumption Mode', _cm_diag.get('assumption_mode', 'PRESET'), 'text', 'PRESET uses built-in selectable horizon/preset assumptions; CUSTOM_FILE reads expert CSV assumptions.'),
        ('Capital Market Horizon', _cm_diag.get('horizon_years', 30), 'years', 'Supported horizons: 1, 3, 5, 10, 20, 25, 30 years. 30 is the long-term baseline.'),
        ('Capital Market Preset', _cm_diag.get('preset', 'BASELINE'), 'text', 'CONSERVATIVE, BASELINE, or AGGRESSIVE. These are planning assumptions, not live forecasts.'),
        ('Correlation Mode', _cm_diag.get('correlation_assumption_mode', 'PRESET'), 'text', 'PRESET, ADVANCED, or CUSTOM_FILE. Pairwise correlations affect diversification benefit.'),
        ('Correlation Preset', _cm_diag.get('correlation_preset', 'MODERATE'), 'text', 'LOW, MODERATE, HIGH, or STRESS. Stress assumes weaker diversification.'),
    ]
    _targets = _ap.normalize_targets(c.get('allocation_target_pct') or getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}))
    _target_sum = c.get('allocation_target_sum', sum(_targets.values()))
    _alloc_mode = _ap.normalize_allocation_mode(c.get('allocation_selection_mode', 'user_target'))
    _alloc_source_label = 'Optimizer-defined allocation' if _alloc_mode == _ap.ALLOCATION_MODE_OPTIMIZER else 'User-defined allocation'
    _pricing_label, _pricing_note = _workbook_pricing_source_label()
    _asset_items.append(('Workbook Pricing Source', _pricing_label, 'text',
                         _pricing_note or 'Actual quote source used for this workbook build.'))
    _asset_items.append(('Asset Allocation Recommendation Source', _alloc_source_label, 'text',
                         f'Selected in the UI and stored in Plan Data CSV as allocation_selection_mode={_alloc_mode}; this drives the workbook asset allocation recommendations.'))
    _asset_items.append(('Allocation Selection Mode', _ap.allocation_mode_label(_alloc_mode), 'text',
                         'UI toggle: use the optimizer recommendation or use the user-specified target_pct allocation.'))
    _asset_items.append(('Optimizer Recommendation Basis', 'Visible as recommendation', 'text',
                         getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', '')) )
    _asset_items.append(('User-Specified Allocation Total', _target_sum, 'decimal',
                         'Must equal 100%. If selected as the allocation mode, these target_pct rows drive allocation recommendations.'))
    _override_targets = c.get('allocation_optimizer_override_pct') or {}
    _override_sum = c.get('allocation_optimizer_override_sum', sum(float(v or 0) for v in _override_targets.values()) if isinstance(_override_targets, dict) else 0.0)
    _asset_items.append(('Optimizer Override Total', _override_sum, 'decimal',
                         '0% or blank means the computed optimizer target is used. If any optimizer override is entered, override percentages must total 100%.'))
    for _cls in getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}):
        _ov = float((_override_targets or {}).get(_cls, 0.0) or 0.0)
        _asset_items.append((f'Optimizer Override — {_cls}', _ov, 'decimal',
                             'Optional optimizer-mode override. If any override row is nonzero, the optimizer override replaces the computed optimizer target and must total 100%.'))
    for _cls, _pct in _targets.items():
        _defs = _ao.ASSET_CLASSES.get(_cls, {})
        _examples = ', '.join(_ap.ETF_CANDIDATES.get(_cls, [])[:3])
        _edu_note = _defs.get('education', '') if isinstance(_defs, dict) else ''
        _asset_items.append((f'User Target — {_cls}', _pct, 'decimal',
                             f'{_ap.default_note(_cls)} User may override this percentage; all target_pct rows must total 100%. {_edu_note}'))
        if _examples:
            _asset_items.append((f'{_cls} Example Vehicles', _examples, 'text',
                                 'Three examples used when the class is recommended but not currently represented. These are examples, not personalized trade instructions.'))
    try:
        _optimizer_view = _ao.compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER)
        for _cls, _pct in (_optimizer_view.get('liquid_targets') or {}).items():
            _asset_items.append((f'Optimizer Target — {_cls}', _pct, 'decimal',
                                 'Computed recommendation using risk tolerance, withdrawal rate, guaranteed-income/home-equity coverage, capital-market assumptions, correlations, glide path, and inflation-sensitive spending.'))
    except Exception as _ex:
        _asset_items.append(('Optimizer Target Snapshot', 'Unavailable', 'text', str(_ex)))
    r = write_section(r, 'Asset Allocation Selection and Recommendations', _asset_items)

    _reb = _rebalance_settings(c)
    r = write_section(r, 'Global Tax-Location Rebalancing Controls', [
        ('Trade Optimizer Mode', _reb['mode'], 'text', 'GLOBAL_TAX_AWARE solves household-level drift/tax/location tradeoffs; HEURISTIC uses the prior account-by-account engine.'),
        ('Objective', 'Minimize drift + tax cost + turnover + location inefficiency', 'text', 'A conservative linear objective balances diversification against taxes, turnover, and account-location fit.'),
        ('Maximum Turnover', _reb['max_turnover_pct'], 'decimal', 'Addresses unintended consequence: excessive turnover and noisy small improvements.'),
        ('Minimum Trade Amount', _reb['min_trade_amount'], 'USD', 'Addresses false precision and operational burden.'),
        ('Taxable Gain Policy', _reb['taxable_gain_policy'], 'text', 'NEVER, DRIFT_THRESHOLD, WITHIN_BUDGET, or ALWAYS; controls tax tail wagging the dog and income-timing effects.'),
        ('Taxable Gain Budget', _reb['taxable_gain_budget_annual'], 'USD', 'Limits estimated tax cost from taxable gain sales in one workbook cycle.'),
        ('Max Tax Cost', _reb['max_tax_cost_bps'], 'bps', 'Basis-point tax-drag limit for taxable sales before deferral.'),
        ('Asset Location Strength', _reb['asset_location_strength'], 'text', 'LIGHT/BALANCED/STRONG controls how hard the optimizer pushes Roth growth, pre-tax income assets, and taxable tax-efficient equity.'),
        ('Max Account Single Asset', _reb['max_account_single_asset_pct'], 'decimal', 'Reduces account-level concentration risk.'),
        ('Max Roth High-Growth Tilt', _reb['max_roth_high_growth_pct'], 'decimal', 'Limits unintended high-volatility concentration in Roth accounts.'),
        ('Annuity calibration dependency', 'Carrier-illustration dependent', 'text', 'PV/reserve and death-benefit figures use editable calibration assumptions; refresh against current carrier illustrations before annuity sale, replacement, or valuation decisions.'),
        ('Max Pre-Tax Fixed Income Tilt', _reb['max_pre_tax_fixed_income_pct'], 'decimal', 'Limits unintended bond-heavy pre-tax allocation and future RMD concentration risk.'),
        ('Wash-Sale Policy', _reb['wash_sale_policy'], 'text', 'Workbook flags review items; it does not certify wash-sale compliance or see outside/spousal trades.'),
        ('Solver Fallback Policy', _reb['solver_fallback_policy'], 'text', 'HEURISTIC keeps workbook usable if the global optimization problem is infeasible.'),
    ])

    r = write_section(r, 'Federal Tax Brackets — Tax Reference Year', [
        ('10% bracket top',     23200,  'USD', 'inflates at bracket inflator'),
        ('12% bracket top',     94300,  'USD', ''),
        ('22% bracket top',    201050,  'USD', ''),
        ('24% bracket top',    383900,  'USD', ''),
        ('32% bracket top',    487450,  'USD', ''),
        ('35% bracket top',    731200,  'USD', ''),
        ('37%+',               float('inf'), 'USD', ''),
    ])

    r = write_section(r, 'SALT Cap Schedule', [
        ('2025 SALT Cap', 40000, 'USD', 'Phase-down: max(cap - 0.30×max(MAGI-500K,0), 10000)'),
        ('Reference-Year SALT Cap', 40400, 'USD', ''),
        ('2027 SALT Cap', 40804, 'USD', ''),
        ('Reference-Year + 2 SALT Cap', 41212, 'USD', ''),
        ('Reference-Year + 3 SALT Cap', 41624, 'USD', ''),
        ('Post-Schedule SALT Cap', 10000, 'USD', 'REVERTS to $10K — model must honor this'),
    ])

    r = write_section(r, 'Other Statutory Parameters', [
        ('§121 Exclusion (MFJ)',         500000,   'USD', 'Home sale gain exclusion'),
        ('QCD Annual Limit (per person)', 108000,   'USD', '2025, indexed'),
        ('Federal Estate Exemption (MFJ)',30000000, 'USD', 'Indexed from the tax reference year'),
        ('IL State Estate Exemption',     c['il_exempt'],  'USD', f'{"With CST doubling" if c.get("cs_enabled") else "No portability"}, cliff structure'),
        ('Annual Gift-Tax Exclusion',     19000,    'USD', 'tax reference year, per donee'),
        ('RMD Start Age',                 75,       'years','SECURE 2.0 §107 — born 1960+'),
        ('NIIT Rate',                     0.038,    'decimal','3.8% on NII above MAGI threshold'),
        ('NIIT MAGI Threshold (MFJ)',     250000,   'USD', 'NOT indexed'),
        ('Standard Deduction MFJ — Reference Year',  31500,    'USD', '+ $1,650/spouse age 65+'),
        ('IRMAA Tier 2 Threshold (MFJ)', 268000,   'USD', 'reference-year threshold, inflated annually'),
    ])

    # Projected brackets table (simplified)
    r += 1
    write_hdr(ws, r, 1, 'Projected Target-Bracket Reference — MFJ', NAVY, WHITE, span=6); r+=1
    write_hdr(ws, r, 1, 'Year', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Reference Bracket Top', DGRAY, WHITE)
    r += 1
    for yr in range(c['plan_start'], min(c['plan_end']+1, c['plan_start']+31)):
        top = 201050 * (1+c['brk_inf'])**(yr - TAX_BASE_YEAR)
        write_cell(ws, r, 1, yr, fmt=FMT_YEAR, align='center')
        write_cell(ws, r, 2, top, fmt=FMT_DOLLAR)
        r += 1

    qc('2. Assumptions', 'All major parameters in editable cells', True, '')


def build_sheet3(ws, c, rows):
    """Balance Sheet (Today)"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, f'BALANCE SHEET — As of {datetime.date.today()}', 6)

    yr0 = rows[0]
    r = 3

    def write_group(title, items):
        nonlocal r
        write_hdr(ws, r, 1, title, BLUE, WHITE, span=3); r+=1
        group_total = 0
        for acct, bal, note in items:
            write_cell(ws, r, 1, '  '+acct)
            write_cell(ws, r, 2, bal, fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 3, note)
            group_total += bal
            r += 1
        write_cell(ws, r, 1, f'  Total {title}', bold=True, bg=LGRAY)
        write_cell(ws, r, 2, group_total, fmt=FMT_DOLLAR, bold=True, bg=LGRAY, align='right')
        write_cell(ws, r, 3, '', bg=LGRAY)
        r += 1
        return group_total

    write_hdr(ws, 2, 1, 'ASSETS', NAVY, WHITE)
    write_hdr(ws, 2, 2, 'Value ($)', NAVY, WHITE)
    write_hdr(ws, 2, 3, 'Notes', NAVY, WHITE)
    r = 3

    # Annuities / Income streams (PV)
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    ann_assets = [
        (f'{_n2} Pension (PV of future income)', yr0['pension_pv'], 'PV through mortality'),
        (f'{_n2} Single Annuity (PV)',            yr0['w_single_pv'], ''),
        (f'{_n2} Joint Annuity (PV)',             yr0['w_joint_pv'], ''),
        (f'{_n1} Single Annuity (PV)',            yr0['h_single_pv'], ''),
        (f'{_n1} Joint Annuity (PV)',             yr0['h_joint_pv'], ''),
    ]
    ann_total = write_group('Annuities & Pension (PV)', ann_assets)

    def _acct_items(tax_type, note):
        return [(acct.get('label') or acct['id'], yr0.get(acct['id'], 0), note)
                for acct in c.get('account_registry', []) if acct.get('tax') == tax_type]

    pretax_total = write_group('Pre-Tax (Tax-Deferred)', _acct_items('pre_tax', 'Tax-deferred'))
    roth_total = write_group('Roth (Tax-Free)', _acct_items('roth', 'Tax-free'))
    trust_total = write_group('Taxable / Trust', _acct_items('taxable', 'Taxable'))
    hsa_total = write_group('Health Savings Account', _acct_items('hsa', 'Triple tax-advantaged'))

    # Other
    # v7.5 normalization: do not list both gross residence value and net home
    # equity as assets. The Balance Sheet now uses conventional presentation:
    # gross primary residence in Assets and the mortgage in Liabilities. This
    # reconciles to the projection, which stores net home equity internally.
    home_gross_value = yr0.get('home_val', c.get('home_val', 0))
    home_net_equity = yr0.get('home_equity', max(0, home_gross_value - c.get('mort_bal', 0)))
    mort_val = max(0, home_gross_value - home_net_equity)
    startup_val = yr0.get('startup_val', c.get('startup_eq', 0))
    autos_val = yr0.get('autos_val', c.get('autos', 0))
    note_val = yr0.get('note_bal', c.get('note_face', 0))
    cash_val = c.get('cash_other', 0)

    other_items = [
        ('Primary Residence', home_gross_value, 'Gross home value; mortgage shown in Liabilities'),
        ('Startup Equity',    startup_val, 'Illiquid'),
        ('Autos',             autos_val, 'Depreciated Y0 value'),
        ('Cash (Checking Accounts)', cash_val, 'Sum of _Checking positions'),
        ('Note Receivable',  note_val, f"Projected balance through {c['note_last']}"),
    ]
    other_total = write_group('Other Assets', other_items)

    total_assets = ann_total + pretax_total + roth_total + trust_total + hsa_total + other_total

    r += 1
    write_hdr(ws, r, 1, 'LIABILITIES', NAVY, WHITE); r+=1
    write_cell(ws, r, 1, '  Mortgage')
    write_cell(ws, r, 2, mort_val, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 3, 'Offsets Primary Residence gross value; not double-counted as Home Equity')
    r+=1
    write_cell(ws, r, 1, '  Total Liabilities', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, mort_val, fmt=FMT_DOLLAR, bold=True, bg=LGRAY, align='right')
    write_cell(ws, r, 3, '', bg=LGRAY)
    r+=2

    net_worth = total_assets - mort_val
    write_cell(ws, r, 1, 'NET WORTH', bold=True, bg=NAVY, fg=WHITE)
    write_cell(ws, r, 2, net_worth, fmt=FMT_DOLLAR, bold=True, bg=NAVY, fg=WHITE, align='right')
    r += 3

    # Holdings detail intentionally omitted from Balance Sheet in v5.1.
    # Detailed positions now live only on Sheet 4 (Asset Allocation) to avoid
    # duplicate holdings tables. Account-level balances remain above.

    grand_total = sum(
        fetch_price(sym, '') * shares
        for holdings in c.get('positions', {}).values()
        for sym, shares in holdings.items()
    )

    _projection_y0_nw = rows[0].get('total_nw', 0) if rows else 0
    _nw_reconciled = abs(net_worth - _projection_y0_nw) < 1.0
    qc('3. Balance Sheet', 'Total assets - liabilities = net worth and reconciles to projection Y0', _nw_reconciled,
       f"NW={net_worth:,.0f} vs projection Y0={_projection_y0_nw:,.0f}")
    # Holdings source QC — verify positions were derived from client_holdings.csv
    _n_holdings = len(c.get('lots_reconcile', {}))
    _n_accounts = len(c.get('positions', {}))
    if _n_holdings > 0:
        qc('3. Balance Sheet', 'Positions sourced from client_holdings.csv', True,
           f'{_n_holdings} holdings across {_n_accounts} accounts')
    else:
        qc('3. Balance Sheet', 'Positions sourced from client_holdings.csv', False,
           'No holdings file found — fell back to client_data.csv Positions rows')
    lot_engine = c.get('lot_engine')
    if lot_engine:
        qc('3. Balance Sheet', 'Tax-lot data coverage',
           lot_engine.use_lots or lot_engine.coverage == 0,
           f'{lot_engine.coverage:.0%} — {"specific-lot sell guidance active" if lot_engine.use_lots else "fallback estimate (add purchase prices for lot-level guidance)"}')

    # Tax-lot data coverage is surfaced as a System / Quality Control item.
    # Actionable lot-by-lot sell guidance appears directly under taxable SELL
    # recommendations on 2B. Asset Allocation, so the Balance Sheet remains a
    # pure balance-sheet report rather than a partial tax-lot engine surface.


    qc('3. Balance Sheet', 'Holdings detail: all positions with live prices', True,
       f"Grand total invested: ${grand_total:,.0f}")


def build_sheet4(ws, c):
    """Asset Allocation"""
    ws.sheet_view.showGridLines = False
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
    _opt = _ao.compute_optimal_allocation(c)
    _optimizer_view = _ao.compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER)
    _user_view = _ao.compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_USER)
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
    # ── Total Portfolio Mix (liquid + non-liquid) ─────────────────────────
    # This top-level table starts with the current portfolio and is backfilled
    # later with projected after-trade columns once recommended trades are
    # generated.  Keeping both states here avoids forcing users to scroll to
    # the detailed before/after section to understand the household mix impact.
    write_hdr(ws, r, 1, 'Total Portfolio Mix (Liquid + Non-Liquid)', NAVY, WHITE, span=9)
    r += 1
    hdrs_total = ['Asset Class', 'Current Value', 'Current %', 'After Trades Value',
                  'After Trades %', 'Type', 'Target %', 'Current Status', 'After Trade Status']
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
    mix_rows = []
    for bucket in BUCKET_TARGETS.keys():
        if bucket == 'Cash':
            continue
        act_val = actual_buckets.get(bucket, 0)
        pct = act_val / total_portfolio if total_portfolio > 0 else 0
        tgt = TOTAL_TARGETS.get(bucket, TOTAL_TARGETS.get(bucket.replace('/Value',''), 0))
        status = _status_for_bucket(bucket, pct, tgt, fi_covered_full, re_covered_full)
        mix_rows.append((bucket, act_val, pct, 'Liquid', tgt, status, False))

    cash_total = sum(h.get('CASH', 0) * 1.0 for h in _invest_positions.values())
    cash_tgt = TOTAL_TARGETS.get('Cash', 0.0)
    cash_pct = cash_total / total_portfolio if total_portfolio > 0 else 0
    cash_status = _status_for_bucket('Cash', cash_pct, cash_tgt, fi_covered_full, re_covered_full)
    if cash_total > 0 or cash_tgt > 0:
        mix_rows.append(('Cash', cash_total, cash_pct, 'Liquid', cash_tgt, cash_status, False))

    # Non-liquid assets. Fixed-income and real-estate coverage are evaluated at
    # the overall coverage sleeve level, so liquid sub-sleeves are not marked
    # Under when the non-liquid coverage already exceeds the recommended target.
    for label, value, asset_type in nonliquid_assets:
        pct = value / total_portfolio if total_portfolio > 0 else 0
        tgt_key = 'Bonds/Fixed Income' if 'Fixed' in label else 'REITs/Real Estate'
        tgt = TOTAL_TARGETS.get(tgt_key, 0)
        if 'Fixed' in label and fi_covered_full:
            status = '✓ Covered'
        elif ('Real Estate' in label or 'Home Equity' in label) and re_covered_full:
            status = '✓ Covered'
        elif not tgt:
            status = 'Shown for context; no liquid target'
        else:
            delta = pct - tgt
            status = '✓ Covered' if pct >= tgt else ('✓ Mostly covered' if pct >= tgt * 0.8 else f'Under {abs(delta):.1%}')
        mix_rows.append((label, value, pct, 'Non-liquid', tgt, status, True))

    for label, value, pct, asset_type, tgt, status, bold_row in sorted(mix_rows, key=lambda x: (-x[1], str(x[0]))):
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
    write_hdr(ws, r, 1, 'Allocation Selection and Optimizer Recommendation', BLUE, WHITE, span=6); r += 1
    write_cell(ws, r, 1, 'Selected Mode', bold=True)
    write_cell(ws, r, 2, _ap.allocation_mode_label(_selected_mode))
    write_cell(ws, r, 3, 'Toggle in the guided UI between the optimizer recommendation and the user-specified target_pct allocation.')
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
    r += 1
    write_cell(ws, r, 1, 'Recommendation Source', bold=True)
    write_cell(ws, r, 2, _allocation_recommendation_source, bold=True, bg='E2F0D9' if _selected_mode == _ap.ALLOCATION_MODE_OPTIMIZER else 'EAF2FF')
    write_cell(ws, r, 3, _allocation_recommendation_source_note)
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
    r += 1
    write_cell(ws, r, 1, 'Pricing Source', bold=True)
    write_cell(ws, r, 2, _pricing_label, bold=True, bg='EAF2FF')
    write_cell(ws, r, 3, _pricing_note or 'Actual quote source used for this workbook build.')
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
         f'{max(0,_opt_diagnostics["years_to_retirement"]):.0f} years to retirement × stability {_opt_diagnostics["stability_factor"]}'),
        ('Fixed-Income Coverage PV', f'${_opt_bond_pv:,.0f}',
         f'Sources counted toward fixed-income target: {", ".join(_opt_diagnostics.get("fixed_income_coverage_sources", [])) or "none"}; funded ratio from guaranteed income: {_opt["funded_ratio"]:.1%}'),
        ('Home Equity REIT Coverage', 'YES' if _opt_diagnostics.get('home_equity_counts_toward_reit') else 'NO',
         'Controls whether primary residence equity satisfies the REIT/real-estate target before recommending liquid REITs'),
        ('Withdrawal Rate', f'{_opt_diagnostics["withdrawal_rate"]:.1%}',
         'Annual spending / liquid portfolio'),
        ('Glide Path Mode', _opt_diagnostics['glide_path_mode'].title(),
         'Target-date: de-risk approaching retirement; Static: fixed allocation'),
        ('Inflation-Sensitive Spending', f'{_opt_diagnostics["inflation_sensitive_pct"]:.0%}',
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

    # ── Liquid Portfolio: Target vs Actual (growth/diversifier sleeve optimization) ───
    write_hdr(ws, r, 1, 'Liquid Portfolio: Target vs Actual', NAVY, WHITE, span=6)
    r += 1
    write_cell(ws, r, 1, f'Asset allocation recommendation source: {_allocation_recommendation_source}. The selected target, target-vs-actual table, and rebalance guidance use this source. Cash is included as its own class. The UI requires user-specified target percentages to total 100% before saving or building.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    r += 1
    hdrs = ['Bucket','Target %','Actual $','Actual %','Delta pp','Action']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    liquid_display_buckets = sorted(set(BUCKET_TARGETS.keys()), key=lambda b: (-actual_buckets.get(b, 0), str(b)))
    underrepresented_buckets = []
    for bucket in liquid_display_buckets:
        tgt = BUCKET_TARGETS.get(bucket, 0)
        act_val = actual_buckets.get(bucket, 0)
        act_pct = act_val / total_port if total_port > 0 else 0
        delta = act_pct - tgt
        if bucket in FIXED_INCOME_BUCKETS and fi_covered_full:
            action = 'Covered'
            delta_to_write = 0
        elif bucket in REAL_ESTATE_BUCKETS and re_covered_full:
            action = 'Covered'
            delta_to_write = 0
        else:
            action = 'Rebalance' if abs(delta) > 0.02 else 'Hold'
            delta_to_write = delta
        if (bucket not in ('Cash', 'Uncategorized', 'Other') and tgt >= 0.005 and
                act_val < max(100, total_port * 0.0025) and action != 'Covered'):
            underrepresented_buckets.append(bucket)
        write_cell(ws, r, 1, bucket)
        write_cell(ws, r, 2, tgt, fmt=FMT_PCT, align='right')
        write_cell(ws, r, 3, act_val, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 4, act_pct, fmt=FMT_PCT, align='right')
        write_cell(ws, r, 5, delta_to_write, fmt=FMT_PCT, align='right',
                   bg='FCE4D6' if abs(delta_to_write)>0.02 else None)
        write_cell(ws, r, 6, action)
        r += 1

    r += 2
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

    write_hdr(ws, r, 1, 'Asset Location Guidance', BLUE, WHITE, span=6); r+=1
    guidance = [
        ('Tax-Deferred (IRA/401k)', 'Bonds, REITs, High-turnover funds, PDBC (commodities)',
         'Interest/dividends shielded from current tax'),
        ('Roth (Tax-Free)', 'Highest-growth assets (AVUV, VBR small-cap)',
         'Growth compounds tax-free; no RMD'),
        ('Taxable Trust', 'Tax-efficient equity (ITOT, VTI, IXUS, VXUS)',
         'Qualified dividends + LTCG rates; step-up at death'),
    ]
    write_hdr(ws, r, 1, 'Account Type', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Recommended Asset Class', DGRAY, WHITE, span=2)
    write_hdr(ws, r, 4, 'Tax Rationale', DGRAY, WHITE, span=3)
    r += 1
    for acct_type, assets, rationale in guidance:
        write_cell(ws, r, 1, acct_type, bold=True)
        write_cell(ws, r, 2, assets); ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=3)
        write_cell(ws, r, 4, rationale); ws.merge_cells(start_row=r,start_column=4,end_row=r,end_column=6)
        r += 1

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
    # SECTION B: Holdings Detail by Account
    # ══════════════════════════════════════════════════════════════════════
    r += 3
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
                    r += 1
                write_cell(ws, r, 1, 'Advisor review note', bold=True, fg='666666')
                write_cell(ws, r, 2, 'Specific-lot instructions should be reviewed against broker lot IDs, wash-sale windows, outside accounts, spouse accounts, and any same/substantially-identical replacement trades before execution.', fg='666666')
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
    # SECTION D: Before & After Allocation (per account + portfolio-wide)
    # ══════════════════════════════════════════════════════════════════════
    # Normalized bucket targets for the before/after comparison
    _nct = {k: v for k, v in BUCKET_TARGETS.items() if k not in ('Cash', 'Uncategorized')}
    _nct_sum = sum(_nct.values()) or 1.0
    NORM_TARGETS = {k: v / _nct_sum for k, v in _nct.items()}
    r += 3
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
    for acct in sorted(_invest_positions.keys()):
        at = acct_totals.get(acct, 0)
        if at < 500:
            continue

        r += 1
        write_hdr(ws, r, 1, f'{display_account(acct, c)}  —  Total: ${at:,.0f}', BLUE, WHITE, span=10)
        r += 1

        ba_hdrs = ['Bucket', 'Before $', 'Before %', '', 'After $', 'After %', '', 'Target %', 'Delta pp', 'Status']
        for i, h in enumerate(ba_hdrs, 1):
            write_hdr(ws, r, i, h, DGRAY, WHITE)
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

            # Arrow showing direction of change
            arrow = ''
            if abs(after_val - before_val) > 50:
                arrow = '→'

            write_cell(ws, r, 1, bucket)
            write_cell(ws, r, 2, before_val, fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 3, before_pct, fmt=FMT_PCT, align='right')
            write_cell(ws, r, 4, arrow, align='center')
            write_cell(ws, r, 5, after_val, fmt=FMT_DOLLAR, align='right',
                       bg='E2EFDA' if abs(after_val - before_val) > 50 else None)
            write_cell(ws, r, 6, after_pct, fmt=FMT_PCT, align='right',
                       bg='E2EFDA' if abs(after_val - before_val) > 50 else None)
            write_cell(ws, r, 7, '')
            write_cell(ws, r, 8, tgt_pct if bucket not in ('Cash', 'Uncategorized') else '',
                       fmt=FMT_PCT if bucket not in ('Cash', 'Uncategorized') else None, align='right')
            write_cell(ws, r, 9, delta_pp if bucket not in ('Cash', 'Uncategorized') else '',
                       fmt='+0.0%;-0.0%' if bucket not in ('Cash', 'Uncategorized') else None, align='right',
                       bg='FCE4D6' if abs(delta_pp) > 0.02 and bucket not in ('Cash', 'Uncategorized') else None)
            write_cell(ws, r, 10, status)
            r += 1

    # ── Portfolio-wide before/after summary ───────────────────────────────
    r += 2
    write_hdr(ws, r, 1, 'PORTFOLIO TOTAL', NAVY, WHITE, span=10)
    r += 1
    ba_hdrs2 = ['Bucket', 'Before $', 'Before %', '', 'After $', 'After %', '', 'Target %', 'Delta pp', 'Status']
    for i, h in enumerate(ba_hdrs2, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

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
    # the detailed before/after section below. (module-level
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
        write_cell(ws, _row, 4, _after_val, fmt=FMT_DOLLAR, align='right', bg='E2EFDA' if _changed else None)
        write_cell(ws, _row, 5, _after_pct, fmt=FMT_PCT, align='right', bg='E2EFDA' if _changed else None)
        write_cell(ws, _row, 9, _after_status, bg='E2EFDA' if _changed else None)

    if _total_mix_total_row:
        write_cell(ws, _total_mix_total_row, 4, total_portfolio, fmt=FMT_DOLLAR, align='right', bold=True)
        write_cell(ws, _total_mix_total_row, 5, 1.0, fmt=FMT_PCT, align='right', bold=True)

    for bucket in all_buckets_ordered:
        bv = port_before.get(bucket, 0)
        av = port_after.get(bucket, 0)
        if _hide_zero_before_after_row(bv, av):
            continue
        bp = bv / total_port if total_port > 0 else 0
        ap = av / total_port if total_port > 0 else 0
        tp = NORM_TARGETS.get(bucket, 0) if bucket not in ('Cash', 'Uncategorized') else 0
        dp = ap - tp if bucket not in ('Cash', 'Uncategorized') else 0

        if bucket in ('Cash', 'Uncategorized'):
            st = ''
        elif bucket in FIXED_INCOME_BUCKETS and fi_covered_full:
            st = '✓ Covered by fixed-income coverage'
            dp = 0
        elif bucket in REAL_ESTATE_BUCKETS and re_covered_full:
            st = '✓ Covered by real-estate coverage'
            dp = 0
        elif abs(dp) < 0.02:
            st = '✓ On target'
        else:
            st = f'Over +{dp:.1%}' if dp > 0 else f'Under {dp:.1%}'

        arrow = '→' if abs(av - bv) > 50 else ''

        write_cell(ws, r, 1, bucket, bold=True)
        write_cell(ws, r, 2, bv, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 3, bp, fmt=FMT_PCT, align='right')
        write_cell(ws, r, 4, arrow, align='center')
        write_cell(ws, r, 5, av, fmt=FMT_DOLLAR, align='right',
                   bg='E2EFDA' if abs(av - bv) > 50 else None)
        write_cell(ws, r, 6, ap, fmt=FMT_PCT, align='right',
                   bg='E2EFDA' if abs(av - bv) > 50 else None)
        write_cell(ws, r, 7, '')
        write_cell(ws, r, 8, tp if bucket not in ('Cash', 'Uncategorized') else '',
                   fmt=FMT_PCT if bucket not in ('Cash', 'Uncategorized') else None, align='right')
        write_cell(ws, r, 9, dp if bucket not in ('Cash', 'Uncategorized') else '',
                   fmt='+0.0%;-0.0%' if bucket not in ('Cash', 'Uncategorized') else None, align='right',
                   bg='FCE4D6' if abs(dp) > 0.02 and bucket not in ('Cash', 'Uncategorized') else None)
        write_cell(ws, r, 10, st)
        r += 1

    r += 1
    write_cell(ws, r, 1, 'Note: Remaining deltas represent work for future contributions, new deposits, '
               'or cross-account rebalancing that requires distributions and contributions (taxable events).')
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

    # ══════════════════════════════════════════════════════════════════════
    # SECTION E: Tax-Efficient Rebalancing Sequence
    # ══════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'TAX-EFFICIENT REBALANCING SEQUENCE', 10); r += 1
    steps = [
        ('1. New contributions first',
         'Direct new 401k/IRA/HSA contributions to underweight buckets. No tax event — just redirect future dollars.',
         'Example: if Roth is underweight AVUV, direct new Roth contributions to AVUV instead of current holdings.'),
        ('2. Rebalance within tax-advantaged accounts',
         'Sell overweight and buy underweight within each IRA, 401k, Roth, and HSA. No capital gains tax on trades inside these accounts.',
         'This is the primary rebalancing mechanism — do these trades first.'),
        ('3. Use dividends and distributions',
         'Reinvest dividends into underweight buckets rather than the same fund. Over time this naturally rebalances without selling.',
         'Turn off auto-reinvest in overweight funds; redirect to underweight funds in the same account.'),
        ('4. Tax-loss harvest in taxable accounts',
         'If a taxable holding has unrealized losses, sell it and buy a similar (not "substantially identical") fund in the target bucket.',
         'Example: sell ITOT (at a loss) and buy VTI — both are US Large but not identical. Harvest the loss.'),
        ('5. Sell overweight taxable positions (last resort)',
         'If the above steps don\'t close the gap, sell overweight positions in taxable accounts. LTCG tax applies.',
         'Prioritize lots held >1 year (LTCG rate 15-20%) over short-term lots (ordinary income rate).'),
        ('6. Gradual rebalancing over time',
         'You don\'t need to reach target in one trade. Spread rebalancing over 2-3 years to smooth tax impact.',
         'Each year: execute steps 1-4, then reassess. Only do step 5 if significantly out of band (>5% delta).'),
    ]
    for step_num, title, detail in steps:
        write_cell(ws, r, 1, title, bold=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
        write_cell(ws, r, 1, detail)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
        r += 1  # blank row




__all__ = ['build_sheet1', 'build_sheet2', 'build_sheet3', 'build_sheet4']
