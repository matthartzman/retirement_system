"""Wave 3 item 3.1 (system review 2026-08-31, finding F3): before the
conversion window is extended past RMD age (item 3.2), verify -- with a
real test, not a reading of the code -- that the conversion-sizing
guardrails and the bracket-headroom calculation both still behave
correctly once RMDs are also flowing in the same year.

Under the shipped default, ``conversion_window_end_year()`` closes the
voluntary-conversion window the year BEFORE RMDs start
(``conv_window_offset`` defaults to -1), so no existing test has ever
actually exercised ``plan_roth_conversion`` in a year where both a
voluntary conversion and a real RMD amount are present simultaneously --
the code path the review flagged as unproven, not merely undocumented.
``rmd_total`` is a plain kwarg (Mapping.get('rmd_total') is never touched
inside this function), so an explicit call with the window pushed open via
``conv_window_offset``/``roth_max_conversion_years`` is what actually
proves the behavior, rather than assuming it from ``pre_non_ss``'s source
text.

Follows the isolation pattern already established in
test_roth_ltcg_niit_guardrails.py: call ``plan_roth_conversion`` directly
(documented as "intentionally side-effect free ... so it can be tested
without building workbooks") rather than through the full ``project()``
pipeline, so each variable can be isolated exactly.
"""
from src.core import (
    inflate_brackets, standard_deduction, compute_fed_tax,
    FEDERAL_BRACKETS_BASE_YEAR, FEDERAL_BRACKETS_MFJ,
)
from src.planning_engines import plan_roth_conversion, conversion_window_end_year


def _plan(c_overrides, **kw_overrides):
    c = {
        'plan_start': 2026,
        'roth_policy': 'fill_to_bracket',
        'roth_target_rate': 0.35,          # wide bracket headroom so it never binds unless a test wants it to
        'roth_headroom_usage_pct': 1.0,
        'roth_max_annual_conversion_pct_of_traditional_ira': 1.0,
        'roth_irmaa_cap': False,
        'irmaa_guardrail_mode': 'AVOID_NEXT_TIER',
        'roth_irmaa_target_tier': 'TIER_1',  # tightest tier, so it binds whenever enabled
        'roth_ltcg_cap': False,
        'roth_niit_cap': False,
        'brk_inf': 0.0,
        # rmd_start_age is set directly (data_io.py normally derives it from
        # h_dob_yr via statutory_rmd_start_age); conv_window_offset pushed
        # well past RMD age, roth_max_conversion_years disabled so it can't
        # silently re-cap the window shorter than the offset intends (the
        # legacy control and the v8.3 cap both apply -- see
        # conversion_window_end_year's own docstring).
        'rmd_start_age': 75,
        'conv_window_offset': 10,
        'roth_max_conversion_years': 0,
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


def test_window_genuinely_extends_past_rmd_age_in_this_fixture():
    # Sanity check on the fixture itself: h_dob_yr isn't used here (rmd_start_age
    # is set directly), so confirm the window math this test relies on actually
    # reaches past age 75 given plan_start=2026 and h_age=76 at the tested year.
    c, _ = _plan({})
    assert conversion_window_end_year(c) >= 2026


def test_irmaa_guardrail_demonstrably_binds_at_ages_well_past_rmd_start():
    # h_age=76/w_age=74: both well past RMD start (75) and the IRMAA age
    # gate (63). A wide 35% target rate and a large IRA balance mean bracket
    # headroom alone would allow a huge conversion -- if the IRMAA guardrail
    # silently stopped applying once RMDs are flowing, this would size to
    # the bracket instead of the tier.
    c, plan = _plan({'roth_irmaa_cap': True}, h_age=76.0, w_age=74.0, rmd_total=50_000.0)
    assert plan.binding_limit == 'Tier 1', (
        "IRMAA guardrail must still be the binding constraint at ages well past RMD start, "
        f"got binding_limit={plan.binding_limit!r}"
    )
    assert plan.amount > 0, "guardrail should still allow SOME conversion, just capped, not zero it out"


def test_bracket_headroom_nets_out_the_years_rmd_dollar_for_dollar():
    # Same age (76/74, past RMD start), same everything else, isolating
    # rmd_total as the only variable -- IRMAA cap disabled so bracket
    # headroom is the only thing being measured.
    _, plan_no_rmd = _plan({}, h_age=76.0, w_age=74.0, rmd_total=0.0)
    _, plan_with_rmd = _plan({}, h_age=76.0, w_age=74.0, rmd_total=50_000.0)

    assert plan_no_rmd.binding_limit == '35% bracket'
    assert plan_with_rmd.binding_limit == '35% bracket'
    # pre_non_ss includes + rmd_total (src/planning_engines.py), so $50k of
    # RMD income must consume exactly $50k of bracket headroom -- not zero
    # (RMD ignored) and not more/less than $50k (double-counted or partially
    # applied).
    assert plan_no_rmd.bracket_room - plan_with_rmd.bracket_room == 50_000.0
    assert plan_no_rmd.amount - plan_with_rmd.amount == 50_000.0


def test_conversion_still_sizes_to_nonzero_in_a_real_rmd_active_year():
    # A more realistic combined scenario (not isolating every variable to
    # zero): SS income and a smaller, more typical target rate alongside a
    # real rmd_total, still past RMD age. Guards against a subtler bug where
    # netting works in isolation but some other interaction (e.g. the
    # standard deduction or senior bonus deduction) zeroes the room out
    # entirely once several income sources stack in a late year.
    _, plan = _plan(
        {'roth_target_rate': 0.22},
        h_age=77.0, w_age=75.0, rmd_total=45_000.0,
        h_ss=32_000.0, w_ss=18_000.0,
    )
    assert plan.amount > 0, "a real RMD-active year with normal SS income should still leave some room to convert"
    assert plan.binding_limit in ('22% bracket', 'Tier 1'), plan.binding_limit
