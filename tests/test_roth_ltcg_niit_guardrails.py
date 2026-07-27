"""Roth conversion sizing must not blow through the LTCG 0%/15% rate-tier
ceilings or the NIIT MAGI threshold just because federal-bracket/IRMAA/ACA
headroom still has room left.

Before this change, ``plan_roth_conversion`` only capped conversions against
the target federal ordinary bracket, IRMAA, and (in ACA-bridge years) the ACA
PTC MAGI cliff -- so a conversion sized to "fill the 24% bracket" could freely
push a household's known qualified-dividend income from the 0% into the 15%
LTCG bracket, or push MAGI over the NIIT threshold, with the cost showing up
only after the fact in the lifetime-tax comparison between whole candidate
strategies, never as a same-year brake the way IRMAA/ACA already get.

These tests exercise ``plan_roth_conversion`` directly (it is documented as
"intentionally side-effect free ... so it can be tested without building
workbooks") rather than through the full ``project()`` pipeline, so the caps
can be isolated and their exact dollar sizing verified against the real
``LTCG_BRACKETS_BASE_YEAR``/``NIIT_THRESHOLD`` tables.
"""
from src.core import (
    inflate_brackets, standard_deduction, compute_fed_tax,
    FEDERAL_BRACKETS_BASE_YEAR, FEDERAL_BRACKETS_MFJ,
)
from src.planning_engines import (
    plan_roth_conversion, _roth_ltcg_thresholds_base, _roth_niit_threshold_base,
)


def _plan(c_overrides, **kw_overrides):
    c = {
        'plan_start': 2026,
        'roth_policy': 'fill_to_bracket',
        'roth_target_rate': 0.35,          # wide federal bracket headroom so it never binds here
        'roth_headroom_usage_pct': 1.0,
        'roth_max_annual_conversion_pct_of_traditional_ira': 1.0,
        'roth_irmaa_cap': False,           # isolate from the separate IRMAA/ACA guardrails
        'roth_ltcg_headroom_usage_pct': 1.0,
        'roth_niit_headroom_usage_pct': 1.0,
        'brk_inf': 0.0,
        'account_registry': [{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': 'IRA'}],
    }
    c.update(c_overrides)
    bal = {'H_IRA': 2_000_000.0}
    kwargs = dict(
        c=c, bal=bal, year=2026, filing='MFJ',
        earned_base=0.0, half_se_ded=0.0, sehi_ded=0.0,
        h_ss=0.0, w_ss=0.0, rmd_total=0.0, pension=0.0,
        wife_single_ann=0.0, wife_joint_ann=0.0, h_single_ann=0.0, h_joint_ann=0.0,
        note_int_yr=0.0, note_princ_yr=0.0, total_spend_need=0.0, spend=0.0,
        portfolio_ordinary=0.0, portfolio_qualified=0.0, portfolio_tax_exempt=0.0,
        aca_bridge_people=0, h_age=60.0, w_age=58.0,
        brackets_by_status=FEDERAL_BRACKETS_BASE_YEAR, brackets_mfj=FEDERAL_BRACKETS_MFJ,
        inflate_brackets_fn=inflate_brackets, standard_deduction_fn=standard_deduction,
        compute_fed_tax_fn=compute_fed_tax, state_tax_estimate_fn=lambda agi, yr: 0.0,
    )
    kwargs.update(kw_overrides)
    return c, plan_roth_conversion(**kwargs)


def test_ltcg_rate_tier_caps_conversion_when_qualified_dividends_present():
    c, plan = _plan({'roth_niit_cap': False}, portfolio_qualified=200_000.0)
    top0, top15 = _roth_ltcg_thresholds_base(c, 'MFJ')
    assert plan.pre_agi == 200_000.0
    assert top0 < plan.pre_agi < top15  # already past the 0% ceiling, not yet at 20%
    assert plan.binding_limit == 'LTCG rate tier'
    assert plan.amount == top15 - plan.pre_agi


def test_ltcg_cap_absent_when_no_capital_gain_rate_income():
    # Nothing taxed at LTCG rates this year -- the cap must not fire (and must
    # not spuriously restrict the conversion) just because ordinary income is
    # near the LTCG bracket ceilings.
    c, plan = _plan({'roth_niit_cap': False}, portfolio_ordinary=200_000.0)
    assert plan.binding_limit != 'LTCG rate tier'


def test_niit_threshold_caps_conversion_when_investment_income_present():
    c, plan = _plan({'roth_ltcg_cap': False}, portfolio_ordinary=220_000.0)
    thr = _roth_niit_threshold_base(c, 'MFJ')
    assert plan.pre_agi == 220_000.0
    assert plan.binding_limit == 'NIIT threshold'
    assert plan.amount == thr - plan.pre_agi


def test_niit_cap_absent_when_no_investment_income():
    c, plan = _plan({'roth_ltcg_cap': False}, earned_base=220_000.0)
    assert plan.binding_limit != 'NIIT threshold'


def test_caps_are_configurable_off():
    # Disabling both guardrails restores the pre-existing behavior: sizing is
    # bound only by the target federal bracket.
    c, plan = _plan({'roth_ltcg_cap': False, 'roth_niit_cap': False}, portfolio_qualified=200_000.0)
    assert plan.binding_limit == '35% bracket'


def test_fill_to_irmaa_policy_also_carries_the_ltcg_and_niit_guardrails():
    # These guardrails must be symmetric with the existing ACA PTC fix for
    # fill_to_irmaa (system review 2026-07-21, P1 adjacent gap): a policy that
    # only caps to the IRMAA threshold must not ignore LTCG/NIIT cliffs either.
    c, plan = _plan(
        # MFJ resolves its IRMAA threshold from roth_irmaa_target_threshold_mfj
        # (see _roth_irmaa_target_threshold_base), not the tier table -- push
        # it far out of the way so only the LTCG cap can bind here.
        {'roth_policy': 'fill_to_irmaa', 'roth_irmaa_target_threshold_mfj': 10_000_000.0, 'roth_niit_cap': False},
        portfolio_qualified=200_000.0,
    )
    top0, top15 = _roth_ltcg_thresholds_base(c, 'MFJ')
    assert plan.binding_limit == 'LTCG rate tier'
    assert plan.amount == top15 - plan.pre_agi


def test_ltcg_and_niit_thresholds_are_filing_status_aware():
    # Must look up the current year's filing status fresh (e.g. a surviving
    # spouse whose filing flips to Single mid-plan), not always resolve MFJ.
    mfj_top0, mfj_top15 = _roth_ltcg_thresholds_base({}, 'MFJ')
    single_top0, single_top15 = _roth_ltcg_thresholds_base({}, 'Single')
    assert single_top0 < mfj_top0
    assert single_top15 < mfj_top15
    assert _roth_niit_threshold_base({}, 'Single') < _roth_niit_threshold_base({}, 'MFJ')
