"""Finding FIN-002 (system review 2026-09-25, Wave 1 item WI-105):
fill_to_bracket sized conversions by comparing AGI (pre_agi, income before
any deduction) directly against a taxable-income bracket threshold
(top_target), leaving a standard-deduction's worth of headroom unused --
bracket_room = max(0, top_target - pre_agi) never added the standard
deduction (or senior bonus) back in.

This pins the fix in src/planning_engines.py (plan_roth_conversion):
bracket_room = max(0, top_target + deduction - pre_agi), where deduction is
the (alive-gated, FIN-003-fixed) standard deduction plus any senior bonus.

Follows the direct-call isolation pattern established in
tests/test_roth_conversion_guardrails_past_rmd_age_unit.py.
"""
from src.core import (
    inflate_brackets, standard_deduction, senior_bonus_deduction, compute_fed_tax,
    FEDERAL_BRACKETS_BASE_YEAR, FEDERAL_BRACKETS_MFJ,
)
from src.planning_engines import plan_roth_conversion


def _plan(c_overrides, **kw_overrides):
    c = {
        'plan_start': 2026,
        'roth_policy': 'fill_to_bracket',
        'roth_target_rate': 0.22,
        'roth_headroom_usage_pct': 0.95,
        'roth_max_annual_conversion_pct_of_traditional_ira': 1.0,
        'roth_irmaa_cap': False,
        'roth_ltcg_cap': False,
        'roth_niit_cap': False,
        'brk_inf': 0.0,
        'account_registry': [{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': 'IRA'}],
    }
    c.update(c_overrides)
    bal = {'H_IRA': 5_000_000.0}
    kwargs = dict(
        c=c, bal=bal, year=2026, filing='MFJ',
        earned_base=0.0, half_se_ded=0.0, sehi_ded=0.0,
        h_ss=0.0, w_ss=0.0, rmd_total=0.0, pension=0.0,
        wife_single_ann=0.0, wife_joint_ann=0.0, h_single_ann=0.0, h_joint_ann=0.0,
        note_int_yr=0.0, note_princ_yr=0.0, total_spend_need=0.0, spend=0.0,
        portfolio_ordinary=0.0, portfolio_qualified=0.0, portfolio_tax_exempt=0.0,
        aca_bridge_people=0, h_age=70.0, w_age=70.0, h_alive=True, w_alive=True,
        brackets_by_status=FEDERAL_BRACKETS_BASE_YEAR, brackets_mfj=FEDERAL_BRACKETS_MFJ,
        inflate_brackets_fn=inflate_brackets, standard_deduction_fn=standard_deduction,
        compute_fed_tax_fn=compute_fed_tax, state_tax_estimate_fn=lambda agi, yr: 0.0,
    )
    kwargs.update(kw_overrides)
    return c, plan_roth_conversion(**kwargs)


def _bracket_top(c, rate):
    brk = inflate_brackets(FEDERAL_BRACKETS_MFJ, 0.0, 0)
    return next(hi for _lo, hi, r in brk if r == rate)


def test_bracket_room_adds_back_the_standard_deduction_and_senior_bonus():
    # MFJ, both 70 (two over-65 add-ons + two 2026 senior bonuses), no other
    # income -- pre_agi is 0, so bracket_room should equal the WHOLE 22%
    # bracket top PLUS the full standard deduction/senior bonus, not just the
    # bracket top.
    c, plan = _plan({})
    top_target = _bracket_top(c, 0.22)
    std = standard_deduction(2026, 'MFJ', 0.0, n_over_65=2)
    std += senior_bonus_deduction(2026, 'MFJ', 0.0, n_over_65=2)
    expected_bracket_room = top_target + std
    expected_amount = expected_bracket_room * 0.95

    assert plan.binding_limit == '22% bracket'
    assert abs(plan.bracket_room - expected_bracket_room) < 1.0
    assert abs(plan.amount - expected_amount) < 1.0
    # The un-fixed formula (bracket_room = top_target alone) would have sized
    # to roughly top_target * 0.95 -- confirm the fix actually converts
    # materially more, not just a rounding-sized difference.
    assert plan.amount > top_target * 0.95 + std * 0.5


def test_taxable_income_after_conversion_lands_close_to_the_bracket_top():
    # Direct restatement of the report's own verification method: taxable
    # income after the conversion should be close to 0.95x the 22% bracket
    # top -- not exact, since the 5% roth_headroom_usage_pct haircut applies
    # to the whole widened bracket_room (top_target + deduction), same as the
    # pre-fix code applied it to bracket_room unconditionally; the haircut
    # taken out of the deduction's own share (0.05 * std) is the source of
    # the small gap, not a bug.
    c, plan = _plan({})
    std = standard_deduction(2026, 'MFJ', 0.0, n_over_65=2)
    std += senior_bonus_deduction(2026, 'MFJ', 0.0, n_over_65=2)
    top_target = _bracket_top(c, 0.22)
    taxable_income_after = plan.amount - std  # pre_agi is 0 in this fixture
    expected = 0.95 * top_target - 0.05 * std
    assert abs(taxable_income_after - expected) < 2.0
    # And it must land far closer to the bracket top than the pre-fix
    # formula did (which left roughly a full standard deduction unused).
    assert abs(taxable_income_after - 0.95 * top_target) < 0.10 * std
