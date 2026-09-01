from __future__ import annotations
import sys as _sys


# ===== BEGIN account_registry.py =====

"""
account_registry.py — Dynamic account model for the retirement projection engine.

Dynamic account registry. Each account has an owner, type, tax treatment, and RMD eligibility.
The projection engine operates on account *types* instead of account-name assumptions.
"""

from .person_labels import infer_member_role

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
    """Infer account type from an account identifier.

    Raises ValueError when the name matches none of the recognized
    type-indicating suffixes (item 1.16 / finding F9), rather than silently
    modeling an unrecognized account as taxable. A typo'd or unsupported
    account name previously produced a fully confident plan that used the
    wrong tax treatment and RMD behavior, with nothing on any report saying
    so -- the same silent-wrongness pattern `_require_supported_state` above
    exists to prevent for residence_state.
    """
    name = account_name.lower()
    if '_401k' in name:        return '401k'
    if '_403b' in name:        return '403b'
    if '_roth' in name:        return 'roth_ira'
    if '_ira' in name:         return 'traditional_ira'
    if '_trust' in name:       return 'trust'
    if '_hsa' in name:         return 'hsa'
    if '_checking' in name:    return 'checking'
    if '_529' in name:         return '529'
    if '_taxable' in name or '_brokerage' in name or '_investment' in name:
        return 'taxable'
    raise ValueError(
        f"Unrecognized account name {account_name!r}: no known account-type "
        "suffix found. Account names must indicate their tax treatment via a "
        "recognized suffix: _401k, _403b, _ira, _roth, _trust, _hsa, "
        "_checking, _529, _taxable, _brokerage, or _investment. Rename the "
        "account in client_holdings.csv (or the Positions section of "
        "client_data.csv) to include one of these suffixes."
    )


def _infer_owner(account_name, members):
    """Infer owner index from an account identifier. Returns 0 or 1."""
    if infer_member_role(account_name) == 'member_2':
        return 1 if len(members) > 1 else 0
    return 0  # member_1, or household/joint/business defaulting to member_1


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
        type_info = ACCOUNT_TYPES[acct_type]
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
        if acct_type not in ACCOUNT_TYPES:
            raise ValueError(
                f"Unrecognized acct_type {acct_type!r} for account "
                f"{acct.get('id', acct.get('label', f'acct_{i+1}'))!r}. Supported "
                f"account types: {', '.join(sorted(ACCOUNT_TYPES))}."
            )
        type_info = ACCOUNT_TYPES[acct_type]
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


def _apply_draw_priority(ids: list[str], priority: Mapping[str, int]) -> list[str]:
    """Re-sort ``ids`` by a user-set per-account draw priority (#276).

    Accounts with an explicit priority (lower number = drawn first) sort
    ahead of accounts without one; ties and unprioritized accounts keep their
    original relative (registry) order -- a stable sort, not a full
    re-ranking, so an override that only touches a couple of accounts
    doesn't scramble the rest of the cascade.
    """
    def key(item):
        i, aid = item
        p = priority.get(aid)
        return (0, p, i) if p is not None else (1, 0, i)
    return [aid for _, aid in sorted(enumerate(ids), key=key)]


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
    # #276: individual-account-level withdrawal order override. Absent/empty
    # by default (no CSV, or all rows still at the app's optimized default),
    # in which case this is a no-op and every existing caller/cascade/golden
    # test sees byte-identical ordering to before.
    priority = c.get('account_draw_priority')
    if priority:
        out = _apply_draw_priority(out, priority)
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


# ===== END account_access.py =====


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

    def _donatable_lots(self, account, current_year=None):
        """Long-term lots for ``account``, most-appreciated first.

        Charitable lot selection is the mirror image of sale lot selection, so
        it deliberately ignores ``self.method``. A sale wants the *highest*
        basis (HIFO) to minimize the gain it realizes; an in-kind gift wants
        the *lowest* basis, because that embedded gain disappears at the
        charity and is never taxed to anyone -- gifting high-basis shares
        wastes the strategy and strands the low-basis shares in the portfolio
        for a future taxable sale.

        Short-term lots are excluded outright: a gift of property held one year
        or less is deductible only at cost basis, not fair market value (IRC
        170(e)(1)(A)), so donating them forfeits the deduction this model
        grants. Callers cap the gift at what long-term lots can cover.
        """
        out = []
        for sym, lot_list in (self.lots.get(account, {}) or {}).items():
            price = self.prices.get(sym, 0)
            for lot in lot_list:
                if not self.is_long_term(lot, current_year):
                    continue
                if lot.qty <= 0 or price <= 0:
                    continue
                out.append((lot, price))
        out.sort(key=lambda x: x[0].cost_per_share)
        return out

    def donatable_value(self, account, current_year=None):
        """Market value of the long-term lots ``account`` could gift in kind."""
        if not self.use_lots:
            return None  # no lot data: caller falls back to balance-based logic
        return sum(lot.qty * price for lot, price in self._donatable_lots(account, current_year))

    def embedded_long_term_gain(self, account, current_year=None):
        """Unrealized long-term gain sitting in ``account``.

        Used to rank accounts for an in-kind gift: donate out of the account
        carrying the most appreciation, so the most gain escapes tax.
        """
        if not self.use_lots:
            return None
        total = 0.0
        for lot, price in self._donatable_lots(account, current_year):
            total += max(0.0, lot.qty * price - lot.cost_basis)
        return total

    def donate_lots(self, account, amount, current_year=None, mutate=True):
        """Consume long-term lots for an in-kind charitable gift.

        Returns ``(value_gifted, gain_avoided, consumed)``. ``value_gifted``
        can fall short of ``amount`` when the account holds too little
        long-term stock -- callers must surface that rather than silently
        treating the whole gift as given. No gain is realized: an in-kind
        charitable transfer is not a realization event, so ``gain_avoided`` is
        reporting only, the tax the household did not pay.
        """
        if not self.use_lots:
            # No usable lot data anywhere: "which lot" is not a meaningful
            # question, so gift by balance and report the flat-fraction gain.
            return amount, amount * self.fallback, []

        remaining = max(0.0, float(amount or 0.0))
        gifted = 0.0
        gain_avoided = 0.0
        consumed = []
        for lot, price in self._donatable_lots(account, current_year):
            if remaining <= 1e-9:
                break
            mv = lot.qty * price
            if mv <= 0:
                continue
            give_mv = min(remaining, mv)
            give_fraction = give_mv / mv
            give_basis = lot.cost_basis * give_fraction
            gain_avoided += max(0.0, give_mv - give_basis)
            if mutate:
                lot.qty *= (1 - give_fraction)
                lot.cost_basis *= (1 - give_fraction)
            gifted += give_mv
            remaining -= give_mv
            consumed.append((lot.symbol, give_mv, max(0.0, give_mv - give_basis)))
        return gifted, gain_avoided, consumed

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
from . import tax_kernel as _tk

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

# IRS Publication 590-B (2025), Appendix B, Table II (Joint and Last Survivor
# Life Expectancy) -- "For Use by Owners Whose Spouses Are More Than 10 Years
# Younger and Are the Sole Beneficiaries of Their IRAs." Transcribed directly
# from the IRS PDF (rows = owner age, columns = spouse age), restricted to
# owner ages 72-105 (the RMD-relevant range this codebase's Uniform Lifetime
# table already covers) and spouse ages strictly more than 10 years younger
# than the owner (columns beyond that gap are never looked up -- see
# joint_life_divisor below, which gates on the >10-year rule itself).
RMD_JOINT_LIFE_DIVISORS = {
    72: {20:65.1, 21:64.2, 22:63.2, 23:62.2, 24:61.3, 25:60.3, 26:59.3, 27:58.4, 28:57.4, 29:56.5, 30:55.5, 31:54.5, 32:53.6, 33:52.6, 34:51.7, 35:50.8, 36:49.8, 37:48.9, 38:47.9, 39:47.0, 40:46.0, 41:45.1, 42:44.2, 43:43.2, 44:42.3, 45:41.4, 46:40.5, 47:39.6, 48:38.7, 49:37.8, 50:36.9, 51:36.0, 52:35.2, 53:34.3, 54:33.5, 55:32.7, 56:31.9, 57:31.1, 58:30.3, 59:29.5, 60:28.8, 61:28.1},
    73: {20:65.1, 21:64.2, 22:63.2, 23:62.2, 24:61.2, 25:60.3, 26:59.3, 27:58.4, 28:57.4, 29:56.4, 30:55.5, 31:54.5, 32:53.6, 33:52.6, 34:51.7, 35:50.7, 36:49.8, 37:48.8, 38:47.9, 39:46.9, 40:46.0, 41:45.1, 42:44.1, 43:43.2, 44:42.3, 45:41.4, 46:40.4, 47:39.5, 48:38.6, 49:37.7, 50:36.8, 51:36.0, 52:35.1, 53:34.2, 54:33.4, 55:32.6, 56:31.7, 57:30.9, 58:30.1, 59:29.4, 60:28.6, 61:27.9, 62:27.2},
    74: {20:65.1, 21:64.1, 22:63.2, 23:62.2, 24:61.2, 25:60.3, 26:59.3, 27:58.3, 28:57.4, 29:56.4, 30:55.5, 31:54.5, 32:53.6, 33:52.6, 34:51.7, 35:50.7, 36:49.8, 37:48.8, 38:47.9, 39:46.9, 40:46.0, 41:45.0, 42:44.1, 43:43.2, 44:42.2, 45:41.3, 46:40.4, 47:39.5, 48:38.6, 49:37.7, 50:36.8, 51:35.9, 52:35.0, 53:34.1, 54:33.3, 55:32.4, 56:31.6, 57:30.8, 58:30.0, 59:29.2, 60:28.4, 61:27.7, 62:27.0, 63:26.2},
    75: {20:65.1, 21:64.1, 22:63.2, 23:62.2, 24:61.2, 25:60.3, 26:59.3, 27:58.3, 28:57.4, 29:56.4, 30:55.5, 31:54.5, 32:53.5, 33:52.6, 34:51.6, 35:50.7, 36:49.7, 37:48.8, 38:47.8, 39:46.9, 40:45.9, 41:45.0, 42:44.1, 43:43.1, 44:42.2, 45:41.3, 46:40.3, 47:39.4, 48:38.5, 49:37.6, 50:36.7, 51:35.8, 52:34.9, 53:34.1, 54:33.2, 55:32.4, 56:31.5, 57:30.7, 58:29.9, 59:29.1, 60:28.3, 61:27.5, 62:26.8, 63:26.1, 64:25.3},
    76: {20:65.1, 21:64.1, 22:63.2, 23:62.2, 24:61.2, 25:60.2, 26:59.3, 27:58.3, 28:57.4, 29:56.4, 30:55.4, 31:54.5, 32:53.5, 33:52.6, 34:51.6, 35:50.7, 36:49.7, 37:48.8, 38:47.8, 39:46.9, 40:45.9, 41:45.0, 42:44.0, 43:43.1, 44:42.2, 45:41.2, 46:40.3, 47:39.4, 48:38.5, 49:37.5, 50:36.6, 51:35.7, 52:34.9, 53:34.0, 54:33.1, 55:32.3, 56:31.4, 57:30.6, 58:29.8, 59:29.0, 60:28.2, 61:27.4, 62:26.6, 63:25.9, 64:25.2, 65:24.4},
    77: {20:65.1, 21:64.1, 22:63.1, 23:62.2, 24:61.2, 25:60.2, 26:59.3, 27:58.3, 28:57.3, 29:56.4, 30:55.4, 31:54.5, 32:53.5, 33:52.6, 34:51.6, 35:50.7, 36:49.7, 37:48.8, 38:47.8, 39:46.9, 40:45.9, 41:45.0, 42:44.0, 43:43.1, 44:42.1, 45:41.2, 46:40.3, 47:39.3, 48:38.4, 49:37.5, 50:36.6, 51:35.7, 52:34.8, 53:33.9, 54:33.0, 55:32.2, 56:31.3, 57:30.5, 58:29.7, 59:28.8, 60:28.0, 61:27.3, 62:26.5, 63:25.7, 64:25.0, 65:24.3, 66:23.5},
    78: {20:65.1, 21:64.1, 22:63.1, 23:62.2, 24:61.2, 25:60.2, 26:59.3, 27:58.3, 28:57.3, 29:56.4, 30:55.4, 31:54.5, 32:53.5, 33:52.6, 34:51.6, 35:50.6, 36:49.7, 37:48.7, 38:47.8, 39:46.8, 40:45.9, 41:44.9, 42:44.0, 43:43.0, 44:42.1, 45:41.2, 46:40.2, 47:39.3, 48:38.4, 49:37.5, 50:36.5, 51:35.6, 52:34.7, 53:33.9, 54:33.0, 55:32.1, 56:31.2, 57:30.4, 58:29.6, 59:28.7, 60:27.9, 61:27.1, 62:26.4, 63:25.6, 64:24.8, 65:24.1, 66:23.4, 67:22.7},
    79: {20:65.1, 21:64.1, 22:63.1, 23:62.2, 24:61.2, 25:60.2, 26:59.3, 27:58.3, 28:57.3, 29:56.4, 30:55.4, 31:54.5, 32:53.5, 33:52.5, 34:51.6, 35:50.6, 36:49.7, 37:48.7, 38:47.8, 39:46.8, 40:45.9, 41:44.9, 42:44.0, 43:43.0, 44:42.1, 45:41.1, 46:40.2, 47:39.3, 48:38.3, 49:37.4, 50:36.5, 51:35.6, 52:34.7, 53:33.8, 54:32.9, 55:32.0, 56:31.2, 57:30.3, 58:29.5, 59:28.7, 60:27.8, 61:27.0, 62:26.2, 63:25.5, 64:24.7, 65:23.9, 66:23.2, 67:22.5, 68:21.8},
    80: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.2, 25:60.2, 26:59.2, 27:58.3, 28:57.3, 29:56.4, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.6, 35:50.6, 36:49.7, 37:48.7, 38:47.8, 39:46.8, 40:45.9, 41:44.9, 42:43.9, 43:43.0, 44:42.1, 45:41.1, 46:40.2, 47:39.2, 48:38.3, 49:37.4, 50:36.5, 51:35.5, 52:34.6, 53:33.7, 54:32.9, 55:32.0, 56:31.1, 57:30.3, 58:29.4, 59:28.6, 60:27.8, 61:26.9, 62:26.1, 63:25.3, 64:24.6, 65:23.8, 66:23.1, 67:22.3, 68:21.6, 69:20.9},
    81: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.2, 25:60.2, 26:59.2, 27:58.3, 28:57.3, 29:56.4, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.6, 35:50.6, 36:49.7, 37:48.7, 38:47.7, 39:46.8, 40:45.8, 41:44.9, 42:43.9, 43:43.0, 44:42.0, 45:41.1, 46:40.1, 47:39.2, 48:38.3, 49:37.3, 50:36.4, 51:35.5, 52:34.6, 53:33.7, 54:32.8, 55:31.9, 56:31.1, 57:30.2, 58:29.3, 59:28.5, 60:27.7, 61:26.9, 62:26.0, 63:25.2, 64:24.5, 65:23.7, 66:22.9, 67:22.2, 68:21.5, 69:20.7, 70:20.0},
    82: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.2, 25:60.2, 26:59.2, 27:58.3, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.6, 35:50.6, 36:49.7, 37:48.7, 38:47.7, 39:46.8, 40:45.8, 41:44.9, 42:43.9, 43:43.0, 44:42.0, 45:41.1, 46:40.1, 47:39.2, 48:38.3, 49:37.3, 50:36.4, 51:35.5, 52:34.6, 53:33.7, 54:32.8, 55:31.9, 56:31.0, 57:30.1, 58:29.3, 59:28.4, 60:27.6, 61:26.8, 62:26.0, 63:25.2, 64:24.4, 65:23.6, 66:22.8, 67:22.1, 68:21.3, 69:20.6, 70:19.9, 71:19.2},
    83: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.2, 25:60.2, 26:59.2, 27:58.3, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.6, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.8, 40:45.8, 41:44.9, 42:43.9, 43:43.0, 44:42.0, 45:41.1, 46:40.1, 47:39.2, 48:38.2, 49:37.3, 50:36.4, 51:35.4, 52:34.5, 53:33.6, 54:32.7, 55:31.8, 56:31.0, 57:30.1, 58:29.2, 59:28.4, 60:27.5, 61:26.7, 62:25.9, 63:25.1, 64:24.3, 65:23.5, 66:22.7, 67:22.0, 68:21.2, 69:20.5, 70:19.7, 71:19.0, 72:18.3},
    84: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.2, 25:60.2, 26:59.2, 27:58.3, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.8, 40:45.8, 41:44.9, 42:43.9, 43:42.9, 44:42.0, 45:41.0, 46:40.1, 47:39.2, 48:38.2, 49:37.3, 50:36.3, 51:35.4, 52:34.5, 53:33.6, 54:32.7, 55:31.8, 56:30.9, 57:30.0, 58:29.2, 59:28.3, 60:27.5, 61:26.7, 62:25.8, 63:25.0, 64:24.2, 65:23.4, 66:22.6, 67:21.9, 68:21.1, 69:20.4, 70:19.6, 71:18.9, 72:18.2, 73:17.5},
    85: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.2, 25:60.2, 26:59.2, 27:58.3, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.8, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:42.0, 45:41.0, 46:40.1, 47:39.1, 48:38.2, 49:37.3, 50:36.3, 51:35.4, 52:34.5, 53:33.6, 54:32.7, 55:31.8, 56:30.9, 57:30.0, 58:29.1, 59:28.3, 60:27.4, 61:26.6, 62:25.8, 63:25.0, 64:24.1, 65:23.3, 66:22.6, 67:21.8, 68:21.0, 69:20.3, 70:19.5, 71:18.8, 72:18.1, 73:17.4, 74:16.7},
    86: {20:65.1, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.5, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:42.0, 45:41.0, 46:40.1, 47:39.1, 48:38.2, 49:37.2, 50:36.3, 51:35.4, 52:34.5, 53:33.5, 54:32.6, 55:31.7, 56:30.9, 57:30.0, 58:29.1, 59:28.2, 60:27.4, 61:26.6, 62:25.7, 63:24.9, 64:24.1, 65:23.3, 66:22.5, 67:21.7, 68:20.9, 69:20.2, 70:19.4, 71:18.7, 72:17.9, 73:17.2, 74:16.5, 75:15.9},
    87: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:42.0, 45:41.0, 46:40.1, 47:39.1, 48:38.2, 49:37.2, 50:36.3, 51:35.4, 52:34.4, 53:33.5, 54:32.6, 55:31.7, 56:30.8, 57:29.9, 58:29.1, 59:28.2, 60:27.4, 61:26.5, 62:25.7, 63:24.9, 64:24.0, 65:23.2, 66:22.4, 67:21.6, 68:20.9, 69:20.1, 70:19.3, 71:18.6, 72:17.8, 73:17.1, 74:16.4, 75:15.7, 76:15.1},
    88: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:42.0, 45:41.0, 46:40.0, 47:39.1, 48:38.2, 49:37.2, 50:36.3, 51:35.3, 52:34.4, 53:33.5, 54:32.6, 55:31.7, 56:30.8, 57:29.9, 58:29.0, 59:28.2, 60:27.3, 61:26.5, 62:25.6, 63:24.8, 64:24.0, 65:23.2, 66:22.4, 67:21.6, 68:20.8, 69:20.0, 70:19.2, 71:18.5, 72:17.7, 73:17.0, 74:16.3, 75:15.6, 76:14.9, 77:14.3},
    89: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.7, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.3, 51:35.3, 52:34.4, 53:33.5, 54:32.6, 55:31.7, 56:30.8, 57:29.9, 58:29.0, 59:28.2, 60:27.3, 61:26.4, 62:25.6, 63:24.8, 64:24.0, 65:23.1, 66:22.3, 67:21.5, 68:20.7, 69:20.0, 70:19.2, 71:18.4, 72:17.7, 73:16.9, 74:16.2, 75:15.5, 76:14.8, 77:14.2, 78:13.5},
    90: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.4, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.3, 51:35.3, 52:34.4, 53:33.5, 54:32.6, 55:31.7, 56:30.8, 57:29.9, 58:29.0, 59:28.1, 60:27.3, 61:26.4, 62:25.6, 63:24.7, 64:23.9, 65:23.1, 66:22.3, 67:21.5, 68:20.7, 69:19.9, 70:19.1, 71:18.4, 72:17.6, 73:16.9, 74:16.1, 75:15.4, 76:14.8, 77:14.1, 78:13.4, 79:12.8},
    91: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.9, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.4, 53:33.5, 54:32.5, 55:31.6, 56:30.7, 57:29.9, 58:29.0, 59:28.1, 60:27.3, 61:26.4, 62:25.6, 63:24.7, 64:23.9, 65:23.1, 66:22.3, 67:21.5, 68:20.7, 69:19.9, 70:19.1, 71:18.3, 72:17.5, 73:16.8, 74:16.1, 75:15.3, 76:14.6, 77:14.0, 78:13.3, 79:12.7, 80:12.1},
    92: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.4, 53:33.5, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:29.0, 59:28.1, 60:27.2, 61:26.4, 62:25.5, 63:24.7, 64:23.9, 65:23.0, 66:22.2, 67:21.4, 68:20.6, 69:19.8, 70:19.0, 71:18.3, 72:17.5, 73:16.7, 74:16.0, 75:15.3, 76:14.6, 77:13.9, 78:13.2, 79:12.6, 80:11.9, 81:11.4},
    93: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.4, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:29.0, 59:28.1, 60:27.2, 61:26.4, 62:25.5, 63:24.7, 64:23.8, 65:23.0, 66:22.2, 67:21.4, 68:20.6, 69:19.8, 70:19.0, 71:18.2, 72:17.4, 73:16.7, 74:15.9, 75:15.2, 76:14.5, 77:13.8, 78:13.1, 79:12.5, 80:11.9, 81:11.3, 82:10.7},
    94: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.4, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.1, 60:27.2, 61:26.3, 62:25.5, 63:24.7, 64:23.8, 65:23.0, 66:22.2, 67:21.4, 68:20.6, 69:19.8, 70:19.0, 71:18.2, 72:17.4, 73:16.6, 74:15.9, 75:15.2, 76:14.4, 77:13.7, 78:13.1, 79:12.4, 80:11.8, 81:11.2, 82:10.6, 83:10.0},
    95: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.4, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.1, 60:27.2, 61:26.3, 62:25.5, 63:24.6, 64:23.8, 65:23.0, 66:22.2, 67:21.4, 68:20.6, 69:19.7, 70:18.9, 71:18.2, 72:17.4, 73:16.6, 74:15.9, 75:15.1, 76:14.4, 77:13.7, 78:13.0, 79:12.3, 80:11.7, 81:11.1, 82:10.5, 83:9.9, 84:9.4},
    96: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.2, 61:26.3, 62:25.5, 63:24.6, 64:23.8, 65:23.0, 66:22.2, 67:21.3, 68:20.5, 69:19.7, 70:18.9, 71:18.1, 72:17.4, 73:16.6, 74:15.8, 75:15.1, 76:14.3, 77:13.6, 78:12.9, 79:12.3, 80:11.6, 81:11.0, 82:10.4, 83:9.9, 84:9.3, 85:8.8},
    97: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.2, 61:26.3, 62:25.5, 63:24.6, 64:23.8, 65:23.0, 66:22.1, 67:21.3, 68:20.5, 69:19.7, 70:18.9, 71:18.1, 72:17.3, 73:16.6, 74:15.8, 75:15.0, 76:14.3, 77:13.6, 78:12.9, 79:12.2, 80:11.6, 81:11.0, 82:10.4, 83:9.8, 84:9.2, 85:8.7, 86:8.3},
    98: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.2, 61:26.3, 62:25.5, 63:24.6, 64:23.8, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.7, 70:18.9, 71:18.1, 72:17.3, 73:16.5, 74:15.8, 75:15.0, 76:14.3, 77:13.6, 78:12.9, 79:12.2, 80:11.5, 81:10.9, 82:10.3, 83:9.7, 84:9.2, 85:8.7, 86:8.2, 87:7.7},
    99: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.1, 48:38.1, 49:37.2, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.2, 61:26.3, 62:25.4, 63:24.6, 64:23.8, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.7, 70:18.9, 71:18.1, 72:17.3, 73:16.5, 74:15.7, 75:15.0, 76:14.3, 77:13.5, 78:12.8, 79:12.2, 80:11.5, 81:10.9, 82:10.2, 83:9.7, 84:9.1, 85:8.6, 86:8.1, 87:7.6, 88:7.2},
    100: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.0, 48:38.1, 49:37.1, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.1, 61:26.3, 62:25.4, 63:24.6, 64:23.8, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.7, 70:18.9, 71:18.1, 72:17.3, 73:16.5, 74:15.7, 75:15.0, 76:14.2, 77:13.5, 78:12.8, 79:12.1, 80:11.5, 81:10.8, 82:10.2, 83:9.6, 84:9.1, 85:8.5, 86:8.0, 87:7.6, 88:7.2, 89:6.8},
    101: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.0, 48:38.1, 49:37.1, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.1, 61:26.3, 62:25.4, 63:24.6, 64:23.8, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.7, 70:18.9, 71:18.1, 72:17.3, 73:16.5, 74:15.7, 75:15.0, 76:14.2, 77:13.5, 78:12.8, 79:12.1, 80:11.4, 81:10.8, 82:10.2, 83:9.6, 84:9.0, 85:8.5, 86:8.0, 87:7.5, 88:7.1, 89:6.7, 90:6.3},
    102: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.6, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.0, 48:38.1, 49:37.1, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.1, 61:26.3, 62:25.4, 63:24.6, 64:23.7, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.7, 70:18.8, 71:18.0, 72:17.3, 73:16.5, 74:15.7, 75:14.9, 76:14.2, 77:13.5, 78:12.8, 79:12.1, 80:11.4, 81:10.8, 82:10.1, 83:9.6, 84:9.0, 85:8.5, 86:8.0, 87:7.5, 88:7.0, 89:6.6, 90:6.3, 91:5.9},
    103: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.5, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.0, 48:38.1, 49:37.1, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.1, 61:26.3, 62:25.4, 63:24.6, 64:23.7, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.6, 70:18.8, 71:18.0, 72:17.3, 73:16.5, 74:15.7, 75:14.9, 76:14.2, 77:13.5, 78:12.8, 79:12.1, 80:11.4, 81:10.7, 82:10.1, 83:9.5, 84:9.0, 85:8.4, 86:7.9, 87:7.4, 88:7.0, 89:6.6, 90:6.2, 91:5.9, 92:5.5},
    104: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.5, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.8, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.0, 48:38.1, 49:37.1, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.1, 61:26.3, 62:25.4, 63:24.6, 64:23.7, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.6, 70:18.8, 71:18.0, 72:17.2, 73:16.5, 74:15.7, 75:14.9, 76:14.2, 77:13.5, 78:12.7, 79:12.0, 80:11.4, 81:10.7, 82:10.1, 83:9.5, 84:8.9, 85:8.4, 86:7.9, 87:7.4, 88:7.0, 89:6.6, 90:6.2, 91:5.8, 92:5.5, 93:5.2},
    105: {20:65.0, 21:64.1, 22:63.1, 23:62.1, 24:61.1, 25:60.2, 26:59.2, 27:58.2, 28:57.3, 29:56.3, 30:55.3, 31:54.4, 32:53.4, 33:52.5, 34:51.5, 35:50.5, 36:49.6, 37:48.6, 38:47.7, 39:46.7, 40:45.7, 41:44.8, 42:43.8, 43:42.9, 44:41.9, 45:41.0, 46:40.0, 47:39.0, 48:38.1, 49:37.1, 50:36.2, 51:35.3, 52:34.3, 53:33.4, 54:32.5, 55:31.6, 56:30.7, 57:29.8, 58:28.9, 59:28.0, 60:27.1, 61:26.3, 62:25.4, 63:24.6, 64:23.7, 65:22.9, 66:22.1, 67:21.3, 68:20.5, 69:19.6, 70:18.8, 71:18.0, 72:17.2, 73:16.5, 74:15.7, 75:14.9, 76:14.2, 77:13.4, 78:12.7, 79:12.0, 80:11.4, 81:10.7, 82:10.1, 83:9.5, 84:8.9, 85:8.4, 86:7.9, 87:7.4, 88:6.9, 89:6.5, 90:6.1, 91:5.8, 92:5.4, 93:5.1, 94:4.9},
}

def joint_life_divisor(owner_age, spouse_age):
    """IRS Table II divisor for ``owner_age`` with a sole-beneficiary spouse
    at ``spouse_age`` more than 10 years younger. Callers must apply the
    >10-year and sole-beneficiary gates themselves (see
    ``planning_engines.rmd_divisor``); this is a pure table lookup.

    Owner ages outside [72, 105] clamp to the nearest tabulated row (the
    table is already nearly flat at both ends of that range -- e.g. row 72
    and row 105 agree to within a few tenths for any given spouse age -- so
    clamping does not manufacture a discontinuity the way linear
    extrapolation would). Spouse ages below the table's minimum column (20)
    clamp to 20; both clamps are conservative in the same direction as
    RMD_DIVISORS' own post-table continuation (never inventing a longer
    joint life expectancy than the table's own boundary row/column shows).
    """
    owner_row = min(max(int(owner_age), min(RMD_JOINT_LIFE_DIVISORS)), max(RMD_JOINT_LIFE_DIVISORS))
    row = RMD_JOINT_LIFE_DIVISORS[owner_row]
    spouse_col = min(max(int(spouse_age), min(row)), max(row))
    return row[spouse_col]


def rmd_divisor(age, spouse_age=None, sole_beneficiary_spouse=False):
    """Uniform Lifetime divisor for ``age``, or the IRS Table II (Joint and
    Last Survivor) divisor when ``sole_beneficiary_spouse`` is true and
    ``spouse_age`` is more than 10 years younger -- the one case where the
    Uniform Lifetime table understates the RMD reduction a household
    actually gets (finding F10 / item 2.9).
    """
    if age < 72:
        return 0
    if sole_beneficiary_spouse and spouse_age is not None and (age - spouse_age) > 10:
        return joint_life_divisor(age, spouse_age)
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
NIIT_THRESHOLD = _td.NIIT_THRESHOLD
LTCG_BRACKETS_BASE_YEAR = _td.LTCG_BRACKETS_BASE_YEAR

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


def require_residence_state_for_build(state):
    """Fail loudly when a REAL build has no usable residence_state (item 291).

    Distinct from `_require_supported_state` below, which is deliberately
    lenient on a BLANK state -- that leniency exists for low-level/defensive
    callers (partial snapshots, autosave backups) that were never going to
    produce a client-facing deliverable in the first place; see its own
    docstring. This function is the actual per-build gate, called once
    `c['state']` is finalized: it treats a MISSING state exactly like an
    unsupported one, because data_io.py no longer silently substitutes
    Illinois for a blank residence_state (item 291's Class 1 fix) -- so by
    the time a real build reaches here, blank genuinely means "the field was
    never filled in", not "an in-progress partial snapshot". A real build
    must never ship Illinois's numbers for a household that never said it
    lives in Illinois.
    """
    if not state:
        raise ValueError(
            "residence_state is not set. State tax, estate, and cost-of-living "
            "figures cannot be computed without it. Set it on the State Residency "
            "page (Plan Data field: residence_state), then rebuild. Supported "
            f"states: {', '.join(supported_states())}. To model another state, "
            "add a row to reference_data/state_tax.csv."
        )
    _require_supported_state(state)


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
    # Item 291 (2026-08-19): a Step 7.7 sweep flagged this fallback and it was
    # reverted after a genuine scope conflict with Class 1's own deliberate,
    # tested design -- see test_existing_low_level_leniency_is_unaffected /
    # test_blank_state_still_falls_back_silently_not_bricked and their
    # docstrings ("this ticket adds a new gate, it does not change the old
    # one"). A blank state can never reach a real build
    # (require_residence_state_for_build already blocks that at the build
    # gate); this fallback exists only for defensive/partial-snapshot callers
    # this repo deliberately keeps lenient, and changing its shape here was
    # out of scope for those callers, not a live silent-Illinois-in-output bug.
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


def state_estate_tax(state, taxable_estate, exemption=None):
    """Dispatch state estate tax on data (item 291's Class 2), not on a
    hardcoded state name. Returns ``(tax_amount, status)``.

    ``status`` is one of:
      - ``'computed'``     -- ``tax_amount`` is a real, modeled figure.
      - ``'none'``         -- this state does not levy an estate tax
                              (``estate_calc == 'none'``); ``tax_amount`` is 0.0
                              and that 0.0 is correct, not a placeholder.
      - ``'not_modeled'``  -- this state DOES levy an estate tax, but this
                              engine has no calculation for its mechanism yet
                              (e.g. New York's own graduated-rate table, which
                              is a genuinely different computation from
                              Illinois's pre-2005-federal-credit-table cliff
                              method -- reusing ``illinois_estate_tax`` for a
                              different state's law would produce a wrong
                              dollar figure, not an approximate one).
                              ``tax_amount`` is 0.0, but callers MUST NOT treat
                              that 0.0 as "no tax owed" the way they may for
                              ``'none'`` -- a reporting caller must render an
                              explicit "not modeled" disclosure rather than
                              silently presenting $0 as if it were computed.
      - ``'unrecognized'`` -- ``state`` has no entry in ``STATE_TAX_RULES`` at
                              all. Same 0.0/must-disclose contract as
                              ``'not_modeled'``.

    Extending to a new state's real mechanism means adding both a new
    ``estate_calc`` value handled here AND its actual calculation -- adding
    just the CSV/STATE_TAX_DEFAULTS row is not sufficient and must not silently
    fall through to ``'none'``.
    """
    rules = STATE_TAX_RULES.get(state)
    if not rules:
        return 0.0, 'unrecognized'
    calc = rules.get('estate_calc', 'none')
    exempt = exemption if exemption is not None else rules.get('estate_exempt', 0.0)
    if calc == 'il_credit_table':
        return illinois_estate_tax(taxable_estate, exempt), 'computed'
    if calc == 'not_modeled':
        return 0.0, 'not_modeled'
    return 0.0, 'none'


def indexed_federal_estate_exemption(fed_exempt_base, plan_start, target_year, brk_inf):
    """Grow the federal estate exemption to the year it is actually applied.

    The exemption is a statutory dollar figure indexed for inflation each
    year (like the income tax brackets), not a fixed constant for the life of
    the plan. Applying the plan-start exemption to a terminal estate decades
    out understates the real future exemption and overstates federal estate
    tax on long-horizon plans. Uses the same bracket inflator (brk_inf) as
    the income-tax brackets, since both are indexed the same way in statute.
    """
    years = max(0, int(target_year) - int(plan_start))
    return max(0.0, float(fed_exempt_base or 0.0)) * ((1.0 + float(brk_inf or 0.0)) ** years)


def deflate_to_present(nominal, year, c):
    """Convert a nominal-year dollar figure to plan-start purchasing power.

    System review C5 / Wave 3.4: every headline dollar figure in the
    workbook/API was nominal-only, so a 2056 dollar reads the same as a 2026
    dollar even though it buys far less. Uses the same general-CPI inflation
    rate (c['inf']) as sheets_projection_charts.py's existing 'real_nw'
    deflation, so the two stay consistent with each other.
    """
    cpi_deflator = (1.0 + float(c.get('inf', 0.0) or 0.0)) ** max(0, int(year) - int(c.get('plan_start', year) or year))
    return nominal / cpi_deflator if cpi_deflator > 0 else nominal


def marginal_rate(taxable, year, filing, brk_inf):
    brk = FEDERAL_BRACKETS_BASE_YEAR.get(filing, FEDERAL_BRACKETS_BASE_YEAR['Single'])
    brk = inflate_brackets(brk, brk_inf, year - getattr(_td, 'FEDERAL_BRACKETS_VALUE_YEAR', TAX_BASE_YEAR))
    for lo, hi, rate in brk:
        if lo <= taxable < hi:
            return rate
    return 0.37

def ltcg_tax_on_gain(c, gain, ordinary_income, year):
    """Thin call site into the canonical kernel implementation.

    Tax-kernel extraction (system review Wave 2 item 2.1): this used to
    inflate LTCG bracket tops using ``irmaa_inflator`` compounded from
    ``plan_start``. It now delegates to ``tax_kernel.ltcg_tax_on_gain``,
    which uses ``brk_inf`` (``fed_tax_bracket_inflator``) compounded from
    the brackets' statutory value year -- see ``src/tax_kernel.py``'s module
    docstring for the sign-off and the measured divergence this fixes.
    """
    return _tk.ltcg_tax_on_gain(c, gain, ordinary_income, year)

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
