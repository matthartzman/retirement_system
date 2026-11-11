"""Per-year factor helpers lifted out of run_deterministic_projection_stage (ARC-001).

Pure functions of the plan config ``c`` (and the live balances dict ``bal`` for the portfolio-income
split). Behaviour is identical to the former closures.
"""
from __future__ import annotations

from ..early_distribution import early_distribution_tax as _early_distribution_tax, early_fraction as _early_fraction
from ..tax_law import default_tax_law_dataset as _tax_law_ds
from .index_paths import path_factor


def infl_factor(c, year):
    return path_factor(c, 'inflation_index_by_year', c['inf'], year)


def spending_factor(c, year):
    if c.get('core_spending_growth_mode') == 'manual_override':
        return (1 + float(c.get('spend_inf', c.get('inf', 0.0)) or 0.0)) ** max(0, year - c['plan_start'])
    return infl_factor(c, year)


def survivor_factor(household_is_couple, survivor_spend_factor, n_alive):
    """1.0 unless exactly one member of a couple is still alive.

    n_alive == 0 is deliberately left at 1.0 here: zeroing living
    expenses after the second death is Task S2's job, and returning a
    scale factor for it would be the wrong mechanism anyway.
    """
    if household_is_couple and n_alive == 1:
        return survivor_spend_factor
    return 1.0


def basis_stepup_fraction(c, decedent_owned=True):
    regime = str(c.get('basis_step_up_property_regime', 'COMMON_LAW') or 'COMMON_LAW').upper()
    if regime in ('COMMUNITY_PROPERTY', 'FULL_STEP_UP'):
        return 1.0
    if regime == 'HALF_STEP_UP':
        return 0.5
    return 1.0 if decedent_owned else 0.5


def taxable_portfolio_income_for_year(c, bal):
    # Dividends/interest are taxable in the year earned whether or not they
    # are reinvested (an account holds every investment type, but only
    # taxable/Trust accounts generate a current tax event; IRA/401k/Roth/
    # HSA dividends aren't taxed until a separate withdrawal occurs).
    # Whether the yield compounds into the holding or converts to
    # account-internal cash is a growth-engine concern (see
    # planning_engines.apply_end_of_year_growth) — either way the money
    # never leaves the account, so this no longer funds spending directly.
    ordinary = qualified = tax_exempt = 0.0
    taxable_ids_set = set(c.get('taxable_ids', []))
    for _acct, _info in (c.get('account_taxable_income_assumptions') or {}).items():
        if _acct not in taxable_ids_set:
            continue
        _bal = max(0.0, float(bal.get(_acct, 0.0) or 0.0))
        ordinary += _bal * float(_info.get('ordinary_yield', 0.0) or 0.0)
        qualified += _bal * float(_info.get('qualified_yield', 0.0) or 0.0)
        tax_exempt += _bal * float(_info.get('tax_exempt_yield', 0.0) or 0.0)
    return ordinary, qualified, tax_exempt


def early_dist_tax_fn_for_year(c, year):
    """WI-039 / FIN-004: the 10% additional tax on early pre-tax distributions, as a function of the
    cumulative pre-tax draws by account. None when no living owner is under 59 1/2 this year, so plans
    without exposure run exactly as before."""
    members = c.get('members') or []
    if not members or not any(
            _early_fraction(year, m['dob_yr'], m.get('dob_month') or 1) > 0.0 for m in members):
        return None
    rate = _tax_law_ds().lookup_or_earliest('early_distribution_additional_tax_rate', year).value
    exceptions = c.get('early_dist_exceptions') or {}
    registry = c.get('account_registry') or []
    return lambda draws: _early_distribution_tax(rate, year, draws, registry, members, exceptions)[0]


def ss_funding_factor(c, year):
    try:
        cut_year = int(c.get('ss_funding_discount_year', 2032) or 2032)
        pct = max(0.0, min(1.0, float(c.get('ss_funding_discount_pct', 0.22) or 0.0)))
    except Exception:
        cut_year, pct = 2032, 0.22
    return 1.0 - pct if int(year) >= cut_year and pct > 0 else 1.0
