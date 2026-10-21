from __future__ import annotations

"""Pure numeric kernels for the retirement projection engines (WI-037, ARC-005).

Portfolio growth, death/inheritance transition, mortality sampling, RMD and
withdrawal ordering, spending guardrails, ACA subsidy and Roth-conversion
planning. These were the growth/inheritance/mortality/withdrawal/conversion
sections of ``planning_engines``; they live here so the projection stages can
import them without importing ``planning_engines`` (which imports the stages),
which removes the circular dependency. ``planning_engines`` re-exports every
name so existing callers and golden masters are unchanged.

Do not import ``planning_engines`` (or ``projection_stages``) from this module;
tests/test_engine_kernels_import_boundary_unit.py enforces that.
"""

import json
import numpy as _np
from .core import *  # noqa: F401,F403

# ===== BEGIN growth_engine.py =====

"""Portfolio growth helpers for the retirement projection engine.

This module centralizes end-of-year account growth so projection code does not
inline account traversal or accidentally compound the same account twice.
"""

from collections import namedtuple
from .fallback_log import log_fallback as _log_fallback
from math import isfinite

GrowthResult = namedtuple('GrowthResult', ['total_growth', 'by_account', 'warnings'])




def _roth_discount_rate(c: dict) -> float:
    """Nominal discount rate for the Roth objective's present-value terms.

    Shared with data_io's parse default so the objective can never score
    against a different rate than the plan page displays. Falls back to
    DEFAULT_ROTH_TAX_DISCOUNT_RATE (6.5% nominal) rather than the inflation
    assumption -- see that constant's note for why those are not the same
    quantity.
    """
    from .data_io import DEFAULT_ROTH_TAX_DISCOUNT_RATE as _default
    raw = c.get('roth_tax_discount_rate')
    if raw is None:
        raw = _default
    try:
        return max(-0.99, float(raw or 0.0))
    except Exception:
        return _default


def _account_return_tilt(c: dict, account_id) -> float:
    """This account's expected return RELATIVE to the plan-wide return.

    ``c['account_returns']`` holds ABSOLUTE expected rates: data_io writes
    ``_base_ret + (acct_ret - portfolio_ret)`` -- the plan return plus the
    account's tilt from its actual holdings mix. The deterministic engine
    consumes them as rates directly.

    A Monte Carlo path already carries its own sampled portfolio return for
    the year, so what transfers onto that path is the TILT, not the rate.
    Adding the absolute rate instead roughly doubles growth: with c['ret']=0.05
    and a 5.5% sampled year, a 4.98% IRA compounds at 10.48%.

    Tilts are dollar-weighted to approximately zero across the portfolio by
    construction, so applying them preserves the plan's expected return as the
    portfolio-wide average while letting asset location redistribute it --
    which is the whole point of finding C3.
    """
    account_returns = c.get('account_returns') or {}
    if account_id not in account_returns:
        return 0.0
    try:
        return float(account_returns[account_id]) - float(c.get('ret', 0.0) or 0.0)
    except Exception:
        return 0.0


def _mc_bucket_return_tilts(c: dict) -> dict:
    """Dollar-weighted return tilt per projection bucket.

    The vectorized MC evolves tax BUCKETS (pretax/roth/taxable/hsa), not
    individual accounts, so per-account tilts have to be collapsed the same way
    the balances are -- weighted by dollars, since a $10k bond-heavy IRA and a
    $1M one cannot move the pretax bucket equally.

    'cash' is deliberately absent: the vectorized path grows cash on its own
    short-rate proxy tied to inflation rather than the equity draw, so a tilt
    against the equity return would be meaningless there.
    """
    account_returns = c.get('account_returns') or {}
    if not account_returns:
        return {}
    balances = c.get('balances') or {}
    weighted: dict = {}
    totals: dict = {}
    for acct in (c.get('account_registry') or []):
        aid = acct.get('id')
        if aid not in account_returns:
            continue
        tax = str(acct.get('tax') or '').lower()
        if tax == 'cash':
            continue
        bucket = {'pre_tax': 'pretax', 'roth': 'roth', 'hsa': 'hsa'}.get(tax, 'taxable')
        try:
            bal = float(balances.get(aid, acct.get('balance', 0.0)) or 0.0)
        except Exception:
            bal = 0.0
        if bal <= 0:
            continue
        weighted[bucket] = weighted.get(bucket, 0.0) + bal * _account_return_tilt(c, aid)
        totals[bucket] = totals.get(bucket, 0.0) + bal
    return {b: weighted[b] / totals[b] for b in weighted if totals.get(b, 0.0) > 0}


def _mc_apply_bucket_growth(balances: dict, growth, bucket_tilts: dict):
    """Grow each market bucket by the sampled return plus that bucket's tilt.

    Tilts REDISTRIBUTE return between buckets; they must never change the
    portfolio total, which stays at the sampled return. That conservation is
    what lets asset location matter without the engine inventing return.

    The tilts arrive computed once from the OPENING balance mix, but that mix
    moves all horizon -- withdrawals and RMDs drain the negatively-tilted
    pretax bucket, conversions fill the positively-tilted Roth one -- so a set
    that nets to zero at t=0 does not stay netted. It drifted to +24.9 bps of
    free return by 2056 on the frozen fixture. Subtracting THIS step's
    balance-weighted mean tilt restores neutrality at every step and on every
    path independently, and leaves the spread between buckets -- the actual
    Wave 3.5 deliverable -- exactly intact.

    Split out so the vectorized projection and its tests exercise the same
    code. With an empty ``bucket_tilts`` this is bit-identical to the previous
    ``balances[b] * (1.0 + growth)``.
    """
    buckets = ('taxable', 'pretax', 'roth', 'hsa')
    if not bucket_tilts:
        for bucket in buckets:
            balances[bucket] = _np.maximum(0.0, balances[bucket] * (1.0 + growth))
        return balances

    tilts = {b: float(bucket_tilts.get(b, 0.0) or 0.0) for b in buckets}
    total = sum(balances[b] for b in buckets)
    weighted = sum(balances[b] * tilts[b] for b in buckets)
    safe_total = _np.where(total > 0.0, total, 1.0)
    mean_tilt = _np.where(total > 0.0, weighted / safe_total, 0.0)

    for bucket in buckets:
        rate = growth + tilts[bucket] - mean_tilt
        balances[bucket] = _np.maximum(0.0, balances[bucket] * (1.0 + rate))
    return balances


def _apply_account_return_adjustments(c: dict, returns_by_year: dict, years: list[int]):
    """Apply per-account return adjustments to a base return-by-year dict.

    For each account in account_returns, creates a per-year return path by
    carrying that account's TILT (see _account_return_tilt) onto the sampled
    portfolio return. This enables asset-location-aware success rates in MC.

    Args:
        c: plan dict containing account_returns (per-account ABSOLUTE rates)
        returns_by_year: dict[year] -> float (sampled portfolio return that year)
        years: list of year values

    Cash-tax accounts are excluded, matching ``_mc_bucket_return_tilts``. The
    vectorized path -- the one that produces the headline success rate -- grows
    cash on a short-rate proxy tied to inflation rather than on the equity draw,
    so a tilt measured against the equity return has no meaning there. Tilting
    cash here and not there made the two MC paths disagree about any cash
    account holding a CMA-classifiable security, e.g. a money-market fund
    (finding S5). The exclusion is now stated once and applied in both places.

    Returns:
        dict[account_id][year] = float, or empty dict if no account_returns configured
    """
    account_returns = c.get('account_returns') or {}
    if not account_returns:
        return {}

    invest_ids = c.get('invest_ids') or []
    cash_ids = {
        acct.get('id')
        for acct in (c.get('account_registry') or [])
        if str(acct.get('tax') or '').lower() == 'cash'
    }
    try:
        result = {}
        for acct_id in invest_ids:
            if acct_id not in account_returns or acct_id in cash_ids:
                continue

            acct_delta = _account_return_tilt(c, acct_id)
            result[acct_id] = {
                yr: returns_by_year.get(yr, 0.0) + acct_delta
                for yr in years
            }
        return result
    except Exception:
        return {}


def _account_return(c, account_id, default_return, year=None):
    """Return the account-specific growth rate, falling back to plan return.

    Future modules can populate ``c['account_returns']`` with per-account rates.
    For now this keeps deterministic projections compatible with the existing
    single return assumption.
    """
    # Monte Carlo per-account per-year returns take precedence (Wave 3.5 completion).
    if year is not None and isinstance(c.get('return_by_account_by_year'), dict):
        acct_returns = c['return_by_account_by_year'].get(account_id, {})
        if isinstance(acct_returns, dict) and year in acct_returns:
            return float(acct_returns[year])
    # Fallback: year-specific simulated return path (single rate for all accounts).
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
    cash_rate = float(c.get('cash_yield_rate', 0.0) or 0.0)
    if not isfinite(cash_rate):
        cash_rate = 0.0
    # Dividends/interest not reinvested never leave the account — they convert
    # to cash sitting inside it, which then only earns cash_rate going forward
    # instead of the account's full return. That cash persists indefinitely
    # (it doesn't get swept back into the holding even if the toggle later
    # switches back to reinvest); a private sub-balance tracked on `balances`
    # is the only place this is recorded — the account's total balance stays
    # the single source of truth everywhere else.
    cash_subbal = balances.setdefault('_dividend_cash_subbalance', {})

    for acct in investable_account_ids(c):
        before = float(balances.get(acct, 0.0) or 0.0)
        rate = _account_return(c, acct, default_return, year=year)
        yinfo = (c.get('account_taxable_income_assumptions') or {}).get(acct, {})
        distribution_yield = 0.0
        reinvest = True
        if c.get('portfolio_income_reduces_growth', True):
            try:
                distribution_yield = float(yinfo.get('total_distribution_yield', 0.0) or 0.0)
                reinvest = bool(yinfo.get('reinvest_dividends', False))
            except Exception:
                distribution_yield = 0.0
                reinvest = True
        # A mid-year withdrawal can shrink the account below its carried cash
        # sub-balance; cash is drawn down first (it's the liquid part).
        acct_cash = min(float(cash_subbal.get(acct, 0.0) or 0.0), before)
        invested_before = max(0.0, before - acct_cash)
        if distribution_yield > 0.0 and not reinvest:
            price_rate = rate - distribution_yield
            new_cash = invested_before * distribution_yield
            invested_growth = invested_before * price_rate
        else:
            new_cash = 0.0
            invested_growth = invested_before * rate
        cash_growth = acct_cash * cash_rate
        acct_cash = acct_cash + cash_growth + new_cash
        growth = invested_growth + cash_growth + new_cash
        after = before + growth
        if not isfinite(after):
            warnings.append(f"Non-finite growth result for {acct}; balance left unchanged")
            continue
        balances[acct] = after
        cash_subbal[acct] = acct_cash
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
from typing import Dict, Iterable, List, Optional


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


def _account_titling(c: Mapping, account_id: str) -> dict:
    """Explicit per-account titling, defaulting joint accounts to JTWROS.

    Finding F8 (item 2.7): an account with no explicit titling on file used
    to fall straight through to the household-wide property_regime default
    via ``_basis_step_fraction_for_death``, which returns 1.0 (a full
    step-up) for common-law-state first deaths. Combined with
    ``core._infer_owner`` assigning every joint/household-named account
    wholesale to member_1, this produced an asymmetric step-up outcome
    depending on which spouse happened to die first, even though the
    account is genuinely jointly held. An account this codebase infers as
    joint/household-named (``infer_member_role(account_id) == 'household'``)
    now defaults to JTWROS (50/50) titling absent an explicit override,
    matching how such accounts are actually owned; an explicit titling
    record on file still takes precedence.
    """
    explicit = (c.get('account_titling') or {}).get(account_id)
    if explicit:
        return explicit
    from .person_labels import infer_member_role
    if infer_member_role(account_id) == 'household':
        return {'titling': 'JTWROS'}
    return {}


def _account_basis_step_fraction(c: Mapping, account_id: str, first_death: bool = True) -> float:
    """Item 4.7 (P8): per-account titling overrides the household-wide
    property_regime default (_basis_step_fraction_for_death) for the fraction
    of a DECEASED owner's own account that receives a fresh §1014 basis.

    - COMMUNITY_PROPERTY: both halves are already the decedent's for basis
      purposes (the "double step-up") -> 1.0, regardless of the household
      default (an account can be titled community property even in a
      common-law-state household, or vice versa).
    - JTWROS / TENANTS_IN_COMMON: only the decedent's own share (typically
      half) was really theirs; the survivor's pre-existing share keeps its
      old basis -> 0.5. The household-level model previously stepped up the
      WHOLE account for any jointly-titled asset, overstating the step-up.
    - SEPARATE_PROPERTY: an explicit "this is solely the decedent's own
      asset" designation -> full step-up on their own basis (1.0) regardless
      of what the household's community-property default would otherwise
      apply — this is the mechanism behind the audit flag for a
      community-property asset titled to defeat the double step-up.
    - Blank / INDIVIDUAL / TRUST_TITLED / TOD_POD / anything else: no
      per-account override on file -> fall back to the existing
      household-level default, unchanged from pre-4.7 behavior.
    """
    titling = str(_account_titling(c, account_id).get('titling') or '').strip().upper()
    if titling == 'COMMUNITY_PROPERTY':
        return 1.0
    if titling in {'JTWROS', 'TENANTS_IN_COMMON'}:
        return 0.5
    if titling == 'SEPARATE_PROPERTY':
        return 1.0
    return _basis_step_fraction_for_death(c, first_death=first_death)


def _survivor_bonus_step_fraction(c: Mapping, account_id: str) -> float:
    """Item 4.7 (P8): per-account version of the "does the surviving spouse's
    OWN taxable account also get a step-up at the first death" community-
    property bonus (previously gated only on the household-wide regime).

    An account explicitly titled COMMUNITY_PROPERTY gets the bonus even if
    the household default is COMMON_LAW; one titled SEPARATE_PROPERTY does
    NOT get it even if the household default is COMMUNITY_PROPERTY. No
    per-account titling on file falls back to the household default,
    unchanged from pre-4.7 behavior.
    """
    titling = str(_account_titling(c, account_id).get('titling') or '').strip().upper()
    if titling == 'COMMUNITY_PROPERTY':
        return 1.0
    if titling == 'SEPARATE_PROPERTY':
        return 0.0
    if titling in {'JTWROS', 'TENANTS_IN_COMMON'}:
        # WI-025 / FIN-010: a jointly held account (explicit JTWROS, or the default
        # titling of a joint/household-named account) gets a half step-up on the
        # decedent's share whichever spouse dies first. The deceased-side logic
        # (_account_basis_step_fraction) already returns 0.5; the survivor-owned
        # side used to fall through to the household regime (0 under common law),
        # so the step-up depended on which spouse happened to die first.
        return 0.5
    regime = str(c.get('basis_step_up_property_regime', 'COMMON_LAW') or 'COMMON_LAW').strip().upper()
    return 1.0 if regime in {'COMMUNITY_PROPERTY', 'FULL_STEP_UP'} else 0.0


# Item 4.7 (P8): the nine community-property states among the eleven this
# build models state tax for (item 4.6's decision record keeps the modeled
# set at eleven; this list is only used to phrase an audit prompt, never to
# gate a calculation).
_COMMUNITY_PROPERTY_STATES = {'California', 'Arizona', 'Nevada', 'Texas'}


def beneficiary_titling_audit(c: Mapping) -> list:
    """Item 4.7 (P8): review prompts, not verdicts, on account beneficiary/
    titling data (c['account_titling'], keyed by account_registry id).

    Each finding is {'account_id', 'label', 'flag', 'prompt'} — a question
    for the advisor to raise with the client, not an assertion that anything
    is wrong. An account absent from account_titling entirely produces no
    findings (nothing on file to review yet, not "passed").
    """
    registry = c.get('account_registry', []) or []
    titling_map = c.get('account_titling') or {}
    former_spouse = str(c.get('former_spouse_name') or '').strip().lower()
    estate_objective = str(c.get('estate_tax_objective_mode', 'BALANCED') or 'BALANCED').strip().upper()
    state = str(c.get('state', '') or '')
    household_regime = str(c.get('basis_step_up_property_regime', 'COMMON_LAW') or 'COMMON_LAW').strip().upper()
    # Wave 5 item W5-1 (finding N4, 2026-09-08 planner sign-off): a >10-year
    # spousal age gap with no titling on file no longer silently assumes
    # Joint Life relief (see _spouse_is_sole_beneficiary) -- flag it here
    # instead, so the household/advisor can make the designation explicit
    # rather than lose the relief silently. Age gap is birth-year-invariant,
    # so no projection year is needed.
    h_dob = int(c.get('h_dob_yr', 0) or 0)
    w_dob = int(c.get('w_dob_yr', 0) or 0)
    age_gap_qualifies = bool(h_dob and w_dob and abs(h_dob - w_dob) > 10)
    spouse_name_by_owner = {0: str(c.get('w_name') or ''), 1: str(c.get('h_name') or '')}

    findings = []
    for acct in registry:
        aid = acct.get('id')
        entry = titling_map.get(aid)
        if not entry:
            if age_gap_qualifies and acct.get('rmd') and acct.get('tax') in {'pre_tax'}:
                owner_idx = acct.get('owner_idx')
                spouse_name = spouse_name_by_owner.get(owner_idx, '')
                if not _spouse_is_sole_beneficiary(c, [aid], spouse_name):
                    label = acct.get('label') or aid
                    findings.append((aid, label, 'joint_life_relief_unconfirmed',
                                      'This account has a >10-year spousal age gap that could qualify for '
                                      'the more favorable IRS Table II (Joint and Last Survivor) RMD divisor, '
                                      'but no beneficiary titling is on file, so RMDs are computed under the '
                                      'standard Uniform Lifetime table instead. If the spouse is intended to '
                                      'be the sole primary beneficiary, record that titling to apply the '
                                      'larger divisor (lower RMDs); if not, no action is needed.'))
            continue
        label = acct.get('label') or aid
        tax = acct.get('tax')
        primary = str(entry.get('primary_beneficiary') or '').strip()
        contingent = str(entry.get('contingent_beneficiary') or '').strip()
        titling = str(entry.get('titling') or '').strip().upper()
        primary_low = primary.lower()
        contingent_low = contingent.lower()

        if tax in {'pre_tax', 'roth'} and not primary:
            findings.append((aid, label, 'estate_named_by_default',
                              'No primary beneficiary on file for this retirement account. Most custodial '
                              'agreements name "the estate" by default when none is designated — confirm '
                              'that is really the intended recipient (it forces probate and loses the '
                              'non-spouse beneficiary\'s stretch/10-year flexibility).'))
        elif primary and not contingent:
            findings.append((aid, label, 'no_contingent',
                              'Primary beneficiary is on file with no contingent beneficiary. Confirm what '
                              'happens if the primary predeceases the client or disclaims.'))

        if former_spouse and (former_spouse in primary_low or former_spouse in contingent_low):
            findings.append((aid, label, 'ex_spouse_named',
                              f'A name matching the configured former spouse ({c.get("former_spouse_name")}) '
                              'still appears as a beneficiary. Beneficiary designations are not automatically '
                              'revoked by divorce in every state — confirm this is intentional.'))

        if '(minor)' in primary_low or '(minor)' in contingent_low:
            has_wrapper = ('utma' in primary_low or 'ugma' in primary_low or 'trust' in primary_low
                           or 'utma' in contingent_low or 'ugma' in contingent_low or 'trust' in contingent_low)
            if not has_wrapper:
                findings.append((aid, label, 'minor_named_outright',
                                  'A beneficiary flagged (minor) appears to be named outright, with no UTMA/UGMA '
                                  'custodianship or trust wrapper on file. A minor cannot directly receive '
                                  'account assets — confirm a guardianship/custodial mechanism is in place.'))

        if tax in {'pre_tax', 'roth'} and 'trust' in (primary_low + ' ' + contingent_low) and not entry.get('trust_see_through'):
            findings.append((aid, label, 'trust_no_see_through',
                              'A trust appears to be named as beneficiary of this retirement account, but '
                              'trust_see_through is not marked TRUE. Confirm the trust qualifies as a '
                              '"see-through" trust (IRS Treas. Reg. 1.401(a)(9)-4) — otherwise the account may '
                              'be forced onto the fastest available distribution schedule.'))

        if titling == 'JTWROS' and estate_objective not in {'OFF', 'MONITOR_ONLY'}:
            findings.append((aid, label, 'jtwros_defeats_credit_shelter',
                              'This account is titled JTWROS, which passes directly to the survivor by '
                              'operation of law outside probate — bypassing any credit-shelter/bypass trust '
                              'the estate plan (estate_tax_objective_mode is not OFF) may be relying on. '
                              'Confirm this titling is intentional.'))

        if titling == 'SEPARATE_PROPERTY' and (household_regime in {'COMMUNITY_PROPERTY', 'FULL_STEP_UP'}
                                                or state in _COMMUNITY_PROPERTY_STATES):
            findings.append((aid, label, 'community_property_defeated',
                              f'This account is titled separate property in a household whose state ({state}) '
                              'or configured regime treats assets as community property elsewhere. Separate-'
                              'property titling forgoes the community-property "double step-up" on this '
                              'specific account at the first death — confirm that trade-off is intentional.'))

    return findings


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

    # member_1 death this year.
    _nick1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _nick2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    if year == h_death:
        deceased, survivor = 0, 1
        first_death = w_alive and h_death < w_death
        second_death = h_death > w_death
        label = _nick1
        survivor_label = _nick2
    else:
        deceased, survivor = 1, 0
        first_death = h_alive and w_death < h_death
        second_death = w_death > h_death
        label = _nick2
        survivor_label = _nick1

    result.deceased_owner_idx = deceased
    result.survivor_owner_idx = survivor if first_death else None

    if first_death:
        result.description = f'{label} → {survivor_label} (spousal rollover)'
        if basis_free is not None and c.get('basis_step_up_at_death', True):
            for _acct in _accounts_by_owner(registry, survivor):
                if _acct.get('tax') == 'taxable':
                    # Item 4.7 (P8): per-account titling (community property vs
                    # separate property) drives whether the SURVIVOR's own
                    # account also gets the community-property "double
                    # step-up" bonus, instead of one household-wide regime.
                    _bonus_frac = _survivor_bonus_step_fraction(c, _acct['id'])
                    if _bonus_frac > 0:
                        basis_free[_acct['id']] = max(float(basis_free.get(_acct['id'], 0.0) or 0.0), float(balance.get(_acct['id'], 0.0) or 0.0) * _bonus_frac)
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
                # gain-bearing lots in later survivor years. Item 4.7: titling
                # drives this per account instead of one household regime.
                _step_frac = _account_basis_step_fraction(c, acct['id'], first_death=True)
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

_MORTALITY_TABLE_CACHE = None


def _mortality_qx_table():
    """Load the reference mortality table (reference.db), cached for the process.

    {age: (male_qx, female_qx)}, ages 18-119. See the table's notes column
    for provenance: SSA Actuarial Study No. 124 anchors at 5-year ages,
    log-linearly interpolated/extrapolated to single-year granularity.
    System review C4 (mortality-gaussian-not-life-table).
    """
    global _MORTALITY_TABLE_CACHE
    if _MORTALITY_TABLE_CACHE is not None:
        return _MORTALITY_TABLE_CACHE
    from .stores.ref_getters.mortality_real_loss import mortality_qx_table
    _MORTALITY_TABLE_CACHE = mortality_qx_table()
    return _MORTALITY_TABLE_CACHE


def _mortality_qx(age: int, sex_idx: int) -> float:
    table = _mortality_qx_table()
    if not table:
        return 1.0 if age >= 110 else 0.01  # degrades to "eventually dies" if the table is empty
    ages = sorted(table.keys())
    clamped = max(ages[0], min(ages[-1], int(age)))
    return table[clamped][sex_idx]


def _population_median_age(sex_idx: int) -> float:
    """Age at which unconditional survival from the table's first age crosses 50%."""
    table = _mortality_qx_table()
    if not table:
        return 80.0
    ages = sorted(table.keys())
    survival = 1.0
    for age in ages:
        survival *= (1.0 - table[age][sex_idx])
        if survival <= 0.5:
            return float(age)
    return float(ages[-1])


def _age_shift_for_member(m: Mapping, sex_idx: int) -> float:
    """Calibrate the population table to this household member's own assumed
    median lifespan (c[..._mort_age]), preserving the user's own longevity
    input while replacing the age-varying SHAPE of the hazard curve -- the
    actual defect: the old model had near-zero probability of death before
    80 and exactly zero below 70, regardless of what the user configured."""
    configured_median = float(m.get('mortality_age', 92) or 92)
    return configured_median - _population_median_age(sex_idx)


def sample_death_year(c: Mapping, owner_idx: int, rng: random.Random) -> int:
    members = c.get('members') or []
    if owner_idx >= len(members):
        return int(c.get('plan_start', 0))
    m = members[owner_idx]
    dob = int(m.get('dob_yr', c.get('h_dob_yr', 1960)))
    sex_idx = 0 if owner_idx == 0 else 1  # h=male col, w=female col by registry convention
    shift = _age_shift_for_member(m, sex_idx)
    plan_start = int(c.get('plan_start', dob + 60) or dob + 60)
    current_age = max(18, plan_start - dob)
    age = current_age
    # Year-by-year Bernoulli survival trial from the household's current age,
    # using the shifted table so the shape is age-realistic (rising hazard,
    # not a symmetric bell curve) while the calibrated median still matches
    # the user's own mortality_age assumption.
    while age < 119:
        qx = _mortality_qx(age - shift, sex_idx)
        if rng.random() < qx:
            return dob + age
        age += 1
    return dob + 119


def sample_household_death_years(c: Mapping, rng: random.Random) -> dict:
    h = sample_death_year(c, 0, rng)
    if len(c.get('members') or []) > 1:
        w = sample_death_year(c, 1, rng)
    else:
        w = int(c.get('w_death_yr', h))
    # Adjacent fix found while implementing Phase 1 items 4-6: without this,
    # every scalar MC path left first_death_yr at the base config's stale
    # value (or 0), so deterministic_engine.py's Qualifying-Surviving-Spouse
    # 2-year MFJ-extension window (gated on qss_dependent) was timed off the
    # wrong year for every qss_dependent=True path. The primary MFJ->single
    # filing-status switch is unaffected (it keys off h_death_yr/w_death_yr
    # directly, not first_death_yr).
    return {'h_death_yr': h, 'w_death_yr': w, 'first_death_yr': min(h, w), 'plan_end': max(h, w)}

# ===== END mortality_engine.py =====


# ===== BEGIN withdrawal_engine.py =====

"""Withdrawal, RMD, and cash-gap helpers for the retirement projection engine.

The functions in this module are intentionally small and side-effect-light:
most mutate only the provided balance dictionary and return a structured
result dict. This makes the projection engine easier to
stabilize before a full projection-engine extraction.
"""


from typing import Callable, MutableMapping, Sequence
from .plan_config import ensure_engine_config

from . import core as _ar  # consolidated from account_registry
from . import tax_kernel as _tk


BalanceMap = MutableMapping[str, float]


def _rmd_divisor_with_table_override(age: int | float, table: Mapping[int, float] | None = None,
                 spouse_age: int | float | None = None,
                 sole_beneficiary_spouse: bool = False) -> float:
    """Return the RMD divisor for an age: SECURE 2.0 Uniform Lifetime by
    default, or IRS Table II (Joint and Last Survivor) when
    `sole_beneficiary_spouse` is true and the spouse is more than 10 years
    younger (finding F10 / item 2.9) -- the Uniform Lifetime table alone
    understates the RMD reduction available in that case.

    `table` is injectable so build_workbook can keep its current source of
    truth while tests can exercise this helper independently; it only
    overrides the Uniform Lifetime lookup, not the Joint Life table.

    Wave 5 item W5-2 (finding N5): delegates to the single canonical
    implementation in `tax_kernel.rmd_divisor` -- see that function's
    docstring for why this used to disagree with `core.rmd_divisor` for
    fractional ages.
    """
    from .tax_kernel import rmd_divisor as _tk_rmd_divisor
    return _tk_rmd_divisor(age, spouse_age=spouse_age,
                            sole_beneficiary_spouse=sole_beneficiary_spouse, table=table)


def _spouse_is_sole_beneficiary(c: Mapping, ids: Sequence[str], spouse_name: str) -> bool:
    """True only if per-account titling data EXPLICITLY names the spouse as
    sole primary beneficiary for at least one of this owner's RMD-eligible
    accounts, with none of them naming anyone else.

    Finding N4 / Wave 5 item W5-1 (2026-09-08, explicit planner sign-off):
    inverts item 2.9's original "automatic detection via titling plus an
    age-gap fallback." That fallback assumed the spouse was the beneficiary
    whenever no titling record existed at all, which silently OVERSTATED
    Joint Life relief (understating RMDs, and understating the value of
    Roth conversions) for any household with a qualifying age gap and no
    titling on file -- the opposite-directional twin of item 2.9's own
    original overstatement bug. The household must now have an explicit
    record naming the spouse for this relief to apply; silence (no titling
    record at all) now defaults to the standard, more conservative Uniform
    Lifetime table, the same as an explicit record naming someone else
    already did. See beneficiary_titling_audit()'s 'joint_life_relief_
    unconfirmed' finding, which flags exactly this silent-default case for
    the advisor/household to resolve explicitly.
    """
    titling = c.get('account_titling') or {}
    spouse_l = str(spouse_name or '').strip().lower()
    explicit_spouse_designation = False
    for aid in ids:
        rec = titling.get(aid)
        if not rec:
            continue
        ben = str(rec.get('primary_beneficiary') or '').strip().lower()
        if not ben:
            continue
        if 'spouse' in ben or (spouse_l and spouse_l in ben):
            explicit_spouse_designation = True
            continue
        return False
    return explicit_spouse_designation


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
    """Compute household RMD obligations from registry-defined RMD accounts.

    Item 175: This RMD base is built ONLY from liquid IRA/401k/403b/SEP
    registry account balances (`_ar.rmd_ids_by_owner`). Qualified/annuitized
    income streams (pension, joint/single-life annuities funded from an IRA,
    etc.) are modeled separately as their own contracts and are intentionally
    NOT aggregated into this aggregate IRA RMD base. A separately annuitized
    qualified contract self-satisfies its own RMD through its periodic
    payments under Treas. Reg. 1.401(a)(9)-6 (annuitized contracts are carved
    out of the account-balance aggregation rule in Treas. Reg.
    1.408-8, A-9 / 1.401(a)(9)-8), so folding the annuity's value into this
    aggregate base would double-count that RMD requirement. Keep this
    separation when modifying account-registry inclusion logic.

    #295: a funded QLAC is the SAME carve-out under the SAME regulation, but
    applies before the QLAC itself starts paying income (that's the whole
    point of a QLAC -- deferred income with no RMD due on the deferred
    premium). _ar.qlac_excluded_rmd_balance() subtracts the (capped) premium
    from this owner's balance base; the dollars stay in the account for
    growth/withdrawal purposes elsewhere, only the RMD divisor's numerator
    shrinks.
    """
    divisor_fn = divisor_fn or rmd_divisor
    registry = c.get("account_registry", [])
    start_age_default = int(c.get("rmd_start_age", 75))
    start_ages = {
        0: int(c.get("h_rmd_start_age", start_age_default) or start_age_default),
        1: int(c.get("w_rmd_start_age", start_age_default) or start_age_default),
    }
    # F10 / item 2.9: the spouse's age and name for the Joint Life table gate
    # -- owner_idx 0 (h)'s spouse is w and vice versa.
    spouse_age_of = {0: w_age, 1: h_age}
    spouse_alive_of = {0: w_alive, 1: h_alive}
    spouse_name_of = {0: c.get("w_name", ""), 1: c.get("h_name", "")}
    by_owner: Dict[int, Dict] = {}

    for owner_idx, age, alive in ((0, h_age, h_alive), (1, w_age, w_alive)):
        ids = _ar.rmd_ids_by_owner(registry, owner_idx)
        total_bal = _ar.sum_bal(bal, ids) - _ar.qlac_excluded_rmd_balance(c, owner_idx, year)
        total_bal = max(0.0, total_bal)
        start_age = start_ages.get(owner_idx, start_age_default)
        sole_spouse = bool(spouse_alive_of[owner_idx]) and _spouse_is_sole_beneficiary(
            c, ids, spouse_name_of[owner_idx])
        try:
            divisor = divisor_fn(age, spouse_age=spouse_age_of[owner_idx],
                                  sole_beneficiary_spouse=sole_spouse) if alive and age >= start_age else 0.0
        except TypeError:
            # A caller-supplied divisor_fn (e.g. in tests) may not accept
            # the newer keyword arguments -- fall back to the plain call
            # rather than breaking existing single-arg callables.
            divisor = divisor_fn(age) if alive and age >= start_age else 0.0
        # Wave 5 item W5-9 (finding N6): the RMD is a statutory requirement
        # with no de-minimis exception -- a prior `total_bal > 500` gate here
        # was an undocumented magic number with no basis in 26 U.S.C. 401(a)
        # (9) or its regulations. Removed; the only real floor is a zero/
        # negative balance, which naturally produces a zero RMD via the
        # division below regardless.
        amount = max(0.0, total_bal / divisor) if divisor and total_bal > 0 else 0.0
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


def hsa_available_to_draw(c: Mapping, bal: BalanceMap, cumulative_drawn: float = 0.0,
                          year: int = 0, spend_floor_base: float = 0.0) -> float:
    """Dollars the HSA can pay out tax-free right now.

    Bounded by three separate things, which compose in a specific order:

    * the account balances;
    * any liquidity reserve configured against the HSA bucket, which reserves
      *balance* -- dollars that must stay in the account;
    * the substantiated expense bank, which caps *tax-free capacity* rather
      than balance. A bank of None means unlimited, which is the default: most
      households have far more unreimbursed receipts than they realize, and the
      constraint only binds once someone actually enters a figure.

    The floor is therefore subtracted from the balance and the bank applied to
    the remainder -- never the reverse, which would charge the reserve against
    the bank as well and zero out draws the household can legitimately take
    (500k balance, 100k bank, 200k floor leaves 100k drawable, not nothing).

    ``year`` and ``spend_floor_base`` default to an inert (no reserve) view so
    existing callers are unchanged; pass both to honor a configured reserve.
    """
    ids = list(c.get("hsa_ids", []) or [])
    balance = sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in ids)
    above_floor = max(0.0, balance - liquidity_reserve_floor(c, year, "hsa", spend_floor_base))
    bank = c.get("hsa_expense_bank")
    if bank is None:
        return above_floor
    bank_remaining = float(bank) - max(0.0, float(cumulative_drawn))
    return max(0.0, min(bank_remaining, above_floor))


def withdraw_hsa_window(c: Mapping, bal: BalanceMap, year: int, wellness_cost: float = 0.0,
                        requested: float | None = None, cumulative_drawn: float = 0.0,
                        spend_floor_base: float = 0.0,
                        hsa_owner_age: float | None = None) -> Dict:
    """Apply scheduled HSA withdrawals across all registry HSA accounts.

    In ``spend_as_needed`` mode the HSA historically paid only that year's
    wellness cost, which throttles the account to one calendar year of medical
    spending even when the household holds a deep bank of substantiated
    receipts. Passing ``requested`` asks for a general tax-free draw instead;
    it is bounded by :func:`hsa_available_to_draw` (balances and expense bank)
    and by any liquidity reserve configured against the HSA bucket. Callers
    that pass no ``requested`` keep the legacy wellness-linked behavior
    exactly. ``annual_pct`` and ``smooth_window`` are unaffected.

    Obligation: passing ``requested`` discards ``wellness_cost`` entirely -- the
    requested figure becomes the whole draw. A caller that supplies
    ``requested`` must therefore fold the year's medical spend into it, or the
    wellness cost stops being paid from the HSA.

    ``hsa_owner_age`` is the HSA owner's age in ``year``. It has no silent
    default: when ``hsa_nonqualified_treatment='allow_taxable'`` actually
    produces non-qualified dollars and no age was supplied, this raises rather
    than quietly assuming 65 and reporting no penalty. A defaulted age is a
    fail-open on a penalty, and this repo has shipped enough guards that could
    not fail. Callers pass the age explicitly, the way ``h_age``/``w_age`` are
    threaded elsewhere.

    Known limitation, deliberately not solved here: a single scalar age cannot
    represent a household holding two HSAs with different owners.
    ``_draw_pro_rata_accounts`` splits the draw across every id in ``hsa_ids``,
    but the 20% pre-65 penalty is assessed per owner, so a mixed-age couple
    needs a per-account age and a per-account penalty split. Wiring the caller
    is the place to fix that.
    """
    mode = str(c.get("hsa_withdrawal_mode", "spend_as_needed") or "spend_as_needed").lower()
    if mode == "spend_as_needed":
        # Draw HSA to cover wellness costs (tax-free qualified medical use), or
        # the explicitly requested general draw when the caller supplies one.
        ids = list(c.get("hsa_ids", []) or [])
        target = float(wellness_cost) if requested is None else max(0.0, float(requested))
        if not ids or target <= 1e-6:
            return {"amount": 0.0, "by_account": {}, "taxable_amount": 0.0, "penalty": 0.0}
        if requested is None:
            qualified_available = sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in ids)
            available = qualified_available
        else:
            # A reserve held in the HSA bucket must survive the general draw;
            # otherwise the floor honored in withdraw_hsa_gap arrives too late.
            # The helper composes the floor and the bank correctly.
            qualified_available = hsa_available_to_draw(c, bal, cumulative_drawn, year, spend_floor_base)
            treatment = str(c.get("hsa_nonqualified_treatment", "block") or "block").strip().lower()
            if treatment == "allow_taxable":
                # Non-qualified dollars beyond the substantiated bank are still
                # permitted -- as taxable income, possibly penalized -- but the
                # liquidity-reserve floor is never bypassed, only the bank is.
                # Re-use the same helper with the bank lifted so the floor
                # composition isn't duplicated here.
                available = hsa_available_to_draw(
                    dict(c, hsa_expense_bank=None), bal, cumulative_drawn, year, spend_floor_base)
            else:
                available = qualified_available
        amount = min(target, available)
        if amount <= 1e-6:
            return {"amount": 0.0, "by_account": {}, "taxable_amount": 0.0, "penalty": 0.0}
        by_account = _draw_pro_rata_accounts(bal, ids, amount)
        drawn = sum(by_account.values())
        taxable_amount = 0.0
        penalty = 0.0
        if requested is not None:
            taxable_amount = max(0.0, drawn - qualified_available)
            if taxable_amount > 1e-9:
                if hsa_owner_age is None:
                    raise ValueError(
                        "withdraw_hsa_window: hsa_nonqualified_treatment='allow_taxable' "
                        f"produced {taxable_amount:,.2f} of non-qualified withdrawal, but no "
                        "hsa_owner_age was supplied. The 20% pre-65 penalty cannot be assessed "
                        "without the owner's age, and defaulting the age would silently report "
                        "no penalty. Pass hsa_owner_age explicitly.")
                if float(hsa_owner_age) < 65:
                    penalty = taxable_amount * 0.20
        return {"amount": drawn, "by_account": by_account,
                "taxable_amount": taxable_amount, "penalty": penalty}
    if mode == "optimize":
        # Item 291-adjacent wiring (2026-08-19): resolve_year_amount's
        # precedence ladder (override > locked > optimizer > mode), applied
        # to whatever row client_hsa_schedule.csv has for this year. There is
        # no automatic search yet (see hsa_schedule.py's module docstring),
        # so optimizer_amount is only ever populated by a user's own entry --
        # 'optimizer'/'locked' sources are therefore currently unreachable in
        # practice, not dead code; they activate the moment something writes
        # optimizer_amount.
        from .hsa_schedule import resolve_year_amount
        row = c.get("hsa_schedule_by_year", {}).get(year)
        resolved_amount, source = resolve_year_amount(row or {})
        ids = list(c.get("hsa_ids", []))
        total = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in ids)
        if source != "mode":
            amount = max(0.0, min(resolved_amount, total))
        elif total > 0:
            # No schedule entry for this year: level the remaining balance
            # over what's left of the plan horizon. This is a simple,
            # conservative stand-in -- not the schedule search's own
            # mortality-percentile deadline (resolve_consume_by_year), which
            # needs the full projection row list this per-year call does not
            # have. Matches smooth_window's own math below, just without a
            # configured window.
            plan_end = int(c.get("plan_end", year) or year)
            years_remaining = max(1, plan_end - year + 1)
            amount = total / years_remaining
        else:
            amount = 0.0
        by_account: Dict[str, float] = {}
        if amount > 0 and total > 0:
            for aid in ids:
                before = max(0.0, float(bal.get(aid, 0.0)))
                draw = amount * before / total
                bal[aid] = max(0.0, before - draw)
                by_account[aid] = draw
        return {"amount": amount, "by_account": by_account}

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


def hsa_unscheduled_draw_allowed(c: Mapping, year: int = 0) -> bool:
    """Whether an UNSCHEDULED HSA draw may run in ``year``, given the
    household's ``hsa_withdrawal_mode``.

    Extracted from ``withdraw_hsa_gap`` so that every unscheduled-draw site
    shares one predicate. There is now a second such site --
    ``fund_contingent_liability_from_hsa`` -- and a copied-and-drifted rule
    here is exactly the failure this function exists to prevent: the
    2026-08-20 defect below was a mode that had simply never been added to
    one of these checks.

    The rule, unchanged from ``withdraw_hsa_gap``'s original inline form:

    * ``optimize`` -- suppressed unconditionally. The schedule
      (``client_hsa_schedule.csv`` via ``resolve_year_amount``) is the sole
      authority on the year's draw, and unlike the window modes it has no
      win_start/win_end pair to scope a suppression to.
    * ``smooth_window`` / ``annual_pct`` -- suppressed before and during the
      configured window, where ``withdraw_hsa_window`` already handles the
      scheduled draw. Permitted after the window ends, when any remaining
      balance is fair game.
    * ``spend_as_needed`` -- always permitted; there is no schedule to
      conflict with.

    ``year=0`` (the parameter default, used by callers that do not thread a
    year) skips the window comparison entirely, preserving the original
    behavior exactly -- a window check against year 0 would otherwise
    suppress every such call.
    """
    mode = str(c.get("hsa_withdrawal_mode", "spend_as_needed") or "spend_as_needed").lower()
    if mode == "optimize":
        return False
    if mode in ("smooth_window", "annual_pct") and year > 0:
        win_start = int(c.get("hsa_win_start", 9999))
        win_end = int(c.get("hsa_win_end", 0))
        if year < win_start or (win_end > 0 and year <= win_end):
            return False
    return True


def fund_contingent_liability_from_hsa(c: Mapping, bal: BalanceMap,
                                        ltc_prem_yr: float = 0.0,
                                        wellness_shock_yr: float = 0.0,
                                        year: int = 0,
                                        spend_floor_base: float = 0.0) -> Dict:
    """Optimization refactor: fund contingent-liability spending from the HSA
    first, ahead of the ordinary withdrawal cascade.

    ``contingent_liability`` (the SPENDING_TIERS tier in
    ``spending_budget_resolver.py``) is ``ltc_prem_yr + wellness_shock_yr`` --
    an LTC insurance premium and a sampled major-medical/LTC shock. Until
    now neither had ANY dedicated funding treatment: both were summed into
    ``total_spend_need`` and funded by whatever the cascade reached first.
    In particular the scheduled HSA draw does not cover them --
    ``deterministic_engine`` calls ``withdraw_hsa_window`` with
    ``wellness_cost=row['wellness_base_yr']``, which is
    ``wellness_premium_yr + wellness_detail_budget_yr`` and excludes both of
    these components.

    That left the one account designed for medical costs funding them only
    incidentally. Both components are qualified medical expenses (LTC
    premiums up to the IRS age-based limits; medical/LTC shocks outright),
    so HSA dollars spent on them are tax-free out -- which is why this draw
    needs no ``hsa_owner_age``/penalty plumbing the way
    ``withdraw_hsa_window``'s general ``requested`` path does: a qualified
    draw can never produce the non-qualified dollars that carry the pre-65
    20% penalty.

    Bounded by the HSA balance net of any liquidity reserve configured
    against the HSA bucket (P8's ``liquidity_reserve_floor``), matching
    ``withdraw_hsa_gap``. Gated by ``hsa_unscheduled_draw_allowed`` -- a
    household that configured a scheduled drawdown mode keeps that schedule
    as the sole authority on the year's draw; see that function for why.

    Returns ``amount`` drawn, ``by_account``, and ``residual`` -- the
    contingent-liability dollars this draw could not cover, which simply
    remain in the caller's cash gap and fall through the existing cascade
    unchanged.
    """
    need = max(0.0, float(ltc_prem_yr or 0.0)) + max(0.0, float(wellness_shock_yr or 0.0))
    if need <= 1e-6:
        return {"amount": 0.0, "by_account": {}, "residual": 0.0}
    unfunded = {"amount": 0.0, "by_account": {}, "residual": need}
    if not hsa_unscheduled_draw_allowed(c, year):
        return unfunded
    ids = list(c.get("hsa_ids", []) or [])
    if not ids:
        return unfunded
    # hsa_available_to_draw composes the liquidity-reserve floor and the
    # substantiated-expense bank correctly (floor first, bank against the
    # remainder) -- see its docstring. Both this function and
    # withdraw_hsa_gap draw only qualified dollars by construction, so the
    # bank cap applies outright; there is no non-qualified overflow to
    # convert to taxable income the way withdraw_hsa_window's requested path
    # can.
    amount = min(need, hsa_available_to_draw(c, bal, 0.0, year, spend_floor_base))
    if amount <= 1e-6:
        return unfunded
    by_account = _draw_pro_rata_accounts(bal, ids, amount)
    drawn = sum(by_account.values())
    return {"amount": drawn, "by_account": by_account, "residual": max(0.0, need - drawn)}


def withdraw_hsa_gap(c: Mapping, bal: BalanceMap, gap: float, year: int = 0,
                     spend_floor_base: float = 0.0) -> Dict:
    """Use remaining HSA dollars for an unfunded spending gap before Roth.

    HSA is a non-Roth liquid bucket. The normal HSA window still controls the
    planned annual draw, but if IRA and taxable/trust dollars cannot fill the
    cash gap, this final pass prevents Roth withdrawals while HSA dollars remain.

    The mode gating -- suppressed unconditionally under optimize, and before
    and during the configured window under smooth_window/annual_pct -- now
    lives in ``hsa_unscheduled_draw_allowed``, shared with
    ``fund_contingent_liability_from_hsa``. See that function for the rule
    and its rationale.

    A real bug (2026-08-20) motivated that gating, and is why it is shared
    rather than duplicated: a user comparing a $2,000/year override entered
    via the UI against the resulting workbook found the entered amount never
    showed up and the account drained years before the household expected.
    This function's own docstring already explained why -- "allowing
    gap-fills on top would double-deplete the HSA" -- but 'optimize' had
    simply never been added to the check, so every year with any unfunded
    cash-flow gap silently topped up (or dwarfed) withdraw_hsa_window's
    scheduled/overridden draw with an unscheduled extra one.
    """
    if gap <= 1e-6:
        return {"amount": 0.0, "new_gap": gap, "by_account": {}}
    if not hsa_unscheduled_draw_allowed(c, year):
        return {"amount": 0.0, "new_gap": gap, "by_account": {}}
    ids = list(c.get("hsa_ids", []) or [])
    # hsa_available_to_draw composes the liquidity-reserve floor (P8) and the
    # substantiated-expense bank (floor first, bank against the remainder).
    # This draw is claimed tax-free like any other qualified HSA withdrawal,
    # so it draws down the same bank capacity Priority 1b does -- there is no
    # non-qualified overflow to convert to taxable income here either.
    amount = min(float(gap or 0.0), hsa_available_to_draw(c, bal, 0.0, year, spend_floor_base))
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
    spend_floor_base: float = 0.0,
) -> Dict:
    """Withdraw pre-tax dollars to fill a cash gap.

    The first elective pass is tax-sensitive and respects the configured
    bracket/IRMAA caps.  A later final-resort pass can call this with
    ``respect_tax_caps=False`` so Roth withdrawals never occur while pre-tax
    IRA/401(k) balances are still available.  This tax bucket is drawn
    pro-rata across husband/wife pre-tax accounts instead of exhausting one
    spouse/member first.

    ``new_gap`` is reduced by the full gross ``amount`` (matching
    ``withdraw_taxable_trust``'s convention), not by an assumed-flat-rate
    ``net_cash``. The caller is responsible for separately adding this
    withdrawal's real incremental tax back onto `gap` (see
    deterministic_engine.py's IRA elective tax true-up, which mirrors the
    LTCG/NIIT fixed-point pattern) — that keeps a single, real-tax-based
    accounting of the gap instead of mixing a flat-rate-haircut gap alongside
    a separately-tracked real-tax figure, which would double-book/mis-book
    the tax and leave the cash-bridge reconciliation off by the mismatch.
    """
    if gap <= 0:
        return {"amount": 0.0, "net_cash": 0.0, "new_gap": gap, "by_account": {}, "h_amount": 0.0, "w_amount": 0.0}
    max_taxable = max(0.0, min(bracket_top_24, irmaa_threshold) - agi)
    gross_up = gap / max(0.01, 1.0 - marginal_rate)
    registry = c.get("account_registry", [])
    h_ids = owner_account_ids(registry, 0, "pre_tax")
    w_ids = owner_account_ids(registry, 1, "pre_tax")
    pretax_ids = _owner_tax_ids_pro_rata_order(registry, "pre_tax")
    # A reserve configured against the IRA bucket holds pre-tax dollars back the
    # same way a taxable reserve holds taxable dollars back (P8). Applied before
    # the tax caps so the reserve is a hard floor, not a tax-sensitive one.
    available = max(0.0, sum(max(0.0, float(bal.get(aid, 0.0))) for aid in pretax_ids)
                    - liquidity_reserve_floor(c, year, "pretax", spend_floor_base))
    tax_cap = max_taxable if respect_tax_caps else available
    amount = min(gross_up, tax_cap, available)
    by_account = _draw_pro_rata_accounts(bal, pretax_ids, amount)
    h_amount = sum(by_account.get(aid, 0.0) for aid in h_ids)
    w_amount = sum(by_account.get(aid, 0.0) for aid in w_ids)
    net_cash = amount * max(0.0, 1.0 - marginal_rate)
    return {
        "amount": amount,
        "net_cash": net_cash,
        "new_gap": gap - amount,
        "by_account": by_account,
        "h_amount": h_amount,
        "w_amount": w_amount,
        "marginal_rate": marginal_rate,
        "max_taxable": max_taxable,
    }


# A Liquidity Buffer row's reserve_account names the bucket whose balance the
# reserve is meant to preserve. These are the choices offered by the UI and
# reference_src/schema.csv; anything unrecognized falls back to taxable, which
# is both the schema default and the behavior every plan had before the field
# was honored (P8).
LIQUIDITY_RESERVE_BUCKETS = {
    "taxable/trust": "taxable",
    "taxable": "taxable",
    "trust": "taxable",
    "roth": "roth",
    "ira": "pretax",
    "pretax": "pretax",
    "pre_tax": "pretax",
    "hsa": "hsa",
    "cash": "cash",
}
DEFAULT_LIQUIDITY_RESERVE_BUCKET = "taxable"


def liquidity_buffer_for_year(c: Mapping, year: int) -> tuple[float, str]:
    """Return (reserve years, reserve bucket) configured for the given year.

    Reserve rules are defined by start year, end year, years of expenses to
    retain, and the account bucket that reserve is meant to preserve. If rows
    overlap, the first matching schedule row wins. Missing configuration
    defaults to zero retained expense years against the taxable bucket.

    Until P8 the bucket half was parsed, stored, round-tripped by the UI and
    then ignored: the floor was applied to taxable/trust whatever the row said,
    so a user who selected "Cash" silently got taxable treatment.
    """
    def _bucket(rec: Mapping) -> str:
        raw = rec.get("reserve_account", rec.get("preserve_account", "")) or ""
        return LIQUIDITY_RESERVE_BUCKETS.get(str(raw).strip().lower(), DEFAULT_LIQUIDITY_RESERVE_BUCKET)

    for rec in c.get("liquidity_buffer_schedule", []) or []:
        try:
            start = int(rec.get("start_year", c.get("plan_start", year)) or c.get("plan_start", year))
            end = int(rec.get("end_year", 9999) or 9999)
            if start <= int(year) <= end:
                return float(rec.get("years_of_expenses", 0) or 0), _bucket(rec)
        except (TypeError, ValueError, AttributeError) as _exc:
            _log_fallback("liquidity_buffer_schedule.row", _exc, year=year)
            continue
    legacy = float(c.get('near_term_buffer_years', 0) if year <= c.get('near_term_buffer_end_year', c.get('plan_start', year)) else c.get('long_term_buffer_years', 0))
    return legacy, DEFAULT_LIQUIDITY_RESERVE_BUCKET


def liquidity_buffer_years_for_year(c: Mapping, year: int) -> float:
    """Return configured liquidity reserve years for the given year.

    Bucket-agnostic view of :func:`liquidity_buffer_for_year`, kept for callers
    that only need the magnitude.
    """
    return liquidity_buffer_for_year(c, year)[0]


def liquidity_reserve_floor(c: Mapping, year: int, bucket: str, spend_floor_base: float) -> float:
    """Dollar floor the configured reserve places under one bucket's balance.

    Returns 0.0 when no reserve applies this year, or when the reserve targets
    a different bucket -- a reserve held in Roth must not restrict the taxable
    draw, which is what made every reserve behave as a taxable reserve before.
    """
    years, reserve_bucket = liquidity_buffer_for_year(c, year)
    if years <= 0 or reserve_bucket != bucket:
        return 0.0
    return float(years) * max(0.0, float(spend_floor_base))


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
    floor = liquidity_reserve_floor(c, year, "taxable", spend_floor_base)
    amount = min(gap, max(0.0, total_taxable - floor))
    by_account = _draw_pro_rata_accounts(bal, taxable_ids, amount)
    return {
        "amount": sum(by_account.values()),
        "new_gap": gap - sum(by_account.values()),
        "by_account": by_account,
        "h_amount": sum(by_account.get(aid, 0.0) for aid in h_ids),
        "w_amount": sum(by_account.get(aid, 0.0) for aid in w_ids),
    }


def donate_taxable_in_kind(c: Mapping, bal: BalanceMap, year: int, amount: float,
                           spend_floor_base: float) -> Dict:
    """Transfer appreciated securities in kind out of the taxable accounts.

    This is not a withdrawal: no cash is produced, no gain is realized, and
    nothing funds household spending. Only the shares move.

    **Taxable accounts only, by law.** An IRA cannot make a qualified
    charitable distribution to a donor-advised fund -- IRC 408(d)(8)(B)(i)
    excludes DAFs from QCD treatment, and SECURE 2.0's one-time split-interest
    election excludes them too. A traditional IRA or 401(k) can of course be
    distributed and the cash donated, but that is ordinary income first and a
    deduction second: it is a *cash* contribution, already modeled by the
    ``daf_contribution_is_appreciated = False`` path, which the normal
    withdrawal waterfall funds from whichever bucket it judges best. Roth and
    HSA dollars have no charitable-transfer mechanism at all, and gifting them
    would trade a tax-free asset for a deduction. So there is no legitimate
    non-taxable source for the in-kind path, and this function does not look
    for one.

    Accounts are ranked by embedded long-term gain, largest first, so the most
    appreciation escapes tax. Without lot data no such ranking is possible and
    the draw falls back to pro-rata by balance. The configured taxable
    liquidity reserve is honored exactly as it is for a cash draw, so a gift
    cannot push the bucket below its floor.

    Returns ``amount`` actually gifted, ``by_account``, ``gain_avoided``, and
    ``shortfall`` -- the requested dollars that could not be gifted, whether
    because of the reserve floor or because too little long-term stock was
    held. Callers must surface a shortfall rather than reporting the full
    requested gift as given.
    """
    requested = max(0.0, float(amount or 0.0))
    if requested <= 0:
        return {"amount": 0.0, "by_account": {}, "gain_avoided": 0.0, "shortfall": 0.0,
                "h_amount": 0.0, "w_amount": 0.0, "long_term_capped": False}

    registry = c.get("account_registry", [])
    h_ids = owner_account_ids(registry, 0, "taxable")
    w_ids = owner_account_ids(registry, 1, "taxable")
    taxable_ids = _owner_tax_ids_pro_rata_order(registry, "taxable")
    total_taxable = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in taxable_ids)
    floor = liquidity_reserve_floor(c, year, "taxable", spend_floor_base)
    budget = min(requested, max(0.0, total_taxable - floor))

    lot_engine = c.get("lot_engine")
    has_lots = bool(lot_engine and getattr(lot_engine, "use_lots", False))
    if not has_lots:
        by_account = _draw_pro_rata_accounts(bal, taxable_ids, budget)
        gifted = sum(by_account.values())
        fallback = float(getattr(lot_engine, "fallback", 0.0) or 0.0) if lot_engine else 0.0
        return {
            "amount": gifted,
            "by_account": by_account,
            "gain_avoided": gifted * fallback,
            "shortfall": max(0.0, requested - gifted),
            "h_amount": sum(by_account.get(aid, 0.0) for aid in h_ids),
            "w_amount": sum(by_account.get(aid, 0.0) for aid in w_ids),
            "long_term_capped": False,
        }

    ranked = sorted(
        (aid for aid in taxable_ids if max(0.0, float(bal.get(aid, 0.0) or 0.0)) > 0),
        key=lambda aid: -(lot_engine.embedded_long_term_gain(aid, current_year=year) or 0.0),
    )
    by_account: Dict[str, float] = {}
    gain_avoided = 0.0
    remaining = budget
    for aid in ranked:
        if remaining <= 1e-9:
            break
        # Never gift more than the account actually holds, and never more than
        # its long-term lots can cover.
        room = min(remaining, max(0.0, float(bal.get(aid, 0.0) or 0.0)))
        if room <= 1e-9:
            continue
        gifted, gain, _consumed = lot_engine.donate_lots(aid, room, current_year=year, mutate=True)
        if gifted <= 1e-9:
            continue
        bal[aid] = max(0.0, float(bal.get(aid, 0.0) or 0.0) - gifted)
        by_account[aid] = by_account.get(aid, 0.0) + gifted
        gain_avoided += gain
        remaining -= gifted

    total_gifted = sum(by_account.values())
    return {
        "amount": total_gifted,
        "by_account": by_account,
        "gain_avoided": gain_avoided,
        "shortfall": max(0.0, requested - total_gifted),
        "h_amount": sum(by_account.get(aid, 0.0) for aid in h_ids),
        "w_amount": sum(by_account.get(aid, 0.0) for aid in w_ids),
        # True when long-term stock, not the reserve floor, was the binding
        # constraint -- the advisor-visible reason a gift came up short.
        "long_term_capped": total_gifted + 1e-6 < budget,
    }


def withdraw_roth(c: Mapping, bal: BalanceMap, gap: float, year: int = 0,
                  spend_floor_base: float = 0.0) -> Dict:
    """Withdraw Roth dollars as final liquid-account resort.

    ``year``/``spend_floor_base`` are optional so existing two-and-three
    argument callers keep working; supplying them lets a reserve configured
    against the Roth bucket hold Roth dollars back, the same way a taxable
    reserve holds taxable dollars back (P8).
    """
    if gap <= 1e-6:
        return {"amount": 0.0, "new_gap": gap, "by_account": {}, "h_amount": 0.0, "w_amount": 0.0}
    registry = c.get("account_registry", [])
    h_ids = owner_account_ids(registry, 0, "roth")
    w_ids = owner_account_ids(registry, 1, "roth")
    roth_ids = _owner_tax_ids_pro_rata_order(registry, "roth")
    total_roth = sum(max(0.0, float(bal.get(aid, 0.0))) for aid in roth_ids)
    floor = liquidity_reserve_floor(c, year, "roth", spend_floor_base)
    amount = min(gap, max(0.0, total_roth - floor))
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

# dataclass/field (line 165) and MutableMapping (line 622) already imported
# above (system review 4.1: removed this section's own duplicate re-import).


def roth_guardrail_id(name: str) -> str:
    """Stable id for a conversion cap's display name (used by the guardrail panel)."""
    n = str(name or "")
    low = n.lower()
    if low.endswith("bracket"):
        return "bracket"
    if low.startswith("tier"):
        return "irmaa"
    if low.startswith("ltcg"):
        return "ltcg"
    if low.startswith("niit"):
        return "niit"
    if low.startswith("aca"):
        return "aca"
    if low.startswith("annual ira"):
        return "pct"
    if low.startswith("ira balance"):
        return "balance"
    if low.startswith("fixed"):
        return "fixed"
    return low.replace(" ", "_")


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
    # JSON list of {"id","name","cap"} for every cap that was sized this year
    # (not just the two that bound), so the Roth guardrail panel can rank them.
    guardrail_caps: str = ""

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
            "conv_guardrail_caps": self.guardrail_caps,
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

    Item 3.2 (F3): ``conv_window_offset`` (CSV field
    ``roth_conv_window_end_offset``) ships in every plan file with the
    schema-documented default of ``-1`` (data_io.py) -- the row is always
    present, so its presence in the CSV can't distinguish "advisor chose
    -1" from "advisor never touched this field". The value itself is the
    only usable signal: at the shipped default (-1), the window now extends
    to plan end rather than closing the year before RMDs start, keeping the
    two highest-value conversion opportunities in play -- the late pre-RMD
    gap years and the survivor's compressed single-filer bracket years.
    RMDs and voluntary conversions coexisting past RMD age is already
    proven correct (item 3.1's guardrail verification); the optimizer's own
    caps size conversions to zero once they stop being profitable, so
    simply not closing the window is sufficient (system review's Option 1).

    Any OTHER offset value means the advisor has deliberately overridden
    it, and that offset remains authoritative, relative to RMD start -- but
    now anchored to whichever member reaches RMD age later, not just the
    primary member. The prior primary-member-only anchoring ignored a
    younger spouse's own (later) RMD start year entirely.

    ``roth_max_conversion_years`` (the v8.3 governance contract's explicit
    cap, 0 = unset) is authoritative whenever set, in both cases.
    """
    plan_start = int(c.get("plan_start", 0))
    h_dob = int(c.get("h_dob_yr", plan_start))
    w_dob = int(c.get("w_dob_yr", h_dob))
    h_rmd_age = int(c.get("h_rmd_start_age", c.get("rmd_start_age", 75)) or 75)
    w_rmd_age = int(c.get("w_rmd_start_age", c.get("rmd_start_age", 75)) or 75)
    later_rmd_year = max(h_dob + h_rmd_age, w_dob + w_rmd_age)

    try:
        max_years = int(float(c.get("roth_max_conversion_years", 0) or 0))
    except Exception:
        max_years = 0

    offset = int(c.get("conv_window_offset", -1))
    if offset == -1:
        end = int(c.get("plan_end", later_rmd_year))
    else:
        end = later_rmd_year + offset

    if max_years > 0:
        end = min(end, plan_start + max_years - 1)
    return end


def _available_by_owner(c: Mapping, bal: Mapping[str, float], owner_idx: int) -> float:
    return _sum_bal(bal, _ids_by_owner_tax(c, owner_idx, "pre_tax"))


# ─────────────────────────────────────────────────────────────────────────────
# Item 3.5 (F6): adoptable spending policy -- deterministic-engine (single
# path) implementation. The 4-rule Guyton-Klinger guardrail and the simpler
# floor-ceiling band, previously modeled only as a Monte Carlo shadow (never
# consumed as real policy -- see the vectorized shadow block in this same
# module), become the LIVE spending figure the deterministic engine actually
# uses when spending_policy is set to one of them.
#
# GK's Rule 1 (freeze the inflation increase after a negative-return year)
# is a documented no-op here: the deterministic engine assumes one flat
# annual return (c['ret']) for every year, so there is no year-to-year
# return variation for the freeze to react to. It fires normally in Monte
# Carlo, which has real per-path realized returns.
# ─────────────────────────────────────────────────────────────────────────────

SPENDING_GUARDRAIL_BAND = 0.20             # +/-20% of the initial withdrawal rate (GK)
SPENDING_GUARDRAIL_ADJUST = 0.10           # 10% cut or raise when a GK guardrail triggers
SPENDING_GUARDRAIL_SUSPENSION_YEARS = 15   # GK capital-preservation rule suspended this close to plan end
SPENDING_FLOOR_CEILING_BAND_PCT = 0.10     # +/-10% of the plan's own fixed-real spend level


def age_phased_spending_factor(age: float, decline_pct: float, start_age: int, end_age: int) -> float:
    """Item 3.5 (F6, Option 2): independent, always-available age-phased real
    spending curve -- discretionary spend declines by ``decline_pct``,
    phased in linearly between ``start_age`` and ``end_age``, then holds at
    the reduced level. Returns 1.0 (no-op) whenever decline_pct/start_age/
    end_age are unset (the default for every existing plan) or malformed
    (end_age <= start_age).
    """
    decline_pct = max(0.0, min(1.0, float(decline_pct or 0.0)))
    start_age = int(start_age or 0)
    end_age = int(end_age or 0)
    if decline_pct <= 0.0 or end_age <= start_age:
        return 1.0
    age = float(age or 0.0)
    if age <= start_age:
        return 1.0
    if age >= end_age:
        return 1.0 - decline_pct
    phase = (age - start_age) / (end_age - start_age)
    return 1.0 - decline_pct * phase


def spending_guardrail_year(
    policy: str,
    baseline_nominal_spend: float,
    portfolio_value: float,
    state: dict,
    *,
    inflation_rate: float = 0.0,
    prior_return: float | None = None,
    years_remaining: int | None = None,
) -> tuple[float, dict, bool, bool]:
    """One year's guardrail-adjusted spend for a SINGLE path (the
    deterministic engine's own, or a per-path caller in the exact-scalar MC
    engine). Returns ``(adjusted_spend, new_state, was_cut, was_raised)``.

    ``state`` carries this path's own running guardrail state across years
    (``{}`` on the first call): ``iwr`` (initial withdrawal rate, fixed once
    from the FIRST call), ``last_withdrawal`` (GK's own running dollar
    figure). Cut/raise are always reported relative to
    ``baseline_nominal_spend`` (this year's normal fixed-real spend) -- the
    plan's own "what would have been spent" figure -- not each policy's
    internal reference, so disclosure means the same thing under either
    policy.
    """
    if policy not in ("guyton_klinger", "floor_ceiling_band") or baseline_nominal_spend <= 0:
        return baseline_nominal_spend, state, False, False
    if not state.get("initialized"):
        iwr = baseline_nominal_spend / max(1.0, float(portfolio_value))
        new_state = {"initialized": True, "iwr": iwr, "last_withdrawal": baseline_nominal_spend}
        return baseline_nominal_spend, new_state, False, False

    iwr = float(state["iwr"])
    portfolio_value = max(0.0, float(portfolio_value))
    if policy == "floor_ceiling_band":
        natural = iwr * portfolio_value
        floor = baseline_nominal_spend * (1.0 - SPENDING_FLOOR_CEILING_BAND_PCT)
        ceiling = baseline_nominal_spend * (1.0 + SPENDING_FLOOR_CEILING_BAND_PCT)
        adjusted = min(ceiling, max(floor, natural))
    else:  # guyton_klinger
        withdrawal = float(state["last_withdrawal"])
        freeze = prior_return is not None and prior_return < 0.0
        if not freeze:
            withdrawal *= (1.0 + float(inflation_rate or 0.0))
        cwr = withdrawal / max(1e-9, portfolio_value)
        suspend_capital_preservation = years_remaining is not None and years_remaining <= SPENDING_GUARDRAIL_SUSPENSION_YEARS
        if not suspend_capital_preservation and cwr > iwr * (1.0 + SPENDING_GUARDRAIL_BAND):
            withdrawal *= (1.0 - SPENDING_GUARDRAIL_ADJUST)
        elif cwr < iwr * (1.0 - SPENDING_GUARDRAIL_BAND):
            withdrawal *= (1.0 + SPENDING_GUARDRAIL_ADJUST)
        adjusted = withdrawal

    new_state = {"initialized": True, "iwr": iwr, "last_withdrawal": adjusted}
    was_cut = adjusted < baseline_nominal_spend - 1e-6
    was_raised = adjusted > baseline_nominal_spend + 1e-6
    return adjusted, new_state, was_cut, was_raised




_ACA_TABLE_CACHE: dict = {}


def _aca_regime_table(enhanced: bool, year: int | None) -> dict:
    """WI-307 / FIN-007: the dated applicable-percentage table for one ACA
    regime, read from tax_law_v10.json (``aca_applicable_pct_enhanced_*`` or
    ``aca_applicable_pct_original_*`` rows). ``year=None`` means the latest
    dated table."""
    from .tax_law import default_tax_law_dataset
    key = (bool(enhanced), None if year is None else int(year))
    if key not in _ACA_TABLE_CACHE:
        regime = 'enhanced' if enhanced else 'original'
        _ACA_TABLE_CACHE[key] = default_tax_law_dataset().aca_applicable_pct_table(regime, 9999 if year is None else int(year))
    return _ACA_TABLE_CACHE[key]


def aca_enhanced_through_year(c: Mapping) -> int:
    """The plan's last enhanced-PTC year; a blank/missing field falls back to
    the dated ``aca_enhanced_subsidies_through_year`` dataset row."""
    raw = c.get('aca_enhanced_subsidies_through_year')
    try:
        if raw is not None and str(raw).strip() != '' and int(float(raw)) > 0:
            return int(float(raw))
    except (TypeError, ValueError):
        pass
    from .tax_law import aca_enhanced_subsidies_through_year_default
    return aca_enhanced_subsidies_through_year_default()


def aca_regime_is_enhanced(c: Mapping, year: int) -> bool:
    """Single regime switch for the PTC and the Roth-conversion guardrail:
    enhanced iff ``year`` <= the enhanced-through year."""
    return int(year) <= aca_enhanced_through_year(c)


def aca_fpl_for_year(c: Mapping, year: int) -> float:
    """Household FPL dollars for ``year`` (base-year FPL indexed by ``inf``)."""
    fpl_base = max(1.0, float(c.get('aca_fpl_base', 0.0) or 0.0))
    return fpl_base * ((1.0 + float(c.get('inf', 0.025) or 0.0)) ** max(0, int(year) - int(c.get('plan_start', year))))


def aca_guardrail_max_fpl_multiple(c: Mapping, year: int) -> float:
    """MAGI ceiling (as a multiple of FPL) for the Roth-conversion ACA
    guardrail, taken from the same regime table as the PTC: a regime with a
    cliff stops at its ``max_fpl``; one whose credit continues above it may
    use the plan's ``aca_ptc_guardrail_fpl_pct`` when that is higher."""
    table = _aca_regime_table(aca_regime_is_enhanced(c, year), year)
    if not table['credit_above_max']:
        return float(table['max_fpl'])
    return max(float(table['max_fpl']), float(c.get('aca_ptc_guardrail_fpl_pct', 4.0) or 4.0))


def aca_magi(agi: float, tax_exempt_interest: float, ss_gross: float, ss_taxable: float) -> float:
    """ACA (IRC 36B(d)(2)(B)) MAGI: AGI + tax-exempt interest + the non-taxable
    part of Social Security. Distinct from IRMAA MAGI, which omits the SS term."""
    return float(agi or 0.0) + float(tax_exempt_interest or 0.0) + max(0.0, float(ss_gross or 0.0) - float(ss_taxable or 0.0))


def aca_applicable_percentage(fpl_pct: float, enhanced: bool = True, cap: float = 0.085, year: int | None = None) -> float:
    """ACA applicable percentage for bridge-year PTC from the dated regime
    table in tax_law_v10.json (WI-307 / FIN-007).

    Within a band the required contribution interpolates linearly from the
    band's initial to its final percentage. The enhanced regime's top-band
    final and above-``max_fpl`` percentages are the plan's ``cap``; the
    original §36B regime has no credit above ``max_fpl`` (400% FPL cliff),
    signalled by returning a very high required contribution. ``year=None``
    uses the latest dated table.
    """
    f = max(0.0, float(fpl_pct or 0.0))
    cap = max(0.0, min(0.20, float(cap or 0.085)))
    table = _aca_regime_table(enhanced, year)
    bands = list(table['bands'])
    max_fpl = float(table['max_fpl'])
    if f > max_fpl:
        if not table['credit_above_max']:
            return 9_999.0
        return cap if enhanced else float(table['above_max_pct'])
    for i, (floor, initial, final) in enumerate(bands):
        top = bands[i + 1][0] if i + 1 < len(bands) else max_fpl
        if enhanced and i + 1 == len(bands):
            final = cap
        if f < top or i + 1 == len(bands):
            width = top - floor
            frac = 0.0 if width <= 0 else min(1.0, max(0.0, (f - floor) / width))
            return initial + (final - initial) * frac
    return cap


def aca_premium_tax_credit(c: Mapping, *, year: int, magi: float, bridge_people: int) -> float:
    if not c.get('aca_ptc_enabled', True) or bridge_people <= 0:
        return 0.0
    fpl = aca_fpl_for_year(c, year)
    fpl_pct = max(0.0, float(magi or 0.0) / fpl)
    enhanced = aca_regime_is_enhanced(c, year)
    app_pct = aca_applicable_percentage(fpl_pct, enhanced=enhanced, cap=float(c.get('aca_applicable_pct_cap', 0.085) or 0.085), year=year)
    if app_pct > 1.0:
        return 0.0
    benchmark = float(c.get('aca_benchmark_silver_premium', c.get('bridge_premium', 0.0)) or 0.0)
    # Scale benchmark if only one spouse is in a bridge year.
    if int(c.get('aca_household_size', 2) or 2) >= 2 and bridge_people == 1:
        benchmark *= 0.5
    required_contribution = max(0.0, float(magi or 0.0) * app_pct)
    return max(0.0, min(benchmark, benchmark - required_contribution))


def _roth_irmaa_guardrail_age_gate_met(c: Mapping, h_age: float, w_age: float) -> bool:
    """True once this year's MAGI could actually determine a future IRMAA
    surcharge for either member (system review 2026-07-21, P1).

    IRMAA is a Medicare premium surcharge assessed from age 65 using MAGI
    from ``irmaa_lookback_years`` (2) years prior -- deterministic_engine.py's
    assessment side already models this lag correctly
    (``irmaa_lookback_magi(..., irmaa_lookback_years=2)``), but this
    conversion-sizing guardrail previously capped every year's conversion
    against the IRMAA threshold with no age gate at all, throttling gap-year
    conversions at ages where the resulting MAGI is more than two years away
    from ever being looked back at -- it can never affect a real surcharge.
    The gate opens once either spouse is within the lookback window of
    Medicare age, i.e. age >= 65 - irmaa_lookback_years (63 by default);
    mixed-age couples are gated on whichever spouse is closer to 65, since a
    surviving/single member's own age already flows correctly once the
    other's dob defaults to a zero-impact mirror (data_io.py) or death cuts
    their own future IRMAA exposure off.
    """
    lookback_years = float(c.get("irmaa_lookback_years", 2) or 2)
    gate_age = 65.0 - lookback_years
    return float(h_age) >= gate_age or float(w_age) >= gate_age


def _roth_irmaa_target_threshold(c: Mapping, filing: str, year: int) -> float:
    """Indexed IRMAA target threshold for ``roth_irmaa_target_tier``, by
    filing status, for ``year``.

    Keyed by the current year's ``filing`` -- most importantly a surviving
    spouse whose filing status switches to Single mid-plan
    (deterministic_engine.py's survivor-filing transition) -- so the
    conversion guardrail and the tax assessment agree on which IRMAA tier is
    being targeted. #334 / W-B: the threshold comes from the single kernel
    implementation (``tax_kernel.irmaa_threshold``: CPI-indexed from the
    tier tables' value year, statutorily rounded, top-tier-aware); the
    retired MFJ tier-2 base-year input and the parsed MFJ target-threshold
    dollar figure are no longer consulted. An absent/unparseable target tier
    falls back to tier 2 (0-based index 1).
    """
    filing = str(filing or "MFJ")
    if filing not in IRMAA_TIERS_BASE_YEAR:
        filing = "MFJ"
    tiers = IRMAA_TIERS_BASE_YEAR[filing]
    tier_name = str(c.get("roth_irmaa_target_tier", "TIER_2") or "TIER_2").strip().upper()
    try:
        idx = int(tier_name.rsplit("_", 1)[-1]) - 1
    except (ValueError, IndexError):
        idx = 1
    idx = min(max(0, idx), len(tiers) - 1)
    return _tk.irmaa_threshold(c, filing, idx, year)


def _roth_ltcg_thresholds_base(c: Mapping, filing: str) -> tuple[float, float]:
    """Un-inflated 0%/15% LTCG bracket ceilings for the given filing status.

    Looked up fresh from ``LTCG_BRACKETS_BASE_YEAR`` by the current year's
    ``filing`` rather than trusting ``c['ltcg_0_top']``/``c['ltcg_15_top']``,
    which data_io.py seeds once from the client's *original* filing status --
    the same staleness the IRMAA threshold lookup above was fixed for, most
    importantly for a surviving spouse whose filing status flips to Single
    mid-plan.
    """
    filing = str(filing or "MFJ")
    tiers = LTCG_BRACKETS_BASE_YEAR.get(filing) or LTCG_BRACKETS_BASE_YEAR.get("MFJ", {})
    top0 = float(tiers.get("zero_top", c.get("ltcg_0_top", 98900)) or 98900)
    top15 = float(tiers.get("fifteen_top", c.get("ltcg_15_top", 613700)) or 613700)
    return top0, top15


def _roth_niit_threshold_base(c: Mapping, filing: str) -> float:
    """NIIT MAGI threshold for the given filing status.

    The 3.8% NIIT threshold is a fixed statutory dollar amount (not inflation
    -indexed) but is still filing-status-dependent, so it needs the same
    current-year ``filing`` lookup as the IRMAA/LTCG thresholds above rather
    than the value ``c['niit_threshold']`` caches once at parse time.
    """
    filing = str(filing or "MFJ")
    return float(NIIT_THRESHOLD.get(filing, c.get("niit_threshold", 250000)) or 250000)


def _roth_resolve_target_rate(c: Mapping, year: int, default_rate: float) -> float:
    """Return the Roth target bracket rate for `year`.

    `c['roth_phase_schedule']`, when present, is a list of `(end_year, rate)`
    tuples in ascending `end_year` order. The rate for the first tuple whose
    `end_year >= year` applies; years beyond the last tuple use its rate.
    Absent a schedule, every existing (flat-rate) candidate is unaffected.
    """
    schedule = c.get('roth_phase_schedule')
    if not schedule:
        return default_rate
    for end_year, rate in schedule:
        if year <= end_year:
            return float(rate)
    return float(schedule[-1][1])


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
    h_alive: bool = True,
    w_alive: bool = True,
    brackets_by_status: Mapping,
    brackets_mfj: list,
    inflate_brackets_fn: Callable,
    standard_deduction_fn: Callable,
    compute_fed_tax_fn: Callable,
    state_tax_estimate_fn: Callable[[float, int], float],
) -> ConversionPlan:
    """Compute the Roth conversion amount and diagnostics for a projection year."""
    _call_args = dict(locals())
    forced_amount = float((c.get("forced_roth", {}) or {}).get(year, 0.0) or 0.0)
    if forced_amount > 0:

        forced_rows = (c.get('forced_roth_accounts') or {}).get(year, []) or []
        forced_source = str(forced_rows[0].get('source_account','') if forced_rows else '')
        # The forced amount is not limited by any guardrail, but the panel still
        # shows what each guardrail would have allowed that year, so size the
        # caps as if no conversion were forced and keep only that diagnostic.
        _caps_json = ""
        try:
            _c2 = dict(c)
            _c2["forced_roth"] = {k: v for k, v in (c.get("forced_roth") or {}).items() if k != year}
            _call_args["c"] = _c2
            _caps_json = plan_roth_conversion(**_call_args).guardrail_caps
        except Exception:
            _caps_json = ""
        return ConversionPlan(amount=forced_amount, forced=True, binding_limit='Forced action', secondary_binding_limit='User-entered forced action', source_account=forced_source, forced_sources=forced_rows, guardrail_caps=_caps_json)

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
    target_rate = _roth_resolve_target_rate(
        c, year, float(c.get("roth_target_rate", c.get("roth_brk", 0.24)) or 0.24)
    )
    _bracket_top_match = next((hi for _lo, hi, rate in brk if rate == target_rate), None)
    if _bracket_top_match is None and policy not in ("fixed_dollar", "fill_to_irmaa"):
        # Item 3.2 (F3, planner's review pass): a roth_target_rate that
        # matches no bracket rate (a typo, or a bracket-table edit that drops
        # a rate) used to fall back silently to a hardcoded $400,000 bracket
        # top -- a wrong conversion-sizing cap with nothing in the output to
        # flag it. Only the target-rate-based policies (fill_to_bracket and
        # its family) actually consume this cap; fixed_dollar and
        # fill_to_irmaa compute it only as an unused diagnostic field, so
        # they are not gated on it matching. Applies to the RESOLVED rate
        # (roth_phase_schedule-aware via _roth_resolve_target_rate), so a
        # phase-varying schedule with a bad rate in any one phase fails
        # loud too, not just a flat roth_target_rate.
        raise ValueError(
            f"roth_target_rate={target_rate!r} matches no bracket rate for filing={filing!r} "
            f"in year={year} (available rates: {sorted({rate for _lo, _hi, rate in brk})}) -- "
            "fix roth_target_rate or the bracket table rather than silently sizing conversions "
            "against a hardcoded $400,000 bracket top"
        )
    top_target = _bracket_top_match if _bracket_top_match is not None else 400000.0

    pre_non_ss = (
        earned_base - half_se_ded - sehi_ded
        + rmd_total + pension + wife_single_ann + wife_joint_ann
        + h_single_ann + h_joint_ann + note_int_yr
        + portfolio_ordinary + portfolio_qualified
    )
    pre_ss_taxable = social_security_taxable_amount(h_ss + w_ss, pre_non_ss + portfolio_tax_exempt, filing)
    pre_agi = pre_non_ss + pre_ss_taxable

    # FIN-003 (system review 2026-09-25): gate each spouse's over-65 count on
    # their own alive flag, same fix as roth_conversion_and_agi_tax.py's
    # apply_agi_and_tax -- otherwise a survivor year double-counts the
    # deceased spouse's own age-65 add-on and OBBBA senior bonus.
    _n65_est = (1 if (h_alive and h_age >= 65) else 0) + (1 if (w_alive and w_age >= 65) else 0)
    std = standard_deduction_fn(
        year, filing, float(c.get("brk_inf", 0.02)),
        _n65_est,
    )
    try:
        std += senior_bonus_deduction(year, filing, pre_agi + portfolio_tax_exempt, _n65_est)
    except (TypeError, ValueError, KeyError) as _exc:
        # WI-029: the estimate proceeds without the senior bonus, but not silently.
        _log_fallback("roth_estimate.senior_bonus_deduction", _exc, year=year, filing=filing)
    base_tax_est = compute_fed_tax_fn(max(0.0, pre_agi - std), year, filing, float(c.get("brk_inf", 0.02)))
    # FIN-002 (system review 2026-09-25): top_target is a taxable-income
    # bracket threshold, but pre_agi is income before any deduction -- comparing
    # them directly (the old `bracket_room = max(0.0, top_target - pre_agi)`)
    # left a standard-deduction's worth of headroom unused, understating
    # fill_to_bracket conversions by roughly $30-45k/year for a 65+ couple.
    # Add the deduction back so bracket_room is sized against AGI, matching
    # the taxable-income threshold it is meant to fill. This planning-pass
    # sizing function has no itemized-deduction estimate available to it (the
    # authoritative itemized-vs-standard comparison happens later in
    # apply_agi_and_tax, against this year's actual, finalized AGI); using
    # the standard deduction alone is the defensible floor in its absence and
    # is never smaller than the true deduction taken.
    deduction_for_bracket_room = std
    bracket_room = max(0.0, top_target + deduction_for_bracket_room - pre_agi)
    base_tax_est += state_tax_estimate_fn(pre_agi, year)

    income_streams = (
        earned_base + h_ss + w_ss + pension + wife_single_ann + wife_joint_ann
        + h_single_ann + h_joint_ann + note_princ_yr + note_int_yr + rmd_total
        + portfolio_ordinary + portfolio_qualified + portfolio_tax_exempt
    )
    # Trust headroom is taxable dollars above the reserve -- but only when the
    # reserve is actually held in taxable. A Roth or HSA reserve leaves the
    # taxable bucket entirely free to fund conversions, and subtracting it here
    # (as every reserve did before P8) understated conversion capacity.
    taxable_ids = c.get("taxable_ids") or _ar.taxable_ids(c.get("account_registry", []))
    trust_surf = max(0.0, _sum_bal(bal, taxable_ids)
                     - liquidity_reserve_floor(c, year, "taxable", spend))
    non_roth_surplus = income_streams + trust_surf - total_spend_need - base_tax_est

    primary_avail = _available_by_owner(c, bal, 0)
    secondary_avail = _available_by_owner(c, bal, 1)
    # An IRA reserve must survive conversions too: converting pre-tax dollars to
    # Roth empties the bucket the reserve is meant to preserve just as surely as
    # spending them would.
    ira_total = max(0.0, primary_avail + secondary_avail
                    - liquidity_reserve_floor(c, year, "pretax", spend))
    amount = 0.0
    binding = ""
    secondary_binding = ""

    max_pct = float(c.get("roth_max_annual_conversion_pct_of_traditional_ira", 0.20) or 0.20)
    max_pct = min(1.0, max(0.0, max_pct))
    max_pct_cap = ira_total * max_pct if max_pct > 0 else float("inf")

    caps_seen: list[dict] = []

    def _ranked_caps(caps: list[tuple[str, float]]) -> tuple[float, str, str]:
        clean = [(name, max(0.0, float(val))) for name, val in caps if val is not None]
        clean.sort(key=lambda x: x[1])
        caps_seen[:] = [{"id": roth_guardrail_id(n), "name": n, "cap": round(v, 2)} for n, v in clean]
        if not clean:
            return 0.0, "", ""
        primary = clean[0]
        secondary = clean[1] if len(clean) > 1 else ("", 0.0)
        return primary[1], primary[0], secondary[0]

    def _ltcg_niit_caps() -> list[tuple[str, float]]:
        """NIIT-cliff and LTCG-rate-tier caps, sized off income already known
        at conversion-sizing time (before this year's realized capital gains
        are computed later in the projection loop, so this can only protect
        the qualified-dividend/interest income already visible here -- it
        cannot see gains TLH/gain-harvesting/portfolio draws realize later
        this same year).
        """
        extra: list[tuple[str, float]] = []
        # WI-306 / FIN-014: use the kernel's signed-off indexing convention
        # (compounded from FEDERAL_BRACKETS_VALUE_YEAR, not plan_start) so the
        # guardrail threshold matches what tax_kernel.ltcg_tax_on_gain uses.
        bracket_factor = _tk.bracket_factor_for_year(c, year)

        if c.get("roth_ltcg_cap", True) and portfolio_qualified > 0:
            ltcg_top0, ltcg_top15 = _roth_ltcg_thresholds_base(c, filing)
            ltcg_top0 *= bracket_factor
            ltcg_top15 *= bracket_factor
            # WI-023 / FIN-003: qualified dividends are now taxed in the 0/15/20%
            # preferential stack, directly below any realized gain. ``pre_agi``
            # already includes ``portfolio_qualified`` (see pre_non_ss above), so the
            # stack position tested here contains the dividends, and the band tops
            # come from the verified 2026 dataset via _roth_ltcg_thresholds_base and
            # the kernel's bracket factor -- the same tops tax_kernel.ltcg_tax_on_gain
            # applies.
            # WI-023b (planner decision): the band tops are TAXABLE-income thresholds,
            # so the stack position is pre-conversion AGI less the deduction (the
            # standard deduction is the floor available at sizing time, as in the
            # bracket-room calculation above). A conversion adds ordinary income
            # dollar for dollar, so headroom is measured from this position.
            _stack_pos = max(0.0, pre_agi - std)
            # roth_ltcg_band: 'auto' stays within whichever band income is in
            # today; '0%' / '15%' name the band to stay within. A named band
            # income has already passed cannot be stayed within, so it adds no
            # cap (a cap of $0 would silently block every conversion).
            _band = str(c.get("roth_ltcg_band", "auto") or "auto").strip().lower()
            if _band in ("0%", "0", "zero"):
                ltcg_ceiling = ltcg_top0 if _stack_pos < ltcg_top0 else None
            elif _band in ("15%", "15", "fifteen"):
                ltcg_ceiling = ltcg_top15 if _stack_pos < ltcg_top15 else None
            elif _stack_pos < ltcg_top0:
                ltcg_ceiling = ltcg_top0
            elif _stack_pos < ltcg_top15:
                ltcg_ceiling = ltcg_top15
            else:
                ltcg_ceiling = None
            if ltcg_ceiling is not None:
                cap_ltcg = max(0.0, ltcg_ceiling - _stack_pos) * float(c.get('roth_ltcg_headroom_usage_pct', 0.95) or 0.95)
                extra.append(("LTCG rate tier", cap_ltcg))

        nii_known_est = max(0.0, float(note_int_yr) + float(portfolio_ordinary) + float(portfolio_qualified))
        if c.get("roth_niit_cap", True) and nii_known_est > 0:
            niit_thr = _roth_niit_threshold_base(c, filing)
            cap_niit = max(0.0, niit_thr - pre_agi) * float(c.get('roth_niit_headroom_usage_pct', 0.95) or 0.95)
            extra.append(("NIIT threshold", cap_niit))

        return extra

    if policy == "fixed_dollar":
        fixed_amt = float(c.get("roth_fixed_amount", 50000) or 0.0)
        if ira_total > 5000 and fixed_amt > 1000:
            cap, binding, secondary_binding = _ranked_caps([
                ("Fixed dollar", fixed_amt), ("IRA balance", ira_total),
                ("Annual IRA percentage cap", max_pct_cap),
            ])
            amount = cap
    elif policy == "fill_to_irmaa":
        irmaa_thr = _roth_irmaa_target_threshold(c, filing, year)
        cap_irmaa = max(0.0, irmaa_thr - pre_agi) * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95)
        # Caps are sized even when the IRMAA tier has no room left (cap_irmaa
        # <= 1000): the amount then stays 0 (reset below), but the guardrail
        # panel can show the IRMAA tier as the limit actually holding it down.
        if ira_total > 5000:
            caps = [
                (str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(), cap_irmaa),
                ("IRA balance", ira_total),
                ("Annual IRA percentage cap", max_pct_cap),
            ]
            if aca_bridge_people and c.get('aca_ptc_enabled', True) and c.get('roth_aca_cap', True):
                # P1 (system review 2026-07-21): this policy caps to the IRMAA
                # threshold alone, which sits far above 400% FPL -- with no
                # ACA guardrail, an ACA-bridge client on "fill to IRMAA" gets
                # conversions sized straight into subsidy-destroying MAGI.
                # Mirrors the fill_to_bracket branch's guardrail above.
                fpl = aca_fpl_for_year(c, year)
                max_fpl = aca_guardrail_max_fpl_multiple(c, year)
                caps.append(("ACA PTC MAGI guardrail", max(0.0, max_fpl * fpl - pre_agi)))
            caps.extend(_ltcg_niit_caps())
            cap, binding, secondary_binding = _ranked_caps(caps)
            amount = cap
    else:
        # roth_bracket_cap off: the target bracket no longer limits conversions
        # (the other active guardrails still do).
        _bracket_on = bool(c.get('roth_bracket_cap', True))
        # Caps are sized every year, even when the bracket has no room left
        # (the amount then stays 0), so the guardrail panel can show why.
        cap_bracket = bracket_room * float(c.get('roth_headroom_usage_pct', 0.95) or 0.95)
        caps = [("IRA balance", ira_total), ("Annual IRA percentage cap", max_pct_cap)]
        if _bracket_on:
            caps.insert(0, (f"{int(target_rate * 100)}% bracket", cap_bracket))
        if aca_bridge_people and c.get('aca_ptc_enabled', True) and c.get('roth_aca_cap', True):
            # Roth conversions in bridge years can destroy ACA premium tax
            # credits.  Add a guardrail that keeps MAGI below the point where
            # the configured benchmark subsidy is largely lost.
            fpl = aca_fpl_for_year(c, year)
            max_fpl = aca_guardrail_max_fpl_multiple(c, year)
            caps.append(("ACA PTC MAGI guardrail", max(0.0, max_fpl * fpl - pre_agi)))
        guard_mode = str(c.get("irmaa_guardrail_mode", "AVOID_NEXT_TIER") or "AVOID_NEXT_TIER").upper()
        if (
            c.get("roth_irmaa_cap", True)
            and guard_mode not in ("IGNORE", "WARN_ONLY")
            and _roth_irmaa_guardrail_age_gate_met(c, h_age, w_age)
        ):
            irmaa_thr = _roth_irmaa_target_threshold(c, filing, year)
            cap_irmaa = max(0.0, irmaa_thr - pre_agi) * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95)
            caps.append((str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(), cap_irmaa))
        caps.extend(_ltcg_niit_caps())
        if ira_total > 5000:
            cap, binding, secondary_binding = _ranked_caps(caps)
            if cap > 1000:
                amount = cap

    if amount < 1000:
        amount = 0.0
        binding = ""
        secondary_binding = ""

    # Every guardrail is quantified every year. The ones enforced this year are
    # the real caps ("active": True); the rest (switched off, or not applicable
    # this year -- IRMAA before the age gate, ACA outside bridge years, no
    # qualified income, a different policy) carry the dollars they WOULD allow
    # with "active": False, so the panel can always show a number.
    for _e in caps_seen:
        _e["active"] = True
    _have = {_e["id"] for _e in caps_seen}

    def _would_allow(gid: str, name: str, cap: float) -> None:
        if gid not in _have:
            caps_seen.append({"id": gid, "name": name, "cap": round(max(0.0, float(cap)), 2), "active": False})
            _have.add(gid)

    try:
        _bf = _tk.bracket_factor_for_year(c, year)
        _would_allow("bracket", f"{int(target_rate * 100)}% bracket",
                     bracket_room * float(c.get('roth_headroom_usage_pct', 0.95) or 0.95))
        _would_allow("irmaa", str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(),
                     (_roth_irmaa_target_threshold(c, filing, year) - pre_agi)
                     * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95))
        _t0, _t15 = _roth_ltcg_thresholds_base(c, filing)
        _sp = max(0.0, pre_agi - std)  # same stack position as the active cap in _ltcg_niit_caps
        _ceil = _t0 * _bf if _sp < _t0 * _bf else (_t15 * _bf if _sp < _t15 * _bf else None)
        if _ceil is not None:
            _would_allow("ltcg", "LTCG rate tier",
                         (_ceil - _sp) * float(c.get('roth_ltcg_headroom_usage_pct', 0.95) or 0.95))
        _would_allow("niit", "NIIT threshold",
                     (_roth_niit_threshold_base(c, filing) - pre_agi)
                     * float(c.get('roth_niit_headroom_usage_pct', 0.95) or 0.95))
        if aca_bridge_people:
            _would_allow("aca", "ACA PTC MAGI guardrail",
                         aca_guardrail_max_fpl_multiple(c, year) * aca_fpl_for_year(c, year) - pre_agi)
        _would_allow("pct", "Annual IRA percentage cap", ira_total * max_pct)
        _would_allow("balance", "IRA balance", ira_total)
    except (TypeError, ValueError, KeyError, ZeroDivisionError) as _exc:
        _log_fallback("roth_guardrail.trace", _exc, year=year)
    # Record which bracket rate this year's bracket cap used (a phase-varying or
    # optimizer-chosen strategy can differ from the configured target bracket).
    for _e in caps_seen:
        if _e["id"] == "bracket":
            _e["rate"] = round(float(target_rate), 4)

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
        guardrail_caps=json.dumps(caps_seen) if caps_seen else "",
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
