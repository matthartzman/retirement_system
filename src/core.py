from __future__ import annotations
import sys as _sys


# ===== BEGIN account_registry.py =====

"""
account_registry.py — Dynamic account model for the retirement projection engine.

Dynamic account registry. Each account has an owner, type, tax treatment, and RMD eligibility.
The projection engine operates on account *types* instead of account-name assumptions.
"""

# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT TYPES — defines the tax treatment and behavior of each account type
# ─────────────────────────────────────────────────────────────────────────────

ACCOUNT_TYPES = {
    'traditional_ira':  {'tax': 'pre_tax',  'rmd': True,  'label': 'Traditional IRA'},
    '401k':             {'tax': 'pre_tax',  'rmd': True,  'label': '401(k)'},
    '403b':             {'tax': 'pre_tax',  'rmd': True,  'label': '403(b)'},
    'sep_ira':          {'tax': 'pre_tax',  'rmd': True,  'label': 'SEP IRA'},
    'roth_ira':         {'tax': 'roth',     'rmd': False, 'label': 'Roth IRA'},
    'roth_401k':        {'tax': 'roth',     'rmd': False, 'label': 'Roth 401(k)'},
    'taxable':          {'tax': 'taxable',  'rmd': False, 'label': 'Taxable / Brokerage'},
    'trust':            {'tax': 'taxable',  'rmd': False, 'label': 'Trust'},
    'hsa':              {'tax': 'hsa',      'rmd': False, 'label': 'HSA'},
    '529':              {'tax': 'tax_free', 'rmd': False, 'label': '529 Plan'},
    'checking':         {'tax': 'cash',     'rmd': False, 'label': 'Checking / Savings'},
}


def _infer_type(account_name):
    """Infer account type from an account identifier."""
    name = account_name.lower()
    if '_401k' in name:        return '401k'
    if '_403b' in name:        return '403b'
    if '_roth' in name:        return 'roth_ira'
    if '_ira' in name:         return 'traditional_ira'
    if '_trust' in name:       return 'trust'
    if '_hsa' in name:         return 'hsa'
    if '_checking' in name:    return 'checking'
    if '_529' in name:         return '529'
    return 'taxable'


def _infer_owner(account_name, members):
    """Infer owner index from an account identifier. Returns 0 or 1."""
    name = account_name.lower()
    if name.startswith('wife_') or name.startswith('spouse_') or name.startswith('member_2'):
        return 1 if len(members) > 1 else 0
    if name.startswith('family_') or name.startswith('joint_') or name.startswith('business_'):
        return 0  # default to member_1
    return 0  # husband / member_1


def build_registry_from_balances(balances, members):
    """Build an account registry from balance keys.

    Args:
        balances: dict {account_name: balance}
        members: list of member dicts from parse_client

    Returns:
        list of account dicts, each with:
            id, owner_idx, owner_name, acct_type, tax, rmd, label, balance
    """
    registry = []
    for acct_name, balance in balances.items():
        acct_type = _infer_type(acct_name)
        owner_idx = _infer_owner(acct_name, members)
        type_info = ACCOUNT_TYPES.get(acct_type, ACCOUNT_TYPES['taxable'])
        owner_name = (members[owner_idx].get('nickname') or members[owner_idx]['name']) if owner_idx < len(members) else 'Unknown'

        registry.append({
            'id':         acct_name,                # key into bal[] dict
            'owner_idx':  owner_idx,                 # 0 = member_1, 1 = member_2
            'owner_name': owner_name,
            'acct_type':  acct_type,
            'tax':        type_info['tax'],
            'rmd':        type_info['rmd'],
            'label':      f"{owner_name}'s {type_info['label']}",
            'balance':    balance,
        })

    return sorted(registry, key=lambda a: (a['owner_idx'], a['tax'], a['id']))


def build_registry_from_json(accounts_json, members):
    """Build an account registry from a wizard JSON plan.

    Args:
        accounts_json: list of {id, owner_idx, acct_type, balance, label?}
        members: list of member dicts

    Returns:
        list of account dicts (same shape as build_registry_from_balances)
    """
    registry = []
    for i, acct in enumerate(accounts_json):
        acct_type = acct.get('acct_type', 'taxable')
        type_info = ACCOUNT_TYPES.get(acct_type, ACCOUNT_TYPES['taxable'])
        owner_idx = acct.get('owner_idx', 0)
        owner_name = (members[owner_idx].get('nickname') or members[owner_idx]['name']) if owner_idx < len(members) else 'Unknown'

        acct_id = acct.get('id', f'acct_{i+1}')
        registry.append({
            'id':         acct_id,
            'owner_idx':  owner_idx,
            'owner_name': owner_name,
            'acct_type':  acct_type,
            'tax':        type_info['tax'],
            'rmd':        type_info['rmd'],
            'label':      acct.get('label', f"{owner_name}'s {type_info['label']}"),
            'balance':    acct.get('balance', 0),
        })

    return sorted(registry, key=lambda a: (a['owner_idx'], a['tax'], a['id']))


# ─────────────────────────────────────────────────────────────────────────────
# LOOKUP HELPERS — used by the projection engine instead of hardcoded names
# ─────────────────────────────────────────────────────────────────────────────

def ids_by_tax(registry, tax_type):
    """Return list of account IDs with the given tax treatment."""
    return [a['id'] for a in registry if a['tax'] == tax_type]


def ids_by_type(registry, acct_type):
    """Return list of account IDs with the given account type."""
    return [a['id'] for a in registry if a['acct_type'] == acct_type]


def ids_by_owner(registry, owner_idx):
    """Return list of account IDs owned by the given member."""
    return [a['id'] for a in registry if a['owner_idx'] == owner_idx]


def ids_by_owner_and_tax(registry, owner_idx, tax_type):
    """Return list of account IDs owned by member with given tax treatment."""
    return [a['id'] for a in registry if a['owner_idx'] == owner_idx and a['tax'] == tax_type]


def all_investment_ids(registry):
    """All accounts that hold investable assets (not checking/cash)."""
    return [a['id'] for a in registry if a['tax'] not in ('cash',)]


def all_ids(registry):
    """All account IDs."""
    return [a['id'] for a in registry]


def rmd_ids_by_owner(registry, owner_idx):
    """RMD-eligible account IDs for a specific owner."""
    return [a['id'] for a in registry if a['owner_idx'] == owner_idx and a['rmd']]


def roth_target_for_owner(registry, owner_idx):
    """The Roth account ID to receive conversions for a given owner.
    Returns the first Roth account found for that owner, or None."""
    roth_ids = [a['id'] for a in registry if a['owner_idx'] == owner_idx and a['tax'] == 'roth']
    return roth_ids[0] if roth_ids else None


def taxable_ids(registry):
    """Taxable (trust/brokerage) account IDs — used in withdrawal cascade."""
    return [a['id'] for a in registry if a['tax'] == 'taxable']


def hsa_ids(registry):
    """HSA account IDs."""
    return [a['id'] for a in registry if a['tax'] == 'hsa']


# ===== END account_registry.py =====


# ===== BEGIN account_access.py =====

"""Registry account access helpers.

This module is the only place that converts account-owner/tax traits into
ordered account id lists. Projection, reporting, and optimization code should
use these helpers instead of literal account names.
"""

from typing import Iterable, Mapping, MutableMapping, Sequence

_ar = _sys.modules[__name__]  # consolidated alias for account_registry


def registry(c: Mapping) -> list[dict]:
    return list(c.get('account_registry') or [])


def accounts(c: Mapping, *, owner_idx: int | None = None, tax: str | None = None,
             acct_type: str | None = None, include_cash: bool = True) -> list[str]:
    out: list[str] = []
    for acct in registry(c):
        if owner_idx is not None and acct.get('owner_idx') != owner_idx:
            continue
        if tax is not None and acct.get('tax') != tax:
            continue
        if acct_type is not None and acct.get('acct_type') != acct_type:
            continue
        if not include_cash and acct.get('tax') == 'cash':
            continue
        out.append(acct['id'])
    return out


def first_account(c: Mapping, *, owner_idx: int | None = None, tax: str | None = None,
                  acct_type: str | None = None, fallback: str | None = None) -> str | None:
    ids = accounts(c, owner_idx=owner_idx, tax=tax, acct_type=acct_type)
    if ids:
        return ids[0]
    if fallback is not None:
        return fallback
    all_ids = list(c.get('all_acct_ids') or [])
    return all_ids[0] if all_ids else None


def first_taxable(c: Mapping, owner_idx: int | None = None) -> str | None:
    return first_account(c, owner_idx=owner_idx, tax='taxable') or first_account(c, tax='taxable')


def first_hsa(c: Mapping, owner_idx: int | None = None) -> str | None:
    return first_account(c, owner_idx=owner_idx, tax='hsa') or first_account(c, tax='hsa')


def first_pretax(c: Mapping, owner_idx: int | None = None) -> str | None:
    return first_account(c, owner_idx=owner_idx, tax='pre_tax') or first_account(c, tax='pre_tax')


def sum_bal(c_or_bal: Mapping, bal_or_ids, *, owner_idx: int | None = None,
            tax: str | None = None, acct_type: str | None = None) -> float:
    """Sum balances.

    Supports both original consolidated call styles:
    - account_registry: sum_bal(balances, ids)
    - account_access:   sum_bal(config, balances, tax=..., owner_idx=...)
    """
    if owner_idx is None and tax is None and acct_type is None:
        bal = c_or_bal
        ids = bal_or_ids
        return sum(float(bal.get(aid, 0.0) or 0.0) for aid in ids)
    c = c_or_bal
    bal = bal_or_ids
    return sum(float(bal.get(aid, 0.0) or 0.0) for aid in accounts(c, owner_idx=owner_idx, tax=tax, acct_type=acct_type))


def deposit(bal: MutableMapping[str, float], acct_id: str | None, amount: float) -> float:
    amount = max(0.0, float(amount or 0.0))
    if acct_id and amount:
        bal[acct_id] = float(bal.get(acct_id, 0.0) or 0.0) + amount
    return amount if acct_id else 0.0


def draw_order(c: Mapping, tax: str, owner_priority: Sequence[int] = (1, 0)) -> list[str]:
    ordered: list[str] = []
    for owner in owner_priority:
        ordered.extend(accounts(c, owner_idx=owner, tax=tax))
    # Include any non-standard additional owners after preferred order.
    for acct in accounts(c, tax=tax):
        if acct not in ordered:
            ordered.append(acct)
    return ordered


def draw_from_accounts(bal: MutableMapping[str, float], ids: Iterable[str], amount: float) -> dict[str, float]:
    remaining = max(0.0, float(amount or 0.0))
    out: dict[str, float] = {}
    for aid in ids:
        if remaining <= 0:
            break
        before = max(0.0, float(bal.get(aid, 0.0) or 0.0))
        draw = min(before, remaining)
        if draw > 0:
            bal[aid] = before - draw
            out[aid] = draw
            remaining -= draw
    return out


def owner_amounts(c: Mapping, by_account: Mapping[str, float], tax: str | None = None) -> dict[int, float]:
    result: dict[int, float] = {}
    acct_owner = {a['id']: a.get('owner_idx', 0) for a in registry(c) if tax is None or a.get('tax') == tax}
    for aid, amt in by_account.items():
        owner = acct_owner.get(aid, 0)
        result[owner] = result.get(owner, 0.0) + float(amt or 0.0)
    return result

# ===== END account_access.py =====


# ===== BEGIN events.py =====

"""
events.py — Event log and typed events for the retirement projection engine.

Every computation step in project() emits typed events to a log.
Events are pure data (namedtuples) — immutable, serializable, traceable.
The log can be queried after projection to answer "where did this $X come from?"
"""
from collections import namedtuple

# ── Event types ──────────────────────────────────────────────────────────────
# Each has (year, ...) so events can be filtered/grouped by year.

Income       = namedtuple('Income',       ['year','source','gross','net','tax','account','note'])
Withdrawal   = namedtuple('Withdrawal',   ['year','priority','source_acct','amount','reason','note'])
Spending     = namedtuple('Spending',      ['year','category','amount','note'])
Tax          = namedtuple('Tax',           ['year','kind','amount','base','rate','note'])
Transfer     = namedtuple('Transfer',      ['year','from_acct','to_acct','amount','reason'])
Contribution = namedtuple('Contribution',  ['year','account','amount','note'])
AssetChange  = namedtuple('AssetChange',   ['year','asset','old_val','new_val','reason'])
Conversion   = namedtuple('Conversion',    ['year','from_acct','to_acct','amount','tax_cost','note'])
HomeSale     = namedtuple('HomeSale',      ['year','gross','costs','mort_payoff','basis','gain',
                                            'sec121','taxable_gain','ltcg_tax','net','dest_acct'])
Growth       = namedtuple('Growth',        ['year','account','balance_before','return_rate','growth_amount'])
Death        = namedtuple('Death',         ['year','spouse','rollover_desc'])
RMD          = namedtuple('RMD',           ['year','account','balance','divisor','amount'])
Scenario     = namedtuple('Scenario',      ['name','overrides','terminal_nw','lifetime_tax','delta_nw'])
Warning      = namedtuple('Warning',       ['year','code','message'])


class EventLog:
    """Append-only event log with query helpers."""

    def __init__(self):
        self._events = []

    def emit(self, event):
        self._events.append(event)
        return event

    def all(self):
        return list(self._events)

    def by_year(self, year):
        return [e for e in self._events if hasattr(e, 'year') and e.year == year]

    def by_type(self, event_type):
        return [e for e in self._events if isinstance(e, event_type)]

    def by_year_type(self, year, event_type):
        return [e for e in self._events
                if isinstance(e, event_type) and hasattr(e, 'year') and e.year == year]

    def incomes(self, year=None):
        return self.by_year_type(year, Income) if year else self.by_type(Income)

    def withdrawals(self, year=None):
        return self.by_year_type(year, Withdrawal) if year else self.by_type(Withdrawal)

    def taxes(self, year=None):
        return self.by_year_type(year, Tax) if year else self.by_type(Tax)

    def warnings(self):
        return self.by_type(Warning)

    def total_income(self, year):
        return sum(e.gross for e in self.incomes(year))

    def total_tax(self, year):
        return sum(e.amount for e in self.taxes(year))

    def total_withdrawals(self, year):
        return sum(e.amount for e in self.withdrawals(year))

    def dollar_lineage(self, year, account):
        """Trace every dollar that flowed into or out of an account in a given year."""
        inflows  = [e for e in self.by_year(year)
                    if hasattr(e, 'account') and e.account == account and hasattr(e, 'amount')]
        outflows = [e for e in self.by_year(year)
                    if hasattr(e, 'source_acct') and e.source_acct == account]
        return {'inflows': inflows, 'outflows': outflows}

    def __len__(self):
        return len(self._events)

    def summary(self):
        """Quick stats for logging."""
        types = {}
        for e in self._events:
            t = type(e).__name__
            types[t] = types.get(t, 0) + 1
        return types


# ── Lot-level basis engine ───────────────────────────────────────────────────

class TaxLot:
    """A single tax lot with purchase price and quantity."""
    __slots__ = ('symbol', 'qty', 'cost_basis', 'purchase_date')

    def __init__(self, symbol, qty, cost_basis, purchase_date=''):
        self.symbol = symbol
        self.qty = qty
        self.cost_basis = cost_basis  # total cost, not per-share
        self.purchase_date = purchase_date

    @property
    def cost_per_share(self):
        return self.cost_basis / self.qty if self.qty > 0 else 0

    def unrealized_gain(self, current_price):
        return max(0, current_price * self.qty - self.cost_basis)

    def gain_fraction(self, current_price):
        mv = current_price * self.qty
        return max(0, mv - self.cost_basis) / mv if mv > 0 else 0


class LotEngine:
    """HIFO/LIFO/FIFO lot selection for capital gains on withdrawals.

    Falls back to flat trust_gain_fraction when < 10% of positions have lot data,
    printing a warning.
    """

    def __init__(self, lots_by_account, prices, fallback_gain_fraction=0.50, method='HIFO'):
        """
        lots_by_account: {account: {symbol: [TaxLot, ...]}}
        prices: {symbol: current_price}
        method: 'HIFO' | 'LIFO' | 'FIFO'
        """
        self.lots = lots_by_account
        self.prices = prices
        self.method = method
        self.fallback = fallback_gain_fraction
        self.warnings = []

        # Check coverage: what fraction of market value has lot data?
        total_mv = 0
        lotted_mv = 0
        for acct, syms in lots_by_account.items():
            for sym, lot_list in syms.items():
                price = prices.get(sym, 0)
                mv = sum(l.qty * price for l in lot_list)
                total_mv += mv
                if any(l.cost_basis > 0 for l in lot_list):
                    lotted_mv += mv

        self.coverage = lotted_mv / total_mv if total_mv > 0 else 0
        self.use_lots = self.coverage >= 0.10

        if not self.use_lots and total_mv > 0:
            self.warnings.append(
                f"Lot data covers only {self.coverage:.0%} of portfolio market value "
                f"(< 10% threshold). Falling back to flat gain fraction of "
                f"{self.fallback:.0%} for all trust draws."
            )

    def _lot_acquisition_year(self, lot):
        try:
            s = str(lot.purchase_date or '')
            if '/' in s:
                return int(s.split('/')[-1])
            if '-' in s:
                return int(s.split('-')[0])
            return int(s[:4])
        except Exception:
            return None

    def is_long_term(self, lot, current_year=None):
        acq = self._lot_acquisition_year(lot)
        if current_year is None or acq is None:
            return True
        return int(current_year) - acq >= 1

    def preview_gain_on_withdrawal(self, account, amount, current_year=None):
        """Non-mutating gain estimate for scenario/planning reads."""
        return self.gain_on_withdrawal(account, amount, current_year=current_year, mutate=False)

    def gain_on_withdrawal(self, account, amount, current_year=None, mutate=True):
        """
        Compute realized gain for a withdrawal of $amount from account.
        Uses HIFO/LIFO/FIFO lot selection when lot data is available.
        Returns (gain_amount, lots_consumed). Set mutate=False for preview.
        When current_year is supplied, long-term lots are preferred over
        short-term lots for equal selection methods to avoid ordinary-rate gains.
        """
        if not self.use_lots:
            return amount * self.fallback, []

        acct_lots = self.lots.get(account, {})
        if not acct_lots:
            return amount * self.fallback, []

        # Flatten all lots for this account, sorted by method
        all_lots = []
        for sym, lot_list in acct_lots.items():
            price = self.prices.get(sym, 0)
            for lot in lot_list:
                all_lots.append((lot, price))

        if self.method == 'HIFO':
            # Prefer long-term lots, then highest basis to minimize tax drag.
            all_lots.sort(key=lambda x: (not self.is_long_term(x[0], current_year), -x[0].cost_per_share))
        elif self.method == 'LIFO':
            all_lots.sort(key=lambda x: (not self.is_long_term(x[0], current_year), x[0].purchase_date), reverse=True)
        else:  # FIFO
            all_lots.sort(key=lambda x: (not self.is_long_term(x[0], current_year), x[0].purchase_date))

        remaining = amount
        total_gain = 0
        consumed = []

        for lot, price in all_lots:
            if remaining <= 0:
                break
            mv = lot.qty * price
            sell_mv = min(remaining, mv)
            sell_fraction = sell_mv / mv if mv > 0 else 0
            sell_basis = lot.cost_basis * sell_fraction
            gain = max(0, sell_mv - sell_basis)
            total_gain += gain

            # Reduce lot only for actual sales. Preview calls are side-effect free.
            if mutate:
                lot.qty *= (1 - sell_fraction)
                lot.cost_basis *= (1 - sell_fraction)
            remaining -= sell_mv
            consumed.append((lot.symbol, sell_mv, gain))

        return total_gain, consumed


# ── Validation framework ─────────────────────────────────────────────────────

class Invariant:
    """A declarative check that can be evaluated against projection data."""
    __slots__ = ('name', 'check_fn', 'severity', 'description')

    def __init__(self, name, check_fn, severity='FAIL', description=''):
        self.name = name
        self.check_fn = check_fn  # fn(row, c) -> bool (True = pass)
        self.severity = severity  # 'FAIL' | 'WARN'
        self.description = description

    def evaluate(self, row, c):
        try:
            passed = self.check_fn(row, c)
        except Exception as e:
            return False, f"Exception: {e}"
        return passed, '' if passed else f"{self.name}: {self.description}"


# Built-in invariants
def _registry_ids(c, tax=None):
    registry = c.get('account_registry') or []
    ids = []
    for acct in registry:
        if tax is None or acct.get('tax') == tax:
            aid = acct.get('id')
            if aid:
                ids.append(aid)
    return ids

def _non_negative_for_ids(row, c, ids):
    return all(row.get(aid, 0) >= -0.01 for aid in ids)

INVARIANTS = [
    Invariant('NW_POSITIVE',
              lambda r, c: r.get('total_nw', 0) >= -1000,
              'WARN', 'Total net worth should not be deeply negative'),
    Invariant('ACCOUNTS_NON_NEGATIVE',
              lambda r, c: _non_negative_for_ids(r, c, _registry_ids(c)),
              'FAIL', 'Registry account balances must not go negative'),
    Invariant('AGI_COMPONENTS',
              lambda r, c: abs(r.get('agi', 0) - (
                  r.get('earned', 0) + r.get('ss_taxable', 0)
                  + r.get('rmd_total', 0) + r.get('roth_conv', 0) + r.get('pension', 0)
                  + r.get('_niit_ws_taxable', r.get('wife_single_ann', 0)) + r.get('wife_joint_ann', 0)
                  + r.get('_niit_hs_taxable', r.get('h_single_ann', 0)) + r.get('h_joint_ann', 0) + r.get('note_int', 0)
              )) < max(1000, r.get('agi', 0) * 0.001),
              'WARN', 'AGI should equal sum of taxable income components'),
    Invariant('TAX_REASONABLE',
              lambda r, c: r.get('total_tax', 0) <= r.get('agi', 1) * 0.50 + 10000,
              'WARN', 'Total tax should not exceed 50% of AGI'),
    Invariant('SPENDING_POSITIVE',
              lambda r, c: r.get('spend_base_yr', 0) >= 0,
              'FAIL', 'Base spending must be non-negative'),
    Invariant('MORT_SCHEDULE_CONSISTENT',
              lambda r, c: r.get('mortgage', 0) >= 0,
              'FAIL', 'Mortgage payment must be non-negative'),
    Invariant('HOME_EQUITY_NON_NEGATIVE',
              lambda r, c: r.get('home_equity', 0) >= -0.01,
              'FAIL', 'Home equity must not go negative'),
]

def validate_projection(rows, c, extra_invariants=None):
    """Run all invariants against every row. Returns list of (row_idx, invariant, message)."""
    checks = INVARIANTS + (extra_invariants or [])
    failures = []
    for i, row in enumerate(rows):
        for inv in checks:
            passed, msg = inv.evaluate(row, c)
            if not passed:
                failures.append((i, row.get('year', '?'), inv.severity, inv.name, msg))
    return failures

# ===== END events.py =====


# ===== BEGIN engine_core.py =====

"""engine_core.py — shared financial primitives for the retirement engine.

This module is the single source of truth for projection helper constants,
event records, tax helpers, RMD tables, and annuity actuarial helpers.
It intentionally has no workbook/reporting/UI dependencies.
"""

import math
import datetime
from collections import namedtuple

from . import taxes as _td  # consolidated from tax_data

TAX_BASE_YEAR = _td.TAX_REFERENCE_YEAR

EvIncome     = namedtuple('EvIncome',     ['year','source','gross','note'])
EvWithdraw   = namedtuple('EvWithdraw',   ['year','priority','acct','amount','reason'])
EvSpend      = namedtuple('EvSpend',      ['year','category','amount'])
EvTax        = namedtuple('EvTax',        ['year','kind','amount','rate'])
EvTransfer   = namedtuple('EvTransfer',   ['year','from_acct','to_acct','amount','reason'])
EvConversion = namedtuple('EvConversion', ['year','from_acct','to_acct','amount'])
EvHomeSale   = namedtuple('EvHomeSale',   ['year','gross','costs','mort','tax','net','dest'])
EvGrowth     = namedtuple('EvGrowth',     ['year','acct','bal_before','ret','growth'])
EvDeath      = namedtuple('EvDeath',      ['year','spouse','rollover'])
EvRMD        = namedtuple('EvRMD',        ['year','acct','bal','divisor','amount'])
EvWarning    = namedtuple('EvWarning',    ['year','code','msg'])
EvScenario   = namedtuple('EvScenario',   ['name','term_nw','life_tax','delta'])

RMD_DIVISORS = {
    72:27.4, 73:26.5, 74:25.5, 75:24.6, 76:23.7, 77:22.9, 78:22.0, 79:21.1,
    80:20.2, 81:19.4, 82:18.5, 83:17.8, 84:16.8, 85:16.0, 86:15.2, 87:14.4,
    88:13.7, 89:12.9, 90:12.2, 91:11.5, 92:10.8, 93:10.1, 94:9.5,  95:8.9,
    96:8.4,  97:7.8,  98:7.3,  99:6.8,  100:6.4, 101:6.0, 102:5.6, 103:5.2,
    104:4.9, 105:4.6, 106:4.3, 107:4.1, 108:3.9, 109:3.7, 110:3.5,
    111:3.4, 112:3.3, 113:3.1, 114:3.0, 115:2.9,
}

def rmd_divisor(age):
    if age < 72:
        return 0
    if age in RMD_DIVISORS:
        return RMD_DIVISORS[age]
    # Conservative post-table continuation, never pretending old ages have long divisors.
    return max(2.0, RMD_DIVISORS[115] - (age - 115) * 0.1)


def statutory_rmd_start_age(dob_year):
    """Return the statutory first-RMD age for a person born in ``dob_year``.

    Implements the SECURE Act / SECURE 2.0 Act Section 107 age ramp:
      * born 1950 or earlier -> age 72
      * born 1951-1959       -> age 73
      * born 1960 or later   -> age 75

    Stated position on the 1959 birth cohort (do not "fix" this to 75 without
    reading this note): SECURE 2.0 Section 107 has a genuine drafting
    conflict for people born in 1959 — depending on which cross-referenced
    clause is read literally, that cohort can be placed in either the "age
    73" bracket or the "age 75" bracket. This is not a bug in this function;
    it is a known ambiguity in the statute itself. This codebase deliberately
    adopts the IRS's administrative position — treating the 1959 cohort as
    subject to age 73, consistent with IRS guidance (Notice 2023-54 and the
    final RMD regulations) and how custodians/providers have implemented the
    rule in practice — rather than the alternative age-75 reading. If the IRS
    or subsequent legislation ever resolves the conflict the other way, this
    is the single place to change.
    """
    year = int(dob_year)
    if year <= 1950:
        return 72
    if year <= 1959:
        return 73
    return 75

ASSET_CLASS_RETURNS = {
    'equity':    0.08,
    'commodity': 0.05,
    'cash':      0.02,
}

FEDERAL_BRACKETS_BASE_YEAR = _td.FEDERAL_BRACKETS_BASE_YEAR
FEDERAL_BRACKETS_MFJ    = FEDERAL_BRACKETS_BASE_YEAR['MFJ']
FEDERAL_BRACKETS_SINGLE = FEDERAL_BRACKETS_BASE_YEAR['Single']
STATE_TAX_RULES = _td.load_state_tax([])
col_factors = _td.col_factors  # geographic cost-of-living factors for State Residency
IRMAA_TIERS_BASE_YEAR = _td.IRMAA_TIERS_BASE_YEAR
IRMAA_TIERS_MFJ = IRMAA_TIERS_BASE_YEAR['MFJ']

def inflate_brackets(brackets, inflator, years):
    factor = (1 + inflator) ** years
    return [(lo * factor, hi * factor if hi != float('inf') else float('inf'), rate)
            for lo, hi, rate in brackets]

def compute_fed_tax(taxable, year, filing, brk_inf):
    years = year - getattr(_td, 'FEDERAL_BRACKETS_VALUE_YEAR', TAX_BASE_YEAR)
    brk = FEDERAL_BRACKETS_BASE_YEAR.get(filing, FEDERAL_BRACKETS_BASE_YEAR['Single'])
    brk = inflate_brackets(brk, brk_inf, years)
    tax = 0.0
    for lo, hi, rate in brk:
        if taxable <= lo:
            break
        tax += (min(taxable, hi) - lo) * rate
    return max(0, tax)

def standard_deduction(year, filing, brk_inf, n_over_65=2):
    base = _td.STANDARD_DEDUCTION_BASE_YEAR.get(filing, 15750)
    add_per = _td.STANDARD_DEDUCTION_OVER65_BASE_YEAR.get(filing, 1650)
    factor = (1 + brk_inf) ** (year - getattr(_td, 'STANDARD_DEDUCTION_VALUE_YEAR', TAX_BASE_YEAR))
    return (base + add_per * n_over_65) * factor


def senior_bonus_deduction(year, filing, magi, n_over_65=0):
    """Temporary OBBBA senior deduction for 2025-2028.

    Adds $6,000 per age-65+ filer, phased out at 6% of MAGI above
    $75k single/MFS/HOH and $150k MFJ.  This sits in the standard/itemized
    deduction stack and must be computed after MAGI/AGI is known.
    """
    if year < 2025 or year > 2028 or n_over_65 <= 0:
        return 0.0
    filing = filing if filing in ('MFJ','Single','HOH','MFS') else 'Single'
    threshold = 150_000.0 if filing == 'MFJ' else 75_000.0
    base = 6_000.0 * max(0, int(n_over_65))
    phaseout = max(0.0, float(magi or 0.0) - threshold) * 0.06
    return max(0.0, base - phaseout)


def social_security_taxable_amount(ss_total, other_income, filing='MFJ'):
    """Compute federally taxable Social Security using the provisional-income phase-in.

    other_income should include AGI components other than Social Security.
    Uses current-law base thresholds, which are not inflation-indexed.
    """
    ss_total = max(0.0, float(ss_total or 0.0))
    other_income = max(0.0, float(other_income or 0.0))
    if ss_total <= 0:
        return 0.0
    if filing == 'MFJ':
        base1, base2 = 32_000.0, 44_000.0
    elif filing == 'MFS':
        base1, base2 = 0.0, 0.0
    else:
        base1, base2 = 25_000.0, 34_000.0
    provisional = other_income + 0.5 * ss_total
    if provisional <= base1:
        return 0.0
    if provisional <= base2:
        return min(0.50 * ss_total, 0.50 * (provisional - base1))
    taxable = 0.85 * (provisional - base2) + min(0.50 * ss_total, 0.50 * max(0.0, base2 - base1))
    return min(0.85 * ss_total, taxable)

def irmaa_lookback_magi(rows, current_agi, lookback_years=2, historical_magi=None):
    """Return MAGI used for IRMAA, applying statutory two-year lookback.

    Once ``lookback_years`` prior projected plan-year rows exist, the
    lookback MAGI is that prior row's actual AGI -- the normal statutory
    case.

    For the first ``lookback_years`` plan years, the lookback target falls
    before plan start, so no projected row exists yet to look back at
    (``rows`` only accumulates as the projection runs). ``historical_magi``,
    if supplied, is a mapping of {years_before_plan_start: actual MAGI} --
    e.g. {2: <MAGI two tax years before plan start>, 1: <MAGI one tax year
    before plan start>} -- sourced from the household's actual tax returns
    (item 2.6). When the entry for the needed year is present, it seeds the
    lookback with that real historical value instead of a stand-in.

    Absent a usable ``historical_magi`` entry (including saved plans made
    before these inputs existed), this falls back to ``current_agi`` -- the
    current plan year's own AGI is used as a stand-in, exactly as before
    these inputs existed. That fallback is a known approximation: it is
    often materially different from actual final-working-year MAGI, so
    callers should surface a preflight nudge to fill in the actual values
    when they are missing.
    """
    if lookback_years <= 0:
        return current_agi
    if len(rows) >= lookback_years:
        return rows[-lookback_years].get('agi', current_agi)
    years_before_start = lookback_years - len(rows)
    hist = historical_magi or {}
    value = hist.get(years_before_start)
    if value not in (None, ''):
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return current_agi

def supported_states():
    """States with modeled state-tax rules, derived from STATE_TAX_RULES.

    This is the single source of truth for "which states does this build
    model" — STATE_TAX_RULES itself is taxes.py's STATE_TAX_DEFAULTS
    overlaid with any reference_data/state_tax.csv rows, so adding a state
    to that CSV extends this set automatically. Do not hardcode a second
    list of state names anywhere else; call this instead.
    """
    return tuple(sorted(STATE_TAX_RULES.keys()))


def _require_supported_state(state):
    """Fail loudly on a residence_state with no modeled tax rules (item 1.11).

    Previously an unrecognized state silently borrowed Illinois' flat 4.95%
    rate AND its exempt_retirement=True treatment — an exemption many states
    do not grant — with nothing on any report saying so. A truthy state that
    isn't in STATE_TAX_RULES now raises instead of silently mapping to
    Illinois.

    A blank/missing state is intentionally NOT raised here: residence_state
    is a required Plan Data field (reference_data/schema.csv) already
    enforced by the separate "missing required field" preflight check, so an
    empty string reaching this function is that upstream validation's
    problem, not a "wrong state name" problem. Raising here too would risk
    hard-failing on incomplete/in-progress plan snapshots (e.g. autosave
    backups captured mid-edit) instead of on genuinely wrong data.
    """
    if state and state not in STATE_TAX_RULES:
        raise ValueError(
            f"Unsupported residence_state {state!r}. State tax is modeled for: "
            f"{', '.join(supported_states())}. Change the state or add a rule "
            f"to reference_data/state_tax.csv."
        )


def state_income_tax(state, earned, retirement_dist, ss_taxable, investment_inc,
                     nonqual_annuity, roth_conv, year, age_over_65=True, filing='MFJ', brk_inf=0.02):
    _require_supported_state(state)
    rules = STATE_TAX_RULES.get(state, STATE_TAX_RULES.get('Illinois', _td.STATE_TAX_DEFAULTS.get('Illinois')))
    if rules['type'] == 'none':
        return 0.0
    taxable = earned + investment_inc + nonqual_annuity
    if not rules.get('exempt_retirement'):
        retirement_taxable = retirement_dist + roth_conv
        exempt_amt = rules.get('retirement_exempt_over_65', 0)
        if age_over_65 and exempt_amt > 0:
            retirement_taxable = max(0, retirement_taxable - exempt_amt)
        taxable += retirement_taxable
    if not rules.get('exempt_ss'):
        taxable += ss_taxable
    taxable = max(0.0, taxable)
    # Flat states use the CSV rate.  CA/NY are bracketed enough that a single
    # rate badly distorts residency comparisons; use a conservative bracket
    # schedule and fall back to the CSV rate for any unlisted graduated state.
    # Item 4.6 (P10 second half): these thresholds are only accurate as of
    # _STATE_INCOME_BRACKETS_VALUE_YEAR — inflate them by brk_inf the same way
    # compute_fed_tax inflates the federal brackets, or a 30-year projection
    # shows CA/NY state tax drifting steadily upward relative to federal
    # purely from frozen bracket thresholds, not from any real law change.
    brackets = _STATE_INCOME_BRACKETS.get((state, filing)) or _STATE_INCOME_BRACKETS.get((state, 'Single'))
    if rules.get('type') == 'graduated' and brackets:
        years = int(year) - _STATE_INCOME_BRACKETS_VALUE_YEAR
        if years:
            brackets = inflate_brackets(brackets, brk_inf, years)
        return _bracket_tax(taxable, brackets)
    return max(0, taxable * rules['rate'])


def _bracket_tax(taxable, brackets):
    tax = 0.0
    for lo, hi, rate in brackets:
        if taxable <= lo:
            break
        tax += (min(taxable, hi) - lo) * rate
    return max(0.0, tax)


_STATE_INCOME_BRACKETS_VALUE_YEAR = TAX_BASE_YEAR

_STATE_INCOME_BRACKETS = {
    # Approximate current-law schedules used only where state_tax.csv marks a
    # state as graduated.  Thresholds should be refreshed in the annual tax-data
    # governance workflow. Accurate as of _STATE_INCOME_BRACKETS_VALUE_YEAR;
    # state_income_tax() inflates them forward by brk_inf for later years.
    ('California','Single'): [(0, 10756, .01), (10756, 25499, .02), (25499, 40245, .04), (40245, 55866, .06), (55866, 70606, .08), (70606, 360659, .093), (360659, 432787, .103), (432787, 721314, .113), (721314, float('inf'), .123)],
    ('California','MFJ'): [(0, 21512, .01), (21512, 50998, .02), (50998, 80490, .04), (80490, 111732, .06), (111732, 141212, .08), (141212, 721318, .093), (721318, 865574, .103), (865574, 1442628, .113), (1442628, float('inf'), .123)],
    ('California','HOH'): [(0, 21527, .01), (21527, 51000, .02), (51000, 65744, .04), (65744, 81364, .06), (81364, 96107, .08), (96107, 490493, .093), (490493, 588593, .103), (588593, 980987, .113), (980987, float('inf'), .123)],
    ('New York','Single'): [(0, 8500, .04), (8500, 11700, .045), (11700, 13900, .0525), (13900, 80650, .055), (80650, 215400, .06), (215400, 1077550, .0685), (1077550, 5000000, .0965), (5000000, 25000000, .103), (25000000, float('inf'), .109)],
    ('New York','MFJ'): [(0, 17150, .04), (17150, 23600, .045), (23600, 27900, .0525), (27900, 161550, .055), (161550, 323200, .06), (323200, 2155350, .0685), (2155350, 5000000, .0965), (5000000, 25000000, .103), (25000000, float('inf'), .109)],
    ('New York','HOH'): [(0, 12800, .04), (12800, 17650, .045), (17650, 20900, .0525), (20900, 107650, .055), (107650, 269300, .06), (269300, 1616450, .0685), (1616450, 5000000, .0965), (5000000, 25000000, .103), (25000000, float('inf'), .109)],
}

def il_income_tax(agi, year):
    return max(0, agi * 0.0495)

def irmaa_surcharge(agi, year, plan_start, inflator=0.02, n_people=2, filing='MFJ'):
    tiers = IRMAA_TIERS_BASE_YEAR.get(filing, IRMAA_TIERS_BASE_YEAR['MFJ'])
    infl = (1 + inflator) ** (year - plan_start)
    for threshold, partb, partd in reversed(tiers):
        if agi > threshold * infl:
            return (partb + partd) * n_people * 12
    return 0.0

def irmaa_tier(agi, year, plan_start, inflator=0.02, filing='MFJ'):
    tiers = IRMAA_TIERS_BASE_YEAR.get(filing, IRMAA_TIERS_BASE_YEAR['MFJ'])
    infl = (1 + inflator) ** (year - plan_start)
    for i, (threshold, _, _) in enumerate(reversed(tiers)):
        if agi > threshold * infl:
            return len(tiers) - i
    return 0

def niit_tax(nii, magi, filing='MFJ'):
    threshold = _td.NIIT_THRESHOLD.get(filing, 250000)
    return max(0, min(nii, magi - threshold)) * 0.038


# ── Qualified Charitable Distribution (QCD) ───────────────────────────────────
# Item 4.1 (P3): IRC §408(d)(8) per-person annual limit, indexed for inflation
# under SECURE 2.0 §307 since 2023. 2025 figure per IRS Notice 2024-80,
# inflated forward by the plan's bracket inflation like every other embedded
# statutory dollar limit in this module.
QCD_ANNUAL_LIMIT_BASE_YEAR = 2025
QCD_ANNUAL_LIMIT_BASE = 108_000.0


def qcd_annual_limit(year, brk_inf):
    return QCD_ANNUAL_LIMIT_BASE * (1.0 + float(brk_inf or 0.0)) ** (int(year) - QCD_ANNUAL_LIMIT_BASE_YEAR)


def qcd_eligible_from_year(dob_yr, dob_month):
    """First calendar year a person may make a QCD (age 70½).

    Year-granular, matching this engine's existing age-gate convention (e.g.
    RMD start age) rather than modeling a mid-year proration: if the date
    six months after the person's 70th birthday falls in the same calendar
    year as that birthday (birth month January-June), QCDs are allowed
    starting that year; a July-December birthday pushes 70½ into the
    following calendar year.
    """
    try:
        dob_yr = int(dob_yr)
        m = int(dob_month) if dob_month else 6
    except (TypeError, ValueError):
        return None
    return dob_yr + 70 if m <= 6 else dob_yr + 71


# ── Alternative Minimum Tax (AMT) ─────────────────────────────────────────────
# IRS 2025 figures (Rev. Proc. 2024-40), indexed forward by the plan's bracket
# inflation. The engine calls this only for households that enable the equity-
# compensation module and hold ISOs, so it is a timing/preference-item AMT: the
# ISO bargain element is an AMT preference that generates a minimum-tax credit
# usable in later years when the regular tax exceeds the tentative minimum tax.
AMT_BASE_YEAR = 2025
AMT_EXEMPTION_BASE = {'MFJ': 137000.0, 'Single': 88100.0, 'MFS': 68500.0}
AMT_PHASEOUT_START_BASE = {'MFJ': 1252700.0, 'Single': 626350.0, 'MFS': 626350.0}
AMT_RATE_BREAK_BASE = 232600.0   # 26% at/below, 28% above (halved for MFS)
AMT_RATE_LOW = 0.26
AMT_RATE_HIGH = 0.28


def _amt_filing_key(filing):
    f = str(filing or 'MFJ').strip().upper()
    if f.startswith('MFS') or 'SEPARATE' in f:
        return 'MFS'
    if f.startswith('MFJ') or f.startswith('MARRIED') or f.startswith('Q') or f.startswith('WIDOW'):
        return 'MFJ'
    return 'Single'


def _amt_indexed(base, year, inf):
    return base * ((1.0 + float(inf or 0.0)) ** max(0, int(year) - AMT_BASE_YEAR))


def tentative_minimum_tax(regular_taxable_income, amt_preferences, filing='MFJ',
                          year=AMT_BASE_YEAR, inf=0.0):
    """Tentative minimum tax on the ordinary AMT base.

    AMTI = regular (ordinary) taxable income + AMT preference items (e.g. the ISO
    bargain element). The exemption phases out 25% above the filing threshold.
    Long-term capital gains keep their preferential rate outside this base and are
    taxed by the engine's separate LTCG path, so they are intentionally excluded
    here.
    """
    key = _amt_filing_key(filing)
    amti = max(0.0, float(regular_taxable_income or 0.0) + float(amt_preferences or 0.0))
    exemption = _amt_indexed(AMT_EXEMPTION_BASE[key], year, inf)
    phase_start = _amt_indexed(AMT_PHASEOUT_START_BASE[key], year, inf)
    exemption = max(0.0, exemption - 0.25 * max(0.0, amti - phase_start))
    rate_break = _amt_indexed(AMT_RATE_BREAK_BASE * (0.5 if key == 'MFS' else 1.0), year, inf)
    base = max(0.0, amti - exemption)
    return AMT_RATE_LOW * min(base, rate_break) + AMT_RATE_HIGH * max(0.0, base - rate_break)


def amt_tax(regular_taxable_income, regular_tax, amt_preferences, filing='MFJ',
            year=AMT_BASE_YEAR, inf=0.0, amt_credit_carryin=0.0):
    """Return ``(amt_adjustment, amt_credit_carryout)``.

    ``amt_adjustment`` is added to the year's total tax: a positive value is AMT
    owed (TMT above the regular tax); a negative value is prior-year minimum-tax
    credit applied to reduce the regular tax when the regular tax exceeds TMT
    (limited to that excess). AMT owed accrues to the credit carryforward because
    ISO/preference AMT is a timing difference.
    """
    tmt = tentative_minimum_tax(regular_taxable_income, amt_preferences, filing, year, inf)
    reg = max(0.0, float(regular_tax or 0.0))
    carry = max(0.0, float(amt_credit_carryin or 0.0))
    owed = tmt - reg
    if owed > 0:
        return owed, carry + owed
    credit_used = min(carry, reg - tmt)
    return -credit_used, carry - credit_used

def salt_cap(year, magi):
    schedule = {
        TAX_BASE_YEAR - 1: 40000,
        TAX_BASE_YEAR: 40400,
        TAX_BASE_YEAR + 1: 40804,
        TAX_BASE_YEAR + 2: 41212,
        TAX_BASE_YEAR + 3: 41624,
    }
    if year >= _td.SALT_REVERSION_YEAR:
        return 10000
    cap = schedule.get(year, schedule.get(TAX_BASE_YEAR, 40000))
    thr = 500000 + (year - (TAX_BASE_YEAR - 1)) * 500
    return max(cap - 0.30 * max(magi - thr, 0), 10000)

def state_death_tax_credit(taxable_estate):
    """Pre-2005 federal state-death-tax-credit table used by Illinois."""
    te = max(0.0, float(taxable_estate or 0.0))
    table = [
        (40_000, 90_000, 0, 0.008), (90_000, 140_000, 400, 0.016),
        (140_000, 240_000, 1_200, 0.024), (240_000, 440_000, 3_600, 0.032),
        (440_000, 640_000, 10_000, 0.040), (640_000, 840_000, 18_000, 0.048),
        (840_000, 1_040_000, 27_600, 0.056), (1_040_000, 1_540_000, 38_800, 0.064),
        (1_540_000, 2_040_000, 70_800, 0.072), (2_040_000, 2_540_000, 106_800, 0.080),
        (2_540_000, 3_040_000, 146_800, 0.088), (3_040_000, 3_540_000, 190_800, 0.096),
        (3_540_000, 4_040_000, 238_800, 0.104), (4_040_000, 5_040_000, 290_800, 0.112),
        (5_040_000, 6_040_000, 402_800, 0.120), (6_040_000, 7_040_000, 522_800, 0.128),
        (7_040_000, 8_040_000, 650_800, 0.136), (8_040_000, 9_040_000, 786_800, 0.144),
        (9_040_000, 10_040_000, 930_800, 0.152), (10_040_000, float('inf'), 1_082_800, 0.160),
    ]
    for lo, hi, base, rate in table:
        if te <= lo:
            return 0.0
        if te <= hi:
            return base + (te - lo) * rate
    return 0.0


def illinois_estate_tax(gross_estate, exemption=4_000_000.0, iterations=30):
    """Approximate Illinois estate tax cliff/interrelated calculation.

    Once the estate exceeds the exclusion, Illinois tax is based on the entire
    taxable estate, not merely the excess.  The state tax itself is deductible
    in the federal-style credit computation, so solve T = credit(gross - T).
    """
    gross = max(0.0, float(gross_estate or 0.0))
    if gross <= max(0.0, float(exemption or 0.0)):
        return 0.0
    tax = state_death_tax_credit(gross)
    for _ in range(max(1, int(iterations or 1))):
        new_tax = state_death_tax_credit(max(0.0, gross - tax))
        if abs(new_tax - tax) < 1.0:
            tax = new_tax
            break
        tax = new_tax
    return max(0.0, tax)


def marginal_rate(taxable, year, filing, brk_inf):
    brk = FEDERAL_BRACKETS_BASE_YEAR.get(filing, FEDERAL_BRACKETS_BASE_YEAR['Single'])
    brk = inflate_brackets(brk, brk_inf, year - getattr(_td, 'FEDERAL_BRACKETS_VALUE_YEAR', TAX_BASE_YEAR))
    for lo, hi, rate in brk:
        if lo <= taxable < hi:
            return rate
    return 0.37

def ltcg_tax_on_gain(c, gain, ordinary_income, year):
    if gain <= 0:
        return 0.0
    infl = (1 + c['irmaa_inflator']) ** (year - c['plan_start'])
    top0 = c['ltcg_0_top'] * infl
    top15 = c['ltcg_15_top'] * infl
    base = max(0.0, ordinary_income)
    tax = 0.0
    remaining = gain
    band0 = max(0.0, top0 - base)
    in0 = min(remaining, band0)
    remaining -= in0
    band15 = max(0.0, top15 - max(base, top0))
    in15 = min(remaining, band15)
    tax += in15 * 0.15
    remaining -= in15
    tax += max(0.0, remaining) * 0.20
    # NIIT is intentionally not included here; the projection adds NIIT once centrally.
    return tax

def annuity_purchase_rate(age, calib=None):
    return _td.annuity_purchase_rate_from_calib(age, calib)

def _annuity_reserve(reserve_start, yr_offset, calib=None):
    return _td.annuity_reserve_from_calib(reserve_start, yr_offset, calib)

def annuity_cash_income(stream, year):
    fy = stream['first_yr']
    base_orig = stream['base']
    div_rate = stream['div_rate']
    add_pct = stream['add_pct']
    init_pmt = stream['init_pmt']
    dob_yr = stream.get('annuitant_dob_yr', 1961)
    rec_age = stream.get('recovery_age', 86)
    recovery_yr = dob_yr + rec_age
    calib = stream.get('annuity_calib')
    if base_orig == 0:
        return init_pmt * 12 if year >= fy else 0.0
    if year < fy:
        return 0.0
    deferral_years = max(0, stream.get('deferral_years', 0))
    defer_dampening = stream.get('deferral_dampening', 0.55)
    guar_annual = init_pmt * 12 * ((1 + div_rate * defer_dampening) ** deferral_years)
    reserve_factor = stream.get('reserve_factor', 0.853)
    reserve_start = base_orig * reserve_factor
    years_of_income = year - fy
    age_at_start = fy - dob_yr
    cache_key = '_pmt_cache'
    cache = stream.get(cache_key)
    if cache and cache[0] == year - 1:
        prev_pmt, prev_yr = cache[1], cache[0]
        yr_off = prev_yr - fy
        pmt = prev_pmt + _annuity_reserve(reserve_start, yr_off, calib) * div_rate * add_pct * annuity_purchase_rate(age_at_start + yr_off, calib)
    elif cache and cache[0] == year:
        pmt = cache[1]
    else:
        pmt = guar_annual
        for yr_off in range(years_of_income):
            pmt += _annuity_reserve(reserve_start, yr_off, calib) * div_rate * add_pct * annuity_purchase_rate(age_at_start + yr_off, calib)
    stream[cache_key] = (year, pmt)
    cash_div = _annuity_reserve(reserve_start, years_of_income, calib) * div_rate * (1.0 - add_pct) if year < recovery_yr else 0.0
    return pmt + cash_div

def annuity_pv(stream, start_year, end_year, discount_rate):
    return sum(annuity_cash_income(stream, yr) / (1 + discount_rate) ** (yr - start_year)
               for yr in range(start_year + 1, end_year + 1))

# ===== END engine_core.py =====
