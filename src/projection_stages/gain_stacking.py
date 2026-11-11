"""Gain-stacking helpers lifted out of the year loop of run_deterministic_projection_stage (ARC-001).

Pure functions. The stage keeps thin wrappers that read the year's loop locals at call time and pass
them in, so behaviour is identical to the former closures.
"""
from __future__ import annotations

from ..core import state_for_year
from ..engine_kernels import (
    aca_magi,
    aca_premium_tax_credit,
    social_security_taxable_amount,
    state_income_tax,
)
from . import other_asset_sale_tax as _other_asset_sale


def state_tax_at(c, year, filing, investment_inc, earned, retirement_dist, ss_taxable, nonqual_ann, roth_conv,
                 over65):
    return state_income_tax(
        state_for_year(c, year), earned, retirement_dist, ss_taxable, investment_inc, nonqual_ann, roth_conv, year,
        over65, filing=filing, brk_inf=c['brk_inf'], rate_override=c.get('state_rate_override'))


def other_asset_stacked_tax(c, year, filing, compute_fed_tax_path, state_tax_at_fn, taxable, agi, gains,
                            sale_gain_in_agi, state_base, base_nii_ordinary, niit_ws_taxable, niit_hs_taxable):
    """Gain tax stacked on the year's ordinary taxable income; re-run after Priority 4b at the converged one.

    ``base_nii_ordinary`` is note interest + portfolio ordinary + portfolio qualified income.
    """
    return _other_asset_sale.stacked_gain_tax(
        gains, taxable_inc=taxable, fed_tax_fn=lambda t: compute_fed_tax_path(t, year, filing),
        state_tax_fn=lambda g: state_tax_at_fn(state_base + g) - state_tax_at_fn(state_base),
        base_nii=(base_nii_ordinary + niit_ws_taxable + niit_hs_taxable + sale_gain_in_agi),
        magi=agi + sale_gain_in_agi, filing=filing, model_niit=bool(c.get('model_niit')))


def aca_ptc_with_gain(c, year, extra_magi, agi, portfolio_tax_exempt, ss_total, ss_taxable, bridge_people):
    return aca_premium_tax_credit(
        c, year=year, magi=aca_magi(agi + extra_magi, portfolio_tax_exempt, ss_total, ss_taxable),
        bridge_people=bridge_people)


def ss_extra_from_gain(ss_total, non_ss, extra_gain, portfolio_tax_exempt, filing):
    """Marginal effect of the gain only (same base income on both sides): elective IRA draws already in
    ``agi`` do not retroactively re-tax the benefit here."""
    return (social_security_taxable_amount(ss_total, non_ss + extra_gain + portfolio_tax_exempt, filing)
            - social_security_taxable_amount(ss_total, non_ss + portfolio_tax_exempt, filing))
