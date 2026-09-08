from __future__ import annotations

from typing import Any


def compute_spend_by_tier(
    c: dict[str, Any],
    *,
    spend: float,
    rec_extra: float,
    lump_yr: float,
    home_improvement_yr: float,
    mort_yr: float,
    re_tax_yr: float,
    rent_yr: float,
    housing_operating_yr: float,
    heloc_interest_yr: float,
    heloc_repayment_principal_yr: float,
    wellness_premium_yr: float,
    wellness_medical_yr: float,
    wellness_dental_yr: float,
    wellness_vision_yr: float,
    wellness_rx_otc_yr: float,
    wellness_other_yr: float,
    wellness_base_yr: float,
    ltc_prem_yr: float,
    wellness_shock_yr: float,
    business_expenses_yr: float,
) -> dict[str, float]:
    """Split this year's ``total_spend_need`` into reporting tiers.

    Breaks total_spend_need into essential / important / discretionary /
    contingent_liability per the SPENDING_TIERS registry in
    spending_budget_resolver.py. Purely additive reporting: it never
    feeds back into total_spend_need, withdrawals, or taxes. spend_base
    is split using the household's actual category mix
    (spend_base_tier_shares); every other component maps to a single
    tier because it is already segregated in the row (e.g. mortgage /
    RE tax / utilities are Housing-essential). The wellness split
    additionally respects the ACA-recompute and the n_alive == 0
    estate-mode zeroing (both resolved by the caller before this is
    invoked, via the wellness_*_yr values passed in) by scaling its raw
    components to wellness_base_yr rather than using them directly.

    contingent_liability holds only ltc_prem_yr -- an insurance
    premium is a genuine (if painful) choice to forgo future coverage,
    so it is cuttable at the tier's documented cascade priority
    (SPENDING_TIER_CUT_ORDER: after important, before essential).
    wellness_shock_yr is routed into 'essential' instead: it is an
    already-incurred health/LTC event cost, not a discretionary
    spending choice, so it is protected at essential's level rather
    than bundled with the premium at a lower cascade priority.

    Returns the dict to assign to ``row['spend_by_tier']`` -- rounded
    to cents, with zero-valued tiers dropped.
    """
    tier_totals: dict[str, float] = {}

    def _tier_add(tier: str, amount: float) -> None:
        if amount:
            tier_totals[tier] = tier_totals.get(tier, 0.0) + amount

    base_shares = c.get('spend_base_tier_shares') or {}
    if base_shares:
        for tier, frac in base_shares.items():
            _tier_add(tier, spend * frac)
    elif spend:
        _tier_add('important', spend)
    _tier_add('discretionary', rec_extra + lump_yr + home_improvement_yr)
    _tier_add('essential', mort_yr + re_tax_yr + rent_yr + housing_operating_yr
               + heloc_interest_yr + heloc_repayment_principal_yr)
    wellness_essential_raw = (wellness_premium_yr + wellness_medical_yr + wellness_dental_yr
                               + wellness_vision_yr + wellness_rx_otc_yr)
    wellness_raw_total = wellness_essential_raw + wellness_other_yr
    if wellness_raw_total > 0 and wellness_base_yr:
        wellness_scale = wellness_base_yr / wellness_raw_total
        _tier_add('essential', wellness_essential_raw * wellness_scale)
        _tier_add('important', wellness_other_yr * wellness_scale)
    # Reconciled with 'claude/confit-optimization-refactor-cyyk9v' PR #70
    # (merged first, then reverted here in favor of this branch's design,
    # per user decision 2026-08-27): ltc_prem_yr (an insurance premium --
    # a genuine choice to forgo future coverage) stays in
    # contingent_liability, cuttable at that tier's documented cascade
    # priority. wellness_shock_yr (an already-incurred health/LTC event
    # cost, not a discretionary choice) routes into essential instead,
    # protecting it at essential's cascade priority rather than bundling
    # it with the premium at a lower one.
    _tier_add('contingent_liability', ltc_prem_yr)
    _tier_add('essential', wellness_shock_yr)
    if business_expenses_yr:
        _tier_add('unclassified', business_expenses_yr)
    return {k: round(v, 2) for k, v in tier_totals.items() if v}
