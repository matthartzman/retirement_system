"""Per-year tax-path helpers lifted out of run_deterministic_projection_stage (ARC-001).

Pure functions of the plan config ``c``. ``qualified_dividends_by_year`` is the dict the
year loop fills as each year's portfolio income split becomes known (WI-023 / FIN-003);
it is passed in rather than captured.
"""
from __future__ import annotations

from .. import core as _ar
from .. import tax_kernel as _tk
from ..core import state_for_year
from ..engine_kernels import FEDERAL_BRACKETS_BASE_YEAR, state_income_tax
from ..tax_assumptions import stressed_ordinary_brackets as _ta_stressed_brackets


def bracket_factor_for_year(c, year):
    return _tk.bracket_factor_for_year(c, year)


def inflate_brackets_path(c, brackets, inflator_unused, years_from_plan_start):
    year_eff = int(c.get('plan_start', 0) or 0) + int(years_from_plan_start or 0)
    factor = bracket_factor_for_year(c, year_eff)
    return [(lo * factor, hi * factor if hi != float('inf') else float('inf'), rate) for lo, hi, rate in brackets]


def fed_brackets_path(c, year, filing):
    brk = FEDERAL_BRACKETS_BASE_YEAR.get(filing, FEDERAL_BRACKETS_BASE_YEAR['Single'])
    brk = inflate_brackets_path(c, brk, None, int(year) - int(c.get('plan_start', year)))
    # Tax-law stress (src/tax_assumptions.py): rates only, tax owed only.
    return _ta_stressed_brackets(brk, year, c.get('law_scenario'))


def ordinary_fed_tax_path(c, taxable, year, filing):
    """Ordinary-schedule tax on ``taxable`` (no preferential income)."""
    brk = fed_brackets_path(c, year, filing)
    tax = 0.0
    taxable = max(0.0, float(taxable or 0.0))
    for lo, hi, rate in brk:
        if taxable <= lo:
            break
        tax += (min(taxable, hi) - lo) * rate
    return max(0.0, tax)


def compute_fed_tax_path(c, qualified_dividends_by_year, taxable, year, filing, brk_inf_unused=None):
    """Federal tax on ``taxable`` (qualified dividends included): the
    ordinary schedule on the rest, plus 0/15/20% on the dividends stacked
    on top of it. Realized gains are priced separately above this stack."""
    return _tk.fed_tax_with_qualified(
        c, lambda o: ordinary_fed_tax_path(c, o, year, filing), taxable,
        qualified_dividends_by_year.get(year, 0.0), year, filing)


def ira_elective_ordinary_tax_delta(c, qualified_dividends_by_year, fed_tax_base, state_tax_base, taxable_inc_base,
                                      retirement_dist_base, ira_wd_cumulative, year, filing,
                                      ss_taxable, earned_net, investment_inc, nonqual_ann,
                                      roth_conv, h_over_65):
    """Real incremental fed+state tax caused by `ira_wd_cumulative` of elective
    IRA/401(k) income, vs. the flat marginal-rate estimate baked into
    withdraw_pretax_elective's gross-up. `fed_tax_base`/`state_tax_base`/
    `taxable_inc_base` should be the values as of the last time this income
    was accounted for, so the return is the tax on just the newest increment.
    """
    if ira_wd_cumulative <= 1e-6:
        return 0.0, fed_tax_base, state_tax_base
    new_taxable_inc = taxable_inc_base + ira_wd_cumulative
    new_fed_tax = compute_fed_tax_path(c, qualified_dividends_by_year, new_taxable_inc, year, filing, c['brk_inf'])
    new_state_tax = state_income_tax(
        state_for_year(c, year), earned_net, retirement_dist_base + ira_wd_cumulative, ss_taxable,
        investment_inc, nonqual_ann, roth_conv, year, h_over_65, filing=filing,
        brk_inf=c['brk_inf'], rate_override=c.get('state_rate_override'),
    )
    delta = (new_fed_tax - fed_tax_base) + (new_state_tax - state_tax_base)
    return delta, new_fed_tax, new_state_tax


def standard_deduction_path(c, year, filing, brk_inf_unused=None, n_over_65=2):
    td = getattr(_ar, '_td', None)
    base = getattr(td, 'STANDARD_DEDUCTION_BASE_YEAR', {}).get(filing, 15750) if td else 15750
    add_per = getattr(td, 'STANDARD_DEDUCTION_OVER65_BASE_YEAR', {}).get(filing, 1650) if td else 1650
    return (base + add_per * n_over_65) * bracket_factor_for_year(c, year)


def irmaa_factor_for_year(c, year):
    return _tk.irmaa_factor_for_year(c, year)


def irmaa_surcharge_path(c, agi, year, n_people, filing):
    return _tk.irmaa_surcharge(agi, year, n_people, filing, c)


def irmaa_tier_path(c, agi, year, filing):
    return _tk.irmaa_tier(agi, year, filing, c)


def ltcg_tax_on_gain_path(c, gain, ordinary_income, year):
    return _tk.ltcg_tax_on_gain(c, gain, ordinary_income, year)
