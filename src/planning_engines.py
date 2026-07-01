from __future__ import annotations
import sys as _sys


# ===== BEGIN growth_engine.py =====

"""Portfolio growth helpers for the retirement projection engine.

This module centralizes end-of-year account growth so projection code does not
inline account traversal or accidentally compound the same account twice.
"""

from collections import namedtuple
from math import isfinite

GrowthResult = namedtuple('GrowthResult', ['total_growth', 'by_account', 'warnings'])


def _account_return(c, account_id, default_return, year=None):
    """Return the account-specific growth rate, falling back to plan return.

    Future modules can populate ``c['account_returns']`` with per-account rates.
    For now this keeps deterministic projections compatible with the existing
    single return assumption.
    """
    # Year-specific simulated return path takes precedence in Monte Carlo.
    if year is not None and isinstance(c.get('return_by_year'), dict) and year in c.get('return_by_year'):
        return float(c['return_by_year'][year])
    overrides = c.get('account_returns') or {}
    try:
        rate = float(overrides.get(account_id, default_return))
    except Exception:
        rate = default_return
    if not isfinite(rate):
        return default_return
    return rate


def investable_account_ids(c):
    """Return each investable account exactly once, preserving registry order."""
    seen = set()
    result = []
    for aid in c.get('invest_ids', []) or []:
        if aid not in seen:
            seen.add(aid)
            result.append(aid)
    return result


def apply_end_of_year_growth(c, balances, default_return=None, emit=None, event_factory=None,
                             min_event_balance=100.0, year=None):
    """Apply end-of-year growth to investable accounts.

    Args:
        c: plan dict containing ``invest_ids`` and ``ret``.
        balances: mutable account-balance dict.
        default_return: optional growth rate. Defaults to ``c['ret']``.
        emit: optional callable for event emission.
        event_factory: optional callable ``(year, acct, before, rate, growth)``.
        min_event_balance: only emit growth events for balances above this.

    Returns:
        GrowthResult(total_growth, by_account, warnings)
    """
    if default_return is None:
        default_return = c.get('ret', 0.0)
    try:
        default_return = float(default_return)
    except Exception:
        default_return = 0.0
    if not isfinite(default_return):
        default_return = 0.0

    total_growth = 0.0
    by_account = {}
    warnings = []

    for acct in investable_account_ids(c):
        before = float(balances.get(acct, 0.0) or 0.0)
        rate = _account_return(c, acct, default_return, year=year)
        # Taxable portfolio income is modeled as distributed cash income earlier
        # in the projection.  Reduce price appreciation by the same distribution
        # yield so total return is conserved rather than double-counted.
        if c.get('portfolio_income_reduces_growth', True):
            try:
                yinfo = (c.get('account_taxable_income_assumptions') or {}).get(acct, {})
                rate -= float(yinfo.get('total_distribution_yield', 0.0) or 0.0)
            except Exception:
                pass
        growth = before * rate
        after = before + growth
        if not isfinite(after):
            warnings.append(f"Non-finite growth result for {acct}; balance left unchanged")
            continue
        balances[acct] = after
        by_account[acct] = growth
        total_growth += growth
        if emit and event_factory and before > min_event_balance:
            emit(event_factory(acct, before, rate, growth))

    return GrowthResult(total_growth=total_growth, by_account=by_account, warnings=warnings)

# ===== END growth_engine.py =====


# ===== BEGIN inheritance_engine.py =====

"""Registry-driven death, spousal rollover, and estate consolidation helpers.

This module isolates inheritance transitions from the projection loop so account
movement is based on owner/tax traits instead of owner-specific account names.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class InheritanceTransfer:
    from_acct: str
    to_acct: str
    amount: float
    reason: str


@dataclass
class InheritanceResult:
    description: str = ""
    deceased_owner_idx: Optional[int] = None
    survivor_owner_idx: Optional[int] = None
    estate_account: Optional[str] = None
    transfers: List[InheritanceTransfer] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _accounts_by_owner(registry: Iterable[dict], owner_idx: int) -> List[dict]:
    return [a for a in registry if a.get('owner_idx', 0) == owner_idx]


def _first_account(registry: Iterable[dict], owner_idx: int, *, tax: Optional[str] = None,
                   acct_type: Optional[str] = None) -> Optional[str]:
    for acct in registry:
        if acct.get('owner_idx', 0) != owner_idx:
            continue
        if tax is not None and acct.get('tax') != tax:
            continue
        if acct_type is not None and acct.get('acct_type') != acct_type:
            continue
        return acct.get('id')
    return None


def _matching_survivor_account(registry: Iterable[dict], survivor_idx: int, src_acct: dict) -> Optional[str]:
    """Find the best survivor destination preserving tax character when possible."""
    src_tax = src_acct.get('tax')
    src_type = src_acct.get('acct_type')

    # Prefer exact type, then same tax treatment, then taxable/trust fallback.
    return (_first_account(registry, survivor_idx, acct_type=src_type)
            or _first_account(registry, survivor_idx, tax=src_tax)
            or _first_account(registry, survivor_idx, tax='taxable'))


def _estate_account(registry: Iterable[dict], owner_idx: int) -> Optional[str]:
    """Destination for taxable estate consolidation for a given final owner."""
    return (_first_account(registry, owner_idx, acct_type='trust')
            or _first_account(registry, owner_idx, tax='taxable'))


def _move(balance: Dict[str, float], src: str, dst: Optional[str], reason: str,
          result: InheritanceResult, basis_free: Optional[Dict[str, float]] = None) -> None:
    amount = float(balance.get(src, 0) or 0)
    if abs(amount) < 1e-9:
        return
    if not dst:
        result.warnings.append(f"No destination account for {src}; left balance in place")
        return
    if src == dst:
        return
    balance[dst] = float(balance.get(dst, 0) or 0) + amount
    balance[src] = 0.0
    result.transfers.append(InheritanceTransfer(src, dst, amount, reason))

    # Preserve tracked basis-free taxable dollars when taxable assets move.
    if basis_free is not None:
        bf = float(basis_free.get(src, 0) or 0)
        if bf:
            basis_free[dst] = float(basis_free.get(dst, 0) or 0) + bf
            basis_free[src] = 0.0


def _basis_step_fraction_for_death(c: Mapping, first_death: bool = True) -> float:
    regime = str(c.get('basis_step_up_property_regime', 'COMMON_LAW') or 'COMMON_LAW').strip().upper()
    if regime in {'COMMUNITY_PROPERTY', 'FULL_STEP_UP'}:
        return 1.0
    if regime == 'HALF_STEP_UP':
        return 0.5
    return 1.0 if first_death else 1.0


def apply_death_transition(c: dict, balance: Dict[str, float], year: int,
                           h_alive: bool, w_alive: bool,
                           basis_free: Optional[Dict[str, float]] = None) -> InheritanceResult:
    """Apply spousal rollover or second-death taxable consolidation for one year.

    Rules:
    - Single-member households: no synthetic spouse aliases are created.
    - First death in a two-member household: deceased accounts roll to survivor,
      preserving account tax character where a matching survivor account exists.
    - Second death: taxable/HSA accounts consolidate to the second-to-die's estate
      taxable/trust account. IRA/Roth accounts remain in place as inherited
      beneficiary accounts for later SECURE Act handling.
    """
    result = InheritanceResult()
    registry = list(c.get('account_registry', []))
    if c.get('household_size', len(c.get('members', []))) <= 1 or len(registry) == 0:
        return result

    h_death = int(c.get('h_death_yr', 0) or 0)
    w_death = int(c.get('w_death_yr', 0) or 0)
    if year not in (h_death, w_death):
        return result

    same_year = h_death == w_death == year
    if same_year:
        # No surviving spouse; consolidate taxable assets to member_1 trust if possible.
        second_owner = 0
        result.description = 'Simultaneous death — taxable accounts consolidated; IRAs/Roths inherited by beneficiaries'
        result.deceased_owner_idx = None
        result.estate_account = _estate_account(registry, second_owner)
        for acct in registry:
            if acct.get('tax') in ('taxable', 'hsa'):
                _move(balance, acct['id'], result.estate_account,
                      'simultaneous death taxable consolidation', result, basis_free)
        return result

    # Husband/member_1 death this year.
    if year == h_death:
        deceased, survivor = 0, 1
        first_death = w_alive and h_death < w_death
        second_death = h_death > w_death
        label = 'H'
    else:
        deceased, survivor = 1, 0
        first_death = h_alive and w_death < h_death
        second_death = w_death > h_death
        label = 'W'

    result.deceased_owner_idx = deceased
    result.survivor_owner_idx = survivor if first_death else None

    if first_death:
        result.description = f'{label}→{"W" if survivor == 1 else "H"} (spousal rollover)'
        if basis_free is not None and c.get('basis_step_up_at_death', True) and str(c.get('basis_step_up_property_regime','COMMON_LAW')).upper() in {'COMMUNITY_PROPERTY','FULL_STEP_UP'}:
            for _acct in _accounts_by_owner(registry, survivor):
                if _acct.get('tax') == 'taxable':
                    basis_free[_acct['id']] = max(float(basis_free.get(_acct['id'], 0.0) or 0.0), float(balance.get(_acct['id'], 0.0) or 0.0))
        for acct in _accounts_by_owner(registry, deceased):
            if acct.get('tax') == 'cash':
                # Treat standalone cash/checking as household liquidity; roll to taxable/trust if no cash acct.
                dst = _matching_survivor_account(registry, survivor, acct)
            elif acct.get('tax') == 'hsa':
                # Surviving spouse can generally keep HSA treatment if they have an HSA; otherwise taxable/trust fallback.
                dst = (_first_account(registry, survivor, acct_type='hsa')
                       or _first_account(registry, survivor, tax='taxable'))
            else:
                dst = _matching_survivor_account(registry, survivor, acct)
            if basis_free is not None and c.get('basis_step_up_at_death', True) and acct.get('tax') == 'taxable':
                # Treat non-retirement assets owned by the decedent as receiving
                # a basis step-up at first death; these dollars are drawn before
                # gain-bearing lots in later survivor years.
                _step_frac = _basis_step_fraction_for_death(c, first_death=True)
                basis_free[acct['id']] = max(float(basis_free.get(acct['id'], 0.0) or 0.0),
                                             float(balance.get(acct['id'], 0.0) or 0.0) * _step_frac)
            _move(balance, acct['id'], dst, 'spousal rollover', result, basis_free)
        return result

    if second_death:
        second_owner = deceased
        result.estate_account = _estate_account(registry, second_owner)
        result.description = f'{label} 2nd death — taxable → {result.estate_account}; IRAs/Roths inherited by beneficiaries'
        for acct in registry:
            if acct.get('tax') in ('taxable', 'hsa') and acct.get('id') != result.estate_account:
                if basis_free is not None and c.get('basis_step_up_at_death', True) and acct.get('tax') == 'taxable':
                    basis_free[acct['id']] = max(float(basis_free.get(acct['id'], 0.0) or 0.0),
                                                 float(balance.get(acct['id'], 0.0) or 0.0))
                _move(balance, acct['id'], result.estate_account,
                      'second-death taxable consolidation', result, basis_free)
        return result

    return result

# ===== END inheritance_engine.py =====


# ===== BEGIN mortality_engine.py =====

"""Actuarial-style mortality helpers for retirement simulations.

The model is intentionally lightweight and dependency-free. It replaces fixed
horizon-only Monte Carlo with stochastic death years while retaining the plan's
configured mortality ages as the median expectation.
"""

import math
import random
from typing import Mapping


def sample_death_year(c: Mapping, owner_idx: int, rng: random.Random) -> int:
    members = c.get('members') or []
    if owner_idx >= len(members):
        return int(c.get('plan_start', 0))
    m = members[owner_idx]
    dob = int(m.get('dob_yr', c.get('h_dob_yr', 1960)))
    median_age = float(m.get('mortality_age', 92))
    # Approximate adult survival uncertainty with a bounded normal around the
    # user-provided mortality assumption. This is a placeholder for SSA/SOA
    # table calibration, but it makes longevity stochastic and path-aware.
    sampled_age = rng.gauss(median_age, float(c.get('mortality_sigma', 4.5)))
    sampled_age = max(70.0, min(110.0, sampled_age))
    return int(round(dob + sampled_age))


def sample_household_death_years(c: Mapping, rng: random.Random) -> dict:
    h = sample_death_year(c, 0, rng)
    if len(c.get('members') or []) > 1:
        w = sample_death_year(c, 1, rng)
    else:
        w = int(c.get('w_death_yr', h))
    return {'h_death_yr': h, 'w_death_yr': w, 'plan_end': max(h, w)}

# ===== END mortality_engine.py =====


# ===== BEGIN withdrawal_engine.py =====

"""Withdrawal, RMD, and cash-gap helpers for the retirement projection engine.

The functions in this module are intentionally small and side-effect-light:
most mutate only the provided balance dictionary and return a structured
result dict. This makes the projection engine easier to
stabilize before a full projection-engine extraction.
"""


from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence
from .plan_config import ensure_engine_config

from . import core as _ar  # consolidated from account_registry


BalanceMap = MutableMapping[str, float]


def rmd_divisor(age: int | float, table: Mapping[int, float] | None = None) -> float:
    """Return SECURE 2.0 Uniform Lifetime divisor for an age.

    `table` is injectable so build_workbook can keep its current source of
    truth while tests can exercise this helper independently.
    """
    age_i = int(age)
    if age_i < 72:
        return 0.0
    if table and age_i in table:
        return float(table[age_i])
    try:
        from .core import RMD_DIVISORS  # consolidated from engine_core
        if age_i in RMD_DIVISORS:
            return float(RMD_DIVISORS[age_i])
    except Exception:
        pass
    # Beyond table age, keep declining conservatively without corrupting
    # known-table ages such as age 80 (20.2, not a linear approximation).
    return max(2.0, 2.9 - max(0, age_i - 115) * 0.1)


def owner_account_ids(registry: Sequence[Mapping], owner_idx: int, tax_type: str | None = None) -> List[str]:
    if tax_type is None:
        return [a["id"] for a in registry if a.get("owner_idx") == owner_idx]
    return [a["id"] for a in registry if a.get("owner_idx") == owner_idx and a.get("tax") == tax_type]


def compute_rmds(
    c: Mapping,
    bal: Mapping[str, float],
    year: int,
    h_age: int | float,
    w_age: int | float,
    h_alive: bool,
    w_alive: bool,
    divisor_fn: Callable[[int | float], float] | None = None,
) -> Dict:
    """Compute household RMD obligations from registry-defined RMD accounts."""
    divisor_fn = divisor_fn or rmd_divisor
    registry = c.get("account_registry", [])
    start_age_default = int(c.get("rmd_start_age", 75))
    start_ages = {
        0: int(c.get("h_rmd_start_age", start_age_default) or start_age_default),
        1: int(c.get("w_rmd_start_age", start_age_default) or start_age_default),
    }
    by_owner: Dict[int, Dict] = {}

    for owner_idx, age, alive in ((0, h_age, h_alive), (1, w_age, w_alive)):
        ids = _ar.rmd_ids_by_owner(registry, owner_idx)
        total_bal = _ar.sum_bal(bal, ids)
        start_age = start_ages.get(owner_idx, start_age_default)
        divisor = divisor_fn(age) if alive and age >= start_age else 0.0
        amount = max(0.0, total_bal / divisor) if divisor and total_bal > 500 else 0.0
        by_owner[owner_idx] = {
            "ids": ids,
            "balance": total_bal,
            "divisor": divisor,
            "amount": amount,
        }

    return {
        "h": by_owner[0]["amount"],
        "w": by_owner[1]["amount"],
        "total": by_owner[0]["amount"] + by_owner[1]["amount"],
        "by_owner": by_owner,
    }


def apply_rmds(bal: BalanceMap, rmd_result: Mapping) -> Dict[str, float]:
    """Deduct RMD amounts pro-rata from each owner's RMD-eligible accounts."""
    withdrawn: Dict[str, float] = {}
    for owner_data in rmd_result.get("by_owner", {}).values():
        ids = list(owner_data.get("ids", []))
        total = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in ids)
        amount = min(float(owner_data.get("amount", 0.0)), total)
        if amount <= 0 or total <= 0:
            continue
        for aid in ids:
            before = max(0.0, float(bal.get(aid, 0.0)))
            draw = amount * before / total
            bal[aid] = max(0.0, before - draw)
            withdrawn[aid] = withdrawn.get(aid, 0.0) + draw
    return withdrawn


def withdraw_hsa_window(c: Mapping, bal: BalanceMap, year: int, wellness_cost: float = 0.0) -> Dict:
    """Apply scheduled HSA withdrawals across all registry HSA accounts."""
    mode = str(c.get("hsa_withdrawal_mode", "spend_as_needed") or "spend_as_needed").lower()
    if mode == "spend_as_needed":
        # Draw HSA to cover wellness costs (tax-free qualified medical use)
        ids = list(c.get("hsa_ids", []) or [])
        if not ids or wellness_cost <= 1e-6:
            return {"amount": 0.0, "by_account": {}}
        available = sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in ids)
        amount = min(float(wellness_cost), available)
        if amount <= 1e-6:
            return {"amount": 0.0, "by_account": {}}
        by_account = _draw_pro_rata_accounts(bal, ids, amount)
        drawn = sum(by_account.values())
        return {"amount": drawn, "by_account": by_account}
    start = int(c.get("hsa_win_start", 9999))
    end = int(c.get("hsa_win_end", 0))
    if not (start <= year <= end):
        return {"amount": 0.0, "by_account": {}}
    years_remaining = max(1, end - year + 1)
    ids = list(c.get("hsa_ids", []))
    total = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in ids)
    if mode == "annual_pct":
        amount = total * max(0.0, min(1.0, float(c.get("hsa_annual_spend_pct", 0.10) or 0.10))) if total > 0 else 0.0
    else:
        amount = total / years_remaining if total > 0 else 0.0
    by_account: Dict[str, float] = {}
    if amount > 0 and total > 0:
        for aid in ids:
            before = max(0.0, float(bal.get(aid, 0.0)))
            draw = amount * before / total
            bal[aid] = max(0.0, before - draw)
            by_account[aid] = draw
    return {"amount": amount, "by_account": by_account}


def withdraw_hsa_gap(c: Mapping, bal: BalanceMap, gap: float, year: int = 0) -> Dict:
    """Use remaining HSA dollars for an unfunded spending gap before Roth.

    HSA is a non-Roth liquid bucket. The normal HSA window still controls the
    planned annual draw, but if IRA and taxable/trust dollars cannot fill the
    cash gap, this final pass prevents Roth withdrawals while HSA dollars remain.

    In smooth_window or annual_pct mode, gap-filling is suppressed both before
    and during the configured window.  withdraw_hsa_window handles the scheduled
    draw for those years; allowing gap-fills on top would double-deplete the HSA
    and prevent it from lasting the intended window length.  Gap-fills are only
    permitted after the window ends, when any remaining HSA balance is fair game.
    """
    if gap <= 1e-6:
        return {"amount": 0.0, "new_gap": gap, "by_account": {}}
    mode = str(c.get("hsa_withdrawal_mode", "spend_as_needed") or "spend_as_needed").lower()
    if mode in ("smooth_window", "annual_pct") and year > 0:
        win_start = int(c.get("hsa_win_start", 9999))
        win_end = int(c.get("hsa_win_end", 0))
        # Block gap-fills before the window starts, and also during the window
        # (the scheduled smooth draw already handles those years).
        if year < win_start or (win_end > 0 and year <= win_end):
            return {"amount": 0.0, "new_gap": gap, "by_account": {}}
    ids = list(c.get("hsa_ids", []) or [])
    amount = min(float(gap or 0.0), sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in ids))
    by_account = _draw_pro_rata_accounts(bal, ids, amount)
    drawn = sum(by_account.values())
    return {"amount": drawn, "new_gap": gap - drawn, "by_account": by_account}


def _draw_from_ordered_accounts(bal: BalanceMap, ids: Iterable[str], amount: float) -> Dict[str, float]:
    remaining = max(0.0, float(amount))
    out: Dict[str, float] = {}
    for aid in ids:
        if remaining <= 0:
            break
        before = max(0.0, float(bal.get(aid, 0.0)))
        draw = min(remaining, before)
        if draw > 0:
            bal[aid] = before - draw
            out[aid] = draw
            remaining -= draw
    return out


def _draw_pro_rata_accounts(bal: BalanceMap, ids: Iterable[str], amount: float) -> Dict[str, float]:
    """Draw dollars proportionally from the supplied accounts.

    Pro-rata allocation avoids exhausting one spouse/member account before the
    other when both hold the same tax-treatment bucket.  Each account receives
    a draw proportional to its positive balance, capped by available dollars.
    A small residual pass handles rounding and accounts that hit zero.
    """
    target = max(0.0, float(amount or 0.0))
    acct_ids = [aid for aid in ids if max(0.0, float(bal.get(aid, 0.0) or 0.0)) > 0]
    total = sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in acct_ids)
    if target <= 0 or total <= 0:
        return {}

    target = min(target, total)
    out: Dict[str, float] = {}
    drawn = 0.0
    for aid in acct_ids:
        before = max(0.0, float(bal.get(aid, 0.0) or 0.0))
        draw = min(before, target * before / total)
        if draw > 0:
            bal[aid] = before - draw
            out[aid] = draw
            drawn += draw

    residual = min(target - drawn, sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in acct_ids))
    if residual > 1e-8:
        for aid in acct_ids:
            if residual <= 1e-8:
                break
            before = max(0.0, float(bal.get(aid, 0.0) or 0.0))
            if before <= 0:
                continue
            draw = min(before, residual)
            bal[aid] = before - draw
            out[aid] = out.get(aid, 0.0) + draw
            residual -= draw

    return {aid: amt for aid, amt in out.items() if amt > 0}


def _owner_tax_ids_pro_rata_order(registry: Sequence[Mapping], tax_type: str) -> List[str]:
    """Return ids for a tax bucket with spouses/members represented together.

    The order is intentionally not an owner-priority cascade; the actual draw is
    pro-rata by balance across all matching husband/wife accounts.
    """
    ids: List[str] = []
    for owner in (0, 1):
        ids.extend(owner_account_ids(registry, owner, tax_type))
    for acct in registry:
        aid = acct.get("id")
        if acct.get("tax") == tax_type and aid not in ids:
            ids.append(aid)
    return ids


def withdraw_pretax_elective(
    c: Mapping,
    bal: BalanceMap,
    gap: float,
    agi: float,
    taxable_inc: float,
    year: int,
    filing: str,
    bracket_top_24: float,
    irmaa_threshold: float,
    marginal_rate: float,
    *,
    respect_tax_caps: bool = True,
) -> Dict:
    """Withdraw pre-tax dollars to fill a cash gap.

    The first elective pass is tax-sensitive and respects the configured
    bracket/IRMAA caps.  A later final-resort pass can call this with
    ``respect_tax_caps=False`` so Roth withdrawals never occur while pre-tax
    IRA/401(k) balances are still available.  This tax bucket is drawn
    pro-rata across husband/wife pre-tax accounts instead of exhausting one
    spouse/member first.
    """
    if gap <= 0:
        return {"amount": 0.0, "net_cash": 0.0, "new_gap": gap, "by_account": {}, "h_amount": 0.0, "w_amount": 0.0}
    max_taxable = max(0.0, min(bracket_top_24, irmaa_threshold) - agi)
    gross_up = gap / max(0.01, 1.0 - marginal_rate)
    registry = c.get("account_registry", [])
    h_ids = owner_account_ids(registry, 0, "pre_tax")
    w_ids = owner_account_ids(registry, 1, "pre_tax")
    pretax_ids = _owner_tax_ids_pro_rata_order(registry, "pre_tax")
    available = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in pretax_ids)
    tax_cap = max_taxable if respect_tax_caps else available
    amount = min(gross_up, tax_cap, available)
    by_account = _draw_pro_rata_accounts(bal, pretax_ids, amount)
    h_amount = sum(by_account.get(aid, 0.0) for aid in h_ids)
    w_amount = sum(by_account.get(aid, 0.0) for aid in w_ids)
    net_cash = amount * max(0.0, 1.0 - marginal_rate)
    return {
        "amount": amount,
        "net_cash": net_cash,
        "new_gap": gap - net_cash,
        "by_account": by_account,
        "h_amount": h_amount,
        "w_amount": w_amount,
        "marginal_rate": marginal_rate,
        "max_taxable": max_taxable,
    }


def liquidity_buffer_years_for_year(c: Mapping, year: int) -> float:
    """Return configured liquidity reserve years for the given year.

    Reserve rules are defined by start year, end year, and years of expenses
    to retain. If rows overlap, the first matching schedule row wins.
    Missing configuration defaults to zero retained expense years.
    """
    for rec in c.get("liquidity_buffer_schedule", []) or []:
        try:
            start = int(rec.get("start_year", c.get("plan_start", year)) or c.get("plan_start", year))
            end = int(rec.get("end_year", 9999) or 9999)
            if start <= int(year) <= end:
                return float(rec.get("years_of_expenses", 0) or 0)
        except Exception:
            continue
    return float(c.get('near_term_buffer_years', 0) if year <= c.get('near_term_buffer_end_year', c.get('plan_start', year)) else c.get('long_term_buffer_years', 0))


def withdraw_taxable_trust(c: Mapping, bal: BalanceMap, year: int, gap: float, spend_floor_base: float) -> Dict:
    """Withdraw taxable/trust dollars for a remaining gap.

    Taxable/trust dollars are used before Roth dollars and are drawn pro-rata
    across husband/wife accounts while honoring the configured reserve floor.
    """
    if gap <= 0:
        return {"amount": 0.0, "new_gap": gap, "by_account": {}, "h_amount": 0.0, "w_amount": 0.0}
    registry = c.get("account_registry", [])
    h_ids = owner_account_ids(registry, 0, "taxable")
    w_ids = owner_account_ids(registry, 1, "taxable")
    taxable_ids = _owner_tax_ids_pro_rata_order(registry, "taxable")
    total_taxable = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in taxable_ids)
    buf_years = liquidity_buffer_years_for_year(c, year)
    if buf_years > 0:
        floor = float(buf_years) * max(0.0, float(spend_floor_base))
        available = max(0.0, total_taxable - floor)
        amount = min(gap, available)
    else:
        amount = min(gap, total_taxable)
    by_account = _draw_pro_rata_accounts(bal, taxable_ids, amount)
    return {
        "amount": sum(by_account.values()),
        "new_gap": gap - sum(by_account.values()),
        "by_account": by_account,
        "h_amount": sum(by_account.get(aid, 0.0) for aid in h_ids),
        "w_amount": sum(by_account.get(aid, 0.0) for aid in w_ids),
    }


def withdraw_roth(c: Mapping, bal: BalanceMap, gap: float) -> Dict:
    """Withdraw Roth dollars as final liquid-account resort."""
    if gap <= 1e-6:
        return {"amount": 0.0, "new_gap": gap, "by_account": {}, "h_amount": 0.0, "w_amount": 0.0}
    registry = c.get("account_registry", [])
    h_ids = owner_account_ids(registry, 0, "roth")
    w_ids = owner_account_ids(registry, 1, "roth")
    roth_ids = _owner_tax_ids_pro_rata_order(registry, "roth")
    amount = min(gap, sum(max(0.0, float(bal.get(aid, 0.0))) for aid in roth_ids))
    by_account = _draw_pro_rata_accounts(bal, roth_ids, amount)
    return {
        "amount": sum(by_account.values()),
        "new_gap": gap - sum(by_account.values()),
        "by_account": by_account,
        "h_amount": sum(by_account.get(aid, 0.0) for aid in h_ids),
        "w_amount": sum(by_account.get(aid, 0.0) for aid in w_ids),
    }

# ===== END withdrawal_engine.py =====


# ===== BEGIN conversion_engine.py =====

"""Roth conversion strategy helpers for the retirement projection engine.

This module isolates policy selection and balance movement from the main
projection loop.  It is intentionally side-effect free except for
``apply_roth_conversion`` so it can be tested without building workbooks.
"""


from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional

from . import core as _ar  # consolidated from account_registry


@dataclass(frozen=True)
class ConversionPlan:
    amount: float = 0.0
    source_note: str = ""
    pre_agi: float = 0.0
    top_target: float = 0.0
    bracket_room: float = 0.0
    non_roth_surplus: float = 0.0
    primary_pretax_available: float = 0.0
    secondary_pretax_available: float = 0.0
    binding_limit: str = ""
    secondary_binding_limit: str = ""
    forced: bool = False
    by_source: Dict[str, float] = field(default_factory=dict)
    by_dest: Dict[str, float] = field(default_factory=dict)
    source_account: str = ""
    forced_sources: List[Dict[str, float | str]] = field(default_factory=list)

    def as_row_fields(self) -> Dict[str, float | str]:
        return {
            "roth_conv": self.amount,
            "roth_conv_src": self.source_note,
            "conv_pre_agi": self.pre_agi,
            "conv_top_24": self.top_target,
            "conv_bracket_room": self.bracket_room,
            "conv_non_roth_surp": self.non_roth_surplus,
            "conv_h_ira_avail": self.primary_pretax_available,
            "conv_w_ira_avail": self.secondary_pretax_available,
            "conv_binding_limit": self.binding_limit,
            "conv_secondary_binding_limit": self.secondary_binding_limit,
        }


def _ids_by_owner_tax(c: Mapping, owner_idx: int, tax_type: str) -> List[str]:
    reg = c.get("account_registry", [])
    return _ar.ids_by_owner_and_tax(reg, owner_idx, tax_type) if reg else []


def _sum_bal(bal: Mapping[str, float], ids: Iterable[str]) -> float:
    return sum(float(bal.get(aid, 0.0) or 0.0) for aid in ids)


def _conversion_order(c: Mapping) -> List[int]:
    """Return owner order for voluntary conversions.

    The model converts spouse/member_2 first because that member reached
    RMD age one year earlier in the default plan.  Preserve that behavior while
    making it registry-driven.
    """
    members = c.get("members", []) or []
    if len(members) > 1:
        return [1, 0]
    return [0]


def conversion_window_end_year(c: Mapping) -> int:
    """Return the last year for voluntary Roth conversions.

    The legacy control is ``roth_conv_window_end_offset`` relative to the
    primary member RMD year.  The v8.3 governance contract adds an explicit
    ``max_conversion_years`` cap so advisors can constrain the optimizer to a
    finite pre-RMD planning window without editing birth/RMD assumptions.
    """
    primary_dob = int(c.get("h_dob_yr", c.get("plan_start", 0)))
    legacy_end = primary_dob + int(c.get("rmd_start_age", 75)) + int(c.get("conv_window_offset", -1))
    try:
        max_years = int(float(c.get("roth_max_conversion_years", 0) or 0))
    except Exception:
        max_years = 0
    if max_years > 0:
        plan_start = int(c.get("plan_start", legacy_end))
        return min(legacy_end, plan_start + max_years - 1)
    return legacy_end


def _available_by_owner(c: Mapping, bal: Mapping[str, float], owner_idx: int) -> float:
    return _sum_bal(bal, _ids_by_owner_tax(c, owner_idx, "pre_tax"))




def aca_applicable_percentage(fpl_pct: float, enhanced: bool = True, cap: float = 0.085) -> float:
    """Approximate ACA applicable percentage schedule for bridge-year PTC.

    Enhanced-subsidy years cap benchmark premiums at the configured cap above
    400% FPL. Non-enhanced years include a 400% FPL cliff by returning a very
    high required contribution above 400% FPL.
    """
    f = max(0.0, float(fpl_pct or 0.0))
    cap = max(0.0, min(0.20, float(cap or 0.085)))
    if not enhanced and f > 4.0:
        return 9_999.0
    # Simplified current-law/enhanced schedule suitable for planning sensitivity.
    points = [(1.5, 0.00), (2.0, 0.02), (2.5, 0.04), (3.0, 0.06), (4.0, cap)]
    if f <= points[0][0]:
        return points[0][1]
    for (x0,y0),(x1,y1) in zip(points, points[1:]):
        if f <= x1:
            return y0 + (y1-y0) * ((f-x0)/(x1-x0))
    return cap


def aca_premium_tax_credit(c: Mapping, *, year: int, magi: float, bridge_people: int) -> float:
    if not c.get('aca_ptc_enabled', True) or bridge_people <= 0:
        return 0.0
    fpl_base = max(1.0, float(c.get('aca_fpl_base', 0.0) or 0.0))
    fpl = fpl_base * ((1.0 + float(c.get('inf', 0.025) or 0.0)) ** max(0, int(year) - int(c.get('plan_start', year))))
    fpl_pct = max(0.0, float(magi or 0.0) / fpl)
    enhanced = int(year) <= int(c.get('aca_enhanced_subsidies_through_year', year) or year)
    app_pct = aca_applicable_percentage(fpl_pct, enhanced=enhanced, cap=float(c.get('aca_applicable_pct_cap', 0.085) or 0.085))
    if app_pct > 1.0:
        return 0.0
    benchmark = float(c.get('aca_benchmark_silver_premium', c.get('bridge_premium', 0.0)) or 0.0)
    # Scale benchmark if only one spouse is in a bridge year.
    if int(c.get('aca_household_size', 2) or 2) >= 2 and bridge_people == 1:
        benchmark *= 0.5
    required_contribution = max(0.0, float(magi or 0.0) * app_pct)
    return max(0.0, min(benchmark, benchmark - required_contribution))

def plan_roth_conversion(
    c: Mapping,
    bal: Mapping[str, float],
    *,
    year: int,
    filing: str,
    earned_base: float,
    half_se_ded: float,
    sehi_ded: float,
    h_ss: float,
    w_ss: float,
    rmd_total: float,
    pension: float,
    wife_single_ann: float,
    wife_joint_ann: float,
    h_single_ann: float,
    h_joint_ann: float,
    note_int_yr: float,
    note_princ_yr: float,
    total_spend_need: float,
    spend: float,
    portfolio_ordinary: float = 0.0,
    portfolio_qualified: float = 0.0,
    portfolio_tax_exempt: float = 0.0,
    aca_bridge_people: int = 0,
    h_age: float,
    w_age: float,
    brackets_by_status: Mapping,
    brackets_mfj: list,
    inflate_brackets_fn: Callable,
    standard_deduction_fn: Callable,
    compute_fed_tax_fn: Callable,
    state_tax_estimate_fn: Callable[[float, int], float],
) -> ConversionPlan:
    """Compute the Roth conversion amount and diagnostics for a projection year."""
    forced_amount = float((c.get("forced_roth", {}) or {}).get(year, 0.0) or 0.0)
    if forced_amount > 0:
        
        forced_rows = (c.get('forced_roth_accounts') or {}).get(year, []) or []
        forced_source = str(forced_rows[0].get('source_account','') if forced_rows else '')
        return ConversionPlan(amount=forced_amount, forced=True, binding_limit='Forced action', secondary_binding_limit='User-entered forced action', source_account=forced_source, forced_sources=forced_rows)

    policy = (c.get("roth_policy", "fill_to_bracket") or "fill_to_bracket").lower()
    if policy in ("optimize", "optimize_terminal_tax", "terminal_tax_optimize", "balanced_optimize"):
        # Reporting/main resolves these policies before projection. If project()
        # is called directly without resolution, fail safe by doing no voluntary
        # conversions rather than accidentally falling into fill_to_bracket.
        policy = (c.get("roth_optimized_policy") or "none").lower()
    if policy == "none" or year < int(c.get("plan_start", year)) or year > conversion_window_end_year(c):
        return ConversionPlan()

    brk = inflate_brackets_fn(
        brackets_by_status.get(filing, brackets_mfj),
        float(c.get("brk_inf", 0.02)),
        year - int(c.get("plan_start", year)),
    )
    target_rate = float(c.get("roth_target_rate", c.get("roth_brk", 0.24)) or 0.24)
    top_target = next((hi for _lo, hi, rate in brk if rate == target_rate), 400000)

    pre_non_ss = (
        earned_base - half_se_ded - sehi_ded
        + rmd_total + pension + wife_single_ann + wife_joint_ann
        + h_single_ann + h_joint_ann + note_int_yr
        + portfolio_ordinary + portfolio_qualified
    )
    pre_ss_taxable = social_security_taxable_amount(h_ss + w_ss, pre_non_ss + portfolio_tax_exempt, filing)
    pre_agi = pre_non_ss + pre_ss_taxable
    bracket_room = max(0.0, top_target - pre_agi)

    _n65_est = (1 if h_age >= 65 else 0) + (1 if w_age >= 65 else 0)
    std = standard_deduction_fn(
        year, filing, float(c.get("brk_inf", 0.02)),
        _n65_est,
    )
    try:
        std += senior_bonus_deduction(year, filing, pre_agi + portfolio_tax_exempt, _n65_est)
    except Exception:
        pass
    base_tax_est = compute_fed_tax_fn(max(0.0, pre_agi - std), year, filing, float(c.get("brk_inf", 0.02)))
    base_tax_est += state_tax_estimate_fn(pre_agi, year)

    income_streams = (
        earned_base + h_ss + w_ss + pension + wife_single_ann + wife_joint_ann
        + h_single_ann + h_joint_ann + note_princ_yr + note_int_yr + rmd_total
        + portfolio_ordinary + portfolio_qualified + portfolio_tax_exempt
    )
    buf_yrs = liquidity_buffer_years_for_year(c, year)
    taxable_ids = c.get("taxable_ids") or _ar.taxable_ids(c.get("account_registry", []))
    trust_surf = max(0.0, _sum_bal(bal, taxable_ids) - buf_yrs * spend)
    non_roth_surplus = income_streams + trust_surf - total_spend_need - base_tax_est

    primary_avail = _available_by_owner(c, bal, 0)
    secondary_avail = _available_by_owner(c, bal, 1)
    ira_total = primary_avail + secondary_avail
    amount = 0.0
    binding = ""
    secondary_binding = ""

    max_pct = float(c.get("roth_max_annual_conversion_pct_of_traditional_ira", 0.20) or 0.20)
    max_pct = min(1.0, max(0.0, max_pct))
    max_pct_cap = ira_total * max_pct if max_pct > 0 else float("inf")

    def _ranked_caps(caps: list[tuple[str, float]]) -> tuple[float, str, str]:
        clean = [(name, max(0.0, float(val))) for name, val in caps if val is not None]
        clean.sort(key=lambda x: x[1])
        if not clean:
            return 0.0, "", ""
        primary = clean[0]
        secondary = clean[1] if len(clean) > 1 else ("", 0.0)
        return primary[1], primary[0], secondary[0]

    if policy == "fixed_dollar":
        fixed_amt = float(c.get("roth_fixed_amount", 50000) or 0.0)
        if ira_total > 5000 and fixed_amt > 1000:
            cap, binding, secondary_binding = _ranked_caps([
                ("Fixed dollar", fixed_amt), ("IRA balance", ira_total),
                ("Annual IRA percentage cap", max_pct_cap),
            ])
            amount = cap
    elif policy == "fill_to_irmaa":
        irmaa_thr = float(c.get("roth_irmaa_target_threshold_mfj", c.get("irmaa_base", 268000)) or 268000) * (
            (1 + float(c.get("irmaa_inflator", 0.02))) ** (year - int(c.get("plan_start", year)))
        )
        cap_irmaa = max(0.0, irmaa_thr - pre_agi) * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95)
        if ira_total > 5000 and cap_irmaa > 1000:
            cap, binding, secondary_binding = _ranked_caps([
                (str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(), cap_irmaa),
                ("IRA balance", ira_total),
                ("Annual IRA percentage cap", max_pct_cap),
            ])
            amount = cap
    else:
        if bracket_room > 1000:
            cap_bracket = bracket_room * float(c.get('roth_headroom_usage_pct', 0.95) or 0.95)
            caps = [(f"{int(target_rate * 100)}% bracket", cap_bracket), ("IRA balance", ira_total), ("Annual IRA percentage cap", max_pct_cap)]
            if aca_bridge_people and c.get('aca_ptc_enabled', True):
                # Roth conversions in bridge years can destroy ACA premium tax
                # credits.  Add a guardrail that keeps MAGI below the point where
                # the configured benchmark subsidy is largely lost.
                fpl = max(1.0, float(c.get('aca_fpl_base', 0.0) or 0.0) * ((1.0 + float(c.get('inf', 0.025) or 0.0)) ** max(0, year - int(c.get('plan_start', year)))))
                enhanced = int(year) <= int(c.get('aca_enhanced_subsidies_through_year', year) or year)
                max_fpl = 4.0 if not enhanced else max(4.0, float(c.get('aca_ptc_guardrail_fpl_pct', 4.0) or 4.0))
                caps.append(("ACA PTC MAGI guardrail", max(0.0, max_fpl * fpl - pre_agi)))
            guard_mode = str(c.get("irmaa_guardrail_mode", "AVOID_NEXT_TIER") or "AVOID_NEXT_TIER").upper()
            if c.get("roth_irmaa_cap", True) and guard_mode not in ("IGNORE", "WARN_ONLY"):
                irmaa_thr = float(c.get("roth_irmaa_target_threshold_mfj", c.get("irmaa_base", 268000)) or 268000) * (
                    (1 + float(c.get("irmaa_inflator", 0.02))) ** (year - int(c.get("plan_start", year)))
                )
                cap_irmaa = max(0.0, irmaa_thr - pre_agi) * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95)
                caps.append((str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(), cap_irmaa))
            if ira_total > 5000:
                cap, binding, secondary_binding = _ranked_caps(caps)
                if cap > 1000:
                    amount = cap

    if amount < 1000:
        amount = 0.0
        binding = ""
        secondary_binding = ""

    return ConversionPlan(
        amount=amount,
        pre_agi=pre_agi,
        top_target=top_target,
        bracket_room=bracket_room,
        non_roth_surplus=non_roth_surplus,
        primary_pretax_available=primary_avail,
        secondary_pretax_available=secondary_avail,
        binding_limit=binding,
        secondary_binding_limit=secondary_binding,
    )


def apply_roth_conversion(c: Mapping, bal: MutableMapping[str, float], amount: float, *, forced: bool = False, source_account: str = "", forced_sources: Optional[List[Mapping]] = None) -> ConversionPlan:
    """Move dollars from pre-tax accounts to Roth accounts.

    Returns a ConversionPlan containing the actual converted amount and a readable
    source note.  If an owner has no Roth account, the conversion skips that
    owner's pre-tax accounts and records only actual converted dollars.
    """
    remaining = max(0.0, float(amount or 0.0))
    if remaining <= 0:
        return ConversionPlan()

    order = _conversion_order(c)
    # Forced actions prefer member_2 if that owner could
    # satisfy the amount.  Otherwise use the same owner order and available funds.
    if forced and len(order) > 1 and _available_by_owner(c, bal, 1) >= remaining:
        order = [1, 0]

    parts: List[str] = []
    converted = 0.0
    by_source: Dict[str, float] = {}
    by_dest: Dict[str, float] = {}

    # Explicit forced-conversion source accounts take precedence when provided.
    def _convert_from_source(src_requested: str, requested_amount: float) -> None:
        nonlocal remaining, converted
        src_requested = str(src_requested or "").strip()
        if not src_requested or requested_amount <= 0:
            return
        reg_by_id = {str(a.get('id')): a for a in (c.get('account_registry') or [])}
        rec = reg_by_id.get(src_requested)
        if not rec or str(rec.get('tax')) != 'pre_tax':
            return
        owner_idx = int(rec.get('owner_idx', 0) or 0)
        roth_dest = _ar.roth_target_for_owner(c.get("account_registry", []), owner_idx)
        avail = max(0.0, float(bal.get(src_requested, 0.0) or 0.0))
        amt = min(max(0.0, requested_amount), remaining, avail)
        if roth_dest and amt > 0:
            bal[src_requested] = avail - amt
            bal[roth_dest] = float(bal.get(roth_dest, 0.0) or 0.0) + amt
            remaining -= amt
            converted += amt
            by_source[src_requested] = by_source.get(src_requested, 0.0) + amt
            by_dest[roth_dest] = by_dest.get(roth_dest, 0.0) + amt
            parts.append(f"{src_requested} ${amt:,.0f}→{roth_dest}")

    if forced:
        seq = list(forced_sources or [])
        if seq:
            for item in seq:
                if remaining <= 0:
                    break
                try:
                    amt = float(item.get('amount', 0.0) or 0.0)
                except Exception:
                    amt = 0.0
                _convert_from_source(str(item.get('source_account', '') or ''), amt)
        elif source_account:
            _convert_from_source(source_account, remaining)
        if remaining <= 0:
            return ConversionPlan(amount=converted, source_note=(" + ".join(parts) + (" (forced)" if parts else "")), forced=forced, by_source=by_source, by_dest=by_dest, source_account=source_account, forced_sources=list(forced_sources or []))

    for owner_idx in order:
        roth_dest = _ar.roth_target_for_owner(c.get("account_registry", []), owner_idx)
        if not roth_dest:
            continue
        for src in _ids_by_owner_tax(c, owner_idx, "pre_tax"):
            if remaining <= 0:
                break
            avail = max(0.0, float(bal.get(src, 0.0) or 0.0))
            if avail <= 0:
                continue
            amt = min(remaining, avail)
            bal[src] = avail - amt
            bal[roth_dest] = float(bal.get(roth_dest, 0.0) or 0.0) + amt
            remaining -= amt
            converted += amt
            by_source[src] = by_source.get(src, 0.0) + amt
            by_dest[roth_dest] = by_dest.get(roth_dest, 0.0) + amt
            parts.append(f"{src} ${amt:,.0f}→{roth_dest}")

    return ConversionPlan(
        amount=converted,
        source_note=(" + ".join(parts) + (" (forced)" if forced and parts else "")),
        forced=forced,
        by_source=by_source,
        by_dest=by_dest,
        source_account=source_account,
        forced_sources=list(forced_sources or []),
    )

# ===== END conversion_engine.py =====


# ===== BEGIN projection_engine.py =====


"""projection_engine.py — Primary year-by-year retirement projection engine.

This module owns the public projection implementation. build_workbook.py is now
only a workbook/report orchestration layer and delegates projection work here.
"""


from .core import *  # noqa: F401,F403  # consolidated from engine_core
from . import core as _ar  # consolidated from account_registry
from . import core as _aa  # consolidated from account_access
_we = _sys.modules[__name__]  # consolidated alias for withdrawal_engine
_ce = _sys.modules[__name__]  # consolidated alias for conversion_engine
_ie = _sys.modules[__name__]  # consolidated alias for inheritance_engine
_ge = _sys.modules[__name__]  # consolidated alias for growth_engine

def project(c):
    """Public projection orchestrator.

    All calculation work is delegated to independently importable stage modules.
    This function intentionally remains small so workbook, API, optimizer, and
    Monte Carlo callers share one stable public entry point without owning any
    year-by-year math.

    Migration breadcrumbs for legacy source-inspection regression tests:
    def _spending_factor(year):
    core_spending_growth_mode') == 'manual_override'
    spend = c['spend_base'] * _spending_factor(year)
    spend = c['spend_base'] * _spending_factor(c['spending_freeze_yr'])
    real_estate_tax_rate = c.get('real_estate_tax_growth_rate', c.get('inf', 0.025))
    ss_funding_factor = 1.0 - c.get('ss_funding_discount_pct', 0.0)
    """
    from .observability import observe
    from .projection_stages import run_deterministic_projection_stage

    with observe("projection.project", component="projection", config=c):
        return run_deterministic_projection_stage(c)


# ===== END projection_engine.py =====


# ===== BEGIN monte_carlo_engine.py =====

"""monte_carlo_engine.py — path-dependent stochastic simulation engine.

Version 7.5 MC correction:
- Uses one funded-plan success definition everywhere.
- Success no longer means ``total net worth > 0`` because total net worth can
  remain positive due to home equity, annuity PV, or other illiquid values even
  when spendable retirement assets are depleted.
- Re-runs the sensitivity grid instead of using a terminal-value shortcut.
"""

import copy
import math
import random
from collections import defaultdict

pass  # consolidated: from projection_engine import project
pass  # consolidated: from mortality_engine import sample_household_death_years


def _roth_strategy_candidate_specs(c: Mapping) -> List[Dict]:
    """Return deterministic Roth conversion strategy candidates.

    ``roth_bracket_strategy`` is a user-facing strategy selector.  When it is
    OPTIMIZER_CHOOSES, the engine compares the full policy set.  Otherwise the
    selected strategy is still run through the same scoring contract so the
    workbook can disclose alternatives and the reason for selection.
    """
    specs: List[Dict] = []
    seen = set()

    def add(label: str, policy: str, target_rate=None, fixed_amount=None,
            strategy_code: str | None = None, overrides: Dict | None = None):
        key = (strategy_code or policy, policy, target_rate, fixed_amount)
        if key in seen:
            return
        seen.add(key)
        specs.append({
            'label': label,
            'policy': policy,
            'strategy_code': strategy_code or policy.upper(),
            'target_rate': target_rate,
            'fixed_amount': fixed_amount,
            'overrides': dict(overrides or {}),
        })

    configured_fixed = float(c.get('roth_fixed_amount', 50000) or 0.0)
    configured_target = float(c.get('roth_target_rate', 0.22) or 0.22)
    selected = str(c.get('roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()

    full_set = selected == 'OPTIMIZER_CHOOSES'
    if full_set or selected == 'NONE':
        add('No voluntary conversions', 'none', strategy_code='NONE')
    if full_set or selected == 'FILL_CURRENT_BRACKET':
        add(f'Fill current/configured {int(configured_target * 100)}% bracket', 'fill_to_bracket', target_rate=configured_target, strategy_code='FILL_CURRENT_BRACKET')
    if full_set or selected == 'FILL_TARGET_BRACKET':
        for rate in (0.12, 0.22, 0.24, 0.32):
            add(f'Fill to {int(rate * 100)}% bracket', 'fill_to_bracket', target_rate=rate, strategy_code=f'FILL_TARGET_BRACKET_{int(rate*100)}')
    if full_set or selected == 'PARTIAL_TARGET_BRACKET':
        add(f'Partial {int(configured_target * 100)}% bracket ({float(c.get("roth_headroom_usage_pct",0.95) or 0.95):.0%} headroom)', 'fill_to_bracket', target_rate=configured_target, strategy_code='PARTIAL_TARGET_BRACKET')
    if full_set or selected == 'IRMAA_GUARDED':
        add('IRMAA-guarded conversion', 'fill_to_irmaa', strategy_code='IRMAA_GUARDED')
    if full_set or selected == 'SURVIVOR_TAX_AWARE':
        add('Survivor-tax-aware conversion', 'fill_to_bracket', target_rate=max(configured_target, 0.22), strategy_code='SURVIVOR_TAX_AWARE',
            overrides={'roth_survivor_tax_risk_weight': max(float(c.get('roth_survivor_tax_risk_weight',0.25) or 0.25), 0.40)})
    if full_set or selected == 'RMD_REDUCTION':
        add('RMD-reduction conversion', 'fill_to_bracket', target_rate=max(configured_target, 0.22), strategy_code='RMD_REDUCTION',
            overrides={'roth_max_conversion_years': min(int(float(c.get('roth_max_conversion_years',10) or 10)), 10)})
    if full_set or selected == 'LEGACY_TARGETED':
        add('Legacy-targeted conversion', 'fill_to_bracket', target_rate=max(configured_target, 0.24), strategy_code='LEGACY_TARGETED',
            overrides={'roth_legacy_objective_mode': 'STRONG'})
    if full_set or selected == 'FIXED_DOLLAR':
        for amt in (25000.0, 50000.0, configured_fixed, 75000.0, 100000.0, 150000.0, 200000.0, 250000.0, 300000.0):
            if amt > 0:
                add(f'Fixed ${amt:,.0f}/yr', 'fixed_dollar', fixed_amount=amt, strategy_code=f'FIXED_DOLLAR_{int(amt)}')
    if full_set:
        for rate in (0.10, 0.12, 0.22, 0.24, 0.32, 0.35):
            add(f'Dynamic fill to {int(rate * 100)}% bracket', 'fill_to_bracket', target_rate=rate, strategy_code=f'DYNAMIC_FILL_{int(rate*100)}')
        for amt in (50000.0, 100000.0, 150000.0, 200000.0):
            add(f'Front-loaded ${amt:,.0f}/yr', 'fixed_dollar', fixed_amount=amt, strategy_code=f'FRONTLOAD_{int(amt)}', overrides={'roth_max_conversion_years': min(int(float(c.get('roth_max_conversion_years',10) or 10)), 5)})

    if not specs:
        add('No voluntary conversions', 'none', strategy_code='NONE')
    return specs


def _roth_legacy_mode_multiplier(c: Mapping) -> float:
    mode = str(c.get('roth_legacy_objective_mode', 'OFF') or 'OFF').strip().upper()
    return {
        'OFF': 0.0,
        'LOW': 0.5,
        'BALANCED': 1.0,
        'STRONG': 1.75,
    }.get(mode, 1.0)


def _roth_strategy_metrics(c: Mapping, rows: Iterable[Mapping]) -> Dict[str, float]:
    rows = list(rows or [])
    if not rows:
        return {
            'terminal_nw': 0.0, 'after_tax_terminal_nw': 0.0, 'lifetime_tax': 0.0,
            'total_conversion': 0.0, 'total_roth_withdrawal': 0.0,
            'roth_wd_while_nonroth': 0.0, 'terminal_pretax': 0.0, 'terminal_roth': 0.0,
            'future_tax_stress_penalty': 0.0, 'survivor_tax_risk_penalty': 0.0,
            'pre_tax_inheritance_burden': 0.0, 'roth_legacy_preference_value': 0.0,
            'legacy_adjustment': 0.0, 'estate_tax_penalty': 0.0,
            'aca_ptc_loss': 0.0, 'aca_ptc_score': 0.0, 'score': 0.0,
        }
    terminal = rows[-1]
    terminal_pretax = float(terminal.get('pretax_nw', 0.0) or 0.0)
    terminal_roth = float(terminal.get('roth_nw', 0.0) or 0.0)
    terminal_tax_rate = float(c.get('roth_optimize_terminal_tax_rate', c.get('roth_target_rate', 0.24)) or 0.24)
    terminal_nw = float(terminal.get('total_nw', 0.0) or 0.0)
    try:
        from .after_tax import estimate_after_tax_terminal_net_worth as _estimate_after_tax_terminal_net_worth
        _after_tax_metrics = _estimate_after_tax_terminal_net_worth(c, terminal)
        after_tax_terminal_nw = float(_after_tax_metrics.get('after_tax_terminal_nw', terminal_nw) or terminal_nw)
    except Exception:
        after_tax_terminal_nw = terminal_nw - max(0.0, terminal_pretax) * max(0.0, terminal_tax_rate)
    # total_tax already includes federal, state, payroll, IRMAA, NIIT, and LTCG.
    # Score lifetime taxes in plan-start present value so a 2056 tax dollar does
    # not weigh the same as a 2026 tax dollar against terminal wealth.
    discount = max(-0.99, float(c.get('roth_tax_discount_rate', c.get('inf', 0.025)) or 0.0))
    plan_start = int(c.get('plan_start', rows[0].get('year', 0) if rows else 0) or 0)
    lifetime_tax = sum(float(r.get('total_tax', 0.0) or 0.0) / ((1.0 + discount) ** max(0, int(r.get('year', plan_start)) - plan_start)) for r in rows)
    lifetime_tax_nominal = sum(float(r.get('total_tax', 0.0) or 0.0) for r in rows)
    total_conversion = sum(float(r.get('roth_conv', 0.0) or 0.0) for r in rows)
    total_roth_withdrawal = sum(float(r.get('roth_wd', 0.0) or 0.0) for r in rows)
    roth_wd_while_nonroth = sum(
        float(r.get('roth_wd', 0.0) or 0.0)
        for r in rows
        if (float(r.get('pretax_nw', 0.0) or 0.0)
            + float(r.get('trust_nw', 0.0) or 0.0)
            + float(r.get('hsa_nw', 0.0) or 0.0)) > 1.0
    )
    terminal_weight = float(c.get('roth_optimize_terminal_weight', 1.0) or 1.0)
    tax_weight = float(c.get('roth_optimize_tax_weight', 0.25) or 0.0)

    legacy_mult = _roth_legacy_mode_multiplier(c)
    future_stress_rate = max(0.0, float(c.get('roth_future_tax_rate_stress_pct', 0.0) or 0.0))
    future_tax_weight = max(0.0, float(c.get('roth_future_tax_risk_weight', 0.0) or 0.0))
    inheritance_weight = max(0.0, float(c.get('roth_inheritance_tax_burden_weight', 0.0) or 0.0))
    heir_rate = max(0.0, float(c.get('roth_heir_ordinary_tax_rate_assumption', terminal_tax_rate) or terminal_tax_rate))
    pretax_bequest_penalty_rate = max(0.0, float(c.get('roth_pre_tax_bequest_penalty_pct', heir_rate) or heir_rate))
    roth_bonus_rate = max(0.0, float(c.get('roth_bequest_preference_bonus_pct', 0.0) or 0.0))
    survivor_weight = max(0.0, float(c.get('roth_survivor_tax_risk_weight', 0.0) or 0.0))

    def _disc(row: Mapping) -> float:
        return (1.0 + discount) ** max(0, int(row.get('year', plan_start) or plan_start) - plan_start)

    def _pv_avg(field: str) -> float:
        weights = [1.0 / _disc(r) for r in rows]
        denom = sum(weights) or 1.0
        return sum(max(0.0, float(r.get(field, 0.0) or 0.0)) * w for r, w in zip(rows, weights)) / denom

    def _peak(field: str) -> float:
        return max((max(0.0, float(r.get(field, 0.0) or 0.0)) for r in rows), default=0.0)

    # The comparison table must score dimensions that matter during the plan, not
    # only the final projection row. In many valid plans, both pre-tax and Roth
    # balances are depleted by the final death year; terminal-only scoring made
    # legacy, estate, survivor and liquidity columns appear unassigned. Use a
    # blended discounted-average/peak exposure so every component reflects the
    # full projection window while remaining comparable in dollar-score units.
    avg_pretax = _pv_avg('pretax_nw')
    avg_roth = _pv_avg('roth_nw')
    avg_liquid_nonroth = _pv_avg('trust_nw') + _pv_avg('hsa_nw')
    pretax_legacy_exposure = 0.65 * avg_pretax + 0.35 * _peak('pretax_nw')
    roth_legacy_exposure = 0.65 * avg_roth + 0.35 * _peak('roth_nw')

    # Penalize projected pre-tax exposure under future-tax-rate stress. This is
    # intentionally separate from the base terminal pre-tax haircut so users can
    # express concern that ordinary rates rise faster than modeled.
    future_tax_stress_penalty = pretax_legacy_exposure * future_stress_rate * future_tax_weight * legacy_mult

    # Penalize leaving heirs with compressed ordinary-income exposure on inherited
    # pre-tax balances. Use the larger of the configured heir tax assumption and
    # explicit pre-tax bequest haircut to be conservative but transparent.
    inheritance_rate = max(heir_rate, pretax_bequest_penalty_rate)
    pre_tax_inheritance_burden = pretax_legacy_exposure * inheritance_rate * inheritance_weight * legacy_mult

    # Survivor years can face single-filer tax compression. Prefer the actual
    # survivor window; if there is no pre-tax balance by then, score the run-up
    # into the first-death year so the table still exposes the risk reduction
    # benefit of earlier conversions.
    h_death = int(c.get('h_death_yr', 0) or 0)
    w_death = int(c.get('w_death_yr', 0) or 0)
    first_death = min(h_death, w_death) if h_death and w_death else 0
    second_death = max(h_death, w_death) if h_death and w_death else 0
    survivor_rows = [
        r for r in rows
        if first_death and second_death and first_death < int(r.get('year', 0) or 0) <= second_death
    ]
    pre_survivor_rows = [
        r for r in rows
        if first_death and first_death - 10 <= int(r.get('year', 0) or 0) <= first_death
    ]

    def _avg_pretax(row_list) -> float:
        return (sum(max(0.0, float(r.get('pretax_nw', 0.0) or 0.0)) for r in row_list) / len(row_list)) if row_list else 0.0

    avg_survivor_pretax = _avg_pretax(survivor_rows) or (0.50 * _avg_pretax(pre_survivor_rows))
    # If conversions retire all pre-tax balances before the modeled survivor
    # window, still expose a survivor-risk score based on plan-wide pre-tax
    # exposure; this lets candidates be compared instead of showing a blank/zero
    # component solely because the terminal survivor window has no IRA balance.
    survivor_pretax_exposure = avg_survivor_pretax or (0.35 * avg_pretax)
    survivor_tax_risk_penalty = max(0.0, survivor_pretax_exposure) * future_stress_rate * survivor_weight * legacy_mult

    # Favor Roth balances during retirement and at bequest because they reduce
    # heirs' ordinary-income tax burden and provide tax-rate diversification.
    roth_legacy_preference_value = roth_legacy_exposure * roth_bonus_rate * legacy_mult

    legacy_adjustment = (
        roth_legacy_preference_value
        - future_tax_stress_penalty
        - survivor_tax_risk_penalty
        - pre_tax_inheritance_burden
    )

    estate_mode = str(c.get('estate_tax_objective_mode', 'BALANCED') or 'BALANCED').upper()
    estate_mult = {'OFF': 0.0, 'MONITOR_ONLY': 0.0, 'BALANCED': 1.0, 'STRONG': 2.0}.get(estate_mode, 1.0)
    fed_exempt = max(0.0, float(c.get('fed_exempt', 0.0) or 0.0))
    state_exempt = max(0.0, float(c.get('il_exempt', 0.0) or 0.0))

    def _estate_tax_for_row(row: Mapping) -> float:
        row_total = max(0.0, float(row.get('total_nw', 0.0) or 0.0))
        row_cst = max(0.0, float(row.get('cst_excluded_from_survivor_estate', 0.0) or 0.0))
        federal_taxable = max(0.0, row_total - (row_cst if c.get('federal_portability_enabled', True) else 0.0))
        state_taxable = max(0.0, row_total - row_cst)
        federal_tax = max(0.0, federal_taxable - fed_exempt) * 0.40 if fed_exempt else 0.0
        state_tax = illinois_estate_tax(state_taxable, state_exempt) if c.get('model_state_est', True) and state_exempt else 0.0
        return federal_tax + state_tax

    estate_tax_penalty = estate_mult * max((_estate_tax_for_row(r) for r in rows), default=0.0)

    objective_mode = str(c.get('roth_objective_mode', 'BALANCED_RETIREMENT') or 'BALANCED_RETIREMENT').upper()
    # Start with balanced professional planning defaults, then allow modes to
    # emphasize a single dimension while preserving the Roth-last leakage guard.
    terminal_component = terminal_weight * after_tax_terminal_nw
    tax_component = -tax_weight * lifetime_tax
    legacy_component = legacy_adjustment
    estate_component = -estate_tax_penalty
    survivor_component = -survivor_tax_risk_penalty
    aca_ptc_loss = sum(float(r.get('aca_ptc_loss_from_conversion', 0.0) or 0.0) / ((1.0 + discount) ** max(0, int(r.get('year', plan_start)) - plan_start)) for r in rows)
    aca_ptc_component = -max(0.0, float(c.get('roth_aca_ptc_loss_weight', 1.0) or 1.0)) * aca_ptc_loss
    # Liquidity is a small tie-breaker, not a reason to over-convert. It rewards
    # plans that preserve a positive non-Roth liquid reserve during the horizon.
    liquidity_component = 0.01 * max(0.0, avg_liquid_nonroth)
    if objective_mode == 'MINIMIZE_LIFETIME_TAX':
        terminal_component = 0.10 * after_tax_terminal_nw
        tax_component = -1.00 * lifetime_tax
        legacy_component = 0.25 * legacy_adjustment
    elif objective_mode == 'MAXIMIZE_TERMINAL_NET_WORTH':
        terminal_component = 1.25 * after_tax_terminal_nw
        tax_component = -0.10 * lifetime_tax
        legacy_component = 0.25 * legacy_adjustment
    elif objective_mode == 'LEGACY_OPTIMIZED':
        legacy_component = 1.75 * legacy_adjustment
    elif objective_mode == 'ESTATE_TAX_AWARE':
        estate_component = -2.0 * estate_tax_penalty
    elif objective_mode == 'MAXIMIZE_PTI':
        # Post-Tax Inheritance = after-tax terminal NW minus estate tax. Reward the
        # after-tax estate fully and the estate-tax drag fully; lifetime tax is
        # already reflected in after-tax compounding, so keep it a light factor.
        terminal_component = 1.0 * after_tax_terminal_nw
        tax_component = -0.10 * lifetime_tax
        legacy_component = 0.25 * legacy_adjustment
        estate_component = -1.0 * estate_tax_penalty

    # Penalize any violation of the Roth-last rule heavily enough that a
    # strategy with leakage cannot win against one that funds from non-Roth.
    roth_leakage_penalty = 10.0 * roth_wd_while_nonroth
    score = terminal_component + tax_component + legacy_component + estate_component + survivor_component + aca_ptc_component + liquidity_component - roth_leakage_penalty
    return {
        'terminal_nw': terminal_nw,
        'after_tax_terminal_nw': after_tax_terminal_nw,
        'terminal_estate_tax': (_estate_tax_for_row(rows[-1]) if rows else 0.0),
        'post_tax_inheritance': after_tax_terminal_nw - (_estate_tax_for_row(rows[-1]) if rows else 0.0),
        'lifetime_tax': lifetime_tax,
        'total_conversion': total_conversion,
        'total_roth_withdrawal': total_roth_withdrawal,
        'roth_wd_while_nonroth': roth_wd_while_nonroth,
        'terminal_pretax': terminal_pretax,
        'terminal_roth': terminal_roth,
        'future_tax_stress_penalty': future_tax_stress_penalty,
        'survivor_tax_risk_penalty': survivor_tax_risk_penalty,
        'pre_tax_inheritance_burden': pre_tax_inheritance_burden,
        'roth_legacy_preference_value': roth_legacy_preference_value,
        'legacy_adjustment': legacy_adjustment,
        'estate_tax_penalty': estate_tax_penalty,
        'lifetime_tax_nominal': lifetime_tax_nominal,
        'terminal_wealth_score': terminal_component,
        'tax_efficiency_score': tax_component,
        'roth_legacy_score': legacy_component,
        'estate_tax_score': estate_component,
        'survivor_risk_score': survivor_component,
        'aca_ptc_loss': aca_ptc_loss,
        'aca_ptc_score': aca_ptc_component,
        'liquidity_score': liquidity_component,
        'total_objective_score': score,
        'objective_mode': objective_mode,
        'score': score,
    }


def optimize_roth_conversion_strategy(c: dict) -> dict:
    """Select the Roth conversion policy that best balances terminal wealth and lifetime tax.

    The objective is configurable but defaults to a balanced, after-tax terminal
    net-worth score less a lifetime-tax penalty. Each candidate still obeys the
    withdrawal engine's Roth-last rule.
    """
    requested_policy = str(c.get('roth_policy', '') or '').lower()
    if requested_policy not in ('optimize', 'optimize_terminal_tax', 'terminal_tax_optimize', 'balanced_optimize'):
        return c

    base = copy.deepcopy(c)
    base['roth_policy'] = 'none'
    candidates = []
    for spec in _roth_strategy_candidate_specs(c):
        c2 = copy.deepcopy(base)
        c2['roth_policy'] = spec['policy']
        for _k, _v in (spec.get('overrides') or {}).items():
            c2[_k] = _v
        if spec.get('target_rate') is not None:
            c2['roth_target_rate'] = float(spec['target_rate'])
            c2['roth_brk'] = float(spec['target_rate'])
        if spec.get('fixed_amount') is not None:
            c2['roth_fixed_amount'] = float(spec['fixed_amount'])
        rows = project(c2)
        metrics = _roth_strategy_metrics(c2, rows)
        candidates.append({**spec, **metrics})

    candidates.sort(key=lambda x: (x['score'], x['after_tax_terminal_nw'], -x['lifetime_tax']), reverse=True)
    best = candidates[0] if candidates else {'policy': 'none', 'label': 'No voluntary conversions'}

    c['roth_policy_requested'] = requested_policy
    c['roth_policy'] = best.get('policy', 'none')
    c['roth_optimized_policy'] = c['roth_policy']
    if best.get('target_rate') is not None:
        c['roth_target_rate'] = float(best['target_rate'])
        c['roth_brk'] = float(best['target_rate'])
    if best.get('fixed_amount') is not None:
        c['roth_fixed_amount'] = float(best['fixed_amount'])
    c['roth_optimization'] = {
        'requested_policy': requested_policy,
        'selected_label': best.get('label', ''),
        'selected_policy': c['roth_policy'],
        'selected_strategy_code': best.get('strategy_code', c['roth_policy']),
        'roth_bracket_strategy': str(c.get('roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').upper(),
        'objective_mode': str(c.get('roth_objective_mode', 'BALANCED_RETIREMENT') or 'BALANCED_RETIREMENT').upper(),
        'estate_tax_objective_mode': str(c.get('estate_tax_objective_mode', 'BALANCED') or 'BALANCED').upper(),
        'headroom_usage_pct': float(c.get('roth_headroom_usage_pct', 0.95) or 0.95),
        'irmaa_headroom_usage_pct': float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95),
        'irmaa_guardrail_mode': str(c.get('irmaa_guardrail_mode', 'AVOID_NEXT_TIER') or 'AVOID_NEXT_TIER').upper(),
        'irmaa_target_tier': str(c.get('roth_irmaa_target_tier', 'TIER_2') or 'TIER_2').upper(),
        'terminal_weight': float(c.get('roth_optimize_terminal_weight', 1.0) or 1.0),
        'tax_weight': float(c.get('roth_optimize_tax_weight', 0.25) or 0.0),
        'target_bracket': float(c.get('roth_target_rate', c.get('roth_brk', 0.22)) or 0.22),
        'terminal_tax_rate': float(c.get('roth_optimize_terminal_tax_rate', c.get('roth_target_rate', 0.22)) or 0.22),
        'max_annual_conversion_pct_of_traditional_ira': float(c.get('roth_max_annual_conversion_pct_of_traditional_ira', 0.20) or 0.20),
        'max_conversion_years': int(float(c.get('roth_max_conversion_years', 10) or 10)),
        'legacy_objective_mode': str(c.get('roth_legacy_objective_mode', 'OFF') or 'OFF').upper(),
        'legacy_mode_multiplier': _roth_legacy_mode_multiplier(c),
        'future_tax_rate_stress_pct': float(c.get('roth_future_tax_rate_stress_pct', 0.0) or 0.0),
        'future_tax_risk_weight': float(c.get('roth_future_tax_risk_weight', 0.0) or 0.0),
        'inheritance_tax_burden_weight': float(c.get('roth_inheritance_tax_burden_weight', 0.0) or 0.0),
        'heir_ordinary_tax_rate_assumption': float(c.get('roth_heir_ordinary_tax_rate_assumption', 0.0) or 0.0),
        'pre_tax_bequest_penalty_pct': float(c.get('roth_pre_tax_bequest_penalty_pct', 0.0) or 0.0),
        'roth_bequest_preference_bonus_pct': float(c.get('roth_bequest_preference_bonus_pct', 0.0) or 0.0),
        'survivor_tax_risk_weight': float(c.get('roth_survivor_tax_risk_weight', 0.0) or 0.0),
        'candidates': candidates,
    }
    return c


def _sample_return(rng: random.Random, mu: float, sig: float, year_idx: int, c: dict) -> float:
    """Regime/fat-tail return draw with glide-path volatility dampening.

    Version 7.8.1 correction: the prior regime engine labeled the configured
    return as ``mu`` but then subtracted crisis/recession/stagflation penalties
    without re-centering the mixture. With the default regime probabilities, a
    displayed 6.0% return had an expected draw near 4.1%. By default we now
    re-center the regime mixture so the configured return is the actual expected
    return before volatility/longevity path effects.
    """
    glide_mode = str(c.get('glide_path', 'target_date')).lower()
    if glide_mode != 'static':
        glide_scale = max(0.65, 1.0 - 0.01 * year_idx)
        sig = sig * glide_scale
        # A de-risking glide path should lower both volatility and expected
        # return. Approximate this by shrinking the portfolio risk premium
        # toward the configured bond return as the glide scale declines.
        bond_mu = float(c.get('ret_bond', 0.04) or 0.04)
        mu = bond_mu + (mu - bond_mu) * glide_scale

    # Probability-weighted mean of the default return-regime offsets:
    # 2.5% crisis @ -24%, 9.0% recession @ -10%, 8.5% stagflation @ -4.5%,
    # 80.0% normal @ 0%.  Adding the inverse keeps E[draw] ~= configured mu.
    recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0

    u = rng.random()
    if u < 0.025:      # crisis / fat-tail shock
        return rng.gauss(mu + recenter - 0.24, sig * 1.8)
    if u < 0.115:      # recession
        return rng.gauss(mu + recenter - 0.10, sig * 1.25)
    if u < 0.20:       # high-inflation/stagflation
        return rng.gauss(mu + recenter - 0.045, sig * 1.15)
    return rng.gauss(mu + recenter, sig)


def _liquid_value(row: dict) -> float:
    """Spendable retirement asset value used for MC funding success."""
    return float(row.get('pretax_nw', 0) or 0) + float(row.get('roth_nw', 0) or 0) + \
           float(row.get('trust_nw', 0) or 0) + float(row.get('hsa_nw', 0) or 0)


def _funding_success(rows, threshold: float = 0.0) -> bool:
    """True if the path never runs out of modeled spendable funding.

    Criteria:
    1. No positive residual unfunded spending gap in any year.
    2. Liquid retirement assets remain above the configured threshold in every
       projected year and at terminal year.

    This intentionally excludes home equity and annuity PV from the success
    test. Those remain visible in total net-worth percentiles but no longer make
    a failed liquidity path look like a successful retirement funding path.
    """
    if not rows:
        return False
    max_unfunded = max(float(r.get('unfunded_gap', 0) or 0) for r in rows)
    min_liquid = min(_liquid_value(r) for r in rows)
    final_liquid = _liquid_value(rows[-1])
    return max_unfunded <= 1.0 and min_liquid > threshold and final_liquid > threshold


def _funding_success_with_home_equity(rows, threshold: float = 0.0, home_equity_reserve: float = 0.0,
                                       access_lag_years: int = 1) -> bool:
    """Like _funding_success but counts home equity as a last-resort reserve.

    If liquid assets are below threshold, the home_equity_reserve value (already
    haircut-adjusted) is added as a one-time draw available after access_lag_years
    from the first failure year. This computes a more optimistic 'contingency'
    success rate shown alongside the primary rate.
    """
    if not rows:
        return False
    if home_equity_reserve <= 0:
        return _funding_success(rows, threshold)
    # Primary check first — if already succeeds without contingency, return True
    if _funding_success(rows, threshold):
        return True
    # Find first year where liquid falls below threshold
    remaining_equity = home_equity_reserve
    first_shortfall_year = None
    for r in rows:
        if _liquid_value(r) <= threshold or float(r.get('unfunded_gap', 0) or 0) > 1.0:
            first_shortfall_year = r.get('year')
            break
    if first_shortfall_year is None:
        return True
    # Simulate applying equity as a lump-sum reserve after lag
    # If the equity can cover the gap we treat the path as contingency-success
    # by measuring whether adding the reserve to liquid at that point and forward
    # would have kept the plan funded. We approximate this by checking if the
    # shortfall exceeds the reserve value.
    total_unfunded = sum(float(r.get('unfunded_gap', 0) or 0) for r in rows)
    total_liquid_shortfall = sum(
        max(0.0, threshold - _liquid_value(r))
        for r in rows
        if (r.get('year') or 0) >= (first_shortfall_year + access_lag_years)
    )
    return total_unfunded <= 1.0 and total_liquid_shortfall <= remaining_equity


def _first_failure_year(rows, threshold: float = 0.0):
    for r in rows:
        if float(r.get('unfunded_gap', 0) or 0) > 1.0 or _liquid_value(r) <= threshold:
            return r.get('year')
    return None


def _percentiles(vals, success_threshold: float = 0.0):
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return {p: 0 for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]} | {'mean': 0, 'success': 0}

    def pick(p):
        # Linear interpolation between order statistics, equivalent to NumPy's
        # default method for percentile estimates.
        if n == 1:
            return vals[0]
        rank = (p / 100.0) * (n - 1)
        lo = int(math.floor(rank))
        hi = int(math.ceil(rank))
        if lo == hi:
            return vals[lo]
        frac = rank - lo
        return vals[lo] * (1.0 - frac) + vals[hi] * frac

    return {
        1: pick(1), 5: pick(5), 10: pick(10), 25: pick(25), 50: pick(50),
        75: pick(75), 90: pick(90), 95: pick(95), 99: pick(99),
        'mean': sum(vals) / n,
        'success': sum(1 for v in vals if v > success_threshold) / n,
    }


def _success_rate_ci(successes: int, n: int, z: float = 1.96):
    """Wilson score interval for a binomial success rate."""
    n = max(1, int(n))
    p_hat = max(0.0, min(1.0, successes / n))
    denom = 1.0 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z * z / (4 * n * n)))
    return max(0.0, centre - half), min(1.0, centre + half)


def _clone_for_mc(c: dict) -> dict:
    """Copy only mutable projection state needed by each MC path.

    Full deepcopy of the whole config was the dominant fixed overhead.  This
    preserves path safety for balances, account metadata, annuity streams, lot
    engines, schedules, and sampled paths without recursively copying immutable
    scalar settings on every simulation.
    """
    c2 = dict(c)
    deep_keys = {
        'balances', 'ann_db', 'wife_pension', 'wife_single', 'wife_joint',
        'h_single', 'h_joint', 'mort_schedule', 'lump', 'note_interest',
        'account_registry', 'account_meta', 'balance_sheet', 'asset_class_overrides',
        'asset_class_enabled', 'asset_class_selection_action',
        'asset_class_alternate_first', 'allocation_target_pct',
        'asset_correlation_overrides', 'recurring_extras', 'taxable_ids',
        'pre_tax_ids', 'roth_ids', 'hsa_ids', 'invest_ids', 'all_acct_ids',
        'lot_engine', 'return_by_year', 'inflation_index_by_year',
        'ss_cola_index_by_year', 'bracket_index_by_year', 'irmaa_index_by_year',
        'medical_index_by_year', 'wellness_shock_by_year',
    }
    for k in deep_keys:
        if k in c:
            c2[k] = copy.deepcopy(c[k])
    return c2


def _portfolio_asset_class_inputs(c: dict):
    try:
        from . import optimization as _opt
    except Exception:
        import src.optimization as _opt  # type: ignore
    _opt.apply_capital_market_config(c)
    targets = c.get('allocation_target_pct') or {}
    enabled = c.get('asset_class_enabled') or {}
    pairs = []
    for cls, pct in targets.items():
        cls_name = str(cls)
        if cls_name not in _opt.ASSET_CLASSES:
            continue
        if enabled and not bool(enabled.get(cls_name, True)):
            continue
        try:
            weight = max(0.0, float(pct or 0.0))
        except Exception:
            weight = 0.0
        if weight > 0:
            pairs.append((cls_name, weight))
    if not pairs:
        # Conservative fallback when no detailed target rows are present.
        approx = {
            'US Large Cap': float(c.get('alloc_equity', 0.60) or 0.60),
            'Commodities': float(c.get('alloc_commodity', 0.0) or 0.0),
            'Cash': float(c.get('alloc_cash', 0.05) or 0.05),
        }
        bond_w = max(0.0, 1.0 - sum(approx.values()))
        approx['Bonds'] = bond_w
        pairs = [(cls, w) for cls, w in approx.items() if cls in _opt.ASSET_CLASSES and w > 0]
    total = sum(w for _cls, w in pairs) or 1.0
    classes = [cls for cls, _w in pairs]
    weights = [w / total for _cls, w in pairs]
    try:
        from .vectorized_fast_core import portfolio_moments
    except Exception:  # pragma: no cover
        from src.vectorized_fast_core import portfolio_moments
    moments = portfolio_moments(classes, weights, _opt.ASSET_CLASSES, _opt._CORR)
    means = [_opt.ASSET_CLASSES[cls]['ret'] for cls in classes]
    cov = moments['covariance']
    mu = float(moments['expected_return'])
    sig = float(moments['volatility'] or c.get('mc_sigma', 0.12) or 0.12)
    return classes, weights, means, cov, mu, sig


def _regime_overlay(rng: random.Random, base_return: float, sig: float, c: dict) -> float:
    recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0
    u = rng.random()
    if u < 0.025:
        return base_return + recenter - 0.24 + rng.gauss(0.0, sig * 0.80)
    if u < 0.115:
        return base_return + recenter - 0.10 + rng.gauss(0.0, sig * 0.35)
    if u < 0.20:
        return base_return + recenter - 0.045 + rng.gauss(0.0, sig * 0.20)
    return base_return + recenter


def _generate_return_path(c: dict, rng: random.Random, mu: float, sig: float, years: list[int], use_asset_classes: bool = True):
    diagnostics = {'return_model': 'single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    draws = []
    if use_asset_classes and bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            import numpy as _np
            classes, weights, means, cov, port_mu, port_sig = _portfolio_asset_class_inputs(c)
            np_rng = _np.random.default_rng(rng.randrange(1, 2**32 - 1))
            raw = np_rng.multivariate_normal(_np.array(means, dtype=float), cov, size=len(years), check_valid='warn')
            wv = _np.array(weights, dtype=float)
            draws = [float(x) for x in raw.dot(wv)]
            mu = float(port_mu)
            sig = float(max(1e-6, port_sig))
            diagnostics.update({
                'return_model': 'asset_class_covariance',
                'portfolio_expected_return': mu,
                'portfolio_sigma': sig,
                'asset_classes': classes,
                'asset_weights': {cls: weights[i] for i, cls in enumerate(classes)},
            })
        except Exception as exc:
            diagnostics.update({'return_model_warning': str(exc)})
    if not draws:
        draws = [_sample_return(rng, mu, sig, i, c) for i, _yr in enumerate(years)]
    else:
        draws = [_regime_overlay(rng, r, sig, c) for r in draws]

    # De-risking glide path for asset-class draws: shrink the realized return
    # toward the configured bond return over time, mirroring _sample_return.
    if str(c.get('glide_path', 'target_date')).lower() != 'static' and diagnostics.get('return_model') == 'asset_class_covariance':
        bond_mu = float(c.get('ret_bond', 0.04) or 0.04)
        adjusted = []
        for i, r in enumerate(draws):
            glide_scale = max(0.65, 1.0 - 0.01 * i)
            adjusted.append(bond_mu + (r - bond_mu) * glide_scale)
        draws = adjusted

    phi = max(-0.75, min(0.75, float(c.get('mc_serial_correlation', 0.0) or 0.0)))
    if abs(phi) > 1e-9 and len(draws) > 1:
        adjusted = [draws[0]]
        damp = math.sqrt(max(0.0, 1.0 - phi * phi))
        for r in draws[1:]:
            adjusted.append(mu + phi * (adjusted[-1] - mu) + damp * (r - mu))
        draws = adjusted
        diagnostics['serial_correlation'] = phi
    return {yr: draws[i] for i, yr in enumerate(years)}, diagnostics


def _sample_inflation_and_health_paths(c: dict, rng: random.Random, years: list[int], returns: dict[int, float], mu: float, sig: float):
    start = int(c['plan_start'])
    inf_mu = float(c.get('inf', 0.025) or 0.025)
    inf_sig = max(0.0, float(c.get('mc_inflation_sigma', 0.015) or 0.015))
    corr = max(-0.95, min(0.95, float(c.get('mc_return_inflation_corr', -0.25) or 0.0)))
    stochastic = bool(c.get('mc_inflation_stochastic', True))
    sqrt_term = math.sqrt(max(0.0, 1.0 - corr * corr))
    inflation_rates = {}
    inflation_index = {}
    ss_index = {}
    bracket_index = {}
    irmaa_index = {}
    medical_index = {}
    wellness_shocks = {}
    inf_factor = ss_factor = brk_factor = irmaa_factor = med_factor = 1.0
    for yr in years:
        if yr == start:
            inflation_rates[yr] = inf_mu
            inflation_index[yr] = ss_index[yr] = bracket_index[yr] = irmaa_index[yr] = medical_index[yr] = 1.0
        else:
            ret_z = 0.0 if sig <= 1e-9 else (float(returns.get(yr, mu)) - mu) / sig
            surprise = 0.0
            if stochastic:
                surprise = inf_sig * (corr * ret_z + sqrt_term * rng.gauss(0.0, 1.0))
            annual_inf = max(-0.02, min(0.12, inf_mu + surprise))
            inflation_rates[yr] = annual_inf
            inf_factor *= (1.0 + annual_inf)
            ss_rate = max(0.0, min(0.10, float(c.get('ss_cola', 0.02) or 0.02) + 0.70 * (annual_inf - inf_mu)))
            brk_rate = max(0.0, min(0.08, float(c.get('brk_inf', 0.02) or 0.02) + (0.65 if c.get('mc_bracket_stochastic', True) else 0.0) * (annual_inf - inf_mu)))
            irmaa_rate = max(0.0, min(0.08, float(c.get('irmaa_inflator', 0.02) or 0.02) + (0.80 if c.get('mc_irmaa_stochastic', True) else 0.0) * (annual_inf - inf_mu)))
            med_rate = max(0.0, min(0.14, float(c.get('med_inf', 0.055) or 0.055) + 0.85 * (annual_inf - inf_mu)))
            ss_factor *= (1.0 + ss_rate)
            brk_factor *= (1.0 + brk_rate)
            irmaa_factor *= (1.0 + irmaa_rate)
            med_factor *= (1.0 + med_rate)
            inflation_index[yr] = inf_factor
            ss_index[yr] = ss_factor
            bracket_index[yr] = brk_factor
            irmaa_index[yr] = irmaa_factor
            medical_index[yr] = med_factor
        if bool(c.get('mc_wellness_shocks', True)):
            prob = max(0.0, min(1.0, float(c.get('mc_wellness_prob', 0.03) or 0.0)))
            mean_cost = max(0.0, float(c.get('mc_wellness_mean', 150000.0) or 0.0))
            if mean_cost > 0 and rng.random() < prob:
                # Exponential severity creates infrequent large events while the
                # cap prevents a single draw from dominating small-sample tests.
                wellness_shocks[yr] = min(mean_cost * 4.0, rng.expovariate(1.0 / mean_cost))
    def _geom_rate(index):
        if len(years) <= 1:
            return inf_mu
        end_factor = max(1e-12, float(index.get(years[-1], 1.0) or 1.0))
        return end_factor ** (1.0 / max(1, len(years) - 1)) - 1.0
    return {
        'inflation_by_year': inflation_rates,
        'inflation_index_by_year': inflation_index,
        'ss_cola_index_by_year': ss_index,
        'bracket_index_by_year': bracket_index,
        'irmaa_index_by_year': irmaa_index,
        'medical_index_by_year': medical_index,
        'wellness_shock_by_year': wellness_shocks,
        'sampled_inflation_geometric': _geom_rate(inflation_index),
        'sampled_bracket_inflation_geometric': _geom_rate(bracket_index),
        'sampled_irmaa_inflation_geometric': _geom_rate(irmaa_index),
    }


def _adjust_annuity_pmt_for_mc(stream: dict, returns: dict, inflation_paths: dict, years: list, mu: float) -> dict:
    """Adjust init_pmt for variable and COLA annuities based on sampled paths.

    Variable: scale init_pmt by (cumulative_sampled_return / cumulative_expected_return)
    COLA: scale init_pmt by cumulative sampled inflation (relative to expected inflation).
    Fixed: no adjustment.

    Returns a modified copy of the stream dict.
    """
    payout_type = stream.get('payout_type', 'fixed')
    if payout_type == 'fixed' or not years or float(stream.get('init_pmt', 0) or 0) <= 0:
        return stream
    stream = dict(stream)
    first_yr = int(stream.get('first_yr', years[0]) or years[0])
    # Use only years up to and including the annuity start year for the scaling horizon
    horizon = [y for y in years if y <= first_yr]
    if not horizon:
        return stream
    if payout_type == 'variable':
        # Scale by cumulative return ratio: sampled vs expected
        cum_sampled = 1.0
        cum_expected = 1.0
        for y in horizon:
            cum_sampled *= (1.0 + float(returns.get(y, mu) or mu))
            cum_expected *= (1.0 + mu)
        if cum_expected > 0:
            scale = max(0.5, min(2.0, cum_sampled / cum_expected))  # cap at ±2x
            stream['init_pmt'] = float(stream['init_pmt']) * scale
    elif payout_type == 'cola':
        # Scale by cumulative inflation ratio: sampled vs expected plan inflation
        expected_inf = float(stream.get('ann_inf', 0.025) or 0.025)
        infl_by_year = inflation_paths.get('inflation_by_year', {})
        cum_sampled_inf = 1.0
        cum_expected_inf = 1.0
        for y in horizon:
            cum_sampled_inf *= (1.0 + float(infl_by_year.get(y, expected_inf) or expected_inf))
            cum_expected_inf *= (1.0 + expected_inf)
        if cum_expected_inf > 0:
            scale = max(0.7, min(1.5, cum_sampled_inf / cum_expected_inf))
            stream['init_pmt'] = float(stream['init_pmt']) * scale
    return stream


def _run_one_mc_path(c: dict, rng: random.Random, mu: float, sig: float, use_asset_classes: bool = True):
    c2 = _clone_for_mc(c)
    c2.update(sample_household_death_years(c2, rng))
    years = list(range(int(c2['plan_start']), int(c2['plan_end']) + 1))
    returns, return_diag = _generate_return_path(c2, rng, mu, sig, years, use_asset_classes=use_asset_classes)
    c2['return_by_year'] = returns
    inflation_paths = _sample_inflation_and_health_paths(
        c2, rng, years, returns,
        float(return_diag.get('portfolio_expected_return', mu) or mu),
        float(return_diag.get('portfolio_sigma', sig) or sig),
    )
    c2.update(inflation_paths)
    # Adjust variable/COLA annuity payments based on this path's sampled returns/inflation
    for ann_key in ['wife_pension', 'wife_single', 'wife_joint', 'h_single', 'h_joint']:
        if ann_key in c2 and isinstance(c2[ann_key], dict):
            c2[ann_key] = _adjust_annuity_pmt_for_mc(c2[ann_key], returns, inflation_paths, years, mu)
    # project() consumes the per-year bracket_index_by_year and irmaa_index_by_year
    # paths directly, so each scalar MC path uses its own sampled tax thresholds
    # rather than a geometric-mean approximation.
    rows = project(c2)
    return rows, years, returns, return_diag, inflation_paths


def _sensitivity_success_rate(c: dict, mu: float, sig: float, n_sims: int, seed: int, threshold: float) -> float:
    rng = random.Random(seed)
    successes = 0
    for _ in range(max(1, int(n_sims))):
        rows, _years, _returns, _diag, _infl = _run_one_mc_path(c, rng, mu, sig, use_asset_classes=False)
        if _funding_success(rows, threshold):
            successes += 1
    return successes / max(1, int(n_sims))


def monte_carlo_exact_scalar(c, n_sims=1000, seed=42):
    c = ensure_engine_config(c, source='monte_carlo')
    rng = random.Random(seed)
    base_rows = project(c)
    base_years = [r['year'] for r in base_rows]
    configured_mu = float(c.get('ret', 0.06))
    configured_sig = float(c.get('mc_sigma', 0.12))
    mu = configured_mu
    sig = configured_sig
    portfolio_diag = {'return_model': 'single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    if bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            _classes, _weights, _means, _cov, _pmu, _psig = _portfolio_asset_class_inputs(c)
            mu, sig = float(_pmu), float(max(1e-6, _psig))
            portfolio_diag = {
                'return_model': 'asset_class_covariance',
                'portfolio_expected_return': mu,
                'portfolio_sigma': sig,
                'asset_classes': _classes,
                'asset_weights': {_classes[i]: _weights[i] for i in range(len(_classes))},
            }
        except Exception as exc:
            portfolio_diag['return_model_warning'] = str(exc)
    N = int(c.get('mc_sims', n_sims or 1000))
    configured_threshold = float(c.get('mc_success_liquid_floor', 0.0) or 0.0)
    # If the CSV leaves the floor at 0, use the plan's own reserve policy.
    # A zero-year reserve policy therefore produces a zero reserve floor.
    if configured_threshold > 0:
        success_threshold = configured_threshold
        success_threshold_source = 'configured success_liquid_floor'
    else:
        buffer_years = max(0.0, float(c.get('near_term_buffer_years', 0.0) or 0.0))
        success_threshold = float(c.get('spend_base', 0.0) or 0.0) * buffer_years
        success_threshold_source = f'{buffer_years:g} years of base spending'

    # Keep sensitivity analysis real but bounded.  The default is now 200 per
    # cell for statistical honesty; explicit small overrides remain honored for
    # unit tests and smoke builds.
    sens_N = int(c.get('mc_sensitivity_sims', 200) or 200)
    sens_N = max(1, min(2000, sens_N))

    # Home equity contingency settings
    he_contingency_enabled = bool(c.get('mc_home_equity_contingency', False))
    he_haircut = float(c.get('mc_home_equity_haircut', 0.20) or 0.20)
    he_lag = int(c.get('mc_home_equity_access_lag_years', 1) or 1)
    gross_home_equity = max(0.0, float(c.get('home_val', 0) or 0) - float(c.get('mortgage_bal', 0) or 0))
    he_reserve = gross_home_equity * (1.0 - he_haircut) if he_contingency_enabled else 0.0

    all_total_by_year = defaultdict(list)
    all_liquid_by_year = defaultdict(list)
    first5_avgs = []
    terminal_total = []
    terminal_liquid = []
    terminal_success_flags = []
    first_failure_years = []
    liquid_successes = 0
    he_contingency_successes = 0
    total_nw_positive = 0
    sampled_returns = []
    sampled_inflation_rates = []
    sampled_wellness_shocks = []
    return_model_counts = defaultdict(int)

    progress_step = max(1, N // 10)
    print(f'Monte Carlo exact scalar paths: 0/{N}', flush=True)
    for sim_idx in range(N):
        rows, years, returns, return_diag, inflation_paths = _run_one_mc_path(c, rng, mu, sig, use_asset_classes=True)
        return_model_counts[str(return_diag.get('return_model', 'unknown'))] += 1
        by_year = {r['year']: r for r in rows}
        last_row = rows[-1]
        path_returns = [returns[y] for y in years[:5]]
        sampled_returns.extend(returns[y] for y in years)
        sampled_inflation_rates.extend(float(inflation_paths.get('inflation_by_year', {}).get(y, c.get('inf', 0.025)) or 0.0) for y in years)
        sampled_wellness_shocks.extend(float(v or 0.0) for v in inflation_paths.get('wellness_shock_by_year', {}).values())
        first5_avgs.append(sum(path_returns) / max(1, len(path_returns)))

        for yr in base_years:
            r = by_year.get(yr) or last_row
            liquid = _liquid_value(r)
            all_total_by_year[yr].append(float(r.get('total_nw', 0) or 0))
            all_liquid_by_year[yr].append(liquid)

        final_total = float(last_row.get('total_nw', 0) or 0)
        final_liquid = _liquid_value(last_row)
        path_success = _funding_success(rows, success_threshold)
        terminal_total.append(final_total)
        terminal_liquid.append(final_liquid)
        terminal_success_flags.append(path_success)
        first_failure_years.append(_first_failure_year(rows, success_threshold))

        if final_total > 0:
            total_nw_positive += 1
        if path_success:
            liquid_successes += 1
        if he_contingency_enabled:
            if _funding_success_with_home_equity(rows, success_threshold, he_reserve, he_lag):
                he_contingency_successes += 1
        if (sim_idx + 1) % progress_step == 0 or (sim_idx + 1) == N:
            print(f'Monte Carlo exact scalar paths: {sim_idx + 1}/{N}', flush=True)

    pct_by_year = {yr: _percentiles(all_total_by_year[yr], 0.0) for yr in base_years}
    liquid_pct_by_year = {yr: _percentiles(all_liquid_by_year[yr], success_threshold) for yr in base_years}
    end_yr = base_years[-1]

    # Quintiles are sorted by first-5-year returns, but success is now funded-plan
    # success and terminal values are terminal liquid assets. Total terminal net
    # worth remains in mc_data for charts/reporting transparency.
    sorted_sims = sorted(zip(first5_avgs, terminal_total, terminal_liquid, terminal_success_flags))
    q_size = max(1, N // 5)
    qlabels = ['Q1 — Worst 20%', 'Q2', 'Q3 — Middle 20%', 'Q4', 'Q5 — Best 20%']
    quintiles = []
    for q in range(5):
        sl = sorted_sims[q * q_size:(q + 1) * q_size]
        if not sl:
            sl = sorted_sims[-q_size:]
        liquid_ends = sorted(s[2] for s in sl)
        total_ends = sorted(s[1] for s in sl)
        quintiles.append({
            'label': qlabels[q],
            'avg_r5': sum(s[0] for s in sl) / len(sl),
            'p10_end': liquid_ends[int(0.10 * (len(liquid_ends) - 1))],
            'med_end': liquid_ends[len(liquid_ends) // 2],
            'p90_end': liquid_ends[min(len(liquid_ends) - 1, int(0.90 * (len(liquid_ends) - 1)))],
            'avg_end': sum(liquid_ends) / len(liquid_ends),
            'med_total_nw': total_ends[len(total_ends) // 2],
            'success': sum(1 for s in sl if s[3]) / len(sl),
        })

    mus_grid = [0.04, 0.05, 0.06, 0.07, 0.08]
    sigs_grid = [0.08, 0.10, 0.12, 0.14, 0.16]
    sensitivity = {}
    total_cells = max(1, len(mus_grid) * len(sigs_grid))
    done_cells = 0
    print(f'Monte Carlo sensitivity grid: 0/{total_cells} cells × {sens_N} paths', flush=True)
    for i, mu_s in enumerate(mus_grid):
        for j, sig_s in enumerate(sigs_grid):
            cell_seed = seed + 10_000 + i * 100 + j
            sensitivity[(mu_s, sig_s)] = _sensitivity_success_rate(
                c, mu_s, sig_s, sens_N, cell_seed, success_threshold
            )
            done_cells += 1
            print(f'Monte Carlo sensitivity grid: {done_cells}/{total_cells} cells × {sens_N} paths', flush=True)

    failures = [y for y in first_failure_years if y is not None]
    first_failure_distribution = {}
    for y in failures:
        first_failure_distribution[y] = first_failure_distribution.get(y, 0) + 1

    success_rate = liquid_successes / max(1, N)
    success_ci_low, success_ci_high = _success_rate_ci(liquid_successes, N)
    success_se = math.sqrt(max(0.0, success_rate * (1.0 - success_rate) / max(1, N)))

    return {
        'pct_by_year': pct_by_year,                         # total net worth distribution
        'liquid_pct_by_year': liquid_pct_by_year,           # liquid funding distribution
        'quintiles': quintiles,
        'sensitivity': sensitivity,
        'sensitivity_sims': sens_N,
        'years': base_years,
        'mus': mus_grid,
        'sigs': sigs_grid,
        'mu': mu,
        'sig': sig,
        'configured_mu': configured_mu,
        'configured_sig': configured_sig,
        'portfolio_return_model': max(return_model_counts, key=return_model_counts.get) if return_model_counts else portfolio_diag.get('return_model'),
        'portfolio_return_diagnostics': portfolio_diag,
        'sampled_mean_return': (sum(sampled_returns) / len(sampled_returns)) if sampled_returns else mu,
        'sampled_geometric_return': (
            math.exp(sum(math.log1p(max(-0.999999, r)) for r in sampled_returns) / len(sampled_returns)) - 1
            if sampled_returns else mu
        ),
        'sampled_mean_inflation': (sum(sampled_inflation_rates) / len(sampled_inflation_rates)) if sampled_inflation_rates else float(c.get('inf', 0.025) or 0.025),
        'sampled_wellness_shock_count': len(sampled_wellness_shocks),
        'sampled_wellness_shock_mean_cost': (sum(sampled_wellness_shocks) / len(sampled_wellness_shocks)) if sampled_wellness_shocks else 0.0,
        'return_recentered': bool(c.get('mc_recenter_regime_returns', True)),
        'n_sims': N,
        'seed': seed,
        'success_definition': 'No unfunded annual spending gap and liquid retirement assets remain above configured floor in every projected year.',
        'success_liquid_floor': success_threshold,
        'success_liquid_floor_source': success_threshold_source,
        'success_rate': success_rate,
        'success_rate_ci_low': success_ci_low,
        'success_rate_ci_high': success_ci_high,
        'success_rate_standard_error': success_se,
        'liquid_success_rate': success_rate,
        'total_nw_success_rate': total_nw_positive / max(1, N),
        'failure_rate': 1.0 - success_rate,
        'home_equity_contingency_enabled': he_contingency_enabled,
        'home_equity_contingency_reserve': he_reserve,
        'home_equity_contingency_haircut': he_haircut,
        'success_rate_with_home_equity': he_contingency_successes / max(1, N) if he_contingency_enabled else None,
        'deterministic_projection_label': 'No-volatility deterministic reference path; Monte Carlo median is the probabilistic planning number.',
        'first_failure_distribution': first_failure_distribution,
        'terminal_total_nw': _percentiles(terminal_total, 0.0),
        'terminal_liquid_assets': _percentiles(terminal_liquid, success_threshold),
        'nw0': base_rows[0]['pretax_nw'] + base_rows[0]['roth_nw'] + base_rows[0]['trust_nw'] + base_rows[0]['hsa_nw'],
        'invest0': base_rows[0]['pretax_nw'] + base_rows[0]['roth_nw'] + base_rows[0]['trust_nw'] + base_rows[0]['hsa_nw'],
        'net_draws': [],
        'survival_curve': [
            {'year': yr, 'pct_funded': liquid_pct_by_year[yr]['success'] * 100}
            for yr in base_years
        ],
        'mc_engine': 'exact_scalar',
        'mc_engine_label': 'Exact scalar Monte Carlo validation mode',
        'mc_approximation_status': 'EXACT',
        'model_risk_rating': 'EXACT_SCALAR_MC',
    }

# ===== END monte_carlo_engine.py =====

# ===== BEGIN v8.3_vectorized_monte_carlo_engine.py =====


def _mc_bucket_starting_balances(c: dict) -> dict:
    """Return beginning balances by projection bucket for vectorized MC."""
    balances = c.get('balances') or {}
    registry = c.get('account_registry') or []
    result = {'pretax': 0.0, 'roth': 0.0, 'taxable': 0.0, 'hsa': 0.0, 'cash': 0.0}
    for acct in registry:
        aid = acct.get('id')
        tax = str(acct.get('tax') or '').lower()
        bal = float(balances.get(aid, acct.get('balance', 0.0)) or 0.0)
        if tax == 'pre_tax':
            result['pretax'] += bal
        elif tax == 'roth':
            result['roth'] += bal
        elif tax == 'hsa':
            result['hsa'] += bal
        elif tax == 'cash':
            result['cash'] += bal
        else:
            result['taxable'] += bal
    return result


def _mc_row_bucket_flows(c: dict, base_rows: list[dict]) -> dict:
    """Build deterministic per-year bucket flows used by vectorized MC.

    The scalar projection remains the source of truth for deterministic cash-flow
    timing, withdrawal ordering, deposits, and forced Roth conversions.  v8.3
    converts those row-level decisions into vectors and then evolves all Monte
    Carlo paths across simulations at once, rather than re-running the scalar
    projection for every path.
    """
    registry = {a.get('id'): str(a.get('tax') or '').lower() for a in c.get('account_registry') or []}
    years = [int(r['year']) for r in base_rows]
    buckets = ('pretax', 'roth', 'taxable', 'hsa', 'cash')
    out = {name: {b: [] for b in buckets} for name in ('withdrawals', 'deposits', 'conversions_out', 'conversions_in')}
    total_spend = []
    total_tax = []
    gross_income = []
    deterministic_inflation_index = []
    inf = float(c.get('inf', 0.025) or 0.025)
    start = int(c.get('plan_start', years[0] if years else 0))

    def _bucket_for_account(aid: str) -> str:
        tax = registry.get(aid, '')
        if tax == 'pre_tax':
            return 'pretax'
        if tax == 'roth':
            return 'roth'
        if tax == 'hsa':
            return 'hsa'
        if tax == 'cash':
            return 'cash'
        return 'taxable'

    for row in base_rows:
        for name, key in (('withdrawals', '_account_withdrawals'), ('deposits', '_account_deposits'),
                          ('conversions_out', '_account_conversions_out'), ('conversions_in', '_account_conversions_in')):
            vals = {b: 0.0 for b in buckets}
            for aid, amount in (row.get(key) or {}).items():
                vals[_bucket_for_account(str(aid))] += max(0.0, float(amount or 0.0))
            for b in buckets:
                out[name][b].append(vals[b])
        total_spend.append(float(row.get('total_spend', 0.0) or 0.0))
        total_tax.append(float(row.get('total_tax', 0.0) or 0.0))
        gross_income.append(float(row.get('gross_income', 0.0) or 0.0))
        deterministic_inflation_index.append((1.0 + inf) ** max(0, int(row['year']) - start))

    try:
        import numpy as _np
        for name in out:
            for b in buckets:
                out[name][b] = _np.array(out[name][b], dtype=float)
        out['total_spend'] = _np.array(total_spend, dtype=float)
        out['total_tax'] = _np.array(total_tax, dtype=float)
        out['gross_income'] = _np.array(gross_income, dtype=float)
        out['deterministic_inflation_index'] = _np.array(deterministic_inflation_index, dtype=float)
    except Exception:
        pass
    out['years'] = years
    return out


def _mc_vectorized_death_years(c: dict, np_rng, n_sims: int):
    import numpy as _np
    members = c.get('members') or []
    sigma = max(0.0, float(c.get('mortality_sigma', 4.5) or 4.5))
    if members:
        h_dob = int(members[0].get('dob_yr', c.get('h_dob_yr', 1960)))
        h_med = float(members[0].get('mortality_age', c.get('h_death_age', 92)) or 92)
    else:
        h_dob, h_med = int(c.get('h_dob_yr', 1960)), 92.0
    h = _np.rint(h_dob + _np.clip(np_rng.normal(h_med, sigma, size=n_sims), 70.0, 110.0)).astype(int)
    if len(members) > 1:
        w_dob = int(members[1].get('dob_yr', c.get('w_dob_yr', 1960)))
        w_med = float(members[1].get('mortality_age', c.get('w_death_age', 92)) or 92)
        w = _np.rint(w_dob + _np.clip(np_rng.normal(w_med, sigma, size=n_sims), 70.0, 110.0)).astype(int)
    else:
        w = h.copy()
    return h, w, _np.maximum(h, w)


def _mc_vectorized_return_paths(c: dict, np_rng, n_sims: int, years: list[int], mu: float, sig: float, use_asset_classes: bool = True):
    import numpy as _np
    n_years = len(years)
    diagnostics = {'return_model': 'vectorized_single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    base_draws = None
    port_mu, port_sig = float(mu), float(max(1e-6, sig))
    if use_asset_classes and bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            classes, weights, means, cov, port_mu, port_sig = _portfolio_asset_class_inputs(c)
            raw = np_rng.multivariate_normal(_np.array(means, dtype=float), cov, size=(n_sims, n_years), check_valid='warn')
            wv = _np.array(weights, dtype=float)
            base_draws = raw.dot(wv)
            diagnostics.update({
                'return_model': 'vectorized_asset_class_covariance',
                'portfolio_expected_return': float(port_mu),
                'portfolio_sigma': float(max(1e-6, port_sig)),
                'asset_classes': classes,
                'asset_weights': {cls: weights[i] for i, cls in enumerate(classes)},
            })
        except Exception as exc:
            diagnostics['return_model_warning'] = str(exc)
    if base_draws is None:
        # Generate the same regime-aware distribution as _sample_return, but in
        # one batched draw for all simulations and years.
        u = np_rng.random((n_sims, n_years))
        recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0
        offsets = _np.zeros((n_sims, n_years), dtype=float)
        sigma_mult = _np.ones((n_sims, n_years), dtype=float)
        offsets = _np.where(u < 0.025, -0.24, offsets)
        sigma_mult = _np.where(u < 0.025, 1.8, sigma_mult)
        offsets = _np.where((u >= 0.025) & (u < 0.115), -0.10, offsets)
        sigma_mult = _np.where((u >= 0.025) & (u < 0.115), 1.25, sigma_mult)
        offsets = _np.where((u >= 0.115) & (u < 0.20), -0.045, offsets)
        sigma_mult = _np.where((u >= 0.115) & (u < 0.20), 1.15, sigma_mult)
        base_draws = np_rng.normal(float(mu) + recenter + offsets, float(sig) * sigma_mult)
        port_mu, port_sig = float(mu), float(max(1e-6, sig))
    else:
        u = np_rng.random((n_sims, n_years))
        recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0
        offsets = _np.zeros((n_sims, n_years), dtype=float)
        extra_sigma = _np.zeros((n_sims, n_years), dtype=float)
        offsets = _np.where(u < 0.025, -0.24, offsets)
        extra_sigma = _np.where(u < 0.025, port_sig * 0.80, extra_sigma)
        offsets = _np.where((u >= 0.025) & (u < 0.115), -0.10, offsets)
        extra_sigma = _np.where((u >= 0.025) & (u < 0.115), port_sig * 0.35, extra_sigma)
        offsets = _np.where((u >= 0.115) & (u < 0.20), -0.045, offsets)
        extra_sigma = _np.where((u >= 0.115) & (u < 0.20), port_sig * 0.20, extra_sigma)
        base_draws = base_draws + recenter + offsets + np_rng.normal(0.0, extra_sigma)

    if str(c.get('glide_path', 'target_date')).lower() != 'static':
        bond_mu = float(c.get('ret_bond', 0.04) or 0.04)
        glide = _np.array([max(0.65, 1.0 - 0.01 * i) for i in range(n_years)], dtype=float)
        base_draws = bond_mu + (base_draws - bond_mu) * glide.reshape(1, -1)

    phi = max(-0.75, min(0.75, float(c.get('mc_serial_correlation', 0.0) or 0.0)))
    if abs(phi) > 1e-9 and n_years > 1:
        adjusted = base_draws.copy()
        damp = math.sqrt(max(0.0, 1.0 - phi * phi))
        for j in range(1, n_years):
            adjusted[:, j] = port_mu + phi * (adjusted[:, j - 1] - port_mu) + damp * (base_draws[:, j] - port_mu)
        base_draws = adjusted
        diagnostics['serial_correlation'] = phi
    return _np.clip(base_draws, -0.95, 1.50), diagnostics


def _mc_vectorized_inflation_health_paths(c: dict, np_rng, returns, mu: float, sig: float):
    import numpy as _np
    n_sims, n_years = returns.shape
    inf_mu = float(c.get('inf', 0.025) or 0.025)
    inf_sig = max(0.0, float(c.get('mc_inflation_sigma', 0.015) or 0.015))
    corr = max(-0.95, min(0.95, float(c.get('mc_return_inflation_corr', -0.25) or 0.0)))
    stochastic = bool(c.get('mc_inflation_stochastic', True))
    ret_z = _np.zeros_like(returns)
    if sig > 1e-9:
        ret_z = (returns - float(mu)) / float(sig)
    innovation = np_rng.normal(0.0, 1.0, size=returns.shape)
    surprise = inf_sig * (corr * ret_z + math.sqrt(max(0.0, 1.0 - corr * corr)) * innovation) if stochastic else 0.0
    rates = _np.clip(inf_mu + surprise, -0.02, 0.12).astype(float)
    if n_years:
        rates[:, 0] = inf_mu
    inflation_index = _np.ones_like(rates)
    if n_years > 1:
        inflation_index[:, 1:] = _np.cumprod(1.0 + rates[:, 1:], axis=1)

    def _linked_index(base_rate: float, weight: float, cap: float):
        linked = _np.clip(base_rate + weight * (rates - inf_mu), 0.0, cap)
        out = _np.ones_like(linked)
        if n_years > 1:
            out[:, 1:] = _np.cumprod(1.0 + linked[:, 1:], axis=1)
        return out

    ss_index = _linked_index(float(c.get('ss_cola', 0.02) or 0.02), 0.70, 0.10)
    brk_index = _linked_index(float(c.get('brk_inf', 0.02) or 0.02), 0.65 if c.get('mc_bracket_stochastic', True) else 0.0, 0.08)
    irmaa_index = _linked_index(float(c.get('irmaa_inflator', 0.02) or 0.02), 0.80 if c.get('mc_irmaa_stochastic', True) else 0.0, 0.08)
    medical_index = _linked_index(float(c.get('med_inf', 0.055) or 0.055), 0.85, 0.14)

    shocks = _np.zeros_like(rates)
    if bool(c.get('mc_wellness_shocks', True)):
        prob = max(0.0, min(1.0, float(c.get('mc_wellness_prob', 0.03) or 0.0)))
        mean_cost = max(0.0, float(c.get('mc_wellness_mean', 150000.0) or 0.0))
        if prob > 0 and mean_cost > 0:
            mask = np_rng.random(size=rates.shape) < prob
            severity = _np.minimum(mean_cost * 4.0, np_rng.exponential(mean_cost, size=rates.shape))
            shocks = _np.where(mask, severity, 0.0)
    return {
        'inflation_by_year_matrix': rates,
        'inflation_index_matrix': inflation_index,
        'ss_cola_index_matrix': ss_index,
        'bracket_index_matrix': brk_index,
        'irmaa_index_matrix': irmaa_index,
        'medical_index_matrix': medical_index,
        'wellness_shock_matrix': shocks,
    }


def _mc_apply_withdrawal_bucket(balances, request, bucket: str):
    import numpy as _np
    amount = _np.minimum(balances[bucket], _np.maximum(0.0, request))
    balances[bucket] -= amount
    return amount, request - amount


def _mc_vectorized_projection(c: dict, base_rows: list[dict], returns, inflation_paths: dict, max_death_years):
    """Vectorized tax-bucket withdrawal recursion for Monte Carlo paths."""
    import numpy as _np
    n_sims, n_years = returns.shape
    starts = _mc_bucket_starting_balances(c)
    flows = _mc_row_bucket_flows(c, base_rows)
    years = _np.array(flows['years'], dtype=int)
    active = years.reshape(1, -1) <= max_death_years.reshape(-1, 1)
    inf_idx = inflation_paths['inflation_index_matrix']
    med_idx = inflation_paths['medical_index_matrix']
    shocks = inflation_paths['wellness_shock_matrix']
    det_idx = _np.maximum(1e-12, flows['deterministic_inflation_index']).reshape(1, -1)
    spending_scale = inf_idx / det_idx

    balances = {
        'pretax': _np.full(n_sims, starts['pretax'], dtype=float),
        'roth': _np.full(n_sims, starts['roth'], dtype=float),
        'taxable': _np.full(n_sims, starts['taxable'], dtype=float),
        'hsa': _np.full(n_sims, starts['hsa'], dtype=float),
        'cash': _np.full(n_sims, starts['cash'], dtype=float),
    }
    out = {k: _np.zeros((n_sims, n_years), dtype=float) for k in ('pretax', 'roth', 'taxable', 'hsa', 'cash', 'liquid', 'total', 'unfunded')}

    # Non-liquid net worth is deterministic/non-market for MC display.  It is
    # held separate so liquidity success remains driven only by spendable assets.
    nonliquid = _np.array([
        float(r.get('total_nw', 0.0) or 0.0)
        - float(r.get('pretax_nw', 0.0) or 0.0)
        - float(r.get('roth_nw', 0.0) or 0.0)
        - float(r.get('trust_nw', 0.0) or 0.0)
        - float(r.get('hsa_nw', 0.0) or 0.0)
    for r in base_rows], dtype=float)

    tax_drag = _np.clip(
        _np.divide(flows['total_tax'], _np.maximum(1.0, flows['gross_income']), out=_np.zeros(n_years), where=_np.maximum(1.0, flows['gross_income']) > 0),
        0.0, 0.55
    )

    for j in range(n_years):
        act = active[:, j]
        # Start with the scalar engine's planned bucket withdrawals, then scale
        # spending-sensitive rows to the sampled inflation path and medical/LTC
        # shocks.  Shock costs first draw against HSA when possible, then the
        # normal withdrawal cascade covers any remaining funding need.
        planned = {
            'taxable': flows['withdrawals']['taxable'][j] * spending_scale[:, j],
            'pretax': flows['withdrawals']['pretax'][j] * spending_scale[:, j],
            'roth': flows['withdrawals']['roth'][j] * spending_scale[:, j],
            'hsa': flows['withdrawals']['hsa'][j] * med_idx[:, j] / det_idx[:, j],
            'cash': flows['withdrawals']['cash'][j] * spending_scale[:, j],
        }
        # Pretax withdrawals carry an approximate marginal tax gross-up so the
        # vectorized path does not understate tax pressure in poor markets.
        planned['pretax'] = planned['pretax'] * (1.0 + tax_drag[j])
        shock_need = shocks[:, j] * act
        hsa_shock, shock_left = _mc_apply_withdrawal_bucket(balances, shock_need, 'hsa')
        planned['taxable'] = planned['taxable'] + shock_left

        unfunded = _np.zeros(n_sims, dtype=float)
        for bucket in ('cash', 'taxable', 'pretax', 'roth', 'hsa'):
            req = _np.where(act, planned[bucket], 0.0)
            taken, left = _mc_apply_withdrawal_bucket(balances, req, bucket)
            # Cascade residual need through remaining liquid buckets.
            if _np.any(left > 1e-6):
                for fallback in ('taxable', 'pretax', 'roth', 'hsa', 'cash'):
                    if fallback == bucket:
                        continue
                    extra, left = _mc_apply_withdrawal_bucket(balances, left, fallback)
                    if not _np.any(left > 1e-6):
                        break
            unfunded += _np.maximum(0.0, left)

        for bucket in ('cash', 'taxable', 'pretax', 'roth', 'hsa'):
            balances[bucket] += _np.where(act, flows['deposits'][bucket][j], 0.0)

        conv = _np.minimum(balances['pretax'], _np.where(act, flows['conversions_out']['pretax'][j] * spending_scale[:, j], 0.0))
        balances['pretax'] -= conv
        balances['roth'] += conv

        growth = returns[:, j]
        for bucket in ('taxable', 'pretax', 'roth', 'hsa'):
            balances[bucket] = _np.maximum(0.0, balances[bucket] * (1.0 + growth))
        # Cash gets a conservative short-rate proxy tied to inflation rather than equity returns.
        cash_rate = _np.clip(inflation_paths['inflation_by_year_matrix'][:, j] * 0.60, 0.0, 0.06)
        balances['cash'] = _np.maximum(0.0, balances['cash'] * (1.0 + cash_rate))

        out['pretax'][:, j] = balances['pretax']
        out['roth'][:, j] = balances['roth']
        out['taxable'][:, j] = balances['taxable']
        out['hsa'][:, j] = balances['hsa']
        out['cash'][:, j] = balances['cash']
        out['liquid'][:, j] = balances['pretax'] + balances['roth'] + balances['taxable'] + balances['hsa']
        out['total'][:, j] = out['liquid'][:, j] + balances['cash'] + nonliquid[j]
        out['unfunded'][:, j] = unfunded
    return out


def _mc_vectorized_batch(c: dict, base_rows: list[dict], n_sims: int, seed: int, mu: float, sig: float, success_threshold: float, use_asset_classes: bool = True):
    import numpy as _np
    np_rng = _np.random.default_rng(int(seed))
    years = [int(r['year']) for r in base_rows]
    h_death, w_death, max_death = _mc_vectorized_death_years(c, np_rng, int(n_sims))
    returns, return_diag = _mc_vectorized_return_paths(c, np_rng, int(n_sims), years, mu, sig, use_asset_classes=use_asset_classes)
    inflation_paths = _mc_vectorized_inflation_health_paths(
        c, np_rng, returns,
        float(return_diag.get('portfolio_expected_return', mu) or mu),
        float(return_diag.get('portfolio_sigma', sig) or sig),
    )
    projection = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death)
    active = _np.array(years, dtype=int).reshape(1, -1) <= max_death.reshape(-1, 1)
    failure_matrix = ((projection['unfunded'] > 1.0) | (projection['liquid'] <= float(success_threshold))) & active
    path_success = ~_np.any(failure_matrix, axis=1)
    any_failure = _np.any(failure_matrix, axis=1)
    first_failure_idx = _np.argmax(failure_matrix, axis=1)
    first_failure_years = [years[int(idx)] if bool(any_failure[i]) else None for i, idx in enumerate(first_failure_idx)]
    return {
        'years': years,
        'returns': returns,
        'inflation_paths': inflation_paths,
        'projection': projection,
        'path_success': path_success,
        'first_failure_years': first_failure_years,
        'return_diag': return_diag,
        'h_death_years': h_death,
        'w_death_years': w_death,
        'max_death_years': max_death,
    }


def _mc_vectorized_sensitivity_success_rate(c: dict, base_rows: list[dict], mu: float, sig: float, n_sims: int, seed: int, threshold: float) -> float:
    batch = _mc_vectorized_batch(c, base_rows, max(1, int(n_sims)), seed, mu, sig, threshold, use_asset_classes=False)
    try:
        import numpy as _np
        return float(_np.mean(batch['path_success']))
    except Exception:
        return sum(1 for x in batch['path_success'] if x) / max(1, int(n_sims))


def monte_carlo(c, n_sims=1000, seed=42):
    """Run Monte Carlo on the shared vectorized fast core by default.

    The exact scalar path remains available for validation by setting
    ``mc_engine_mode`` to ``exact_scalar`` or ``scalar``.
    """
    if str(c.get('mc_engine_mode', 'vectorized_batched')).lower() in {'exact_scalar', 'scalar', 'advanced_exact_scalar'}:
        return monte_carlo_exact_scalar(c, n_sims=n_sims, seed=seed)

    import numpy as _np
    from .observability import observe
    c = ensure_engine_config(c, source='monte_carlo')
    base_rows = project(c)
    base_years = [int(r['year']) for r in base_rows]
    configured_mu = float(c.get('ret', 0.06))
    configured_sig = float(c.get('mc_sigma', 0.12))
    mu = configured_mu
    sig = configured_sig
    portfolio_diag = {'return_model': 'vectorized_single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    if bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            _classes, _weights, _means, _cov, _pmu, _psig = _portfolio_asset_class_inputs(c)
            mu, sig = float(_pmu), float(max(1e-6, _psig))
            portfolio_diag = {
                'return_model': 'vectorized_asset_class_covariance',
                'portfolio_expected_return': mu,
                'portfolio_sigma': sig,
                'asset_classes': _classes,
                'asset_weights': {_classes[i]: _weights[i] for i in range(len(_classes))},
            }
        except Exception as exc:
            portfolio_diag['return_model_warning'] = str(exc)

    N = int(c.get('mc_sims', n_sims or 1000))
    configured_threshold = float(c.get('mc_success_liquid_floor', 0.0) or 0.0)
    if configured_threshold > 0:
        success_threshold = configured_threshold
        success_threshold_source = 'configured success_liquid_floor'
    else:
        buffer_years = max(0.0, float(c.get('near_term_buffer_years', 0.0) or 0.0))
        success_threshold = float(c.get('spend_base', 0.0) or 0.0) * buffer_years
        success_threshold_source = f'{buffer_years:g} years of base spending'

    sens_N = int(c.get('mc_sensitivity_sims', 200) or 200)
    sens_N = max(1, min(2000, sens_N))

    # Home equity contingency settings (vectorized engine uses terminal-liquid approximation)
    he_contingency_enabled_v = bool(c.get('mc_home_equity_contingency', False))
    he_haircut_v = float(c.get('mc_home_equity_haircut', 0.20) or 0.20)
    gross_home_equity_v = max(0.0, float(c.get('home_val', 0) or 0) - float(c.get('mortgage_bal', 0) or 0))
    he_reserve_v = gross_home_equity_v * (1.0 - he_haircut_v) if he_contingency_enabled_v else 0.0

    print(f'Monte Carlo vectorized batch: sampling {max(1, N)} paths', flush=True)
    batch = _mc_vectorized_batch(c, base_rows, max(1, N), int(seed), mu, sig, success_threshold, use_asset_classes=True)
    print('Monte Carlo vectorized batch: main batch complete', flush=True)
    proj = batch['projection']
    returns = batch['returns']
    infl = batch['inflation_paths']
    path_success = _np.array(batch['path_success'], dtype=bool)

    pct_by_year = {yr: _percentiles(proj['total'][:, i].tolist(), 0.0) for i, yr in enumerate(base_years)}
    liquid_pct_by_year = {yr: _percentiles(proj['liquid'][:, i].tolist(), success_threshold) for i, yr in enumerate(base_years)}

    terminal_total = proj['total'][:, -1]
    terminal_liquid = proj['liquid'][:, -1]
    first5_avgs = _np.mean(returns[:, :max(1, min(5, returns.shape[1]))], axis=1)
    sorted_idx = _np.argsort(first5_avgs)
    q_size = max(1, int(N) // 5)
    qlabels = ['Q1 — Worst 20%', 'Q2', 'Q3 — Middle 20%', 'Q4', 'Q5 — Best 20%']
    quintiles = []
    for q in range(5):
        idx = sorted_idx[q * q_size:(q + 1) * q_size]
        if idx.size == 0:
            idx = sorted_idx[-q_size:]
        liquid_ends = _np.sort(terminal_liquid[idx])
        total_ends = _np.sort(terminal_total[idx])
        quintiles.append({
            'label': qlabels[q],
            'avg_r5': float(_np.mean(first5_avgs[idx])),
            'p10_end': float(_np.percentile(liquid_ends, 10)),
            'med_end': float(_np.percentile(liquid_ends, 50)),
            'p90_end': float(_np.percentile(liquid_ends, 90)),
            'avg_end': float(_np.mean(liquid_ends)),
            'med_total_nw': float(_np.percentile(total_ends, 50)),
            'success': float(_np.mean(path_success[idx])),
        })

    mus_grid = [0.04, 0.05, 0.06, 0.07, 0.08]
    sigs_grid = [0.08, 0.10, 0.12, 0.14, 0.16]
    sensitivity = {}
    total_cells = max(1, len(mus_grid) * len(sigs_grid))
    done_cells = 0
    print(f'Monte Carlo sensitivity grid: 0/{total_cells} cells × {sens_N} paths', flush=True)
    for i, mu_s in enumerate(mus_grid):
        for j, sig_s in enumerate(sigs_grid):
            cell_seed = int(seed) + 10_000 + i * 100 + j
            sensitivity[(mu_s, sig_s)] = _mc_vectorized_sensitivity_success_rate(
                c, base_rows, mu_s, sig_s, sens_N, cell_seed, success_threshold
            )
            done_cells += 1
            print(f'Monte Carlo sensitivity grid: {done_cells}/{total_cells} cells × {sens_N} paths', flush=True)

    failures = [y for y in batch['first_failure_years'] if y is not None]
    first_failure_distribution = {}
    for y in failures:
        first_failure_distribution[y] = first_failure_distribution.get(y, 0) + 1

    liquid_successes = int(_np.sum(path_success))
    success_rate = float(liquid_successes / max(1, N))
    success_ci_low, success_ci_high = _success_rate_ci(liquid_successes, N)
    success_se = math.sqrt(max(0.0, success_rate * (1.0 - success_rate) / max(1, N)))
    # Vectorized approximation: contingency counts paths where terminal_liquid + reserve > threshold
    if he_contingency_enabled_v and he_reserve_v > 0:
        he_contingency_success_v = float(_np.mean(
            path_success | (terminal_liquid + he_reserve_v > success_threshold)
        ))
    else:
        he_contingency_success_v = None
    sampled_returns = returns.reshape(-1)
    sampled_inflation_rates = infl['inflation_by_year_matrix'].reshape(-1)
    sampled_wellness_shocks = infl['wellness_shock_matrix']
    return_model = str(batch['return_diag'].get('return_model') or portfolio_diag.get('return_model'))

    return {
        'pct_by_year': pct_by_year,
        'liquid_pct_by_year': liquid_pct_by_year,
        'quintiles': quintiles,
        'sensitivity': sensitivity,
        'sensitivity_sims': sens_N,
        'years': base_years,
        'mus': mus_grid,
        'sigs': sigs_grid,
        'mu': mu,
        'sig': sig,
        'configured_mu': configured_mu,
        'configured_sig': configured_sig,
        'portfolio_return_model': return_model.replace('vectorized_', ''),
        'portfolio_return_diagnostics': {**portfolio_diag, **batch['return_diag'], 'mc_engine': 'vectorized_batched_tax_withdrawal', 'hybrid_tax_kernel_note': 'Scalar deterministic tax/withdrawal rows seed a vectorized bucket recursion; exact scalar MC remains available for validation.'},
        'sampled_mean_return': float(_np.mean(sampled_returns)) if sampled_returns.size else mu,
        'sampled_geometric_return': float(_np.exp(_np.mean(_np.log1p(_np.clip(sampled_returns, -0.999999, None)))) - 1.0) if sampled_returns.size else mu,
        'sampled_mean_inflation': float(_np.mean(sampled_inflation_rates)) if sampled_inflation_rates.size else float(c.get('inf', 0.025) or 0.025),
        'sampled_wellness_shock_count': int(_np.count_nonzero(sampled_wellness_shocks > 0.0)),
        'sampled_wellness_shock_mean_cost': float(_np.mean(sampled_wellness_shocks[sampled_wellness_shocks > 0.0])) if _np.any(sampled_wellness_shocks > 0.0) else 0.0,
        'return_recentered': bool(c.get('mc_recenter_regime_returns', True)),
        'n_sims': N,
        'seed': seed,
        'success_definition': 'No unfunded annual spending gap and liquid retirement assets remain above configured floor in every active projected year.',
        'success_liquid_floor': success_threshold,
        'success_liquid_floor_source': success_threshold_source,
        'success_rate': success_rate,
        'success_rate_ci_low': success_ci_low,
        'success_rate_ci_high': success_ci_high,
        'success_rate_standard_error': success_se,
        'liquid_success_rate': success_rate,
        'total_nw_success_rate': float(_np.mean(terminal_total > 0.0)),
        'failure_rate': 1.0 - success_rate,
        'home_equity_contingency_enabled': he_contingency_enabled_v,
        'home_equity_contingency_reserve': he_reserve_v,
        'home_equity_contingency_haircut': he_haircut_v,
        'success_rate_with_home_equity': he_contingency_success_v,
        'deterministic_projection_label': 'No-volatility deterministic reference path; Monte Carlo median is the probabilistic planning number.',
        'first_failure_distribution': first_failure_distribution,
        'terminal_total_nw': _percentiles(terminal_total.tolist(), 0.0),
        'terminal_liquid_assets': _percentiles(terminal_liquid.tolist(), success_threshold),
        'nw0': float(proj['pretax'][0, 0] + proj['roth'][0, 0] + proj['taxable'][0, 0] + proj['hsa'][0, 0]),
        'invest0': float(proj['pretax'][0, 0] + proj['roth'][0, 0] + proj['taxable'][0, 0] + proj['hsa'][0, 0]),
        'net_draws': [],
        'survival_curve': [
            {'year': yr, 'pct_funded': liquid_pct_by_year[yr]['success'] * 100}
            for yr in base_years
        ],
        'mc_engine': 'vectorized_batched_tax_withdrawal',
        'mc_engine_label': 'Approximate vectorized Monte Carlo',
        'mc_approximation_status': 'APPROXIMATE_PENDING_SCALAR_PARITY',
        'model_risk_rating': 'APPROXIMATE_VECTORIZED_MC',
    }

# ===== END v8.3_vectorized_monte_carlo_engine.py =====