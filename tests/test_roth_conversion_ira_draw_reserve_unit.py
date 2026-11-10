"""fill_to_bracket conversions leave bracket room for the year's pre-tax draw.

The withdrawal cascade runs after the conversion is sized. When the year's
non-Roth surplus cannot pay the spending gap plus the conversion's own tax,
the cascade draws the rest from pre-tax accounts, and that draw is ordinary
income on top of the conversion. Sizing the conversion to the whole bracket
room pushed a real plan into the 32% and 35% brackets. The conversion is now
capped at room*(1 - t) + surplus, so conversion plus draw fits the bracket.
"""
import pytest

from src.core import FEDERAL_BRACKETS_BASE_YEAR, FEDERAL_BRACKETS_MFJ, compute_fed_tax, inflate_brackets, standard_deduction
from src.engine_sections.roth_conversion import _conversion_funding_cap
from src.planning_engines import plan_roth_conversion
from src.reporting.sheets_strategy import _over_target_bracket


def _plan(c_overrides=None, **kw):
    c = {
        'plan_start': 2026,
        'roth_policy': 'fill_to_bracket',
        'roth_target_rate': 0.24,
        'roth_headroom_usage_pct': 1.0,
        'roth_max_annual_conversion_pct_of_traditional_ira': 1.0,
        'roth_irmaa_cap': False,
        'roth_ltcg_cap': False,
        'roth_niit_cap': False,
        'brk_inf': 0.0,
        'account_registry': [{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': 'IRA'}],
    }
    c.update(c_overrides or {})
    kwargs = dict(
        c=c, bal={'H_IRA': 5_000_000.0}, year=2026, filing='MFJ',
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
    kwargs.update(kw)
    return plan_roth_conversion(**kwargs)


def _draw(conversion, surplus, t):
    """Pre-tax draw the cascade takes: spending shortfall plus the conversion's tax, grossed up."""
    return max(0.0, (t * conversion - surplus) / (1.0 - t))


@pytest.mark.parametrize('surplus', [-130_000.0, -10_000.0, 0.0, 20_000.0, 60_000.0])
def test_conversion_plus_resulting_draw_fills_the_room_exactly(surplus):
    room, t = 400_000.0, 0.24
    cap, reserve = _conversion_funding_cap(room, surplus, t)
    assert cap + reserve == pytest.approx(room)
    assert cap + _draw(cap, surplus, t) == pytest.approx(room, abs=0.01)


def test_surplus_that_pays_the_conversion_tax_leaves_the_cap_alone():
    assert _conversion_funding_cap(400_000.0, 96_000.0, 0.24) == (400_000.0, 0.0)
    assert _conversion_funding_cap(400_000.0, 250_000.0, 0.24) == (400_000.0, 0.0)


def test_spending_shortfall_larger_than_the_room_means_no_conversion():
    cap, reserve = _conversion_funding_cap(300_000.0, -400_000.0, 0.24)
    assert cap == 0.0
    assert reserve == 300_000.0


def test_shortfall_year_converts_less_and_records_the_reserve():
    # $150k of spending, no income and no taxable assets: every dollar of
    # spending and of conversion tax comes from the IRA.
    plan = _plan(total_spend_need=150_000.0, spend=150_000.0)
    room = plan.bracket_room
    expected = room * (1 - 0.24) - 150_000.0
    assert plan.binding_limit == '24% bracket'
    assert plan.amount == pytest.approx(expected, abs=1.0)
    assert plan.ira_draw_reserve == pytest.approx(room - expected, abs=1.0)
    assert plan.as_row_fields()['conv_ira_draw_reserve'] == plan.ira_draw_reserve
    assert plan.amount + _draw(plan.amount, -150_000.0, 0.24) == pytest.approx(room, abs=1.0)


def test_year_with_ample_surplus_still_fills_the_bracket():
    # Note principal is cash that is not income: it pays spending and tax.
    plan = _plan(total_spend_need=150_000.0, spend=150_000.0, note_princ_yr=1_000_000.0)
    assert plan.amount == pytest.approx(plan.bracket_room, abs=1.0)
    assert plan.ira_draw_reserve == 0.0


def test_state_marginal_rate_widens_the_reserve():
    no_state = _plan(total_spend_need=100_000.0, spend=100_000.0)
    with_state = _plan(total_spend_need=100_000.0, spend=100_000.0,
                       state_tax_estimate_fn=lambda agi, yr: 0.05 * max(0.0, agi))
    assert with_state.amount < no_state.amount
    assert with_state.amount == pytest.approx(with_state.bracket_room * (1 - 0.29) - 100_000.0, abs=1.0)


def test_known_irmaa_surcharge_counts_against_the_surplus():
    # The IRMAA surcharge is fixed by the two-year lookback before the
    # conversion is sized; it is paid from the same cash as the spending.
    base = _plan(total_spend_need=100_000.0, spend=100_000.0)
    with_irmaa = _plan(total_spend_need=100_000.0, spend=100_000.0, other_cash_need=15_000.0)
    assert with_irmaa.non_roth_surplus == pytest.approx(base.non_roth_surplus - 15_000.0)
    assert with_irmaa.amount == pytest.approx(base.amount - 15_000.0, abs=1.0)


def test_bracket_cap_switched_off_ignores_the_reserve():
    plan = _plan({'roth_bracket_cap': False}, total_spend_need=150_000.0, spend=150_000.0)
    assert plan.ira_draw_reserve == 0.0
    assert plan.binding_limit != '24% bracket'


def test_over_target_bracket_flag_reads_ordinary_taxable_income():
    top = 419_853.0
    assert _over_target_bracket({'taxable_inc': 450_523.0, 'portfolio_qualified_dividends': 5_000.0}, top)
    assert not _over_target_bracket({'taxable_inc': 403_240.0}, top)
    # Qualified dividends stack above ordinary income, so they do not count.
    assert not _over_target_bracket({'taxable_inc': 440_000.0, 'portfolio_qualified_dividends': 30_000.0}, top)
    assert not _over_target_bracket({'taxable_inc': 450_000.0}, 0)
